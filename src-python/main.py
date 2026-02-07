"""Main entry point for the document anonymizer sidecar.

When run directly, starts a FastAPI server on a random available port
and prints the port to stdout (for the Tauri shell to read).
"""

from __future__ import annotations

import logging
import socket
import sys

import uvicorn

from core.config import config


def find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

    # Print port to stdout for Tauri to read
    # This MUST be the first line of stdout
    print(f"PORT:{port}", flush=True)

    logging.getLogger("doc-anonymizer").info(
        f"Starting sidecar on {config.host}:{port}"
    )

    uvicorn.run(
        "api.server:app",
        host=config.host,
        port=port,
        log_level="info",
        # Don't use reload in production/sidecar mode
        reload=False,
    )


if __name__ == "__main__":
    main()
