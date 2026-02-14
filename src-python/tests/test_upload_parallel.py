"""Tests for multi-file and multi-page PDF upload stability.

Verifies that _process_pdf handles multi-page documents correctly
with sequential processing (PDFium is not thread-safe) and that
the upload endpoint handles concurrent requests without crashes.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import MagicMock

import pypdfium2 as pdfium
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.server import app
from api import deps
from core.ingestion.loader import _process_pdf, _build_full_text
from core.config import config


# ──────────────────── helpers ────────────────────


def _make_pdf(n_pages: int = 1, text: str = "Hello world") -> bytes:
    """Create a minimal valid PDF with *n_pages* pages, each containing *text*."""
    doc = pdfium.PdfDocument.new()
    for _ in range(n_pages):
        page = doc.new_page(612, 792)  # US Letter
        page.close()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _write_pdf(path: Path, n_pages: int = 1) -> Path:
    """Write a temp PDF and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_pdf(n_pages))
    return path


# ──────────────────── _process_pdf unit tests ────────────────────


class TestProcessPdf:
    """Unit tests for the core _process_pdf function."""

    def test_single_page(self, tmp_path: Path):
        pdf = _write_pdf(tmp_path / "one.pdf", n_pages=1)
        pages = _process_pdf(pdf, "test_single")
        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert pages[0].width > 0 and pages[0].height > 0

    def test_multi_page(self, tmp_path: Path):
        pdf = _write_pdf(tmp_path / "multi.pdf", n_pages=5)
        pages = _process_pdf(pdf, "test_multi")
        assert len(pages) == 5
        for i, p in enumerate(pages):
            assert p.page_number == i + 1

    def test_invalid_pdf_raises(self, tmp_path: Path):
        """A corrupt/empty file should raise, not crash with a native error."""
        path = tmp_path / "bad.pdf"
        path.write_bytes(b"not a pdf")
        with pytest.raises(Exception):
            _process_pdf(path, "test_bad")

    def test_sequential_calls(self, tmp_path: Path):
        """Multiple sequential calls must all succeed (no leaked state)."""
        results = []
        for i in range(6):
            pdf = _write_pdf(tmp_path / f"seq_{i}.pdf", n_pages=3)
            pages = _process_pdf(pdf, f"test_seq_{i}")
            results.append(len(pages))
        assert results == [3] * 6

    def test_large_page_count(self, tmp_path: Path):
        """Stress test with a 20-page PDF."""
        pdf = _write_pdf(tmp_path / "large.pdf", n_pages=20)
        pages = _process_pdf(pdf, "test_large")
        assert len(pages) == 20
        assert pages[-1].page_number == 20

    def test_bitmap_paths_exist(self, tmp_path: Path):
        """Each page should have a bitmap PNG written to disk."""
        pdf = _write_pdf(tmp_path / "bitmaps.pdf", n_pages=3)
        # Point config temp_dir at our tmp_path so bitmaps land there
        original_temp = config.temp_dir
        config.temp_dir = tmp_path
        try:
            pages = _process_pdf(pdf, "test_bitmaps")
        finally:
            config.temp_dir = original_temp
        for p in pages:
            assert Path(p.bitmap_path).exists(), f"Missing bitmap: {p.bitmap_path}"


# ──────────────────── Upload endpoint integration tests ────────────────────


@pytest_asyncio.fixture
async def client():
    # Provide a mock store so upload endpoint doesn't fail on get_store()
    mock_store = MagicMock()
    mock_store.store_uploaded_file.side_effect = lambda doc_id, src, fname: src
    mock_store.store_page_bitmaps.return_value = None
    mock_store.save_document.return_value = None
    old_store = deps.store
    deps.store = mock_store
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        deps.store = old_store


class TestUploadEndpoint:
    """Integration tests for /api/documents/upload."""

    @pytest.mark.asyncio
    async def test_upload_single_pdf(self, client: AsyncClient):
        pdf_bytes = _make_pdf(n_pages=2)
        resp = await client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_count"] == 2
        assert data["filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_upload_multiple_sequential(self, client: AsyncClient):
        """Upload 5 PDFs sequentially — all must succeed."""
        for i in range(5):
            pdf_bytes = _make_pdf(n_pages=3)
            resp = await client.post(
                "/api/documents/upload",
                files={"file": (f"doc_{i}.pdf", pdf_bytes, "application/pdf")},
            )
            assert resp.status_code == 200, f"Upload {i} failed: {resp.text}"
            assert resp.json()["page_count"] == 3

    @pytest.mark.asyncio
    async def test_upload_multiple_concurrent(self, client: AsyncClient):
        """Upload 4 PDFs concurrently — all must succeed without crashes."""

        async def _upload(idx: int):
            pdf_bytes = _make_pdf(n_pages=2)
            resp = await client.post(
                "/api/documents/upload",
                files={"file": (f"concurrent_{idx}.pdf", pdf_bytes, "application/pdf")},
            )
            return idx, resp.status_code, resp.json()

        results = await asyncio.gather(*[_upload(i) for i in range(4)])
        for idx, status, data in results:
            assert status == 200, f"Concurrent upload {idx} failed: {data}"
            assert data["page_count"] == 2

    @pytest.mark.asyncio
    async def test_reject_unsupported_extension(self, client: AsyncClient):
        resp = await client.post(
            "/api/documents/upload",
            files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_path_traversal(self, client: AsyncClient):
        resp = await client.post(
            "/api/documents/upload",
            files={"file": ("../../../etc/passwd.pdf", b"%PDF", "application/pdf")},
        )
        assert resp.status_code == 400
