"""Pydantic data models for the document anonymizer."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PIIType(str, enum.Enum):
    """Categories of personally identifiable information."""
    PERSON = "PERSON"
    ORG = "ORG"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    DATE = "DATE"
    ADDRESS = "ADDRESS"
    LOCATION = "LOCATION"
    IP_ADDRESS = "IP_ADDRESS"
    IBAN = "IBAN"
    PASSPORT = "PASSPORT"
    DRIVER_LICENSE = "DRIVER_LICENSE"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


class DetectionSource(str, enum.Enum):
    """Which detection layer produced the match."""
    REGEX = "REGEX"
    NER = "NER"
    LLM = "LLM"
    MANUAL = "MANUAL"


class RegionAction(str, enum.Enum):
    """What the user decided to do with a detected region."""
    PENDING = "PENDING"       # Awaiting user decision
    CANCEL = "CANCEL"         # Dismiss highlight, keep content
    REMOVE = "REMOVE"         # Permanently redact
    TOKENIZE = "TOKENIZE"     # Replace with reversible token


class DocumentStatus(str, enum.Enum):
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    DETECTING = "DETECTING"
    REVIEWING = "REVIEWING"
    ANONYMIZING = "ANONYMIZING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

class BBox(BaseModel):
    """Bounding box in page coordinates (points from top-left)."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

class TextBlock(BaseModel):
    """A block of text with its spatial position on the page."""
    text: str
    bbox: BBox
    confidence: float = 1.0          # 1.0 for native PDF text, <1 for OCR
    block_index: int = 0
    line_index: int = 0
    word_index: int = 0
    is_ocr: bool = False


class PageData(BaseModel):
    """Extracted data for a single document page."""
    page_number: int
    width: float                      # Page width in points
    height: float                     # Page height in points
    bitmap_path: str                  # Path to rendered bitmap file
    text_blocks: list[TextBlock] = []
    full_text: str = ""               # Concatenated text of all blocks


# ---------------------------------------------------------------------------
# PII Detection
# ---------------------------------------------------------------------------

class PIIRegion(BaseModel):
    """A detected PII region on a document page."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    page_number: int
    bbox: BBox
    text: str
    pii_type: PIIType
    confidence: float                  # 0.0 – 1.0
    source: DetectionSource
    char_start: int = 0
    char_end: int = 0
    action: RegionAction = RegionAction.PENDING


# ---------------------------------------------------------------------------
# Token / Vault
# ---------------------------------------------------------------------------

class TokenMapping(BaseModel):
    """Maps an anonymization token to its original content."""
    token_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    token_string: str                  # e.g. [ANON_PERSON_A3F2B1]
    original_text: str
    pii_type: PIIType
    source_document: str = ""
    context_snippet: str = ""          # Surrounding text for disambiguation
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class DocumentInfo(BaseModel):
    """Metadata for an uploaded document."""
    doc_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    original_filename: str
    file_path: str
    mime_type: str = ""
    page_count: int = 0
    status: DocumentStatus = DocumentStatus.UPLOADING
    pages: list[PageData] = []
    regions: list[PIIRegion] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# API Request / Response schemas
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    page_count: int
    status: DocumentStatus


class DetectionProgress(BaseModel):
    doc_id: str
    page_number: int
    total_pages: int
    layer: str                         # "REGEX", "NER", "LLM"
    regions_found: int


class RegionActionRequest(BaseModel):
    region_id: str
    action: RegionAction


class BatchActionRequest(BaseModel):
    region_ids: list[str]
    action: RegionAction


class RegionSyncItem(BaseModel):
    """Minimal region state sent from the frontend before anonymize."""
    id: str
    action: RegionAction
    bbox: BBox


class AnonymizeRequest(BaseModel):
    doc_id: str
    output_format: str = "pdf"         # "pdf" or "text" or "both"


class AnonymizeResponse(BaseModel):
    doc_id: str
    output_pdf_path: Optional[str] = None
    output_text_path: Optional[str] = None
    tokens_created: int = 0
    regions_removed: int = 0


class DetokenizeRequest(BaseModel):
    text: str


class DetokenizeResponse(BaseModel):
    original_text: str
    tokens_replaced: int
    unresolved_tokens: list[str] = []


class LLMStatusResponse(BaseModel):
    loaded: bool
    model_name: str = ""
    model_path: str = ""
    gpu_enabled: bool = False
    context_size: int = 0


class VaultStatsResponse(BaseModel):
    total_tokens: int
    total_documents: int
    vault_size_bytes: int
