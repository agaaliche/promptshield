"""Document persistence store."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.schemas import DocumentInfo

logger = logging.getLogger(__name__)


class DocumentStore:
    """Manages persistent storage of documents and their state."""

    def __init__(self, storage_dir: Path):
        """Initialize the document store.
        
        Args:
            storage_dir: Base directory for storing documents
        """
        self.storage_dir = Path(storage_dir)
        self.docs_dir = self.storage_dir / "documents"
        self.files_dir = self.storage_dir / "files"
        self.bitmaps_dir = self.storage_dir / "bitmaps"
        
        # Create directories
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.bitmaps_dir.mkdir(parents=True, exist_ok=True)
        
        # Settings file for label config etc.
        self._labels_file = self.storage_dir / "pii_labels.json"
        
        logger.info(f"Document store initialized at {self.storage_dir}")

    def save_document(self, doc: DocumentInfo) -> None:
        """Save document state to disk.
        
        Args:
            doc: Document to save
        """
        try:
            doc_file = self.docs_dir / f"{doc.doc_id}.json"
            
            # Serialize document to JSON
            doc_data = doc.model_dump(mode="json")
            doc_data["saved_at"] = datetime.now(timezone.utc).isoformat()
            
            # Write to file
            with open(doc_file, "w", encoding="utf-8") as f:
                json.dump(doc_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved document {doc.doc_id} to {doc_file}")
            
        except Exception as e:
            logger.error(f"Failed to save document {doc.doc_id}: {e}")
            raise

    def load_document(self, doc_id: str) -> Optional[DocumentInfo]:
        """Load document state from disk.
        
        Args:
            doc_id: Document ID to load
            
        Returns:
            Document info or None if not found
        """
        try:
            doc_file = self.docs_dir / f"{doc_id}.json"
            
            if not doc_file.exists():
                return None
            
            with open(doc_file, "r", encoding="utf-8") as f:
                doc_data = json.load(f)
            
            # Remove saved_at field (not part of DocumentInfo schema)
            doc_data.pop("saved_at", None)
            
            doc = DocumentInfo.model_validate(doc_data)
            logger.info(f"Loaded document {doc_id} from {doc_file}")
            return doc
            
        except Exception as e:
            logger.error(f"Failed to load document {doc_id}: {e}")
            return None

    def list_documents(self) -> list[str]:
        """List all stored document IDs.
        
        Returns:
            List of document IDs
        """
        try:
            doc_files = list(self.docs_dir.glob("*.json"))
            doc_ids = [f.stem for f in doc_files]
            return sorted(doc_ids)
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document and all its associated files.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            doc_file = self.docs_dir / f"{doc_id}.json"
            
            # Delete document state file
            if doc_file.exists():
                doc_file.unlink()
            
            # Delete associated file (if it exists in our storage)
            file_pattern = f"{doc_id}_*"
            for file in self.files_dir.glob(file_pattern):
                file.unlink()
            
            # Delete associated bitmaps
            bitmap_dir = self.bitmaps_dir / doc_id
            if bitmap_dir.exists():
                shutil.rmtree(bitmap_dir)
            
            logger.info(f"Deleted document {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def store_uploaded_file(self, doc_id: str, source_path: Path, original_filename: str) -> Path:
        """Move an uploaded file to persistent storage.
        
        Args:
            doc_id: Document ID
            source_path: Path to the temporary uploaded file
            original_filename: Original name of the file
            
        Returns:
            Path to the stored file
        """
        try:
            # Use doc_id and original filename for storage
            stored_path = self.files_dir / f"{doc_id}_{original_filename}"
            
            # Copy file to storage (keep original in temp until processing is done)
            shutil.copy2(source_path, stored_path)
            
            logger.info(f"Stored file {original_filename} as {stored_path}")
            return stored_path
            
        except Exception as e:
            logger.error(f"Failed to store uploaded file: {e}")
            raise

    def get_stored_file_path(self, doc_id: str, original_filename: str) -> Optional[Path]:
        """Get the path to a stored file.
        
        Args:
            doc_id: Document ID
            original_filename: Original name of the file
            
        Returns:
            Path to stored file or None
        """
        stored_path = self.files_dir / f"{doc_id}_{original_filename}"
        return stored_path if stored_path.exists() else None

    def ensure_bitmap_dir(self, doc_id: str) -> Path:
        """Ensure bitmap directory exists for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Path to bitmap directory
        """
        bitmap_dir = self.bitmaps_dir / doc_id
        bitmap_dir.mkdir(parents=True, exist_ok=True)
        return bitmap_dir

    def get_bitmap_path(self, doc_id: str, page_number: int) -> Path:
        """Get the path for a page bitmap.
        
        Args:
            doc_id: Document ID
            page_number: Page number (1-based)
            
        Returns:
            Path to bitmap file
        """
        bitmap_dir = self.ensure_bitmap_dir(doc_id)
        return bitmap_dir / f"page_{page_number:04d}.png"

    def store_page_bitmaps(self, doc: DocumentInfo) -> None:
        """Copy page bitmaps from temp to persistent storage and update paths.
        
        Args:
            doc: Document whose page bitmaps to persist
        """
        for page in doc.pages:
            src = Path(page.bitmap_path)
            if not src.exists():
                logger.warning(f"Bitmap not found: {src}")
                continue
            dst = self.get_bitmap_path(doc.doc_id, page.page_number)
            if src != dst:
                shutil.copy2(src, dst)
                page.bitmap_path = str(dst)
                logger.debug(f"Stored bitmap page {page.page_number} -> {dst}")

    def load_all_documents(self) -> dict[str, DocumentInfo]:
        """Load all stored documents into memory.
        
        Returns:
            Dictionary mapping doc_id to DocumentInfo
        """
        documents = {}
        doc_ids = self.list_documents()
        
        for doc_id in doc_ids:
            doc = self.load_document(doc_id)
            if doc:
                documents[doc_id] = doc
        
        logger.info(f"Loaded {len(documents)} documents from storage")
        return documents

    # ── PII Label config persistence ──

    def load_label_config(self) -> list[dict]:
        """Load PII label config from disk.
        
        Returns:
            List of label entry dicts, or empty list if none saved.
        """
        try:
            if self._labels_file.exists():
                with open(self._labels_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.error(f"Failed to load label config: {e}")
        return []

    def save_label_config(self, labels: list[dict]) -> None:
        """Save PII label config to disk.
        
        Args:
            labels: List of label entry dicts.
        """
        try:
            with open(self._labels_file, "w", encoding="utf-8") as f:
                json.dump(labels, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(labels)} PII label entries")
        except Exception as e:
            logger.error(f"Failed to save label config: {e}")
