"""Anki Flashcard App — FastAPI Backend."""

import json
import logging
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
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
    seed_ai_configs()
    seed_article_sources()

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
