#!/usr/bin/env bash
# ============================================================
# build.sh — Build and run Anki Flashcard App (Linux / macOS)
# Usage:
#   ./build.sh          Build frontend + backend, then start server
#   ./build.sh build    Build only (no server start)
#   ./build.sh run      Start server only (assumes already built)
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_DIR="$ROOT_DIR/backend"
STATIC_DIR="$BACKEND_DIR/static"

build_frontend() {
    echo "=== [1/3] Building frontend ==="
    cd "$FRONTEND_DIR"
    npm install --no-audit --no-fund
    npm run build
    echo "    Frontend built → frontend/out/"
}

copy_static() {
    echo "=== [2/3] Copying frontend → backend/static/ ==="
    rm -rf "$STATIC_DIR"
    cp -r "$FRONTEND_DIR/out" "$STATIC_DIR"
    echo "    Static files ready."
}

install_backend() {
    echo "=== [3/3] Installing backend dependencies ==="
    cd "$BACKEND_DIR"

    # Create venv if not exists
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate

    pip install -q -e ".[dev]"
    echo "    Backend dependencies installed."
}

start_server() {
    cd "$BACKEND_DIR"
    source .venv/bin/activate

    # Create data dir
    mkdir -p data

    HOST="${HOST:-0.0.0.0}"
    PORT="${PORT:-8000}"

    echo ""
    echo "=== Server starting at http://${HOST}:${PORT} ==="
    echo "    Press Ctrl+C to stop."
    echo ""
    python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
}

# ---- Main ----
case "${1:-all}" in
    build)
        build_frontend
        copy_static
        install_backend
        echo ""
        echo "✅ Build complete. Run './build.sh run' to start the server."
        ;;
    run)
        start_server
        ;;
    all|"")
        build_frontend
        copy_static
        install_backend
        start_server
        ;;
    *)
        echo "Usage: $0 [build|run|all]"
        exit 1
        ;;
esac
