# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone Document Anonymizer executable.

Bundles the Python backend + React frontend into a single .exe.
Models (spaCy, BERT) are downloaded on first use — NOT bundled.

Run with:
  cd src-python
  pyinstaller --clean doc-anonymizer-standalone.spec

Output: dist/doc-anonymizer.exe
"""

import platform
import sys
from pathlib import Path

block_cipher = None

# Paths
FRONTEND_DIST = str(Path("..") / "frontend" / "dist")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle the built React frontend
        (FRONTEND_DIST, "frontend_dist"),
    ],
    hiddenimports=[
        # ── Our own modules (PyInstaller can't trace string imports) ──
        "api",
        "api.server",
        "core",
        "core.config",
        "core.ingestion",
        "core.ingestion.loader",
        "core.detection",
        "core.detection.pipeline",
        "core.detection.regex_detector",
        "core.detection.ner_detector",
        "core.detection.bert_detector",
        "core.detection.llm_detector",
        "core.anonymizer",
        "core.anonymizer.engine",
        "core.ocr",
        "core.ocr.engine",
        "core.llm",
        "core.llm.engine",
        "core.vault",
        "core.vault.store",
        "core.detokenize_file",
        "models",
        "models.schemas",
        # ── uvicorn ──
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # ── FastAPI / Starlette ──
        "starlette.responses",
        "starlette.routing",
        "starlette.middleware.cors",
        "multipart",
        "multipart.multipart",
        # ── spaCy ──
        "spacy",
        "spacy.lang.en",
        # ── Transformers (BERT NER) — models download on first use ──
        "transformers",
        "transformers.models.bert",
        "transformers.models.deberta_v2",
        "transformers.pipelines",
        "transformers.pipelines.token_classification",
        "torch",
        # ── Crypto ──
        "cryptography.fernet",
        # ── PDF ──
        "pypdfium2",
        "pypdfium2._helpers",
        # ── PIL / Pillow ──
        "PIL",
        # ── OCR ──
        "pytesseract",
        # ── async / other ──
        "aiofiles",
        "anyio._backends._asyncio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy/unnecessary packages
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "IPython",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="doc-anonymizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # Keep console for logs / first-run model downloads
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(Path("..") / "frontend" / "src-tauri" / "icons" / "icon.ico")
    if (Path("..") / "frontend" / "src-tauri" / "icons" / "icon.ico").exists()
    else None,
)
