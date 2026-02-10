"""FastAPI application — main API for the promptShield sidecar."""

from __future__ import annotations

import logging
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import config
from core.persistence import DocumentStore
from pydantic import BaseModel as _PydanticBaseModel
from models.schemas import (
    AnonymizeRequest,
    AnonymizeResponse,
    BatchActionRequest,
    BBox,
    DetectionProgress,
    DetectionSource,
    DetokenizeRequest,
    DetokenizeResponse,
    DocumentInfo,
    DocumentStatus,
    LLMStatusResponse,
    PIIRegion,
    PIIType,
    RegionAction,
    RegionActionRequest,
    RegionSyncItem,
    UploadResponse,
    VaultStatsResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="promptShield",
    version="0.1.0",
    description="Offline document anonymizer with local LLM — promptShield",
)

# CORS — allow Tauri webview and local dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri uses tauri://localhost or https://tauri.localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Document storage
# ---------------------------------------------------------------------------
_documents: dict[str, DocumentInfo] = {}
_store: Optional[DocumentStore] = None


def _get_store() -> DocumentStore:
    """Get the document store instance."""
    if _store is None:
        raise RuntimeError("Document store not initialized")
    return _store


def _get_doc(doc_id: str) -> DocumentInfo:
    if doc_id not in _documents:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return _documents[doc_id]


def _save_doc(doc: DocumentInfo) -> None:
    """Save document state to persistent storage."""
    try:
        store = _get_store()
        store.save_document(doc)
        logger.debug(f"Auto-saved document {doc.doc_id}")
    except Exception as e:
        logger.error(f"Failed to auto-save document {doc.doc_id}: {e}")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    global _store, _documents
    logger.info("Starting promptShield sidecar...")

    # Initialize document store
    storage_dir = config.data_dir / "storage"
    _store = DocumentStore(storage_dir)
    
    # Load existing documents from storage
    try:
        _documents = _store.load_all_documents()
        logger.info(f"Loaded {len(_documents)} existing documents")
    except Exception as e:
        logger.error(f"Failed to load documents: {e}")
        _documents = {}

    # Mount temp dir for serving page bitmaps (legacy support)
    config.temp_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/bitmaps",
        StaticFiles(directory=str(config.temp_dir)),
        name="bitmaps",
    )
    
    # Also mount persistent storage bitmaps
    app.mount(
        "/storage-bitmaps",
        StaticFiles(directory=str(_store.bitmaps_dir)),
        name="storage-bitmaps",
    )
    logger.info(f"Serving bitmaps from {config.temp_dir} (temp) and {_store.bitmaps_dir} (persistent)")

    # Auto-load first available GGUF model if enabled
    if config.auto_load_llm:
        try:
            from core.llm.engine import llm_engine

            gguf_files = sorted(config.models_dir.glob("*.gguf"))
            if gguf_files:
                model_path = str(gguf_files[0])
                logger.info(f"Auto-loading LLM model: {gguf_files[0].name}")
                llm_engine.load_model(model_path)
                logger.info("LLM model loaded successfully")
            else:
                logger.info("No GGUF models found — skipping auto-load")
        except Exception as e:
            logger.warning(f"Auto-load LLM failed (non-fatal): {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Document upload & processing
# ---------------------------------------------------------------------------

@app.post("/api/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a document for anonymization."""
    from core.ingestion.loader import SUPPORTED_EXTENSIONS, guess_mime

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Save uploaded file to temp
    upload_id = uuid.uuid4().hex[:8]
    upload_dir = config.temp_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{upload_id}_{file.filename}"

    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info(f"Saved upload: {upload_path} ({len(content)} bytes)")

    # Ingest the document
    from core.ingestion.loader import ingest_document

    try:
        doc = await ingest_document(upload_path, file.filename)
    except Exception as e:
        raise HTTPException(500, f"Failed to process document: {e}")

    # Store file in persistent storage
    store = _get_store()
    try:
        stored_file_path = store.store_uploaded_file(doc.doc_id, upload_path, file.filename)
        doc.file_path = str(stored_file_path)
        logger.info(f"Stored file permanently: {stored_file_path}")
    except Exception as e:
        logger.error(f"Failed to store file permanently: {e}")

    # Copy page bitmaps to persistent storage
    try:
        store.store_page_bitmaps(doc)
        logger.info(f"Stored {len(doc.pages)} page bitmaps for {doc.doc_id}")
    except Exception as e:
        logger.error(f"Failed to store bitmaps: {e}")

    # Save document state
    _documents[doc.doc_id] = doc
    try:
        store.save_document(doc)
        logger.info(f"Saved document state for {doc.doc_id}")
    except Exception as e:
        logger.error(f"Failed to save document state: {e}")

    return UploadResponse(
        doc_id=doc.doc_id,
        filename=doc.original_filename,
        page_count=doc.page_count,
        status=doc.status,
    )


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get document metadata and page info."""
    doc = _get_doc(doc_id)
    return doc.model_dump(mode="json")


@app.get("/api/documents/{doc_id}/pages/{page_number}")
async def get_page(doc_id: str, page_number: int):
    """Get page data including text blocks."""
    doc = _get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number {page_number} (1-{doc.page_count})")
    page = doc.pages[page_number - 1]
    return page.model_dump(mode="json")


@app.get("/api/documents/{doc_id}/pages/{page_number}/bitmap")
async def get_page_bitmap(doc_id: str, page_number: int):
    """Serve the rendered page bitmap image."""
    doc = _get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number")
    page = doc.pages[page_number - 1]
    bitmap_path = Path(page.bitmap_path)
    if not bitmap_path.exists():
        raise HTTPException(404, "Bitmap not found")
    return FileResponse(str(bitmap_path), media_type="image/png")


@app.get("/api/documents")
async def list_documents():
    """List all uploaded documents."""
    return [
        {
            "doc_id": d.doc_id,
            "original_filename": d.original_filename,
            "filename": d.original_filename,
            "file_path": d.file_path,
            "mime_type": d.mime_type,
            "page_count": d.page_count,
            "status": d.status.value,
            "regions_count": len(d.regions),
            "is_protected": (
                len(d.regions) > 0
                and not any(r.action == RegionAction.PENDING for r in d.regions)
                and any(r.action in (RegionAction.TOKENIZE, RegionAction.REMOVE) for r in d.regions)
            ),
            "created_at": d.created_at.isoformat(),
        }
        for d in _documents.values()
    ]


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and all its persisted data."""
    if doc_id not in _documents:
        raise HTTPException(404, f"Document '{doc_id}' not found")

    del _documents[doc_id]

    try:
        store = _get_store()
        store.delete_document(doc_id)
    except Exception as e:
        logger.error(f"Failed to delete persistent data for {doc_id}: {e}")

    return {"status": "ok", "doc_id": doc_id}


# ---------------------------------------------------------------------------
# PII Detection
# ---------------------------------------------------------------------------

@app.post("/api/documents/{doc_id}/detect")
async def detect_pii(doc_id: str):
    """
    Run PII detection on all pages of a document.

    Returns the list of detected PII regions.
    """
    import traceback

    try:
        from core.detection.pipeline import detect_pii_on_page
        from core.llm.engine import llm_engine

        doc = _get_doc(doc_id)
        doc.status = DocumentStatus.DETECTING
        doc.regions = []

        engine = llm_engine if llm_engine.is_loaded() else None

        for page in doc.pages:
            regions = detect_pii_on_page(page, llm_engine=engine)
            doc.regions.extend(regions)

        doc.status = DocumentStatus.REVIEWING
        logger.info(f"Detection complete for '{doc.original_filename}': {len(doc.regions)} regions")

        _save_doc(doc)

        return {
            "doc_id": doc_id,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Detection failed: {e}\n{tb}")
        raise HTTPException(500, detail=f"Detection error: {e}\n{tb}")


class RedetectRequest(_PydanticBaseModel):
    """Request body for the redetect (autodetect) endpoint."""
    confidence_threshold: float = 0.55
    page_number: Optional[int] = None  # None = all pages
    regex_enabled: bool = True
    ner_enabled: bool = True
    llm_detection_enabled: bool = True


@app.post("/api/documents/{doc_id}/redetect")
async def redetect_pii(doc_id: str, body: RedetectRequest):
    """
    Re-run PII detection with custom fuzziness (confidence threshold).

    Merge strategy:
    - New regions (no significant bbox overlap with existing) → added.
    - Existing regions that overlap with a new detection → updated in place
      (text, pii_type, confidence, source refreshed) but action preserved.
    - Existing regions with no new match → kept untouched (never deleted).
    """
    import traceback

    try:
        from core.detection.pipeline import detect_pii_on_page, _bbox_overlap_area, _bbox_area
        from core.llm.engine import llm_engine

        doc = _get_doc(doc_id)

        # Temporarily override config thresholds for this detection run
        original_threshold = config.confidence_threshold
        original_regex = config.regex_enabled
        original_ner = config.ner_enabled
        original_llm = config.llm_detection_enabled
        try:
            config.confidence_threshold = body.confidence_threshold
            config.regex_enabled = body.regex_enabled
            config.ner_enabled = body.ner_enabled
            config.llm_detection_enabled = body.llm_detection_enabled

            engine = llm_engine if llm_engine.is_loaded() else None

            # Determine which pages to scan
            pages_to_scan = doc.pages
            if body.page_number is not None:
                pages_to_scan = [p for p in doc.pages if p.page_number == body.page_number]
                if not pages_to_scan:
                    raise HTTPException(404, detail=f"Page {body.page_number} not found")

            # Run detection on target pages
            new_regions: list[PIIRegion] = []
            for page in pages_to_scan:
                detected = detect_pii_on_page(page, llm_engine=engine)
                new_regions.extend(detected)

        finally:
            # Restore original config
            config.confidence_threshold = original_threshold
            config.regex_enabled = original_regex
            config.ner_enabled = original_ner
            config.llm_detection_enabled = original_llm

        # ── Merge new detections into existing regions ──
        scanned_pages = {p.page_number for p in pages_to_scan}
        # Separate existing regions into scanned-page vs other-page
        existing_on_scanned = [r for r in doc.regions if r.page_number in scanned_pages]
        existing_other = [r for r in doc.regions if r.page_number not in scanned_pages]

        OVERLAP_THRESHOLD = 0.50  # 50% IoU to consider "same region"
        matched_existing_ids: set[str] = set()
        updated_indices: set[int] = set()  # new region indices that matched an existing
        added_count = 0
        updated_count = 0

        # For each new region, find best-matching existing region
        for ni, nr in enumerate(new_regions):
            nr_area = _bbox_area(nr.bbox)
            if nr_area <= 0:
                continue

            best_match = None
            best_iou = 0.0
            for er in existing_on_scanned:
                if er.page_number != nr.page_number or er.id in matched_existing_ids:
                    continue
                overlap = _bbox_overlap_area(nr.bbox, er.bbox)
                er_area = _bbox_area(er.bbox)
                if er_area <= 0:
                    continue
                union = nr_area + er_area - overlap
                iou = overlap / union if union > 0 else 0
                if iou > best_iou:
                    best_iou = iou
                    best_match = er

            if best_match and best_iou >= OVERLAP_THRESHOLD:
                # Update existing region in place — keep action
                best_match.bbox = nr.bbox
                best_match.text = nr.text
                best_match.pii_type = nr.pii_type
                best_match.confidence = nr.confidence
                best_match.source = nr.source
                best_match.char_start = nr.char_start
                best_match.char_end = nr.char_end
                matched_existing_ids.add(best_match.id)
                updated_indices.add(ni)
                updated_count += 1

        # Add truly new regions (not matched to any existing)
        for ni, nr in enumerate(new_regions):
            if ni not in updated_indices:
                existing_on_scanned.append(nr)
                added_count += 1

        # Rebuild doc.regions: untouched other-page regions + merged scanned-page regions
        doc.regions = existing_other + existing_on_scanned
        doc.status = DocumentStatus.REVIEWING
        _save_doc(doc)

        logger.info(
            f"Redetect for '{doc.original_filename}' "
            f"(threshold={body.confidence_threshold}, pages={body.page_number or 'all'}): "
            f"{added_count} added, {updated_count} updated, "
            f"{len(doc.regions)} total"
        )

        return {
            "doc_id": doc_id,
            "added": added_count,
            "updated": updated_count,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Redetect failed: {e}\n{tb}")
        raise HTTPException(500, detail=f"Redetect error: {e}\n{tb}")


@app.get("/api/documents/{doc_id}/regions")
async def get_regions(doc_id: str, page_number: Optional[int] = None):
    """Get detected PII regions, optionally filtered by page."""
    doc = _get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    return [r.model_dump(mode="json") for r in regions]


@app.get("/api/documents/{doc_id}/debug-detections")
async def debug_detections(doc_id: str, page_number: Optional[int] = None):
    """Debug endpoint — shows every detection with type, confidence, source, text."""
    doc = _get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    summary = []
    for r in regions:
        summary.append({
            "page": r.page_number,
            "type": r.pii_type.value if hasattr(r.pii_type, "value") else str(r.pii_type),
            "confidence": round(r.confidence, 3),
            "source": r.source.value if hasattr(r.source, "value") else str(r.source),
            "text": r.text[:80],
        })
    summary.sort(key=lambda x: (-x["confidence"], x["type"]))
    return {"total": len(summary), "regions": summary}


@app.put("/api/documents/{doc_id}/regions/{region_id}/action")
async def set_region_action(doc_id: str, region_id: str, req: RegionActionRequest):
    """Set the action for a specific PII region."""
    doc = _get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.action = req.action
            _save_doc(doc)
            return {"status": "ok", "region_id": region_id, "action": req.action.value}
    raise HTTPException(404, f"Region '{region_id}' not found")


@app.delete("/api/documents/{doc_id}/regions/{region_id}")
async def delete_region(doc_id: str, region_id: str):
    """Delete a PII region entirely from the document."""
    doc = _get_doc(doc_id)
    original_len = len(doc.regions)
    doc.regions = [r for r in doc.regions if r.id != region_id]
    if len(doc.regions) == original_len:
        raise HTTPException(404, f"Region '{region_id}' not found")
    _save_doc(doc)
    return {"status": "ok", "region_id": region_id}


@app.put("/api/documents/{doc_id}/regions/{region_id}/bbox")
async def update_region_bbox(doc_id: str, region_id: str, bbox: BBox):
    """Update the bounding box of a PII region (move / resize)."""
    doc = _get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.bbox = bbox
            _save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


class UpdateLabelRequest(_PydanticBaseModel):
    pii_type: PIIType


@app.put("/api/documents/{doc_id}/regions/{region_id}/label")
async def update_region_label(doc_id: str, region_id: str, req: UpdateLabelRequest):
    """Update the PII type label of a region."""
    doc = _get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.pii_type = req.pii_type
            _save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


class UpdateTextRequest(_PydanticBaseModel):
    text: str


@app.put("/api/documents/{doc_id}/regions/{region_id}/text")
async def update_region_text(doc_id: str, region_id: str, req: UpdateTextRequest):
    """Update the detected text content of a region."""
    doc = _get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.text = req.text
            _save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


@app.post("/api/documents/{doc_id}/regions/{region_id}/reanalyze")
async def reanalyze_region(doc_id: str, region_id: str):
    """Re-analyze the content under a region's bounding box.

    Extracts text beneath the bbox, runs the detection pipeline,
    and updates the region's text, pii_type, confidence, and source.
    """
    from core.detection.pipeline import reanalyze_bbox
    from core.llm.engine import llm_engine

    doc = _get_doc(doc_id)
    region = None
    for r in doc.regions:
        if r.id == region_id:
            region = r
            break
    if region is None:
        raise HTTPException(404, f"Region '{region_id}' not found")

    # Find the page data for this region
    page_data = None
    for p in doc.pages:
        if p.page_number == region.page_number:
            page_data = p
            break
    if page_data is None:
        raise HTTPException(400, f"Page {region.page_number} data not available")

    engine = llm_engine if llm_engine.is_loaded() else None
    result = reanalyze_bbox(page_data, region.bbox, llm_engine=engine)

    # Update the region in-place
    region.text = result["text"] or region.text
    if result["confidence"] > 0:
        region.pii_type = result["pii_type"]
        region.confidence = result["confidence"]
        region.source = result["source"]

    _save_doc(doc)

    return {
        "region_id": region_id,
        "text": region.text,
        "pii_type": region.pii_type if isinstance(region.pii_type, str) else region.pii_type.value,
        "confidence": region.confidence,
        "source": region.source if isinstance(region.source, str) else region.source.value,
    }


@app.put("/api/documents/{doc_id}/regions/batch-action")
async def batch_region_action(doc_id: str, req: BatchActionRequest):
    """Apply an action to multiple regions at once."""
    doc = _get_doc(doc_id)
    region_map = {r.id: r for r in doc.regions}
    updated = 0
    for rid in req.region_ids:
        if rid in region_map:
            region_map[rid].action = req.action
            updated += 1
    _save_doc(doc)
    return {"status": "ok", "updated": updated}


@app.post("/api/documents/{doc_id}/regions/batch-delete")
async def batch_delete_regions(doc_id: str, req: BatchActionRequest):
    """Delete multiple regions at once."""
    doc = _get_doc(doc_id)
    ids_to_delete = set(req.region_ids)
    original_len = len(doc.regions)
    doc.regions = [r for r in doc.regions if r.id not in ids_to_delete]
    deleted = original_len - len(doc.regions)
    _save_doc(doc)
    return {"status": "ok", "deleted": deleted}


@app.post("/api/documents/{doc_id}/regions/add")
async def add_manual_region(doc_id: str, region: PIIRegion):
    """Add a manually selected PII region."""
    doc = _get_doc(doc_id)
    region.source = "MANUAL"
    doc.regions.append(region)
    _save_doc(doc)
    return {"status": "ok", "region_id": region.id}


class HighlightAllRequest(_PydanticBaseModel):
    region_id: str


@app.post("/api/documents/{doc_id}/regions/highlight-all")
async def highlight_all(doc_id: str, req: HighlightAllRequest):
    """Find all occurrences of a region's text across every page and create
    new MANUAL regions for any that don't already have one."""
    import traceback
    try:
        return _highlight_all_impl(doc_id, req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"highlight-all error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, detail=str(e))


def _normalize(text: str) -> str:
    """Normalize for fuzzy matching: lowercase, collapse whitespace, strip accents."""
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fuzzy_ratio(a: str, b: str) -> float:
    """Quick similarity ratio between two strings (0..1)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


_FUZZY_THRESHOLD = 0.75  # 75% similarity


def _highlight_all_impl(doc_id: str, req: HighlightAllRequest):
    doc = _get_doc(doc_id)

    # Find the source region
    source_region = next((r for r in doc.regions if r.id == req.region_id), None)
    if source_region is None:
        raise HTTPException(404, "Region not found")

    needle = source_region.text.strip()
    needle_lower = needle.lower()
    needle_norm = _normalize(needle)
    if not needle_norm:
        return {"created": 0, "new_regions": [], "all_ids": [source_region.id]}

    # Gather existing region bboxes per page to avoid duplicates.
    existing_spans: dict[int, list[tuple[float, float, float, float, str]]] = {}
    for r in doc.regions:
        if r.action == RegionAction.CANCEL:
            continue
        existing_spans.setdefault(r.page_number, []).append(
            (r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1, r.text.strip().lower())
        )

    new_regions: list[PIIRegion] = []

    for page in doc.pages:
        full_text = page.full_text
        if not full_text:
            continue

        # Rebuild the char-offset mapping by replicating the same logic
        # used in _build_full_text (sorted by y0, x0; newline if vertical
        # gap > 0.6 * line_height, else space).
        sorted_blocks = sorted(page.text_blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))
        block_spans: list[tuple[int, int, int]] = []  # (char_start, char_end, original_index)
        offset = 0
        prev_y: float | None = None
        line_height = 0.0
        block_index_map = {id(b): i for i, b in enumerate(page.text_blocks)}

        for blk in sorted_blocks:
            if prev_y is not None:
                gap = blk.bbox.y0 - prev_y
                if line_height > 0 and gap > line_height * 0.6:
                    offset += 1  # newline char
                else:
                    offset += 1  # space char

            blen = len(blk.text)
            orig_idx = block_index_map[id(blk)]
            block_spans.append((offset, offset + blen, orig_idx))
            offset += blen
            line_height = max(line_height, blk.bbox.y1 - blk.bbox.y0)
            prev_y = blk.bbox.y0

        # ---- Fuzzy sliding-window search for needle in full_text ----
        needle_len = len(needle_norm)
        full_norm = _normalize(full_text)

        # Build a mapping from normalized-string index → original char index.
        # _normalize lowercases, strips accents, collapses whitespace.
        import unicodedata, re as _re
        tmp = unicodedata.normalize("NFKD", full_text)
        tmp2 = "".join(c for c in tmp if not unicodedata.combining(c))
        tmp3 = tmp2.lower()
        # tmp3 has same length as tmp2; now we need to map through
        # whitespace collapsing.  Rebuild manually:
        _norm_chars = []
        in_space = False
        stripped_leading = False
        for ci, ch in enumerate(tmp3):
            is_ws = ch in (" ", "\t", "\n", "\r")
            if not stripped_leading and is_ws:
                continue
            if is_ws:
                if not in_space:
                    _norm_chars.append(ci)
                    in_space = True
            else:
                stripped_leading = True
                _norm_chars.append(ci)
                in_space = False
        # _norm_chars[ni] gives index into tmp3 (== index into original text
        # after NFKD + combining removal but before lowering, which preserves
        # length). For practical purposes we use it to slice `full_text`.

        # map from tmp3 index -> original full_text index
        # Since NFKD may change length, build a proper mapping:
        # original -> NFKD expanded chars
        orig_to_nfkd: list[int] = []  # orig char idx -> first nfkd idx
        nfkd_to_orig: list[int] = []  # nfkd idx -> orig char idx
        ni = 0
        for oi_c, orig_c in enumerate(full_text):
            nfkd_of_c = unicodedata.normalize("NFKD", orig_c)
            orig_to_nfkd.append(ni)
            for _ in nfkd_of_c:
                nfkd_to_orig.append(oi_c)
                ni += 1

        # Now _norm_chars[k] indexes into tmp3 (same length as nfkd_text).
        # Convert to original full_text indices.
        def norm_idx_to_orig(ni_: int) -> int:
            """Map normalized string index to original full_text index."""
            if ni_ < len(_norm_chars):
                nfkd_idx = _norm_chars[ni_]
                if nfkd_idx < len(nfkd_to_orig):
                    return nfkd_to_orig[nfkd_idx]
            return len(full_text)

        # Try exact normalized match first (fast path)
        search_start_n = 0
        matches: list[tuple[int, int]] = []  # (orig_start, orig_end)

        while True:
            idx_n = full_norm.find(needle_norm, search_start_n)
            if idx_n == -1:
                break
            search_start_n = idx_n + 1
            orig_start = norm_idx_to_orig(idx_n)
            orig_end_idx = idx_n + needle_len
            orig_end = norm_idx_to_orig(orig_end_idx) if orig_end_idx < len(full_norm) else len(full_text)
            matches.append((orig_start, orig_end))

        # Also try fuzzy sliding window to catch OCR variations
        if needle_len >= 2:
            window = needle_len
            for tol in (0, 1, 2):  # allow window slightly smaller/larger
                wlen = window + tol
                if wlen > len(full_norm):
                    continue
                for si in range(len(full_norm) - wlen + 1):
                    chunk = full_norm[si : si + wlen]
                    if _fuzzy_ratio(needle_norm, chunk) >= _FUZZY_THRESHOLD:
                        orig_start = norm_idx_to_orig(si)
                        orig_end = norm_idx_to_orig(si + wlen) if si + wlen < len(full_norm) else len(full_text)
                        # Avoid adding near-duplicates (within half needle length)
                        if any(abs(orig_start - ms) < max(needle_len // 2, 2) for ms, _ in matches):
                            continue
                        matches.append((orig_start, orig_end))
                wlen = window - tol if tol > 0 else -1
                if wlen >= 2 and wlen <= len(full_norm):
                    for si in range(len(full_norm) - wlen + 1):
                        chunk = full_norm[si : si + wlen]
                        if _fuzzy_ratio(needle_norm, chunk) >= _FUZZY_THRESHOLD:
                            orig_start = norm_idx_to_orig(si)
                            orig_end = norm_idx_to_orig(si + wlen) if si + wlen < len(full_norm) else len(full_text)
                            if any(abs(orig_start - ms) < max(needle_len // 2, 2) for ms, _ in matches):
                                continue
                            matches.append((orig_start, orig_end))

        for idx, match_end in matches:

            # Find all text_blocks that overlap with [idx, match_end)
            hit_blocks = []
            for cs, ce, bi in block_spans:
                if ce <= idx:
                    continue
                if cs >= match_end:
                    break
                hit_blocks.append(page.text_blocks[bi])

            if not hit_blocks:
                continue

            # Compute bounding box as union of the hit blocks
            bx0 = min(b.bbox.x0 for b in hit_blocks)
            by0 = min(b.bbox.y0 for b in hit_blocks)
            bx1 = max(b.bbox.x1 for b in hit_blocks)
            by1 = max(b.bbox.y1 for b in hit_blocks)

            # Check for existing region that already covers this area
            page_existing = existing_spans.get(page.page_number, [])
            already_covered = False
            for ex0, ey0, ex1, ey1, etxt in page_existing:
                # Compute intersection area
                ix0 = max(bx0, ex0)
                iy0 = max(by0, ey0)
                ix1 = min(bx1, ex1)
                iy1 = min(by1, ey1)
                if ix0 < ix1 and iy0 < iy1:
                    inter_area = (ix1 - ix0) * (iy1 - iy0)
                    new_area = max((bx1 - bx0) * (by1 - by0), 1e-6)
                    # Skip if >40% of the new region overlaps an existing one
                    if inter_area / new_area > 0.4:
                        already_covered = True
                        break
            if already_covered:
                continue

            matched_text = full_text[idx:match_end]
            region = PIIRegion(
                page_number=page.page_number,
                bbox=BBox(x0=round(bx0, 2), y0=round(by0, 2),
                          x1=round(bx1, 2), y1=round(by1, 2)),
                text=matched_text,
                pii_type=source_region.pii_type,
                confidence=source_region.confidence,
                source=DetectionSource.MANUAL,
                action=RegionAction.PENDING,
                char_start=idx,
                char_end=match_end,
            )
            new_regions.append(region)
            doc.regions.append(region)
            # Track so we don't duplicate within same page
            existing_spans.setdefault(page.page_number, []).append(
                (bx0, by0, bx1, by1, needle_lower)
            )

    # Collect all matching region IDs (existing + new) using fuzzy match
    all_ids = []
    for r in doc.regions:
        if r.action == RegionAction.CANCEL:
            continue
        r_norm = _normalize(r.text.strip())
        if not r_norm:
            continue
        # Exact normalized match or fuzzy match
        if needle_norm in r_norm or r_norm in needle_norm or _fuzzy_ratio(needle_norm, r_norm) >= _FUZZY_THRESHOLD:
            all_ids.append(r.id)

    _save_doc(doc)

    return {
        "created": len(new_regions),
        "new_regions": [r.model_dump(mode="json") for r in new_regions],
        "all_ids": all_ids,
    }


# ---------------------------------------------------------------------------
# Sync & Anonymization
# ---------------------------------------------------------------------------

@app.put("/api/documents/{doc_id}/regions/sync")
async def sync_regions(doc_id: str, items: list[RegionSyncItem]):
    """Bulk-sync region actions and bboxes from the frontend.

    Called right before anonymize to guarantee the backend has the latest
    user edits (moved/resized regions, changed actions) regardless of
    whether individual PUT calls have completed."""
    doc = _get_doc(doc_id)
    region_map = {r.id: r for r in doc.regions}
    synced = 0
    for item in items:
        r = region_map.get(item.id)
        if r:
            r.action = item.action
            r.bbox = item.bbox
            synced += 1
    _save_doc(doc)
    return {"status": "ok", "synced": synced}


@app.post("/api/documents/{doc_id}/anonymize", response_model=AnonymizeResponse)
async def anonymize(doc_id: str):
    """Apply anonymization to the document based on region actions."""
    from core.anonymizer.engine import anonymize_document

    doc = _get_doc(doc_id)
    doc.status = DocumentStatus.ANONYMIZING

    try:
        result = await anonymize_document(doc)
        doc.status = DocumentStatus.COMPLETED
        _save_doc(doc)
        return result
    except Exception as e:
        import traceback
        logger.error(f"Anonymization failed:\n{traceback.format_exc()}")
        doc.status = DocumentStatus.ERROR
        _save_doc(doc)
        raise HTTPException(500, f"Anonymization failed: {e}")


@app.get("/api/documents/{doc_id}/download/{file_type}")
async def download_output(doc_id: str, file_type: str):
    """Download the anonymized output file (pdf or text)."""
    doc = _get_doc(doc_id)
    output_dir = config.temp_dir / doc_id / "output"

    if file_type == "pdf":
        files = list(output_dir.glob("*_anonymized_*.pdf"))
    elif file_type == "text":
        files = list(output_dir.glob("*_anonymized_*.txt"))
    else:
        raise HTTPException(400, "file_type must be 'pdf' or 'text'")

    if not files:
        raise HTTPException(404, "Output file not found. Run anonymization first.")

    # Return the latest file
    latest = max(files, key=lambda f: f.stat().st_mtime)
    media_type = "application/pdf" if file_type == "pdf" else "text/plain"
    return FileResponse(str(latest), media_type=media_type, filename=latest.name)


# ---------------------------------------------------------------------------
# De-tokenization
# ---------------------------------------------------------------------------

@app.post("/api/detokenize", response_model=DetokenizeResponse)
async def detokenize(req: DetokenizeRequest):
    """Replace tokens in text with their original values."""
    from core.vault.store import vault

    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked. Unlock it first.")

    result_text, count, unresolved = vault.resolve_all_tokens(req.text)
    return DetokenizeResponse(
        original_text=result_text,
        tokens_replaced=count,
        unresolved_tokens=unresolved,
    )


@app.post("/api/detokenize/file")
async def detokenize_file_endpoint(file: UploadFile = File(...)):
    """De-tokenize tokens inside an uploaded file (.docx, .xlsx, .pdf, .txt, .csv).

    Returns the processed file as a download.
    Metadata (tokens_replaced, unresolved) is passed via response headers.
    """
    from core.vault.store import vault
    from core.detokenize_file import detokenize_file, SUPPORTED_EXTENSIONS

    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked. Unlock it first.")

    filename = file.filename or "unknown.txt"
    data = await file.read()

    try:
        out_bytes, out_name, count, unresolved = detokenize_file(data, filename, vault)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"File de-tokenization failed: {e}")
        raise HTTPException(500, f"De-tokenization failed: {e}")

    # Determine media type
    ext = Path(out_name).suffix.lower()
    media_types = {
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    # Write to temp file and return
    import tempfile, os
    tmp = Path(tempfile.mkdtemp(dir=str(config.temp_dir)))
    out_path = tmp / out_name
    out_path.write_bytes(out_bytes)

    headers = {
        "X-Tokens-Replaced": str(count),
        "X-Unresolved-Tokens": ",".join(unresolved) if unresolved else "",
        "Access-Control-Expose-Headers": "X-Tokens-Replaced, X-Unresolved-Tokens",
    }

    return FileResponse(
        str(out_path),
        media_type=media_type,
        filename=out_name,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Vault management
# ---------------------------------------------------------------------------

class _PassphraseBody(_PydanticBaseModel):
    passphrase: str


@app.post("/api/vault/unlock")
async def unlock_vault(body: _PassphraseBody):
    """Unlock the token vault with a passphrase."""
    from core.vault.store import vault

    try:
        vault.initialize(body.passphrase)
        return {"status": "ok", "message": "Vault unlocked"}
    except ValueError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to open vault: {e}")


@app.get("/api/vault/status")
async def vault_status():
    """Check vault status."""
    from core.vault.store import vault
    return {
        "unlocked": vault.is_unlocked,
        "path": str(vault.db_path),
    }


@app.get("/api/vault/stats", response_model=VaultStatsResponse)
async def vault_stats():
    """Get vault statistics."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    stats = vault.get_stats()
    return VaultStatsResponse(**stats)


@app.get("/api/vault/tokens")
async def list_vault_tokens(source_document: Optional[str] = None):
    """List all tokens in the vault."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    tokens = vault.list_tokens(source_document=source_document)
    return [t.model_dump(mode="json") for t in tokens]


# ---------------------------------------------------------------------------
# LLM management
# ---------------------------------------------------------------------------

@app.get("/api/llm/status", response_model=LLMStatusResponse)
async def llm_status():
    """Get LLM engine status."""
    from core.llm.engine import llm_engine
    return LLMStatusResponse(
        loaded=llm_engine.is_loaded(),
        model_name=llm_engine.model_name,
        model_path=llm_engine.model_path,
        gpu_enabled=llm_engine.gpu_enabled,
        context_size=config.llm_context_size,
    )


@app.post("/api/llm/load")
async def load_llm(model_path: str, force_cpu: bool = False):
    """Load a GGUF model."""
    from core.llm.engine import llm_engine
    try:
        llm_engine.load_model(model_path, force_cpu=force_cpu)
        return {"status": "ok", "model": llm_engine.model_name}
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {e}")


@app.post("/api/llm/unload")
async def unload_llm():
    """Unload the current LLM model."""
    from core.llm.engine import llm_engine
    llm_engine.unload_model()
    return {"status": "ok"}


@app.get("/api/llm/models")
async def list_models():
    """List available GGUF models in the models directory."""
    from core.llm.engine import llm_engine
    return llm_engine.list_available_models()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def get_settings():
    """Get current app settings."""
    return config.model_dump(mode="json")


@app.patch("/api/settings")
async def update_settings(updates: dict):
    """Update app settings (partial update)."""
    allowed = {
        "regex_enabled", "ner_enabled", "llm_detection_enabled",
        "confidence_threshold", "ocr_language", "ocr_dpi",
        "render_dpi", "tesseract_cmd",
        "ner_backend", "ner_model_preference",
    }
    applied = {}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if hasattr(config, key):
            setattr(config, key, value)
            applied[key] = value

    # When the NER backend changes, unload the cached BERT pipeline so the
    # newly selected model is loaded on the next detection run.
    if "ner_backend" in applied:
        try:
            from core.detection.bert_detector import unload_pipeline
            unload_pipeline()
            logger.info(f"NER backend changed to '{applied['ner_backend']}' — BERT pipeline unloaded")
        except Exception:
            pass  # non-fatal; pipeline will reload on next detection

    # Persist to disk so settings survive server restarts
    if applied:
        config.save_user_settings()

    return {"status": "ok", "applied": applied}


# ---------------------------------------------------------------------------
# Vault export
# ---------------------------------------------------------------------------

@app.post("/api/vault/export")
async def export_vault(passphrase: str):
    """Export all vault tokens as encrypted JSON."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    try:
        data = vault.export_vault(passphrase)
        return JSONResponse(content={"export": data})
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")


# ---------------------------------------------------------------------------
# Bundled frontend — serve the React SPA when running as a standalone exe
# ---------------------------------------------------------------------------

def _get_frontend_dir() -> Path | None:
    """Locate the bundled frontend dist directory."""
    # When frozen by PyInstaller, files are in sys._MEIPASS
    if getattr(sys, "frozen", False):
        candidate = Path(sys._MEIPASS) / "frontend_dist"     # type: ignore[attr-defined]
        if candidate.is_dir():
            return candidate
    # Dev / non-frozen: look relative to this file
    candidate = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if candidate.is_dir():
        return candidate
    return None


_frontend_dir = _get_frontend_dir()

if _frontend_dir is not None:
    # Serve static assets (JS, CSS, images)
    app.mount(
        "/assets",
        StaticFiles(directory=str(_frontend_dir / "assets")),
        name="frontend-assets",
    )

    @app.get("/")
    async def serve_index():
        return HTMLResponse((_frontend_dir / "index.html").read_text(encoding="utf-8"))

    # SPA catch-all — any unmatched GET that isn't /api/* serves index.html
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Don't intercept API or bitmap paths
        if full_path.startswith(("api/", "health", "bitmaps/")):
            raise HTTPException(404)
        file_path = _frontend_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return HTMLResponse((_frontend_dir / "index.html").read_text(encoding="utf-8"))
