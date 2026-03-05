# Anki Flashcard App

A spaced-repetition flashcard web app powered by the **FSRS-6** algorithm. Supports multiple card types, AI-assisted content generation, and cross-device study via PWA.

## Features

- **FSRS-6** spaced repetition — state-of-the-art scheduling for optimal retention
- **Multiple card types** — basic Q&A, multiple choice, fill-in-the-blank, cloze deletion, true/false
- **20 built-in categories** — pre-configured with sensible defaults (fully customizable)
- **Mix mode** — cross-category interleaved study sessions
- **Quiz mode** — timed, scored practice tests
- **AI-powered** — generate cards from text, explain wrong answers, AI tutor chat (OpenAI-compatible API)
- **Daily ingestion** — background job fetches content from RSS/web sources and generates cards
- **Import / Export** — CSV, JSON, and `.apkg` (Anki) format support
- **PWA** — installable, works on desktop and mobile browsers
- **SQLite** — zero-config database, good for up to 100K cards
- **Single container** — one Docker image serves both API and frontend

## Architecture

| Layer     | Tech                                      |
|-----------|-------------------------------------------|
| Frontend  | Next.js 14, Tailwind CSS, shadcn/ui, Zustand |
| Backend   | Python, FastAPI, SQLModel, SQLite, py-fsrs |
| Container | Single Docker image (multi-stage build)   |
| Proxy     | Your existing Nginx (config file included)|

## Quick Start

### Docker (recommended)

```bash
# Build the image
docker build -t anki-app .

# Run (data persisted in a named volume)
docker run -d \
  --name anki \
  -p 8000:8000 \
  -v anki-data:/data \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  anki-app

# Open http://localhost:8000
```

### Local Development

**Prerequisites**: Node.js 20+, Python 3.11+

#### Linux / macOS

```bash
chmod +x build.sh
./build.sh            # build + run
./build.sh build      # build only
./build.sh run        # run only (after build)
```

#### Windows

```bat
build.bat             REM build + run
build.bat build       REM build only
build.bat run         REM run only (after build)
```

#### Manual steps

```bash
# 1. Build frontend
cd frontend
npm ci && npm run build

# 2. Copy static files to backend
cp -r out ../backend/static   # Linux/macOS
# xcopy /E /I /Y out ..\backend\static   # Windows

# 3. Install backend
cd ../backend
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows
pip install -e ".[dev]"

# 4. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 to use the app.

## Nginx Reverse Proxy

If you already have an Nginx Docker container as a reverse proxy, copy `nginx-reverse-proxy.conf` into your Nginx config directory:

```bash
# Copy to your nginx conf.d
cp nginx-reverse-proxy.conf /path/to/nginx/conf.d/anki.conf

# Make sure both containers are on the same Docker network
docker network create web
docker run -d --name anki --network web -v anki-data:/data anki-app
# Reload your nginx
docker exec nginx nginx -s reload
```

Edit `anki.conf` to set your domain and container name.

## Project Structure

```
├── backend/              # FastAPI Python backend
│   ├── app/
│   │   ├── models/       # SQLModel database models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── routers/      # API route handlers
│   │   ├── services/     # Business logic (FSRS, AI, ingestion)
│   │   └── utils/        # Shared utilities
│   └── tests/            # pytest test suite (109 tests)
├── frontend/             # Next.js frontend (static export)
│   ├── src/app/          # Pages (dashboard, study, quiz, etc.)
│   ├── src/components/   # Reusable UI components
│   └── src/lib/          # API client, store, utilities
├── Dockerfile            # Single-container multi-stage build
├── nginx-reverse-proxy.conf  # Config for your existing Nginx
├── build.sh              # Build + run script (Linux/macOS)
└── build.bat             # Build + run script (Windows)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///data/flashcards.db` | SQLite database path |
| `SECRET_KEY` | `change-me...` | JWT signing key (set a random string!) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime (24 hours) |
| `AI_ENABLED` | `false` | Enable AI features |
| `AI_API_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API endpoint |
| `AI_API_KEY` | — | API key for AI provider |
| `AI_MODEL` | `gpt-4o-mini` | Model to use |
| `AI_MAX_DAILY_CALLS` | `50` | Rate limit for AI calls per day |
| `INGESTION_ENABLED` | `false` | Enable daily content ingestion |

See `backend/.env.example` for a full template.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest                  # 109 tests
pytest --cov=app        # with coverage
```

## License

MIT
