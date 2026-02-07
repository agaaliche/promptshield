# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Document Anonymizer sidecar binary.

Run with:
  cd src-python
  pyinstaller --clean doc-anonymizer.spec

The output binary goes to dist/doc-anonymizer-sidecar[.exe]
which Tauri picks up via its externalBin configuration.
"""

import platform
import sys
from pathlib import Path

block_cipher = None

# Determine target triple for Tauri sidecar naming
_arch = platform.machine().lower()
if _arch in ("amd64", "x86_64"):
    arch = "x86_64"
elif _arch in ("aarch64", "arm64"):
    arch = "aarch64"
else:
    arch = _arch

if sys.platform == "win32":
    target_triple = f"{arch}-pc-windows-msvc"
    exe_ext = ".exe"
elif sys.platform == "darwin":
    target_triple = f"{arch}-apple-darwin"
    exe_ext = ""
else:
    target_triple = f"{arch}-unknown-linux-gnu"
    exe_ext = ""

sidecar_name = f"doc-anonymizer-sidecar-{target_triple}{exe_ext}"

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
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
        # FastAPI / Starlette
        "starlette.responses",
        "starlette.routing",
        "starlette.middleware.cors",
        "multipart",
        "multipart.multipart",
        # spaCy — include the installed model
        "spacy",
        "en_core_web_sm",
        # Crypto
        "cryptography.fernet",
        # PDF
        "pypdfium2",
        # PIL
        "PIL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "IPython",
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
    name=sidecar_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Sidecar needs console for stdout/stderr pipe
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
