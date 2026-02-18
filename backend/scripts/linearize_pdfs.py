#!/usr/bin/env python3
import argparse
import os
import subprocess
from pathlib import Path

import fitz


def is_linearized(pdf_path: Path) -> bool:
    try:
        with pdf_path.open("rb") as f:
            head = f.read(4096)
        return b"/Linearized" in head
    except OSError:
        return False


def linearize_pdf_with_qpdf(pdf_path: Path, dry_run: bool = False) -> str:
    if dry_run:
        return "would-convert"

    tmp_path = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    try:
        subprocess.run(
            ["qpdf", "--linearize", str(pdf_path), str(tmp_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        os.replace(tmp_path, pdf_path)
        return "converted(qpdf)"
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def linearize_pdf_with_fitz(pdf_path: Path, dry_run: bool = False) -> str:
    if dry_run:
        return "would-convert"

    tmp_path = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    with fitz.open(pdf_path) as doc:
        doc.save(
            tmp_path,
            linear=True,
            garbage=3,
            deflate=True,
            clean=True,
        )
    os.replace(tmp_path, pdf_path)
    return "converted(fitz)"


def linearize_pdf(pdf_path: Path, force: bool = False, dry_run: bool = False) -> str:
    if not force and is_linearized(pdf_path):
        return "skip(already-linearized)"

    try:
        return linearize_pdf_with_qpdf(pdf_path, dry_run=dry_run)
    except FileNotFoundError as e:
        raise RuntimeError("qpdf is not installed") from e
    except subprocess.CalledProcessError as qpdf_err:
        qpdf_msg = (qpdf_err.stderr or qpdf_err.stdout or "").strip()
        # Fallback for environments where qpdf cannot process the file.
        try:
            status = linearize_pdf_with_fitz(pdf_path, dry_run=dry_run)
            return f"{status}(fallback)"
        except Exception as fitz_err:  # noqa: BLE001
            raise RuntimeError(
                f"qpdf failed: {qpdf_msg}; fitz fallback failed: {fitz_err}"
            ) from fitz_err


def main():
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    default_candidates = [
        Path("/app/app/resources/pdfs"),  # docker container
        repo_root / "backend" / "app" / "resources" / "pdfs",  # local from repo root
        repo_root / "app" / "resources" / "pdfs",  # local from backend/
    ]
    default_pdf_dir = next((p for p in default_candidates if p.exists()), default_candidates[0])

    parser = argparse.ArgumentParser(
        description="Linearize PDF files (Fast Web View) in-place."
    )
    parser.add_argument(
        "--pdf-dir",
        default=str(default_pdf_dir),
        help="Directory containing PDF files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if already linearized.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be converted without writing files.",
    )
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        raise SystemExit(f"PDF directory not found: {pdf_dir}")

    files = sorted(p for p in pdf_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not files:
        print("No PDF files found.")
        return

    converted = 0
    skipped = 0
    failed = 0

    for pdf in files:
        try:
            status = linearize_pdf(pdf, force=args.force, dry_run=args.dry_run)
            if status in {"converted", "would-convert"}:
                converted += 1
            else:
                skipped += 1
            print(f"{status}: {pdf.name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"failed: {pdf.name} ({e})")

    print(
        f"done: converted={converted}, skipped={skipped}, failed={failed}, dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
