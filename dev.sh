#!/usr/bin/env bash
# dev.sh — Start both backend and frontend for development.
# Usage:  ./dev.sh            (starts both)
#         ./dev.sh backend    (backend only)
#         ./dev.sh frontend   (frontend only)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/src-python/.venv/bin/python"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_DIR="$ROOT/src-python"

MODE="${1:-both}"
PIDS=()

cleanup() {
    echo ""
    echo "[*] Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo "[*] Done."
}
trap cleanup EXIT INT TERM

# --- Backend ---
if [[ "$MODE" == "both" || "$MODE" == "backend" ]]; then
    if [[ ! -f "$PYTHON" ]]; then
        echo "[!] Python venv not found. Run setup first:"
        echo "    cd src-python && python3 -m venv .venv && .venv/bin/pip install -e .[dev]"
        exit 1
    fi
    echo "[*] Starting Python backend on port 8910..."
    (cd "$BACKEND_DIR" && "$PYTHON" -u main.py) &
    PIDS+=($!)
fi

# --- Frontend ---
if [[ "$MODE" == "both" || "$MODE" == "frontend" ]]; then
    echo "[*] Starting Vite dev server..."
    (cd "$FRONTEND_DIR" && npx vite --host) &
    PIDS+=($!)
fi

echo ""
echo "=== Development servers running ==="
[[ "$MODE" == "both" || "$MODE" == "backend" ]]  && echo "  Backend  → http://127.0.0.1:8910"
[[ "$MODE" == "both" || "$MODE" == "frontend" ]] && echo "  Frontend → http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all."

wait
