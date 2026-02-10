"""Shared state, helpers, and re-exports used by all API routers."""

from __future__ import annotations

import logging
import time as _time
from typing import Optional

from fastapi import HTTPException

from core.config import config
from core.persistence import DocumentStore
from models.schemas import DocumentInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton state  (mutated by server.startup, read everywhere)
# ---------------------------------------------------------------------------
documents: dict[str, DocumentInfo] = {}
store: Optional[DocumentStore] = None

# In-memory detection progress tracker  (doc_id → progress dict)
detection_progress: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def get_store() -> DocumentStore:
    """Return the document store; raise if not initialised."""
    if store is None:
        raise RuntimeError("Document store not initialized")
    return store


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
    except Exception as e:
        logger.error(f"Failed to auto-save document {doc.doc_id}: {e}")


def now_ts() -> float:
    """Monotonic-ish wall-clock timestamp (``time.time()``)."""
    return _time.time()


def get_active_llm_engine():
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
