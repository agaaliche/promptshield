"""Global application configuration."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


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

    # LLM
    llm_model_path: str = ""
    llm_context_size: int = 4096
    llm_gpu_layers: int = -1                          # -1 = auto (all if GPU available)
    llm_threads: int = 0                              # 0 = auto (cpu_count)

    # PII Detection thresholds
    regex_enabled: bool = True
    ner_enabled: bool = True
    llm_detection_enabled: bool = True
    confidence_threshold: float = 0.3                  # Minimum confidence to show highlight

    # NER model preference: "trf" tries en_core_web_trf first, "lg" tries
    # en_core_web_lg, "sm" uses the small model.  Falls back automatically.
    ner_model_preference: str = "trf"                   # trf > lg > sm

    # Auto-load the first available GGUF model at startup
    auto_load_llm: bool = True

    # OCR
    tesseract_cmd: str = ""                            # Empty = auto-detect
    ocr_language: str = "eng"
    ocr_dpi: int = 300

    # Rendering
    render_dpi: int = 200

    # Server
    host: str = "127.0.0.1"
    port: int = 8910                                   # Default dev port; 0 = random

    # Token format
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


# Singleton — importable from anywhere
config = AppConfig()
