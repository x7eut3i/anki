# ============================================================
# Anki Flashcard App — Multi-Stage Build (minimized image)
# Stage 1: Build Next.js frontend → static HTML/JS/CSS
# Stage 2: Build Python deps (gcc, dev headers for lxml/bcrypt)
# Stage 3: Lean runtime — only Python + runtime libs
# ============================================================

# --- Stage 1: Frontend build ---
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# --- Stage 2: Python dependency builder ---
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# --- Stage 3: Lean runtime ---
FROM python:3.11-slim

WORKDIR /app

# Only runtime libraries (no gcc, no -dev headers)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/app/ ./app/

# Copy frontend static export from stage 1
COPY --from=frontend /build/out ./static/

# Create persistent data directory for SQLite
RUN mkdir -p /data

# Default env vars (override via docker run -e or .env file)
ENV DATABASE_URL=sqlite:///data/anki.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
