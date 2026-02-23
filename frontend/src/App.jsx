import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API = "/api";
// const API = "http://localhost:8000";
const GROUPS_PER_PAGE = 12;
const DETAILS_PER_PAGE = 20;

function getRouteState() {
  const path = window.location.pathname;
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q") || "";
  const p = Number(params.get("p") || "1");
  const dp = Number(params.get("dp") || "1");
  const pdf = params.get("pdf") || "";
  const groupPage = Number.isFinite(p) && p > 0 ? Math.floor(p) : 1;
  const detailPage = Number.isFinite(dp) && dp > 0 ? Math.floor(dp) : 1;
  if (path === "/search") {
    return { view: "search", q, groupPage, selectedPdf: pdf, detailPage };
  }
  return { view: "library", q: "", groupPage: 1, selectedPdf: "", detailPage: 1 };
}

function tokenizeQuery(query) {
  if (!query) return [];
  const parts = [];
  const re = /"([^"]+)"|([0-9A-Za-z_一-龯ぁ-ゔァ-ヴー々〆〤]+)/g;
  for (const m of query.matchAll(re)) {
    const phrase = m[1]?.trim();
    const token = m[2]?.trim();
    if (phrase) {
      parts.push(phrase);
      continue;
    }
    if (token) {
      parts.push(token);
    }
  }
  return parts;
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const SNIPPET_HIT_START = "__CODX_HIT_START__";
const SNIPPET_HIT_END = "__CODX_HIT_END__";

function parseMarkedSnippet(snippet) {
  const text = snippet || "";
  if (!text.includes(SNIPPET_HIT_START) || !text.includes(SNIPPET_HIT_END)) return null;

  const parts = [];
  let i = 0;
  let hasHit = false;

  while (i < text.length) {
    const start = text.indexOf(SNIPPET_HIT_START, i);
    if (start < 0) {
      if (i < text.length) parts.push({ text: text.slice(i), hit: false });
      break;
    }

    if (start > i) {
      parts.push({ text: text.slice(i, start), hit: false });
    }

    const hitTextStart = start + SNIPPET_HIT_START.length;
    const end = text.indexOf(SNIPPET_HIT_END, hitTextStart);
    if (end < 0) {
      return null;
    }

    parts.push({ text: text.slice(hitTextStart, end), hit: true });
    hasHit = true;
    i = end + SNIPPET_HIT_END.length;
  }

  return hasHit ? parts : null;
}

function toHighlightedParts(snippet, query) {
  const markedParts = parseMarkedSnippet(snippet);
  if (markedParts) {
    return markedParts;
  }

  const cleanSnippet = (snippet || "")
    .replaceAll(SNIPPET_HIT_START, "")
    .replaceAll(SNIPPET_HIT_END, "")
    .replaceAll("[", "")
    .replaceAll("]", "");
  const tokens = tokenizeQuery(query);
  if (!tokens.length || !cleanSnippet) {
    return [{ text: cleanSnippet, hit: false }];
  }

  const uniqueTokens = [...new Set(tokens)];
  uniqueTokens.sort((a, b) => b.length - a.length);
  const re = new RegExp(`(${uniqueTokens.map(escapeRegExp).join("|")})`, "giu");

  const parts = [];
  let lastIndex = 0;
  for (const m of cleanSnippet.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > lastIndex) {
      parts.push({ text: cleanSnippet.slice(lastIndex, idx), hit: false });
    }
    parts.push({ text: m[0], hit: true });
    lastIndex = idx + m[0].length;
  }
  if (lastIndex < cleanSnippet.length) {
    parts.push({ text: cleanSnippet.slice(lastIndex), hit: false });
  }
  return parts;
}

export default function App() {
  const initialRoute = getRouteState();

  const [view, setView] = useState(initialRoute.view);
  const [routeQuery, setRouteQuery] = useState(initialRoute.q);
  const [groupPage, setGroupPage] = useState(initialRoute.groupPage);
  const [selectedPdf, setSelectedPdf] = useState(initialRoute.selectedPdf);
  const [detailPage, setDetailPage] = useState(initialRoute.detailPage);

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoadingPdfs, setIsLoadingPdfs] = useState(false);

  const [pdfs, setPdfs] = useState([]);
  const [current, setCurrent] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pdfUrl, setPdfUrl] = useState(null);

  const [searchQuery, setSearchQuery] = useState(initialRoute.q);
  const [searchError, setSearchError] = useState("");
  const [isSearching, setIsSearching] = useState(false);

  const [groupResults, setGroupResults] = useState([]);
  const [groupTotal, setGroupTotal] = useState(0);
  const [groupTotalPages, setGroupTotalPages] = useState(0);

  const [detailResults, setDetailResults] = useState([]);
  const [detailTitle, setDetailTitle] = useState("");
  const [detailTotal, setDetailTotal] = useState(0);
  const [detailTotalPages, setDetailTotalPages] = useState(0);

  const buildAuthUrl = path => `${API}${path}`;

  const thumbnailUrls = useMemo(() => {
    const map = {};
    if (!isAuthenticated) return map;
    for (const p of pdfs) {
      map[p.id] = buildAuthUrl(p.thumbnail_url);
    }
    return map;
  }, [pdfs, isAuthenticated]);

  const navigate = (
    nextView,
    { q = "", p = 1, pdf = "", dp = 1 } = {}
  ) => {
    if (nextView === "search") {
      const params = new URLSearchParams();
      if (q) {
        params.set("q", q);
      }
      if (p > 1) {
        params.set("p", String(p));
      }
      if (pdf) {
        params.set("pdf", pdf);
      }
      if (dp > 1) {
        params.set("dp", String(dp));
      }
      const suffix = params.toString() ? `?${params.toString()}` : "";
      window.history.pushState({}, "", `/search${suffix}`);
      setView("search");
      setRouteQuery(q);
      setGroupPage(p);
      setSelectedPdf(pdf);
      setDetailPage(dp);
      return;
    }

    window.history.pushState({}, "", "/");
    setView("library");
    setRouteQuery("");
    setGroupPage(1);
    setSelectedPdf("");
    setDetailPage(1);
  };

  useEffect(() => {
    const onPopState = () => {
      const route = getRouteState();
      setView(route.view);
      setRouteQuery(route.q);
      setSearchQuery(route.q);
      setGroupPage(route.groupPage);
      setSelectedPdf(route.selectedPdf);
      setDetailPage(route.detailPage);
    };
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, []);

  const loadPdfs = () => {
    setIsLoadingPdfs(true);
    return fetch(`${API}/pdfs`, {
      credentials: "include"
    })
      .then(res => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then(data => {
        setPdfs(data);
        setIsAuthenticated(true);
      })
      .catch(() => {
        setIsAuthenticated(false);
        setPdfs([]);
      })
      .finally(() => {
        setIsLoadingPdfs(false);
      });
  };

  useEffect(() => {
    loadPdfs();
  }, []);

  useEffect(() => {
    if (!current || !isAuthenticated) return;
    setPdfUrl(`${API}/pdf/${current}`);
    return () => setPdfUrl(null);
  }, [current, isAuthenticated]);

  const login = async () => {
    if (isLoadingPdfs) return;

    const form = new URLSearchParams();
    form.append("username", username);
    form.append("password", password);

    const res = await fetch(`${API}/login`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: form
    });

    if (!res.ok) {
      alert("ログイン失敗");
      return;
    }

    setPassword("");
    await loadPdfs();
  };

  const logout = () => {
    fetch(`${API}/logout`, { method: "POST", credentials: "include" }).catch(() => {});
    setIsAuthenticated(false);
    setPdfs([]);
    setCurrent(null);
    setCurrentPage(1);
    setSearchQuery("");
    setRouteQuery("");
    setGroupPage(1);
    setSelectedPdf("");
    setDetailPage(1);
    setGroupResults([]);
    setGroupTotal(0);
    setGroupTotalPages(0);
    setDetailResults([]);
    setDetailTitle("");
    setDetailTotal(0);
    setDetailTotalPages(0);
    setSearchError("");
    navigate("library");
  };

  const openPdf = (id, page = 1) => {
    setCurrent(id);
    setCurrentPage(page);
  };

  const submitSearch = async e => {
    e.preventDefault();
    const q = searchQuery.trim();
    navigate("search", { q, p: 1, pdf: "", dp: 1 });
  };

  useEffect(() => {
    if (!isAuthenticated || view !== "search") return;
    if (!routeQuery.trim()) {
      setGroupResults([]);
      setGroupTotal(0);
      setGroupTotalPages(0);
      setDetailResults([]);
      setDetailTitle("");
      setDetailTotal(0);
      setDetailTotalPages(0);
      setSearchError("");
      return;
    }

    let cancelled = false;
    (async () => {
      setIsSearching(true);
      setSearchError("");
      try {
        if (selectedPdf) {
          const params = new URLSearchParams({
            q: routeQuery,
            pdf_id: selectedPdf,
            page: String(detailPage),
            per_page: String(DETAILS_PER_PAGE)
          });
          const res = await fetch(`${API}/search/pdf?${params.toString()}`, {
            credentials: "include"
          });
          if (!res.ok) throw new Error("search failed");
          const data = await res.json();
          if (cancelled) return;
          setDetailResults(data.results || []);
          setDetailTitle(data.title || selectedPdf);
          setDetailTotal(data.total || 0);
          setDetailTotalPages(data.total_pages || 0);
        } else {
          const params = new URLSearchParams({
            q: routeQuery,
            page: String(groupPage),
            per_page: String(GROUPS_PER_PAGE)
          });
          const res = await fetch(`${API}/search?${params.toString()}`, {
            credentials: "include"
          });
          if (!res.ok) throw new Error("search failed");
          const data = await res.json();
          if (cancelled) return;
          setGroupResults(data.results || []);
          setGroupTotal(data.total || 0);
          setGroupTotalPages(data.total_pages || 0);
          setDetailResults([]);
          setDetailTitle("");
          setDetailTotal(0);
          setDetailTotalPages(0);
        }
      } catch {
        if (!cancelled) {
          setSearchError("検索に失敗しました");
        }
      } finally {
        if (!cancelled) {
          setIsSearching(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, view, routeQuery, groupPage, selectedPdf, detailPage]);

  if (!isAuthenticated) {
    return (
      <div className="login">
        <h2>Login</h2>
        <input
          placeholder="username"
          value={username}
          onChange={e => setUsername(e.target.value)}
        />
        <input
          type="password"
          placeholder="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
        />
        <button onClick={login} disabled={isLoadingPdfs}>
          {isLoadingPdfs ? "Loading..." : "Login"}
        </button>
        {isLoadingPdfs && (
          <div className="loading-inline">
            <span className="spinner" aria-hidden="true" />
            <span className="status">読み込み中...</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <header className="topbar">
        <div className="left">
          <h1>FaiLab Library</h1>
          <button
            className={`nav-btn ${view === "library" ? "active" : ""}`}
            onClick={() => navigate("library")}
          >
            Library
          </button>
          <button
            className={`nav-btn ${view === "search" ? "active" : ""}`}
            onClick={() =>
              navigate("search", { q: searchQuery.trim(), p: 1, pdf: "", dp: 1 })
            }
          >
            Search
          </button>
        </div>
        <div className="right">
          <button onClick={logout}>Logout</button>
        </div>
      </header>

      {view === "search" ? (
        <section className="search-page">
          <form className="search-form" onSubmit={submitSearch}>
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="横断検索キーワード"
            />
            <button type="submit" disabled={isSearching}>
              {isSearching ? "Searching..." : "Search"}
            </button>
          </form>

          {searchError && <div className="search-error">{searchError}</div>}

          {!searchError && !isSearching && routeQuery.trim() && !selectedPdf && (
            <div className="search-results">
              <div className="search-summary">{`${groupTotal} PDF ヒット`}</div>
              {groupResults.map(item => (
                <button
                  key={item.id}
                  className="group-item"
                  onClick={() =>
                    navigate("search", {
                      q: routeQuery,
                      p: groupPage,
                      pdf: item.id,
                      dp: 1
                    })
                  }
                >
                  <div className="group-item-left">
                    {thumbnailUrls[item.id] ? (
                      <img className="group-thumb" src={thumbnailUrls[item.id]} />
                    ) : (
                      <div className="group-thumb placeholder">...</div>
                    )}
                    <span className="group-item-title">{item.title}</span>
                  </div>
                  <span className="group-item-count">{`${item.hit_count} matches`}</span>
                </button>
              ))}
              {groupResults.length === 0 && (
                <div className="search-empty">一致する結果はありません</div>
              )}
            </div>
          )}

          {!searchError && !isSearching && routeQuery.trim() && selectedPdf && (
            <div className="search-results">
              <div className="detail-head">
                <button
                  className="back-btn"
                  onClick={() =>
                    navigate("search", {
                      q: routeQuery,
                      p: groupPage,
                      pdf: "",
                      dp: 1
                    })
                  }
                >
                  Back
                </button>
                {thumbnailUrls[selectedPdf] ? (
                  <img className="detail-thumb" src={thumbnailUrls[selectedPdf]} />
                ) : (
                  <div className="detail-thumb placeholder">...</div>
                )}
                <div className="search-summary">{`${detailTitle} / ${detailTotal} matches`}</div>
              </div>
              {detailResults.map((item, i) => (
                <button
                  key={`${item.id}-${item.page}-${i}`}
                  className="search-result-item"
                  onClick={() => openPdf(item.id, item.page)}
                >
                  <div className="search-result-head">
                    <span>{`p.${item.page}`}</span>
                  </div>
                  <div className="search-result-snippet">
                    {toHighlightedParts(item.snippet, routeQuery).map((part, idx) =>
                      part.hit ? (
                        <mark key={idx} className="snippet-hit">
                          <strong>{part.text}</strong>
                        </mark>
                      ) : (
                        <span key={idx}>{part.text}</span>
                      )
                    )}
                  </div>
                </button>
              ))}
              {detailResults.length === 0 && (
                <div className="search-empty">一致する結果はありません</div>
              )}
            </div>
          )}

          {!searchError && !isSearching && !selectedPdf && groupTotalPages > 1 && (
            <div className="pager">
              <button
                onClick={() =>
                  navigate("search", {
                    q: routeQuery,
                    p: groupPage - 1,
                    pdf: "",
                    dp: 1
                  })
                }
                disabled={groupPage <= 1}
              >
                Prev
              </button>
              <span>{`${groupPage} / ${groupTotalPages}`}</span>
              <button
                onClick={() =>
                  navigate("search", {
                    q: routeQuery,
                    p: groupPage + 1,
                    pdf: "",
                    dp: 1
                  })
                }
                disabled={groupPage >= groupTotalPages}
              >
                Next
              </button>
            </div>
          )}

          {!searchError && !isSearching && selectedPdf && detailTotalPages > 1 && (
            <div className="pager">
              <button
                onClick={() =>
                  navigate("search", {
                    q: routeQuery,
                    p: groupPage,
                    pdf: selectedPdf,
                    dp: detailPage - 1
                  })
                }
                disabled={detailPage <= 1}
              >
                Prev
              </button>
              <span>{`${detailPage} / ${detailTotalPages}`}</span>
              <button
                onClick={() =>
                  navigate("search", {
                    q: routeQuery,
                    p: groupPage,
                    pdf: selectedPdf,
                    dp: detailPage + 1
                  })
                }
                disabled={detailPage >= detailTotalPages}
              >
                Next
              </button>
            </div>
          )}
        </section>
      ) : (
        <>
          <section className="search-panel">
            <form className="search-form" onSubmit={submitSearch}>
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="横断検索キーワード"
              />
              <button type="submit">Search</button>
            </form>
          </section>
          <div className="grid">
            {pdfs.map(p => (
              <div key={p.id} className="thumb-card" onClick={() => openPdf(p.id)}>
                {thumbnailUrls[p.id] ? (
                  <img src={thumbnailUrls[p.id]} />
                ) : (
                  <div className="thumb-placeholder">Loading...</div>
                )}
                <div className="thumb-title">{p.title}</div>
              </div>
            ))}
          </div>
          {isLoadingPdfs && (
            <div className="loading-inline status-inline">
              <span className="spinner" aria-hidden="true" />
              <span className="status">読み込み中...</span>
            </div>
          )}
        </>
      )}

      {current && pdfUrl && (
        <div id="overlay" onClick={() => setCurrent(null)}>
          <div id="popup" onClick={e => e.stopPropagation()}>
            <div id="closeBtn" onClick={() => setCurrent(null)}>✕</div>
            {(() => {
              const hashParams = new URLSearchParams({
                page: String(currentPage || 1)
              });
              const src = `/pdfjs/web/viewer.html?file=${encodeURIComponent(pdfUrl)}#${hashParams.toString()}`;
              return <iframe src={src} />;
            })()}
          </div>
        </div>
      )}
    </>
  );
}
