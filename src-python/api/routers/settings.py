"""Application settings, PII label configuration, and system hardware info."""

from __future__ import annotations

import logging
import os
import platform
import subprocess

from fastapi import APIRouter

from core.config import config
from api.deps import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["settings"])


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings():
    """Get current app settings."""
    return config.model_dump(mode="json")


@router.patch("/settings")
async def update_settings(updates: dict):
    """Update app settings (partial update)."""
    allowed = {
        "regex_enabled", "ner_enabled", "llm_detection_enabled",
        "confidence_threshold", "ocr_language", "ocr_dpi",
        "render_dpi", "tesseract_cmd",
        "ner_backend", "ner_model_preference",
        "llm_provider", "llm_api_url", "llm_api_key", "llm_api_model",
    }
    applied = {}
    for key, value in updates.items():
        if key not in allowed:
            continue
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
async def get_label_config():
    """Get PII label configuration."""
    store = get_store()
    entries = store.load_label_config()
    entries = _ensure_builtin_labels(entries)
    return entries


@router.put("/settings/labels")
async def save_label_config(labels: list[dict]):
    """Save PII label configuration."""
    store = get_store()
    store.save_label_config(labels)
    return {"status": "ok", "count": len(labels)}


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
async def get_hardware_info():
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
