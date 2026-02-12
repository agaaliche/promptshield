"""Global application configuration."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _default_data_dir() -> Path:
    """Return the platform-appropriate data directory."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif os.uname().sysname == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "doc-anonymizer"


class AppConfig(BaseModel):
    """Application-wide settings — loaded once at startup."""

    # Directories
    data_dir: Path = Field(default_factory=_default_data_dir)
    models_dir: Path = Field(default=None)          # type: ignore[assignment]
    temp_dir: Path = Field(default_factory=lambda: Path(tempfile.gettempdir()) / "doc-anonymizer")
    vault_path: Path = Field(default=None)           # type: ignore[assignment]

    # LLM — local
    llm_model_path: str = ""
    llm_context_size: int = 2048
    llm_gpu_layers: int = 0                           # 0 = CPU only (avoids NaN assertions with mixed GPU/CPU)
    llm_threads: int = 0                              # 0 = auto (use all physical cores)
    llm_batch_size: int = 2048                        # token batch size for llama.cpp
    llm_flash_attn: bool = True                       # use flash attention if supported

    # LLM — remote API (OpenAI-compatible)
    llm_provider: str = "local"                       # "local" | "remote"
    llm_api_url: str = ""                              # e.g. https://api.openai.com/v1
    llm_api_key: str = Field(                          # Bearer token — prefer DOC_ANON_LLM_API_KEY env var
        default_factory=lambda: os.environ.get("DOC_ANON_LLM_API_KEY", ""),
    )
    llm_api_model: str = ""                            # e.g. gpt-4o-mini, claude-sonnet-4-20250514

    # PII Detection thresholds
    regex_enabled: bool = True
    ner_enabled: bool = True
    llm_detection_enabled: bool = True
    regex_types: Optional[list[str]] = None   # None = all; e.g. ["EMAIL", "SSN"]
    ner_types: Optional[list[str]] = None     # None = all; e.g. ["PERSON", "ORG"]
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    detection_fuzziness: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description=(
            "Controls how aggressively neighbouring words are grouped into "
            "the same PII region. 0 = strict (only very close words merge), "
            "1 = permissive (wider gaps allowed). The actual pixel threshold "
            "scales with font size and is hard-capped at 20 PDF pts."
        ),
    )

    # Skip text whose rendered height >= this many PDF points.
    # Prevents redacting watermarks, headers, decorative text, etc.
    # 0 = disabled (redact everything regardless of size).
    max_font_size_pt: float = Field(
        default=28.0, ge=0.0,
        description=(
            "Maximum font size (in PDF points, approximated by bbox height) "
            "that the detection pipeline will consider as redactable text. "
            "Text rendered at or above this size — watermarks, large titles, "
            "decorative elements — will be excluded from auto-detection."
        ),
    )

    # NER backend: "auto" auto-selects the best model per detected language,
    # "spacy" uses spaCy models, or set to a HuggingFace model id
    # like "dslim/bert-base-NER" for BERT-based detection.
    ner_backend: str = "auto"

    # When ner_backend == "spacy": which spaCy model to prefer (trf > lg > sm)
    ner_model_preference: str = "trf"                   # trf > lg > sm

    # Convenience alias — when ner_backend is a HF model id this mirrors it.
    @property
    def ner_hf_model(self) -> str:
        if self.ner_backend in ("spacy", "auto"):
            return "dslim/bert-base-NER"
        return self.ner_backend

    # Auto-load the first available GGUF model at startup
    auto_load_llm: bool = True

    # OCR
    tesseract_cmd: str = ""                            # Empty = auto-detect
    ocr_language: str = "eng"
    ocr_dpi: int = Field(default=300, ge=72, le=1200)

    # Rendering
    render_dpi: int = Field(default=200, ge=72, le=1200)

    # Server
    host: str = "127.0.0.1"
    port: int = Field(default=8910, ge=0, le=65535)   # 0 = random

    # Token format — short tokens: [P38291] = letter prefix + 5 digits
    token_prefix: str = "ANON"
    token_format: str = "[{prefix}_{type}_{hex}]"

    def model_post_init(self, __context: object) -> None:
        if self.models_dir is None:
            self.models_dir = self.data_dir / "models"
        if self.vault_path is None:
            self.vault_path = self.data_dir / "vault.db"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Load any previously-saved user settings from disk
        self._load_user_settings()

    # ------------------------------------------------------------------
    # Persistence — user-editable settings are saved to a JSON sidecar
    # ------------------------------------------------------------------

    # Keys that are persisted when changed via the API
    _PERSISTABLE_KEYS: set[str] = {
        "regex_enabled", "ner_enabled", "llm_detection_enabled",
        "confidence_threshold", "detection_fuzziness", "max_font_size_pt",
        "ocr_language", "ocr_dpi",
        "render_dpi", "tesseract_cmd",
        "ner_backend", "ner_model_preference",
        "llm_model_path",
        "llm_provider", "llm_api_url", "llm_api_model",
        "llm_batch_size", "llm_flash_attn",
    }

    @property
    def _settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def _load_user_settings(self) -> None:
        """Read persisted user settings from disk and apply them."""
        path = self._settings_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for key, value in data.items():
                if key in self._PERSISTABLE_KEYS and hasattr(self, key):
                    setattr(self, key, value)
            logger.info(f"Loaded user settings from {path}")
        except Exception as exc:
            logger.warning(f"Failed to load settings from {path}: {exc}")

    def save_user_settings(self) -> None:
        """Persist current user-editable settings to disk."""
        data = {k: getattr(self, k) for k in self._PERSISTABLE_KEYS if hasattr(self, k)}
        try:
            self._settings_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(f"Saved user settings to {self._settings_path}")
        except Exception as exc:
            logger.warning(f"Failed to save settings: {exc}")


# Singleton — importable from anywhere
config = AppConfig()
