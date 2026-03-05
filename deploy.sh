#!/usr/bin/env bash
# ============================================================
# deploy.sh — Build, push and deploy Anki Flashcard App
#
# Usage:
#   ./deploy.sh                 Build & run locally via docker compose
#   ./deploy.sh build           Build image only
#   ./deploy.sh push            Build & push to registry
#   ./deploy.sh remote          Deploy to a remote server via SSH
#
# Environment variables:
#   IMAGE_NAME    Docker image name  (default: anki-app)
#   IMAGE_TAG     Docker image tag   (default: latest)
#   REGISTRY      Registry prefix    (default: none)
#   REMOTE_HOST   SSH host for remote deploy
#   REMOTE_DIR    Remote directory   (default: ~/anki)
# ============================================================
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-anki-app}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-}"
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_DIR="${REMOTE_DIR:-~/anki}"

FULL_IMAGE="${REGISTRY:+${REGISTRY}/}${IMAGE_NAME}:${IMAGE_TAG}"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# ---- Helpers ----
info()  { echo -e "\033[1;34m==>\033[0m $*"; }
ok()    { echo -e "\033[1;32m ✔\033[0m  $*"; }
err()   { echo -e "\033[1;31m ✘\033[0m  $*" >&2; }

# ---- Pre-flight checks ----
preflight() {
    if [ ! -f "ai_config.json" ]; then
        err "ai_config.json not found. Copy ai_config.json.example and fill in your API key."
        exit 1
    fi
    if ! command -v docker &>/dev/null; then
        err "docker not found. Please install Docker first."
        exit 1
    fi
}

# ---- Build ----
build_image() {
    info "Building Docker image: ${FULL_IMAGE}"
    docker build -t "${FULL_IMAGE}" .
    ok "Image built: ${FULL_IMAGE}"
}

# ---- Run locally ----
run_local() {
    preflight
    info "Starting services via docker compose..."
    docker compose up -d --build
    ok "App running at http://localhost:${PORT:-8000}"
    echo ""
    echo "  Useful commands:"
    echo "    docker compose logs -f        Follow logs"
    echo "    docker compose down            Stop"
    echo "    docker compose up -d --build   Rebuild & restart"
}

# ---- Push to registry ----
push_image() {
    build_image
    if [ -z "$REGISTRY" ]; then
        err "Set REGISTRY env var to push. Example: REGISTRY=ghcr.io/myuser ./deploy.sh push"
        exit 1
    fi
    info "Pushing ${FULL_IMAGE}..."
    docker push "${FULL_IMAGE}"
    ok "Pushed: ${FULL_IMAGE}"
}

# ---- Remote deploy via SSH ----
remote_deploy() {
    if [ -z "$REMOTE_HOST" ]; then
        err "Set REMOTE_HOST env var. Example: REMOTE_HOST=user@server ./deploy.sh remote"
        exit 1
    fi

    info "Deploying to ${REMOTE_HOST}:${REMOTE_DIR}"

    # Copy required files to remote
    ssh "$REMOTE_HOST" "mkdir -p ${REMOTE_DIR}"
    scp docker-compose.yml Dockerfile "$REMOTE_HOST:${REMOTE_DIR}/"
    scp -r backend/pyproject.toml "$REMOTE_HOST:${REMOTE_DIR}/backend/"
    scp ai_config.json "$REMOTE_HOST:${REMOTE_DIR}/ai_config.json"

    # Sync source code (exclude large dirs)
    rsync -az --delete \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='*.db' \
        --exclude='.next' \
        --exclude='out' \
        --exclude='data/' \
        ./ "$REMOTE_HOST:${REMOTE_DIR}/"

    # Build & start on remote
    ssh "$REMOTE_HOST" "cd ${REMOTE_DIR} && docker compose up -d --build"
    ok "Deployed to ${REMOTE_HOST}"
}

# ---- Main ----
case "${1:-}" in
    build)
        build_image
        ;;
    push)
        push_image
        ;;
    remote)
        preflight
        remote_deploy
        ;;
    *)
        run_local
        ;;
esac
