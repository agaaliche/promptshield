"""Document Repository pattern for cleaner data access.

This module provides a DocumentRepository class that encapsulates
all document storage operations, providing a cleaner interface
than direct dictionary manipulation.

Benefits:
- Single point of access for document CRUD operations
- Easier to add caching, pagination, or database backends later
- Better testability through dependency injection
- Cleaner separation of concerns
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterator, Optional

from models.schemas import DocumentInfo, PIIRegion, RegionAction

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository for managing DocumentInfo instances.
    
    Provides CRUD operations and queries on the document collection.
    Currently uses an in-memory dict, but could be backed by a database.
    """

    def __init__(self, documents: dict[str, DocumentInfo]):
        """Initialize with a documents dictionary.
        
        Args:
            documents: The backing dictionary for document storage.
                       Pass the shared `documents` dict from deps.py.
        """
        self._documents = documents

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def get(self, doc_id: str) -> Optional[DocumentInfo]:
        """Get a document by ID, or None if not found."""
        return self._documents.get(doc_id)

    def get_or_raise(self, doc_id: str) -> DocumentInfo:
        """Get a document by ID, raising KeyError if not found."""
        doc = self._documents.get(doc_id)
        if doc is None:
            raise KeyError(f"Document '{doc_id}' not found")
        return doc

    def exists(self, doc_id: str) -> bool:
        """Check if a document exists."""
        return doc_id in self._documents

    def add(self, doc: DocumentInfo) -> None:
        """Add a new document to the repository."""
        self._documents[doc.doc_id] = doc

    def remove(self, doc_id: str) -> Optional[DocumentInfo]:
        """Remove and return a document, or None if not found."""
        return self._documents.pop(doc_id, None)

    def update(self, doc: DocumentInfo) -> None:
        """Update an existing document (same as add, but semantic)."""
        self._documents[doc.doc_id] = doc

    # -------------------------------------------------------------------------
    # Query Operations
    # -------------------------------------------------------------------------

    def all(self) -> list[DocumentInfo]:
        """Return all documents as a list."""
        return list(self._documents.values())

    def count(self) -> int:
        """Return the total number of documents."""
        return len(self._documents)

    def iter_all(self) -> Iterator[DocumentInfo]:
        """Iterate over all documents."""
        return iter(self._documents.values())

    def sorted_by_date(self, descending: bool = True) -> list[DocumentInfo]:
        """Return documents sorted by created_at."""
        return sorted(
            self._documents.values(),
            key=lambda d: d.created_at,
            reverse=descending,
        )

    def paginate(
        self,
        page: int = 1,
        limit: int = 50,
        sort_descending: bool = True,
    ) -> tuple[list[DocumentInfo], int]:
        """Return a paginated list of documents.
        
        Args:
            page: Page number (1-indexed)
            limit: Items per page
            sort_descending: Sort by created_at descending (newest first)
            
        Returns:
            Tuple of (documents_for_page, total_count)
        """
        all_docs = self.sorted_by_date(descending=sort_descending)
        total = len(all_docs)
        start = (page - 1) * limit
        end = start + limit
        return all_docs[start:end], total

    def filter_by_status(self, status: str) -> list[DocumentInfo]:
        """Return documents with a specific status."""
        return [d for d in self._documents.values() if d.status.value == status]

    def filter_protected(self) -> list[DocumentInfo]:
        """Return documents that have been protected (tokenized/removed regions)."""
        protected = []
        for doc in self._documents.values():
            if len(doc.regions) == 0:
                continue
            has_pending = any(r.action == RegionAction.PENDING for r in doc.regions)
            has_protected = any(
                r.action in (RegionAction.TOKENIZE, RegionAction.REMOVE) 
                for r in doc.regions
            )
            if not has_pending and has_protected:
                protected.append(doc)
        return protected

    # -------------------------------------------------------------------------
    # Region Operations (convenience methods)
    # -------------------------------------------------------------------------

    def get_regions(
        self, 
        doc_id: str, 
        page_number: Optional[int] = None,
    ) -> list[PIIRegion]:
        """Get regions for a document, optionally filtered by page."""
        doc = self.get(doc_id)
        if doc is None:
            return []
        regions = doc.regions
        if page_number is not None:
            regions = [r for r in regions if r.page_number == page_number]
        return regions

    def update_region_action(
        self,
        doc_id: str,
        region_id: str,
        action: RegionAction,
    ) -> bool:
        """Update the action for a specific region.
        
        Returns True if the region was found and updated.
        """
        doc = self.get(doc_id)
        if doc is None:
            return False
        for region in doc.regions:
            if region.id == region_id:
                region.action = action
                return True
        return False

    def clear_regions(self, doc_id: str) -> int:
        """Clear all regions from a document.
        
        Returns the count of regions that were cleared.
        """
        doc = self.get(doc_id)
        if doc is None:
            return 0
        count = len(doc.regions)
        doc.regions = []
        return count
