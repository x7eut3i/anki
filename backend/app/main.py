"""Anki Flashcard App — FastAPI Backend."""

import json
import logging
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.auth import get_current_user
from app.database import create_db_and_tables, get_session
from app.models.category import Category, DEFAULT_CATEGORIES
from app.models.deck import Deck
from app.models.user import User
from app.models.ai_config import AIConfig
from app.models.article_analysis import ArticleAnalysis
from app.models.ingestion import IngestionConfig, IngestionLog
# Ensure all model tables are registered with SQLModel.metadata for create_all
from app.models.ai_interaction_log import AIInteractionLog  # noqa: F401
from app.models.tag import Tag, CardTag, ArticleTag  # noqa: F401
from app.models.ai_job import AIJob  # noqa: F401
from app.models.card import Card  # noqa: F401
from app.models.review_log import ReviewLog  # noqa: F401
from app.models.study_session import StudySession  # noqa: F401
from app.models.user_card_progress import UserCardProgress  # noqa: F401
from app.models.prompt_config import PromptConfig  # noqa: F401
from app.models.article_source import ArticleSource  # noqa: F401
from app.models.study_preset import StudyPreset  # noqa: F401
from app.routers import auth, cards, decks, categories, review, quiz, import_export, ai, article_analysis
from app.routers import sources as sources_router, prompts as prompts_router
from app.routers import ingestion as ingestion_router, users as users_router
from app.routers import logs as logs_router
from app.routers import stats as stats_router
from app.routers import tags as tags_router
from app.routers import ai_jobs as ai_jobs_router
from app.routers import study_presets as study_presets_router

# ── Logging Setup ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anki")

# Also log to file for the log viewer
_log_dir = Path(__file__).resolve().parent.parent / "data"
_log_dir.mkdir(parents=True, exist_ok=True)
_file_handler = logging.FileHandler(str(_log_dir / "app.log"), encoding="utf-8")
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)

# Suppress noisy third-party HTTP request logs
for _noisy_logger in ("uvicorn.access", "httpx", "httpcore"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

settings = get_settings()

# ── Auto-generate JWT secret key if not set ────────────────────────────
SECRET_KEY_FILE = Path(__file__).resolve().parent.parent / "data" / ".secret_key"

def _ensure_secret_key():
    """Generate a strong random secret key on first startup if none is configured."""
    if settings.secret_key:
        return  # Already set via .env or environment
    if SECRET_KEY_FILE.is_file():
        settings.secret_key = SECRET_KEY_FILE.read_text().strip()
        logger.info("🔑 Loaded secret key from %s", SECRET_KEY_FILE)
        return
    new_key = secrets.token_urlsafe(64)
    SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_FILE.write_text(new_key)
    settings.secret_key = new_key
    logger.info("🔑 Generated new secret key → %s", SECRET_KEY_FILE)


# ── Security Headers Middleware ────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # HSTS — only in production behind HTTPS
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# ── Simple Rate Limiter ────────────────────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter. Per-IP, sliding window."""

    def __init__(self, app, login_rpm: int = 10, api_rpm: int = 120):
        super().__init__(app)
        self.login_rpm = login_rpm
        self.api_rpm = api_rpm
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _check(self, key: str, limit: int) -> bool:
        now = time.time()
        window = [t for t in self._hits[key] if now - t < 60]
        self._hits[key] = window
        if len(window) >= limit:
            return False
        self._hits[key].append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        if path == "/api/auth/login" and request.method == "POST":
            if not self._check(f"login:{client_ip}", self.login_rpm):
                return JSONResponse(
                    {"detail": "登录尝试过于频繁，请稍后再试"},
                    status_code=429,
                )
        elif path.startswith("/api/"):
            if not self._check(f"api:{client_ip}", self.api_rpm):
                return JSONResponse(
                    {"detail": "请求过于频繁，请稍后再试"},
                    status_code=429,
                )

        return await call_next(request)

# Path to project-level AI configuration file
AI_CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "ai_config.json"


def _load_ai_config_file() -> dict | None:
    """Load AI configuration defaults from ai_config.json at project root."""
    if not AI_CONFIG_FILE.is_file():
        return None
    try:
        with open(AI_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Only return fields relevant to AIConfig model
        return {
            "api_base_url": data.get("api_base_url", ""),
            "api_key": data.get("api_key", ""),
            "model": data.get("model", ""),
            "max_daily_calls": data.get("max_daily_calls", 100),
        }
    except Exception as e:
        logger.warning("Failed to load ai_config.json: %s", e)
        return None


def seed_categories():
    """Seed default categories if they don't exist."""
    from sqlmodel import Session, select
    from app.database import engine

    try:
        with Session(engine) as session:
            existing = session.exec(select(Category)).first()
            if not existing:
                logger.info("No categories found, seeding %d default categories...", len(DEFAULT_CATEGORIES))
                for cat_data in DEFAULT_CATEGORIES:
                    cat = Category(**cat_data)
                    session.add(cat)
                session.commit()
                logger.info("✅ Default categories seeded successfully")
            else:
                logger.debug("Categories already exist, skipping seed")
    except Exception as e:
        logger.error("❌ Failed to seed categories: %s", e, exc_info=True)


def seed_default_decks():
    """Create one default deck per category if none exist yet."""
    from sqlmodel import Session, select
    from app.database import engine

    try:
        with Session(engine) as session:
            all_categories = session.exec(
                select(Category).order_by(Category.sort_order)
            ).all()
            if not all_categories:
                return

            # Only create decks that don't already exist (by name match)
            existing_names = set(
                r for r in session.exec(select(Deck.name)).all()
            )
            created = 0
            for cat in all_categories:
                deck_name = f"{cat.icon} {cat.name}"
                if deck_name in existing_names:
                    continue
                deck = Deck(
                    name=deck_name,
                    description=cat.description,
                    category_id=cat.id,
                    is_public=False,
                )
                session.add(deck)
                created += 1
            if created:
                session.commit()
                logger.info("✅ Created %d default decks (skipped %d existing)", created, len(all_categories) - created)
    except Exception as e:
        logger.error("❌ Failed to seed default decks: %s", e, exc_info=True)


def _backfill_ai_deck_categories():
    """Backfill category_id for AI-generated decks (AI-成语, AI-时政热点, etc.).

    Matches deck names like "AI-{category.name}" and sets the correct category_id.
    Runs on every startup so existing decks get fixed automatically.
    """
    from sqlmodel import Session, select
    from app.database import engine

    try:
        with Session(engine) as session:
            all_categories = session.exec(select(Category)).all()
            cat_by_name = {c.name: c for c in all_categories}

            ai_decks = session.exec(
                select(Deck).where(Deck.name.startswith("AI-"))  # type: ignore[union-attr]
            ).all()

            updated = 0
            for deck in ai_decks:
                if deck.category_id:
                    continue  # already has category
                # Extract category name from "AI-成语" → "成语"
                cat_name = deck.name[3:]  # strip "AI-" prefix
                cat = cat_by_name.get(cat_name)
                if cat:
                    deck.category_id = cat.id
                    session.add(deck)
                    updated += 1

            if updated:
                session.commit()
                logger.info("🔧 Backfilled category_id for %d AI decks", updated)
    except Exception as e:
        logger.warning("Failed to backfill AI deck categories: %s", e)


def seed_ai_configs():
    """Auto-configure AI for each user who has no AI config, using ai_config.json."""
    from sqlmodel import Session, select
    from app.database import engine

    defaults = _load_ai_config_file()
    if not defaults or not defaults.get("api_key"):
        logger.debug("No ai_config.json with API key found, skipping AI config seeding")
        return

    try:
        with Session(engine) as session:
            users = session.exec(select(User)).all()
            for user in users:
                existing = session.exec(
                    select(AIConfig).where(AIConfig.user_id == user.id)
                ).first()
                if existing:
                    # If config exists but is not enabled and has no key, update it
                    if not existing.api_key and defaults.get("api_key"):
                        existing.api_base_url = defaults["api_base_url"]
                        existing.api_key = defaults["api_key"]
                        existing.model = defaults["model"]
                        existing.max_daily_calls = defaults["max_daily_calls"]
                        existing.is_enabled = True
                        session.add(existing)
                        logger.info("🤖 Updated AI config for user '%s'", user.username)
                    continue

                config = AIConfig(
                    user_id=user.id,
                    api_base_url=defaults["api_base_url"],
                    api_key=defaults["api_key"],
                    model=defaults["model"],
                    max_daily_calls=defaults["max_daily_calls"],
                    is_enabled=True,
                )
                session.add(config)
                logger.info("🤖 Created AI config for user '%s'", user.username)
            session.commit()
    except Exception as e:
        logger.error("❌ Failed to seed AI configs: %s", e, exc_info=True)


def seed_article_sources():
    """Seed default article sources (人民日报 & 求是) if none exist."""
    from sqlmodel import Session, select
    from app.database import engine

    DEFAULT_SOURCES = [
        {
            "name": "人民日报",
            "url": "https://paper.people.com.cn/rmrb/",
            "source_type": "html",
            "category": "时政热点",
            "is_system": True,
            "is_enabled": True,
            "description": "人民日报电子版，权威时政新闻来源",
        },
        {
            "name": "求是",
            "url": "http://www.qstheory.cn/",
            "source_type": "html",
            "category": "政治理论",
            "is_system": True,
            "is_enabled": True,
            "description": "求是网，党的理论学习和政策解读",
        },
    ]

    try:
        with Session(engine) as session:
            existing = session.exec(select(ArticleSource)).first()
            if not existing:
                logger.info("No article sources found, seeding %d default sources...", len(DEFAULT_SOURCES))
                for src_data in DEFAULT_SOURCES:
                    src = ArticleSource(**src_data)
                    session.add(src)
                session.commit()
                logger.info("✅ Default article sources seeded successfully")
            else:
                logger.debug("Article sources already exist, skipping seed")
    except Exception as e:
        logger.error("❌ Failed to seed article sources: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Anki Flashcard API...")
    _ensure_secret_key()
    create_db_and_tables()
    logger.info("✅ Database tables ready")
    seed_categories()
    seed_default_decks()
    _backfill_ai_deck_categories()
    seed_ai_configs()
    seed_article_sources()

    # Mark any "running" ingestion logs as interrupted (server restarted)
    try:
        from sqlmodel import Session as _Session, select as _select
        from app.database import engine as _engine
        with _Session(_engine) as _sess:
            stale = _sess.exec(
                _select(IngestionLog).where(IngestionLog.status == "running")
            ).all()
            for sl in stale:
                sl.status = "error"
                sl.finished_at = sl.finished_at or datetime.now(timezone.utc)
                try:
                    entries = json.loads(sl.log_detail) if sl.log_detail else []
                except (json.JSONDecodeError, TypeError):
                    entries = []
                entries.append({
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "level": "error",
                    "source": "系统",
                    "message": "服务器重启，任务被中断",
                })
                sl.log_detail = json.dumps(entries, ensure_ascii=False)
                _sess.add(sl)
            if stale:
                _sess.commit()
                logger.info("🔧 Marked %d stale 'running' ingestion logs as interrupted", len(stale))
    except Exception as e:
        logger.warning("Failed to clean up stale ingestion logs: %s", e)

    # Mark any "running"/"pending" AI jobs as failed (server restarted)
    try:
        from app.models.ai_job import AIJob
        from sqlmodel import col as _col
        with _Session(_engine) as _sess:
            stale_jobs = _sess.exec(
                _select(AIJob).where(_col(AIJob.status).in_(["running", "pending"]))
            ).all()
            for sj in stale_jobs:
                sj.status = "failed"
                sj.error_message = "服务器重启，任务被中断"
                sj.completed_at = datetime.now(timezone.utc)
                _sess.add(sj)
            if stale_jobs:
                _sess.commit()
                logger.info("🔧 Marked %d stale AI jobs as failed (server restart)", len(stale_jobs))
    except Exception as e:
        logger.warning("Failed to clean up stale AI jobs: %s", e)

    # Clean up old logs based on retention setting
    try:
        from app.routers.logs import cleanup_old_logs
        result = cleanup_old_logs()
        if result.get("cleaned"):
            logger.info("🗑️ Log cleanup: %s", result.get("stats", {}))
    except Exception as e:
        logger.debug("Log cleanup skipped: %s", e)

    # Sync prompts — update non-customized prompts to latest code defaults
    from app.routers.prompts import sync_default_prompts
    sync_default_prompts()

    # Start APScheduler for scheduled ingestion
    from app.services.scheduler import setup_scheduler, shutdown_scheduler
    await setup_scheduler()

    # Memory diagnostics (opt-in via MEMORY_DIAG=1)
    from app.services import mem_diag
    mem_diag.init()

    logger.info("✅ Startup complete")
    yield
    # Shutdown
    logger.info("👋 Shutting down...")
    await shutdown_scheduler()


app = FastAPI(
    title="Anki Flashcard API",
    description="Spaced-repetition flashcard API with FSRS algorithm",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (for development; in production, Nginx handles same-origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, login_rpm=10, api_rpm=120)

# GZip compression — reduces JSON/HTML payload sizes significantly
app.add_middleware(GZipMiddleware, minimum_size=500)

# Register routers
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(decks.router)
app.include_router(categories.router)
app.include_router(review.router)
app.include_router(quiz.router)
app.include_router(import_export.router)
app.include_router(ai.router)
app.include_router(article_analysis.router)
app.include_router(sources_router.router)
app.include_router(prompts_router.router)
app.include_router(ingestion_router.router)
app.include_router(users_router.router)
app.include_router(logs_router.router)
app.include_router(stats_router.router)
app.include_router(tags_router.router)
app.include_router(ai_jobs_router.router)
app.include_router(study_presets_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/debug/memory")
def debug_memory(current_user: User = Depends(get_current_user)):
    """Memory diagnostics snapshot (requires MEMORY_DIAG=1 env var)."""
    from app.services import mem_diag
    return mem_diag.take_snapshot()


@app.get("/debug-memory")
def debug_memory_page():
    """Standalone HTML page that fetches /api/debug/memory with the stored JWT."""
    return Response(content=_DEBUG_MEMORY_HTML, media_type="text/html")


_DEBUG_MEMORY_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memory Diagnostics</title>
<style>
  body{font-family:monospace;margin:2em;background:#1a1a2e;color:#e0e0e0}
  h1{color:#e94560} pre{white-space:pre-wrap;word-break:break-all;background:#16213e;padding:1em;border-radius:6px;max-height:80vh;overflow-y:auto}
  .err{color:#e94560}
</style>
</head>
<body>
<h1>Memory Diagnostics</h1>
<pre id="o">Loading...</pre>
<script>
(async()=>{
  const o=document.getElementById('o');
  try{
    const raw=localStorage.getItem('anki-auth');
    if(!raw){o.innerHTML='<span class="err">Not logged in. Open the app and log in first.</span>';return}
    const token=JSON.parse(raw)?.state?.token;
    if(!token){o.innerHTML='<span class="err">No token in auth store.</span>';return}
    const r=await fetch('/api/debug/memory',{headers:{'Authorization':'Bearer '+token}});
    if(!r.ok){o.innerHTML='<span class="err">HTTP '+r.status+': '+(await r.text())+'</span>';return}
    o.textContent=JSON.stringify(await r.json(),null,2);
  }catch(e){o.innerHTML='<span class="err">'+e.message+'</span>'}
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Serve frontend static files (Next.js static export)
# Must be AFTER all API routers so /api/* routes take priority.
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if STATIC_DIR.is_dir():
    # Serve static assets from _next/
    app.mount("/_next", StaticFiles(directory=str(STATIC_DIR / "_next")), name="next-static")
    
    # Catch-all: serve .html files for all routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve Next.js static export with proper routing."""
        # Prevent path traversal
        resolved = (STATIC_DIR / full_path).resolve()
        if not str(resolved).startswith(str(STATIC_DIR.resolve())):
            return FileResponse(STATIC_DIR / "404.html", status_code=404, media_type="text/html")

        # Try exact .html file first
        html_file = STATIC_DIR / f"{full_path}.html"
        if html_file.is_file():
            return FileResponse(html_file, media_type="text/html")
        
        # Try index.html in directory
        index_file = STATIC_DIR / full_path / "index.html"
        if index_file.is_file():
            return FileResponse(index_file, media_type="text/html")
        
        # Try as static file (for manifest.json, etc.)
        static_file = STATIC_DIR / full_path
        if static_file.is_file():
            return FileResponse(static_file)
        
        # Fallback to index.html (for client-side routing)
        index_html = STATIC_DIR / "index.html"
        if index_html.is_file():
            return FileResponse(index_html, media_type="text/html")
        
        # Nothing found
        return FileResponse(STATIC_DIR / "404.html", status_code=404, media_type="text/html")
