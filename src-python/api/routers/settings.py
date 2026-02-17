"""Application settings, PII label configuration, and system hardware info."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import config
from api.deps import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["settings"])


# ---------------------------------------------------------------------------
# Settings update schema — typed validation instead of raw dict
# ---------------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    """Validated partial settings update."""
    regex_enabled: Optional[bool] = None
    custom_patterns_enabled: Optional[bool] = None
    ner_enabled: Optional[bool] = None
    llm_detection_enabled: Optional[bool] = None
    confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    detection_fuzziness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ocr_language: Optional[str] = None
    ocr_dpi: Optional[int] = Field(default=None, ge=72, le=1200)
    render_dpi: Optional[int] = Field(default=None, ge=72, le=1200)
    tesseract_cmd: Optional[str] = None
    ner_backend: Optional[str] = None
    ner_model_preference: Optional[str] = None
    detection_language: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_api_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_api_model: Optional[str] = None


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    """Get current app settings (masks sensitive fields, excludes internal paths)."""
    data = config.model_dump(mode="json")
    # Never expose the full API key over the wire
    if data.get("llm_api_key"):
        data["llm_api_key"] = "••••••••"
    # M12: Don't expose internal file-system paths to the frontend
    _sensitive_path_keys = {"data_dir", "temp_dir", "models_dir", "app_data_dir"}
    for key in _sensitive_path_keys:
        data.pop(key, None)
    return data


@router.patch("/settings")
async def update_settings(body: SettingsUpdate) -> dict[str, Any]:
    """Update app settings (partial update with Pydantic validation)."""
    from api.deps import acquire_config_lock, release_config_lock

    updates = body.model_dump(exclude_none=True)
    applied = {}

    # H2: Acquire config lock; if busy, reject with 409 instead of ignoring
    lock_held = acquire_config_lock("settings-update")
    if not lock_held:
        raise HTTPException(
            status_code=409,
            detail="Detection is in progress. Please try again after it finishes.",
        )
    try:
        for key, value in updates.items():
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

        if applied:
            config.save_user_settings()
    finally:
        if lock_held:
            release_config_lock()

    return {"status": "ok", "applied": applied}


# ---------------------------------------------------------------------------
# PII Label configuration
# ---------------------------------------------------------------------------

_DEFAULT_FREQUENT = {"PERSON", "ORG", "EMAIL", "PHONE", "DATE", "ADDRESS"}
_BUILTIN_LABELS = [
    "PERSON", "ORG", "EMAIL", "PHONE", "SSN",
    "CREDIT_CARD", "DATE", "ADDRESS", "LOCATION",
    "IP_ADDRESS", "IBAN", "PASSPORT", "DRIVER_LICENSE",
    "CUSTOM", "UNKNOWN",
]
_BUILTIN_COLORS = {
    "PERSON": "#e91e63", "ORG": "#ff5722", "EMAIL": "#2196f3",
    "PHONE": "#00bcd4", "SSN": "#f44336", "CREDIT_CARD": "#ff9800",
    "DATE": "#8bc34a", "ADDRESS": "#795548", "LOCATION": "#607d8b",
    "IP_ADDRESS": "#9e9e9e", "IBAN": "#ff5722", "PASSPORT": "#673ab7",
    "DRIVER_LICENSE": "#3f51b5", "CUSTOM": "#9c27b0", "UNKNOWN": "#757575",
}


def _ensure_builtin_labels(entries: list[dict]) -> list[dict]:
    """Ensure all built-in labels exist in the list."""
    existing = {e["label"] for e in entries}
    for t in _BUILTIN_LABELS:
        if t not in existing:
            entries.append({
                "label": t,
                "frequent": t in _DEFAULT_FREQUENT,
                "hidden": False,
                "user_added": False,
                "color": _BUILTIN_COLORS.get(t, "#888"),
            })
    return entries


@router.get("/settings/labels")
async def get_label_config() -> list[dict[str, Any]]:
    """Get PII label configuration."""
    store = get_store()
    entries = store.load_label_config()
    entries = _ensure_builtin_labels(entries)
    return entries


@router.put("/settings/labels")
async def save_label_config(labels: list[dict]) -> dict[str, Any]:
    """Save PII label configuration.

    Validates that each entry has the required keys.
    """
    _REQUIRED_KEYS = {"label"}
    _ALLOWED_KEYS = {"label", "frequent", "hidden", "user_added", "color"}
    validated: list[dict] = []
    for entry in labels:
        if not isinstance(entry, dict) or not _REQUIRED_KEYS.issubset(entry.keys()):
            raise HTTPException(400, f"Each label entry must contain at least: {_REQUIRED_KEYS}")
        # Only keep allowed keys to prevent injection of arbitrary data
        clean = {k: v for k, v in entry.items() if k in _ALLOWED_KEYS}
        validated.append(clean)
    store = get_store()
    store.save_label_config(validated)
    return {"status": "ok", "count": len(validated)}


# ---------------------------------------------------------------------------
# Custom regex patterns
# ---------------------------------------------------------------------------

class CustomPatternCreate(BaseModel):
    """Schema for creating/updating a custom pattern."""
    name: str = Field(..., min_length=1, max_length=100)
    pattern: Optional[str] = Field(default=None, max_length=2000)
    template: Optional[list[dict]] = None  # [{type: "letters"|"digits"|"separator", count?: int, value?: str}]
    pii_type: str = Field(default="CUSTOM", max_length=50)
    enabled: bool = True
    case_sensitive: bool = False
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class PatternTestRequest(BaseModel):
    """Schema for testing a pattern against sample text."""
    pattern: str = Field(..., min_length=1, max_length=2000)
    test_text: str = Field(..., max_length=10000)
    case_sensitive: bool = False


def _template_to_regex(template: list[dict]) -> str:
    """Convert a template definition to a regex pattern.
    
    Template blocks:
    - {type: "letters", count: 3} → [A-Za-z]{3}
    - {type: "LETTERS", count: 3} → [A-Z]{3}  (uppercase only)
    - {type: "digits", count: 5} → \\d{5}
    - {type: "alphanumeric", count: 4} → [A-Za-z0-9]{4}
    - {type: "separator", value: "-"} → \\-
    - {type: "any", count: 2} → .{2}
    """
    import re as re_mod
    parts = []
    for block in template:
        btype = block.get("type", "")
        count = block.get("count", 1)
        value = block.get("value", "")
        
        if btype == "letters":
            parts.append(f"[A-Za-z]{{{count}}}")
        elif btype == "LETTERS":
            parts.append(f"[A-Z]{{{count}}}")
        elif btype == "digits":
            parts.append(f"\\d{{{count}}}")
        elif btype == "alphanumeric":
            parts.append(f"[A-Za-z0-9]{{{count}}}")
        elif btype == "separator":
            parts.append(re_mod.escape(value))
        elif btype == "any":
            parts.append(f".{{{count}}}")
        elif btype == "literal":
            parts.append(re_mod.escape(value))
    
    return "".join(parts)


@router.get("/settings/patterns")
async def get_custom_patterns() -> list[dict[str, Any]]:
    """Get all custom regex patterns."""
    store = get_store()
    return store.load_custom_patterns()


@router.put("/settings/patterns")
async def save_custom_patterns(patterns: list[dict]) -> dict[str, Any]:
    """Replace all custom patterns.
    
    Validates each pattern entry has required fields and valid regex.
    """
    import re as re_mod
    import uuid
    
    _REQUIRED_KEYS = {"name"}
    _ALLOWED_KEYS = {"id", "name", "pattern", "template", "pii_type", "enabled", "case_sensitive", "confidence"}
    validated: list[dict] = []
    
    for entry in patterns:
        if not isinstance(entry, dict) or not _REQUIRED_KEYS.issubset(entry.keys()):
            raise HTTPException(400, f"Each pattern must have at least: {_REQUIRED_KEYS}")
        
        # Only keep allowed keys
        clean = {k: v for k, v in entry.items() if k in _ALLOWED_KEYS}
        
        # Ensure ID exists
        if "id" not in clean:
            clean["id"] = str(uuid.uuid4())[:8]
        
        # Validate regex if provided
        pattern_str = clean.get("pattern")
        template = clean.get("template")
        
        if pattern_str:
            try:
                re_mod.compile(pattern_str)
            except re_mod.error as e:
                raise HTTPException(400, f"Invalid regex in pattern '{clean['name']}': {e}")
        elif template:
            # Convert template to regex and validate
            try:
                generated = _template_to_regex(template)
                re_mod.compile(generated)
                clean["_generated_pattern"] = generated
            except Exception as e:
                raise HTTPException(400, f"Invalid template in pattern '{clean['name']}': {e}")
        else:
            raise HTTPException(400, f"Pattern '{clean['name']}' must have either 'pattern' or 'template'")
        
        # Set defaults
        clean.setdefault("pii_type", "CUSTOM")
        clean.setdefault("enabled", True)
        clean.setdefault("case_sensitive", False)
        clean.setdefault("confidence", 0.85)
        
        validated.append(clean)
    
    store = get_store()
    store.save_custom_patterns(validated)
    
    # Notify regex detector to reload patterns
    try:
        from core.detection.regex_detector import reload_custom_patterns
        reload_custom_patterns()
    except Exception:
        pass  # Non-fatal
    
    return {"status": "ok", "count": len(validated)}


@router.post("/settings/patterns")
async def add_custom_pattern(body: CustomPatternCreate) -> dict[str, Any]:
    """Add a new custom pattern."""
    import re as re_mod
    import uuid
    
    store = get_store()
    patterns = store.load_custom_patterns()
    
    # Build the new pattern entry
    new_pattern: dict[str, Any] = {
        "id": str(uuid.uuid4())[:8],
        "name": body.name,
        "pii_type": body.pii_type,
        "enabled": body.enabled,
        "case_sensitive": body.case_sensitive,
        "confidence": body.confidence,
    }
    
    if body.pattern:
        try:
            re_mod.compile(body.pattern)
        except re_mod.error as e:
            raise HTTPException(400, f"Invalid regex: {e}")
        new_pattern["pattern"] = body.pattern
    elif body.template:
        try:
            generated = _template_to_regex(body.template)
            re_mod.compile(generated)
            new_pattern["template"] = body.template
            new_pattern["_generated_pattern"] = generated
        except Exception as e:
            raise HTTPException(400, f"Invalid template: {e}")
    else:
        raise HTTPException(400, "Must provide either 'pattern' or 'template'")
    
    patterns.append(new_pattern)
    store.save_custom_patterns(patterns)
    
    # Notify regex detector to reload
    try:
        from core.detection.regex_detector import reload_custom_patterns
        reload_custom_patterns()
    except Exception:
        pass
    
    return {"status": "ok", "pattern": new_pattern}


@router.delete("/settings/patterns/{pattern_id}")
async def delete_custom_pattern(pattern_id: str) -> dict[str, Any]:
    """Delete a custom pattern by ID."""
    store = get_store()
    patterns = store.load_custom_patterns()
    
    original_count = len(patterns)
    patterns = [p for p in patterns if p.get("id") != pattern_id]
    
    if len(patterns) == original_count:
        raise HTTPException(404, f"Pattern '{pattern_id}' not found")
    
    store.save_custom_patterns(patterns)
    
    # Notify regex detector to reload
    try:
        from core.detection.regex_detector import reload_custom_patterns
        reload_custom_patterns()
    except Exception:
        pass
    
    return {"status": "ok", "deleted": pattern_id}


@router.post("/settings/patterns/test")
async def test_pattern(body: PatternTestRequest) -> dict[str, Any]:
    """Test a regex pattern against sample text.
    
    Returns all matches found in the text.
    """
    import re as re_mod
    
    try:
        flags = 0 if body.case_sensitive else re_mod.IGNORECASE
        compiled = re_mod.compile(body.pattern, flags)
    except re_mod.error as e:
        raise HTTPException(400, f"Invalid regex: {e}")
    
    matches = []
    for m in compiled.finditer(body.test_text):
        matches.append({
            "text": m.group(),
            "start": m.start(),
            "end": m.end(),
        })
    
    return {
        "status": "ok",
        "pattern": body.pattern,
        "match_count": len(matches),
        "matches": matches,
    }


# ---------------------------------------------------------------------------
# System hardware info
# ---------------------------------------------------------------------------

def _get_gpu_info() -> list[dict]:
    """Detect NVIDIA GPUs via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpus.append({
                    "name": parts[0],
                    "vram_total_mb": int(float(parts[1])),
                    "vram_free_mb": int(float(parts[2])),
                    "driver_version": parts[3],
                })
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []


@router.get("/system/hardware")
async def get_hardware_info() -> dict[str, Any]:
    """Return system hardware summary: CPU, RAM, GPU(s)."""
    import psutil

    cpu_name = platform.processor() or "Unknown"
    cpu_count_logical = os.cpu_count() or 0
    cpu_count_physical = psutil.cpu_count(logical=False) or 0

    mem = psutil.virtual_memory()
    ram_total_gb = round(mem.total / (1024 ** 3), 1)
    ram_available_gb = round(mem.available / (1024 ** 3), 1)

    gpus = _get_gpu_info()

    return {
        "cpu": {
            "name": cpu_name,
            "cores_physical": cpu_count_physical,
            "cores_logical": cpu_count_logical,
        },
        "ram": {
            "total_gb": ram_total_gb,
            "available_gb": ram_available_gb,
        },
        "gpus": gpus,
    }
