"""Main entry point for promptShield.

When run directly (or as a standalone exe), starts a FastAPI server
and opens the browser UI.
"""

from __future__ import annotations

import logging
import socket
import sys
import webbrowser
import threading

import uvicorn

from core.config import config


def find_free_port() -> int:
    """Find an available TCP port.

    L8: To mitigate TOCTOU, we keep SO_REUSEADDR so the port can be
    immediately rebound by uvicorn.  The window is tiny and acceptable
    for a local-only desktop app.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _open_browser_delayed(url: str, delay: float = 1.5):
    """Open the browser after a short delay to let the server start."""
    import time
    time.sleep(delay)
    webbrowser.open(url)


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    # Find port
    port = config.port if config.port != 0 else find_free_port()
    config.port = port

    # Print port to stdout for Tauri to read (sidecar mode)
    print(f"PORT:{port}", flush=True)

    log = logging.getLogger("promptshield")
    log.info(f"Starting on {config.host}:{port}")

    # If running as standalone exe (frozen), open the browser automatically
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        url = f"http://{config.host}:{port}"
        log.info(f"Standalone mode — opening {url}")
        threading.Thread(target=_open_browser_delayed, args=(url,), daemon=True).start()

    if is_frozen:
        # When frozen by PyInstaller, string-based import doesn't work.
        # Import the app object directly and pass it to uvicorn.
        from api.server import app  # noqa: F811
        uvicorn.run(
            app,
            host=config.host,
            port=port,
            log_level="info",
            reload=False,
        )
    else:
        uvicorn.run(
            "api.server:app",
            host=config.host,
            port=port,
            log_level="info",
            reload=False,
        )


if __name__ == "__main__":
    main()
