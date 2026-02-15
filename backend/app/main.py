import os
import re
import sqlite3
from contextlib import closing

import fitz
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm

from .auth import authenticate_user, create_access_token, get_current_user

app = FastAPI()

# CORS（React用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(__file__)
PDF_DIR = os.path.join(BASE_DIR, "resources/pdfs")
THUMB_DIR = os.path.join(BASE_DIR, "resources/thumbnails")
DB_PATH = os.path.join(BASE_DIR, "resources/search.db")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

TOKENS = set()


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401)
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer"}


def generate_thumbnail(pdf_path, thumb_path):
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
    pix.save(thumb_path)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_search_db():
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_index_meta (
                pdf_id TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                page_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS pdf_index USING fts5 (
                pdf_id UNINDEXED,
                title,
                page UNINDEXED,
                content,
                tokenize='unicode61'
            )
            """
        )
        conn.commit()


def resolve_safe_path(base_dir: str, file_name: str, ext: str):
    if os.path.basename(file_name) != file_name:
        raise HTTPException(status_code=404)
    if not file_name.lower().endswith(ext):
        raise HTTPException(status_code=404)

    base = os.path.realpath(base_dir)
    path = os.path.realpath(os.path.join(base, file_name))
    if not path.startswith(f"{base}{os.sep}"):
        raise HTTPException(status_code=404)
    return path


def clean_text(text: str):
    return re.sub(r"\s+", " ", text).strip()


def index_pdf(pdf_id: str):
    pdf_path = os.path.join(PDF_DIR, pdf_id)
    mtime = os.path.getmtime(pdf_path)

    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT mtime FROM pdf_index_meta WHERE pdf_id = ?", (pdf_id,)
        ).fetchone()
        if row and row["mtime"] == mtime:
            return

        with fitz.open(pdf_path) as doc:
            page_count = doc.page_count
            rows = []
            for i, page in enumerate(doc):
                text = clean_text(page.get_text("text"))
                if text:
                    rows.append((pdf_id, pdf_id, i + 1, text))

        conn.execute("DELETE FROM pdf_index WHERE pdf_id = ?", (pdf_id,))
        if rows:
            conn.executemany(
                "INSERT INTO pdf_index (pdf_id, title, page, content) VALUES (?, ?, ?, ?)",
                rows,
            )

        conn.execute(
            """
            INSERT INTO pdf_index_meta (pdf_id, mtime, page_count, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pdf_id) DO UPDATE SET
                mtime = excluded.mtime,
                page_count = excluded.page_count,
                updated_at = CURRENT_TIMESTAMP
            """,
            (pdf_id, mtime, page_count),
        )
        conn.commit()


def sync_search_index():
    pdf_files = {
        file_name for file_name in os.listdir(PDF_DIR) if file_name.lower().endswith(".pdf")
    }

    with closing(get_db_connection()) as conn:
        indexed = {
            row["pdf_id"] for row in conn.execute("SELECT pdf_id FROM pdf_index_meta")
        }
        stale = indexed - pdf_files
        for pdf_id in stale:
            conn.execute("DELETE FROM pdf_index WHERE pdf_id = ?", (pdf_id,))
            conn.execute("DELETE FROM pdf_index_meta WHERE pdf_id = ?", (pdf_id,))
        conn.commit()

    for pdf_id in pdf_files:
        index_pdf(pdf_id)


def build_fts_query(q: str):
    normalized = q.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="query is required")

    tokens = re.findall(r"[0-9A-Za-z_一-龯ぁ-ゔァ-ヴー々〆〤]+", normalized)
    if not tokens:
        escaped = normalized.replace('"', '""')
        return f'content:"{escaped}"'

    # Prefix search on each token for practical partial matching.
    parts = [f"content:{token}*" if len(token) >= 2 else f"content:{token}" for token in tokens]
    return " AND ".join(parts)


@app.on_event("startup")
def startup():
    init_search_db()
    sync_search_index()


@app.get("/pdfs")
def list_pdfs(user=Depends(get_current_user)):
    sync_search_index()
    pdfs = []

    for file in os.listdir(PDF_DIR):
        if not file.lower().endswith(".pdf"):
            continue

        pdf_id = file
        thumb_name = file.replace(".pdf", ".png")
        thumb_path = os.path.join(THUMB_DIR, thumb_name)

        if not os.path.exists(thumb_path):
            generate_thumbnail(os.path.join(PDF_DIR, file), thumb_path)

        pdfs.append(
            {"id": pdf_id, "title": file, "thumbnail_url": f"/thumbnail/{thumb_name}"}
        )

    return pdfs


@app.get("/pdf/{pdf_id}")
def get_pdf(pdf_id: str, user=Depends(get_current_user)):
    path = resolve_safe_path(PDF_DIR, pdf_id, ".pdf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404)

    return FileResponse(path, media_type="application/pdf")


@app.get("/thumbnail/{thumb_name}")
def get_thumbnail(thumb_name: str, user=Depends(get_current_user)):
    path = resolve_safe_path(THUMB_DIR, thumb_name, ".png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404)

    return FileResponse(path, media_type="image/png")


@app.get("/search")
def search_pdfs(
    q: str,
    page: int = 1,
    per_page: int = 20,
    user=Depends(get_current_user),
):
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if per_page < 1:
        raise HTTPException(status_code=400, detail="per_page must be >= 1")
    if per_page > 100:
        per_page = 100

    sync_search_index()
    match_query = build_fts_query(q)
    offset = (page - 1) * per_page

    with closing(get_db_connection()) as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM (
                SELECT pdf_id
                FROM pdf_index
                WHERE pdf_index MATCH ?
                GROUP BY pdf_id
            ) g
            """,
            (match_query,),
        ).fetchone()["total"]

        rows = conn.execute(
            """
            SELECT
                pdf_id,
                title,
                COUNT(*) AS hit_count
            FROM pdf_index
            WHERE pdf_index MATCH ?
            GROUP BY pdf_id, title
            ORDER BY hit_count DESC, title ASC
            LIMIT ?
            OFFSET ?
            """,
            (match_query, per_page, offset),
        ).fetchall()

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "query": q,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "count": len(rows),
        "results": [
            {
                "id": row["pdf_id"],
                "title": row["title"],
                "hit_count": row["hit_count"],
            }
            for row in rows
        ],
    }


@app.get("/search/pdf")
def search_pdf_details(
    q: str,
    pdf_id: str,
    page: int = 1,
    per_page: int = 20,
    user=Depends(get_current_user),
):
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if per_page < 1:
        raise HTTPException(status_code=400, detail="per_page must be >= 1")
    if per_page > 100:
        per_page = 100

    sync_search_index()
    match_query = build_fts_query(q)
    offset = (page - 1) * per_page

    with closing(get_db_connection()) as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM pdf_index
            WHERE pdf_index MATCH ? AND pdf_id = ?
            """,
            (match_query, pdf_id),
        ).fetchone()["total"]

        rows = conn.execute(
            """
            SELECT
                pdf_id,
                title,
                page,
                snippet(pdf_index, 3, '[', ']', ' ... ', 10) AS snippet,
                bm25(pdf_index) AS score
            FROM pdf_index
            WHERE pdf_index MATCH ? AND pdf_id = ?
            ORDER BY score
            LIMIT ?
            OFFSET ?
            """,
            (match_query, pdf_id, per_page, offset),
        ).fetchall()

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    title = rows[0]["title"] if rows else pdf_id
    return {
        "query": q,
        "id": pdf_id,
        "title": title,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "count": len(rows),
        "results": [
            {
                "id": row["pdf_id"],
                "title": row["title"],
                "page": row["page"],
                "snippet": row["snippet"],
            }
            for row in rows
        ],
    }
