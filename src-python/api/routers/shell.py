"""Shell helper endpoints — open files and folders via the OS."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/shell", tags=["shell"])


class PathRequest(BaseModel):
    path: str


class SplitFileRequest(BaseModel):
    path: str
    max_size_mb: float = 30.0
    split_id: str | None = None


# ── In-memory split progress ────────────────────────────────────────────
_split_progress: dict[str, dict[str, Any]] = {}


def _update_split(sid: str, **kw: Any) -> None:
    if sid:
        _split_progress.setdefault(sid, {})
        _split_progress[sid].update(kw)


@router.get("/split-progress/{split_id}")
async def get_split_progress(split_id: str) -> dict[str, Any]:
    """Poll split progress."""
    return _split_progress.get(split_id, {"phase": "idle"})


def _validate_path(p: str) -> Path:
    """Validate that the path exists and is absolute."""
    path = Path(p)
    if not path.is_absolute():
        raise HTTPException(400, "Path must be absolute")
    if not path.exists():
        raise HTTPException(404, f"Path does not exist: {p}")
    return path


@router.post("/open-file")
async def open_file(req: PathRequest) -> dict[str, Any]:
    """Open a file with the OS default application."""
    path = _validate_path(req.path)
    if not path.is_file():
        raise HTTPException(400, "Path is not a file")
    try:
        _os_open(str(path))
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to open file: {e}")
        raise HTTPException(500, f"Failed to open file: {e}")


@router.post("/reveal-file")
async def reveal_file(req: PathRequest) -> dict[str, Any]:
    """Open the folder containing the file and select it in the OS file manager."""
    path = _validate_path(req.path)
    try:
        _os_reveal(str(path))
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to reveal file: {e}")
        raise HTTPException(500, f"Failed to reveal file: {e}")


def _os_open(filepath: str) -> None:
    """Open a file with the default OS handler."""
    system = platform.system()
    if system == "Windows":
        os.startfile(filepath)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", filepath])
    else:
        subprocess.Popen(["xdg-open", filepath])


def _os_reveal(filepath: str) -> None:
    """Reveal a file in the file manager."""
    system = platform.system()
    if system == "Windows":
        subprocess.Popen(["explorer", "/select,", filepath])
    elif system == "Darwin":
        subprocess.Popen(["open", "-R", filepath])
    else:
        # On Linux, open the parent directory
        parent = str(Path(filepath).parent)
        subprocess.Popen(["xdg-open", parent])


# ── PDF split ────────────────────────────────────────────────────────────

def _do_split(path: Path, max_bytes: int, sid: str) -> dict[str, Any]:
    """Synchronous split logic — runs in a worker thread so async progress
    polling remains responsive."""
    import fitz  # PyMuPDF
    import tempfile
    import time as _time

    src_size = path.stat().st_size
    t0 = _time.monotonic()

    try:
        src_doc = fitz.open(str(path))
    except Exception as e:
        raise RuntimeError(f"Cannot open PDF: {e}")

    total_pages = len(src_doc)
    if total_pages == 0:
        src_doc.close()
        raise RuntimeError("PDF has no pages")

    _update_split(sid,
        phase="sampling",
        total_pages=total_pages,
        pages_sampled=0,
        total_parts=0,
        parts_done=0,
        message=f"Analysing {total_pages} pages…",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # For docs with ≤ 200 pages, measure every page.
        # For larger docs, sample ~50 pages and interpolate.
        if total_pages <= 200:
            sample_indices = list(range(total_pages))
        else:
            step = max(1, total_pages // 50)
            sample_indices = list(range(0, total_pages, step))
            if sample_indices[-1] != total_pages - 1:
                sample_indices.append(total_pages - 1)

        sampled_sizes: dict[int, int] = {}
        samples_total = len(sample_indices)
        for si, idx in enumerate(sample_indices):
            probe = fitz.open()
            probe.insert_pdf(src_doc, from_page=idx, to_page=idx)
            # Measure with deflate+garbage to match the actual save settings.
            # This gives an accurate estimate of what each page will
            # contribute to a multi-page output PDF.
            sampled_sizes[idx] = len(probe.tobytes(garbage=4, deflate=True))
            probe.close()
            if si % 10 == 0 or si == samples_total - 1:
                _update_split(sid,
                    pages_sampled=si + 1,
                    message=f"Sampling page sizes… {si + 1}/{samples_total}",
                )

        # Interpolate sizes for unsampled pages
        page_sizes: list[int] = []
        sorted_samples = sorted(sampled_sizes.keys())
        for p in range(total_pages):
            if p in sampled_sizes:
                page_sizes.append(sampled_sizes[p])
            else:
                lo = max(s for s in sorted_samples if s <= p)
                hi = min(s for s in sorted_samples if s >= p)
                if lo == hi:
                    page_sizes.append(sampled_sizes[lo])
                else:
                    frac = (p - lo) / (hi - lo)
                    est = int(sampled_sizes[lo] + frac * (sampled_sizes[hi] - sampled_sizes[lo]))
                    page_sizes.append(est)

        # Use compressed probe sizes directly as estimates — no ratio scaling.
        # Each probe measures a single-page PDF (includes per-page overhead),
        # so sums slightly over-estimate multi-page outputs, providing a
        # natural safety margin.  Budget = max_bytes directly.
        budget = max_bytes

        # Greedy grouping by cumulative estimated size
        parts: list[list[int]] = []
        current_part: list[int] = []
        current_est = 0

        for p in range(total_pages):
            if current_part and current_est + page_sizes[p] > budget:
                parts.append(current_part)
                current_part = []
                current_est = 0
            current_part.append(p)
            current_est += page_sizes[p]
        if current_part:
            parts.append(current_part)

        total_parts = len(parts)
        stem = path.stem
        parent_dir = path.parent

        _update_split(sid,
            phase="writing",
            total_parts=total_parts,
            parts_done=0,
            message=f"Writing {total_parts} parts…",
        )

        # Build the zip
        zip_name = f"{stem}_split_{total_parts}parts.zip"
        zip_path = parent_dir / zip_name
        counter = 1
        while zip_path.exists():
            zip_path = parent_dir / f"{stem}_split_{total_parts}parts ({counter}).zip"
            counter += 1

        part_files: list[str] = []
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page_indices in enumerate(parts, start=1):
                part_name = f"{stem}_part_{i:02d}_of_{total_parts:02d}.pdf"
                part_path = tmp_path / part_name
                part_doc = fitz.open()
                for p in page_indices:
                    part_doc.insert_pdf(src_doc, from_page=p, to_page=p)
                part_doc.save(str(part_path), deflate=True, garbage=4)
                part_doc.close()
                zf.write(str(part_path), part_name)
                part_files.append(part_name)
                _update_split(sid,
                    parts_done=i,
                    message=f"Writing part {i}/{total_parts}…",
                )

        src_doc.close()
        total_size = zip_path.stat().st_size

    _update_split(sid,
        phase="done",
        parts_done=total_parts,
        message=f"Split into {total_parts} parts",
    )

    elapsed = _time.monotonic() - t0
    logger.info(
        f"Split {path.name} ({total_pages} pages) into {total_parts} parts "
        f"→ {zip_path.name} ({total_size} bytes) in {elapsed:.1f}s"
    )

    return {
        "ok": True,
        "split": True,
        "saved_path": str(zip_path),
        "filename": zip_path.name,
        "part_count": total_parts,
        "parts": part_files,
        "total_size": total_size,
        "message": f"Split into {total_parts} parts, saved as {zip_path.name}",
    }


@router.post("/split-file")
async def split_file(req: SplitFileRequest) -> dict[str, Any]:
    """Split a PDF into multiple smaller PDFs so each part stays
    below *max_size_mb*, then bundle them into a zip.

    Files are named so that an AI ingestion pipeline can process them
    in the correct order:
      ``<basename>_part_01_of_04.pdf``  …  ``<basename>_part_04_of_04.pdf``

    Returns the path and metadata of the resulting zip file.
    """
    import asyncio

    path = _validate_path(req.path)
    if not path.is_file():
        raise HTTPException(400, "Path is not a file")
    if path.suffix.lower() != ".pdf":
        raise HTTPException(400, "Only PDF files can be split")
    if req.max_size_mb <= 0:
        raise HTTPException(400, "max_size_mb must be positive")

    sid = req.split_id or ""
    max_bytes = int(req.max_size_mb * 1024 * 1024)
    src_size = path.stat().st_size

    if src_size <= max_bytes:
        _update_split(sid, phase="done", message="No split needed")
        return {
            "ok": True,
            "split": False,
            "message": f"File is already below {req.max_size_mb} MB — no split needed.",
            "saved_path": str(path),
            "filename": path.name,
            "part_count": 1,
            "total_size": src_size,
        }

    # Run heavy work in a thread so progress polling stays responsive
    try:
        return await asyncio.to_thread(_do_split, path, max_bytes, sid)
    except RuntimeError as e:
        raise HTTPException(500, str(e))

