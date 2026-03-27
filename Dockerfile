# ============================================================
# Anki Flashcard App — Two-Stage Build
# Stage 1: Build Next.js frontend → static HTML/JS/CSS
# Stage 2: Python runtime + app code + static frontend
# ============================================================

# --- Stage 1: Frontend build ---
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# --- Stage 2: Runtime ---
FROM python:3.14.3-slim
WORKDIR /app

# jemalloc: dramatically reduces memory fragmentation in long-running Python
# processes (lxml, cryptography, SQLAlchemy all fragment glibc malloc badly).
RUN apt-get update && apt-get install -y --no-install-recommends libjemalloc2 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf $(find /usr/lib -name "libjemalloc.so.2" | head -1) /usr/lib/libjemalloc.so.2

# Install Python deps (all have pre-built wheels, no gcc needed)
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir . && rm -rf /root/.cache

# Copy application code
COPY backend/app/ ./app/
COPY backend/manage_users.py ./manage_users.py

# Copy frontend static export
COPY --from=frontend /build/out ./static/


EXPOSE 8000

# Use jemalloc as the system allocator — replaces glibc malloc.
# Reduces RSS by 30-50% for Python apps with heavy C extensions.
ENV LD_PRELOAD=/usr/lib/libjemalloc.so.2
# Keep MALLOC_ARENA_MAX as a fallback hint (jemalloc respects it too).
ENV MALLOC_ARENA_MAX=2

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
