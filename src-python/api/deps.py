"""Shared state, helpers, and re-exports used by all API routers."""

from __future__ import annotations

import asyncio
import logging
import threading
import time as _time
from contextlib import contextmanager
from typing import Any, Generator, Optional

from fastapi import HTTPException

from core.config import config
from core.persistence import DocumentStore
from models.schemas import BBox, DocumentInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton state  (mutated by server.startup, read everywhere)
# ---------------------------------------------------------------------------
documents: dict[str, DocumentInfo] = {}
store: Optional[DocumentStore] = None

# H1: asyncio lock to serialise document mutations from concurrent requests
_documents_lock = asyncio.Lock()

# In-memory detection progress tracker  (doc_id → progress dict)
detection_progress: dict[str, dict] = {}

# Maximum age (seconds) for completed/errored detection progress entries
_PROGRESS_TTL = 300  # 5 minutes


def cleanup_stale_progress() -> None:
    """Remove completed/errored detection_progress entries older than TTL."""
    now = _time.time()
    stale = [
        k for k, v in detection_progress.items()
        if v.get("status") in ("complete", "error")
        and now - v.get("_started_at", now) > _PROGRESS_TTL
    ]
    for k in stale:
        detection_progress.pop(k, None)

# Detection lock — prevents concurrent detection runs from racing on config
_detection_lock = threading.Lock()
_detection_lock_acquired_at: float | None = None
_DETECTION_LOCK_TIMEOUT_S: float = 600.0  # 10 minutes max


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def get_store() -> DocumentStore:
    """Return the document store; raise if not initialised."""
    if store is None:
        raise RuntimeError("Document store not initialized")
    return store


def _clamp_bbox(bbox: BBox, page_w: float, page_h: float) -> BBox:
    """Clamp a bounding box so it sits within [0, page_w] × [0, page_h]."""
    return BBox(
        x0=max(0.0, min(bbox.x0, page_w)),
        y0=max(0.0, min(bbox.y0, page_h)),
        x1=max(0.0, min(bbox.x1, page_w)),
        y1=max(0.0, min(bbox.y1, page_h)),
    )


def sanitize_document_regions(doc: DocumentInfo) -> bool:
    """Clamp every region's bbox to its page bounds.

    Returns True if any region was modified.
    """
    page_map = {p.page_number: p for p in doc.pages}
    changed = False
    for region in doc.regions:
        pd = page_map.get(region.page_number)
        if pd is None:
            continue
        clamped = _clamp_bbox(region.bbox, pd.width, pd.height)
        if clamped != region.bbox:
            region.bbox = clamped
            changed = True
    return changed


def get_doc(doc_id: str) -> DocumentInfo:
    """Fetch a document by id or 404."""
    if doc_id not in documents:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return documents[doc_id]


def save_doc(doc: DocumentInfo) -> None:
    """Persist the document to disk."""
    try:
        s = get_store()
        s.save_document(doc)
        logger.debug(f"Auto-saved document {doc.doc_id}")
    except Exception:
        # M9: Log full traceback — callers should not silently lose data
        logger.exception(f"Failed to auto-save document {doc.doc_id}")


def now_ts() -> float:
    """Monotonic-ish wall-clock timestamp (``time.time()``)."""
    return _time.time()


def get_active_llm_engine() -> object | None:
    """Return the currently active LLM engine (local or remote) or None."""
    from core.llm.engine import llm_engine
    from core.llm.remote_engine import remote_llm_engine

    if config.llm_provider == "remote":
        if remote_llm_engine.is_loaded():
            return remote_llm_engine
        return None
    # default: local
    if llm_engine.is_loaded():
        return llm_engine
    return None


def acquire_detection_lock(doc_id: str) -> bool:
    """Try to acquire the detection lock (non-blocking). Returns True if acquired.

    If a previous lock has been held longer than ``_DETECTION_LOCK_TIMEOUT_S``,
    it is considered stale and forcibly released before re-acquiring.
    """
    global _detection_lock_acquired_at

    acquired = _detection_lock.acquire(blocking=False)
    if acquired:
        _detection_lock_acquired_at = _time.time()
        return True

    # Check for stale lock
    if _detection_lock_acquired_at is not None:
        held_for = _time.time() - _detection_lock_acquired_at
        if held_for > _DETECTION_LOCK_TIMEOUT_S:
            logger.warning(
                "Detection lock held for %.0fs (>%.0fs) — forcing release (stale lock for doc %s)",
                held_for, _DETECTION_LOCK_TIMEOUT_S, doc_id,
            )
            try:
                _detection_lock.release()
            except RuntimeError:
                pass
            acquired = _detection_lock.acquire(blocking=False)
            if acquired:
                _detection_lock_acquired_at = _time.time()
                return True

    logger.warning(f"Detection already running — rejecting request for {doc_id}")
    return False


def release_detection_lock() -> None:
    """Release the detection lock."""
    global _detection_lock_acquired_at
    _detection_lock_acquired_at = None
    try:
        _detection_lock.release()
    except RuntimeError:
        logger.warning("Detection lock was already released — possible double-release bug")


@contextmanager
def config_override(**overrides: Any) -> Generator[None, None, None]:
    """Temporarily override config attributes in a thread-safe manner.

    C6: This mutates a global singleton. Must ONLY be used while the
    detection lock is held to prevent concurrent mutations.
    """
    originals = {}
    for key, value in overrides.items():
        if hasattr(config, key):
            originals[key] = getattr(config, key)
            setattr(config, key, value)
    try:
        yield
    finally:
        for key, value in originals.items():
            setattr(config, key, value)
