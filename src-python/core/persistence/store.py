"""Document persistence store."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.schemas import DocumentInfo

logger = logging.getLogger(__name__)

# Validation pattern for doc_id — alphanumeric only (hex from uuid4)
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9]+$")


def _validate_doc_id(doc_id: str) -> str:
    """Validate that doc_id is safe for use in filesystem paths.

    Raises ValueError if the doc_id contains path traversal characters
    or other unsafe patterns.
    """
    if not doc_id or not _SAFE_ID_RE.match(doc_id):
        raise ValueError(f"Invalid doc_id: must be alphanumeric, got {doc_id!r}")
    return doc_id


def _sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and special chars.

    Strips directory components, null bytes, and replaces unsafe characters.
    """
    # Strip directory components
    name = Path(filename).name
    # Remove null bytes
    name = name.replace("\x00", "")
    # Replace path-traversal and unsafe characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Ensure the result is not empty
    if not name or name in ('.', '..'):
        name = 'unnamed_document'
    return name


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
        self._patterns_file = self.storage_dir / "custom_patterns.json"
        
        logger.info(f"Document store initialized at {self.storage_dir}")

    def save_document(self, doc: DocumentInfo) -> None:
        """Save document state to disk (atomic write via tmp + rename).

        Args:
            doc: Document to save
        """
        try:
            _validate_doc_id(doc.doc_id)
            doc_file = self.docs_dir / f"{doc.doc_id}.json"

            # Serialize document to JSON
            doc_data = doc.model_dump(mode="json")
            doc_data["saved_at"] = datetime.now(timezone.utc).isoformat()

            # Atomic write: write to temp file then rename
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.docs_dir), suffix=".tmp", prefix=f"{doc.doc_id}_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(doc_data, f, indent=2, ensure_ascii=False)
                # Atomic rename (on Windows this replaces the target)
                os.replace(tmp_path, str(doc_file))
            except BaseException:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

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

        Raises:
            ValueError: If doc_id is invalid or data is corrupted.
        """
        _validate_doc_id(doc_id)
        doc_file = self.docs_dir / f"{doc_id}.json"

        if not doc_file.exists():
            return None

        try:
            with open(doc_file, "r", encoding="utf-8") as f:
                doc_data = json.load(f)

            # Remove saved_at field (not part of DocumentInfo schema)
            doc_data.pop("saved_at", None)

            doc = DocumentInfo.model_validate(doc_data)
            logger.info(f"Loaded document {doc_id} from {doc_file}")
            return doc

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted JSON for document {doc_id}: {e}")
            raise ValueError(f"Corrupted document data for {doc_id}") from e
        except Exception as e:
            logger.error(f"Failed to load document {doc_id}: {e}")
            raise ValueError(f"Failed to load document {doc_id}: {e}") from e

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
            _validate_doc_id(doc_id)
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
            _validate_doc_id(doc_id)
            safe_name = _sanitize_filename(original_filename)
            stored_path = self.files_dir / f"{doc_id}_{safe_name}"
            
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
        _validate_doc_id(doc_id)
        safe_name = _sanitize_filename(original_filename)
        stored_path = self.files_dir / f"{doc_id}_{safe_name}"
        return stored_path if stored_path.exists() else None

    def ensure_bitmap_dir(self, doc_id: str) -> Path:
        """Ensure bitmap directory exists for a document.

        Args:
            doc_id: Document ID

        Returns:
            Path to bitmap directory
        """
        _validate_doc_id(doc_id)
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
            try:
                doc = self.load_document(doc_id)
                if doc:
                    documents[doc_id] = doc
            except (ValueError, Exception) as e:
                logger.warning(f"Skipping corrupted document {doc_id}: {e}")
        
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

    # ── Custom pattern persistence ──

    def load_custom_patterns(self) -> list[dict]:
        """Load custom regex patterns from disk.
        
        Returns:
            List of pattern dicts, each containing:
            - id: Unique pattern identifier
            - name: Human-readable name
            - pattern: Regex string (or None if using template mode)
            - template: Template definition (or None if using regex mode)
            - pii_type: Target PIIType label
            - enabled: Whether pattern is active
            - case_sensitive: Whether regex should be case-sensitive
            - confidence: Default confidence score (0.0-1.0)
        """
        try:
            if self._patterns_file.exists():
                with open(self._patterns_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.error(f"Failed to load custom patterns: {e}")
        return []

    def save_custom_patterns(self, patterns: list[dict]) -> None:
        """Save custom regex patterns to disk.
        
        Args:
            patterns: List of pattern dicts.
        """
        try:
            with open(self._patterns_file, "w", encoding="utf-8") as f:
                json.dump(patterns, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(patterns)} custom patterns")
        except Exception as e:
            logger.error(f"Failed to save custom patterns: {e}")
