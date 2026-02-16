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

# In-memory upload/ingestion progress tracker (doc_id → progress dict)
# Tracks file loading, page extraction, and OCR progress
upload_progress: dict[str, dict] = {}

# In-memory export progress tracker (export_id → progress dict)
export_progress: dict[str, dict] = {}

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


def cleanup_stale_upload_progress() -> None:
    """Remove completed/errored upload_progress entries older than TTL."""
    now = _time.time()
    stale = [
        k for k, v in upload_progress.items()
        if v.get("status") in ("complete", "error")
        and now - v.get("_started_at", now) > _PROGRESS_TTL
    ]
    for k in stale:
        upload_progress.pop(k, None)


def cleanup_stale_export_progress() -> None:
    """Remove completed/errored export_progress entries older than TTL."""
    now = _time.time()
    stale = [
        k for k, v in export_progress.items()
        if v.get("status") in ("complete", "error")
        and now - v.get("_started_at", now) > _PROGRESS_TTL
    ]
    for k in stale:
        export_progress.pop(k, None)

# Detection lock — per-document to allow parallel detection of different docs.
# A separate config lock prevents concurrent config mutations (redetect, settings).
_doc_locks: dict[str, threading.Lock] = {}
_doc_lock_times: dict[str, float] = {}
_doc_locks_guard = threading.Lock()  # protects _doc_locks dict itself
_config_lock = threading.Lock()
_config_lock_acquired_at: float | None = None
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


@contextmanager
def mutate_doc(doc: DocumentInfo) -> Generator[DocumentInfo, None, None]:
    """Context manager for document mutations — auto-saves on exit.

    Usage::

        with mutate_doc(doc) as d:
            d.regions.append(new_region)
        # doc is auto-persisted here

    If the block raises, the document is still saved to avoid data loss
    from partial mutations.
    """
    try:
        yield doc
    finally:
        save_doc(doc)


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
    """Try to acquire the per-document detection lock (non-blocking).

    Returns True if acquired.  Different documents can detect in parallel;
    only the *same* document is serialised.

    If a previous lock for this doc has been held longer than
    ``_DETECTION_LOCK_TIMEOUT_S``, it is considered stale and forcibly
    released before re-acquiring.
    """
    with _doc_locks_guard:
        if doc_id not in _doc_locks:
            _doc_locks[doc_id] = threading.Lock()
        lock = _doc_locks[doc_id]

    acquired = lock.acquire(blocking=False)
    if acquired:
        _doc_lock_times[doc_id] = _time.time()
        return True

    # Check for stale lock
    acq_time = _doc_lock_times.get(doc_id)
    if acq_time is not None:
        held_for = _time.time() - acq_time
        if held_for > _DETECTION_LOCK_TIMEOUT_S:
            logger.warning(
                "Detection lock for doc %s held for %.0fs (>%.0fs) — forcing release (stale)",
                doc_id, held_for, _DETECTION_LOCK_TIMEOUT_S,
            )
            try:
                lock.release()
            except RuntimeError:
                pass
            acquired = lock.acquire(blocking=False)
            if acquired:
                _doc_lock_times[doc_id] = _time.time()
                return True

    logger.warning("Detection already running for doc %s — rejecting", doc_id)
    return False


def release_detection_lock(doc_id: str) -> None:
    """Release the per-document detection lock."""
    _doc_lock_times.pop(doc_id, None)
    with _doc_locks_guard:
        lock = _doc_locks.get(doc_id)
    if lock is None:
        return
    try:
        lock.release()
    except RuntimeError:
        logger.warning("Detection lock for doc %s was already released", doc_id)


def prune_doc_locks() -> None:
    """Remove lock entries for documents that no longer exist in memory.

    Should be called periodically (e.g. after document deletion) to prevent
    unbounded growth of ``_doc_locks`` / ``_doc_lock_times``.
    """
    with _doc_locks_guard:
        stale = [k for k in _doc_locks if k not in documents]
        for k in stale:
            _doc_locks.pop(k, None)
            _doc_lock_times.pop(k, None)
        if stale:
            logger.debug("Pruned %d stale detection lock(s)", len(stale))


def acquire_config_lock(doc_id: str) -> bool:
    """Acquire the global config lock (for redetect / settings that mutate config).

    Only one config-mutating operation can run at a time.
    """
    global _config_lock_acquired_at
    acquired = _config_lock.acquire(blocking=False)
    if acquired:
        _config_lock_acquired_at = _time.time()
        return True

    # Check for stale config lock
    if _config_lock_acquired_at is not None:
        held_for = _time.time() - _config_lock_acquired_at
        if held_for > _DETECTION_LOCK_TIMEOUT_S:
            logger.warning(
                "Config lock held for %.0fs (>%.0fs) — forcing release",
                held_for, _DETECTION_LOCK_TIMEOUT_S,
            )
            try:
                _config_lock.release()
            except RuntimeError:
                pass
            acquired = _config_lock.acquire(blocking=False)
            if acquired:
                _config_lock_acquired_at = _time.time()
                return True

    logger.warning("Config lock busy — rejecting request for %s", doc_id)
    return False


def release_config_lock() -> None:
    """Release the global config lock."""
    global _config_lock_acquired_at
    _config_lock_acquired_at = None
    try:
        _config_lock.release()
    except RuntimeError:
        logger.warning("Config lock was already released")


@contextmanager
def config_override(**overrides: Any) -> Generator[None, None, None]:
    """Temporarily override config attributes in a thread-safe manner.

    C6: This mutates a global singleton. Must ONLY be used while the
    config lock is held to prevent concurrent mutations.
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
