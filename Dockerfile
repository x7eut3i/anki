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
FROM python:3.12-slim
WORKDIR /app

# Install Python deps (all have pre-built wheels, no gcc needed)
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir . && rm -rf /root/.cache

# Copy application code
COPY backend/app/ ./app/
COPY backend/manage_users.py ./manage_users.py

# Copy frontend static export
COPY --from=frontend /build/out ./static/


EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
