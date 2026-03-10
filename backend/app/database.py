import logging
import os
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event, text
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = logging.getLogger("anki.db")

settings = get_settings()

# Resolve database path relative to the backend directory
_backend_dir = Path(__file__).resolve().parent.parent
_db_url = settings.database_url
if _db_url.startswith("sqlite:///") and not os.path.isabs(_db_url.replace("sqlite:///", "")):
    _rel_path = _db_url.replace("sqlite:///", "")
    _abs_path = str(_backend_dir / _rel_path)
    _db_url = f"sqlite:///{_abs_path}"

# Ensure data directory exists
db_path = _db_url.replace("sqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

engine = create_engine(
    _db_url,
    echo=False,
    connect_args={"check_same_thread": False},
    # NullPool: no connection pooling — each Session opens a fresh connection
    # and closes it on exit.  SQLite connections are just file-handles (~2 KB,
    # ~0.1 ms to open), so pooling is unnecessary and the default QueuePool
    # (size 5 + overflow 10 = 15 max) causes TimeoutError when background
    # tasks hold connections during long AI HTTP calls.
    poolclass=NullPool,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Configure every new SQLite connection for safe concurrency.

    WAL (Write-Ahead Logging):
      - Readers never block writers and writers never block readers.
      - Without WAL (default DELETE journal mode), a SELECT acquires a SHARED
        lock that prevents *any* writer from committing until the reader's
        transaction ends.  Background tasks (complete_cards, smart_import …)
        open a long-lived Session A for reading, then call update_job_status()
        which opens Session B and tries to COMMIT — blocked by Session A's
        SHARED lock → "database is locked" after 5 s.
      - WAL mode is persistent (survives restarts); setting it on every
        connection is harmless.

    busy_timeout 30 s:
      - Default is only 5 s.  Long AI HTTP calls (up to 120 s × 9 retries)
        mean a background task's session can legitimately hold a lock for a
        while.  30 s gives enough room for concurrent writers to wait.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def create_db_and_tables():
    logger.info("Creating database tables (URL: %s)", settings.database_url)
    SQLModel.metadata.create_all(engine)
    # Run lightweight migrations for new columns on existing tables
    _migrate_add_columns()


def _migrate_add_columns():
    """Add new columns to existing tables if they don't exist yet."""
    migrations = [
        ("users", "ai_import_batch_size", "INTEGER DEFAULT 30"),
        ("ai_configs", "model_pipeline", "TEXT DEFAULT ''"),
        ("ai_configs", "model_reading", "TEXT DEFAULT ''"),
        ("ai_configs", "name", "TEXT DEFAULT '默认'"),
        ("ai_configs", "is_active", "BOOLEAN DEFAULT 1"),
        ("ai_configs", "import_batch_size", "INTEGER DEFAULT 30"),
        ("ai_configs", "max_tokens", "INTEGER DEFAULT 8192"),
        ("ai_configs", "temperature", "REAL DEFAULT 0.3"),
        ("ingestion_configs", "cron_expression", "TEXT DEFAULT ''"),
        ("ai_configs", "fallback_model", "TEXT DEFAULT ''"),
        ("ai_configs", "fallback_cooldown", "INTEGER DEFAULT 600"),
        ("ai_configs", "rpm_limit", "INTEGER DEFAULT 0"),
        ("ingestion_configs", "schedule_type", "TEXT DEFAULT 'daily'"),
        ("ingestion_configs", "schedule_days", "TEXT DEFAULT ''"),
        ("ingestion_configs", "timezone", "TEXT DEFAULT 'Asia/Shanghai'"),
        ("ingestion_logs", "updated_at", "TIMESTAMP"),
        ("users", "timezone", "TEXT DEFAULT 'Asia/Shanghai'"),
        ("users", "study_question_mode", "TEXT DEFAULT 'custom'"),
        ("users", "study_custom_ratio", "INTEGER DEFAULT 60"),
        ("study_sessions", "question_mode", "TEXT DEFAULT 'custom'"),
        ("study_sessions", "custom_ratio", "INTEGER DEFAULT 60"),
        ("ai_interaction_logs", "source", "TEXT DEFAULT ''"),
        ("ai_interaction_logs", "raw_response", "TEXT DEFAULT ''"),
        ("study_sessions", "all_card_ids", "TEXT DEFAULT '[]'"),
        ("study_sessions", "quiz_questions", "TEXT DEFAULT '[]'"),
        ("study_sessions", "quiz_user_answers", "TEXT DEFAULT '{}'"),
        ("study_sessions", "current_question", "INTEGER DEFAULT 0"),
        ("study_sessions", "quiz_answer_map", "TEXT DEFAULT '{}'"),
        ("article_analyses", "last_read_at", "TIMESTAMP"),
        ("article_analyses", "error_state", "INTEGER DEFAULT 0"),
        ("ai_configs", "ai_timeout", "INTEGER DEFAULT 300"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger.info("Migration: added %s.%s", table, column)
            except Exception:
                # Column already exists — ignore
                conn.rollback()

        # Remove UNIQUE constraint on ai_configs.user_id (allow multiple configs per user)
        _migrate_remove_unique_user_id(conn)

        # Create article_sources table
        _migrate_create_article_sources(conn)

        # Add is_system column to article_sources
        try:
            conn.execute(text("ALTER TABLE article_sources ADD COLUMN is_system BOOLEAN DEFAULT 0"))
            conn.commit()
            logger.info("Migration: added article_sources.is_system")
        except Exception:
            conn.rollback()

        # Create prompt_configs table
        _migrate_create_prompt_configs(conn)

        # Create ingestion tables
        _migrate_create_ingestion_tables(conn)

        # Merge old 常识 sub-categories into 常识判断
        _migrate_merge_changshi_categories(conn)

        # Drop deprecated columns
        _migrate_drop_deprecated_columns(conn)


def _migrate_merge_changshi_categories(conn):
    """Merge 法律常识, 地理科技, 经济常识 into a single 常识判断 category."""
    old_names = ("法律常识", "地理科技", "经济常识")
    new_name = "常识判断"
    try:
        # Check if any old categories exist
        rows = conn.execute(
            text("SELECT id, name FROM categories WHERE name IN (:a, :b, :c)"),
            {"a": old_names[0], "b": old_names[1], "c": old_names[2]},
        ).fetchall()
        if not rows:
            return  # Nothing to migrate

        # Ensure 常识判断 category exists
        target = conn.execute(
            text("SELECT id FROM categories WHERE name = :n"), {"n": new_name}
        ).fetchone()
        if target:
            target_id = target[0]
        else:
            conn.execute(
                text(
                    "INSERT INTO categories (name, description, icon, sort_order) "
                    "VALUES (:n, :d, :i, :s)"
                ),
                {"n": new_name, "d": "法律、经济、地理、科技、生活常识", "i": "💡", "s": 5},
            )
            target_id = conn.execute(
                text("SELECT id FROM categories WHERE name = :n"), {"n": new_name}
            ).fetchone()[0]

        old_ids = [r[0] for r in rows]
        # Move cards from old categories to new one
        for oid in old_ids:
            conn.execute(
                text("UPDATE cards SET category_id = :new WHERE category_id = :old"),
                {"new": target_id, "old": oid},
            )
        # Deactivate old categories
        for oid in old_ids:
            conn.execute(
                text("UPDATE categories SET is_active = 0 WHERE id = :id"), {"id": oid}
            )
        conn.commit()
        logger.info(
            "Migration: merged categories %s -> %s (id=%d), moved cards",
            [r[1] for r in rows], new_name, target_id,
        )
    except Exception as e:
        conn.rollback()
        logger.debug("changshi category merge skipped: %s", e)


def _migrate_drop_deprecated_columns(conn):
    """Drop deprecated columns from cards table (SQLite 3.35+)."""
    drop_cols = [
        ("cards", "ai_review_status"),
        ("cards", "source_date"),
    ]
    for table, column in drop_cols:
        try:
            # Check if column exists first
            cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
            if column not in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            conn.commit()
            logger.info("Migration: dropped %s.%s", table, column)
        except Exception as e:
            conn.rollback()
            logger.debug("drop column %s.%s skipped: %s", table, column, e)


def _migrate_remove_unique_user_id(conn):
    """Remove UNIQUE constraint on ai_configs.user_id by recreating the table."""
    try:
        # Check if unique constraint exists
        rows = conn.execute(text("PRAGMA index_list(ai_configs)")).fetchall()
        has_unique = False
        for row in rows:
            idx_name = row[1]
            is_unique = row[2]
            if is_unique:
                cols = conn.execute(text(f"PRAGMA index_info(\"{idx_name}\")")).fetchall()
                for col in cols:
                    if col[2] == "user_id":
                        has_unique = True
                        break
            if has_unique:
                break

        if not has_unique:
            return

        logger.info("Migration: removing UNIQUE constraint on ai_configs.user_id")
        conn.execute(text("""
            CREATE TABLE ai_configs_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT DEFAULT '默认',
                is_active BOOLEAN DEFAULT 1,
                api_base_url TEXT DEFAULT 'https://api.openai.com/v1',
                api_key TEXT DEFAULT '',
                model TEXT DEFAULT 'gpt-4o-mini',
                model_pipeline TEXT DEFAULT '',
                model_reading TEXT DEFAULT '',
                max_daily_calls INTEGER DEFAULT 50,
                import_batch_size INTEGER DEFAULT 30,
                is_enabled BOOLEAN DEFAULT 0,
                auto_explain_wrong BOOLEAN DEFAULT 1,
                auto_generate_mnemonics BOOLEAN DEFAULT 0,
                auto_generate_related BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO ai_configs_new
                (id, user_id, name, is_active, api_base_url, api_key, model,
                 model_pipeline, model_reading, max_daily_calls, import_batch_size,
                 is_enabled, auto_explain_wrong, auto_generate_mnemonics,
                 auto_generate_related, updated_at)
            SELECT id, user_id,
                COALESCE(name, '默认'), COALESCE(is_active, 1),
                api_base_url, api_key, model,
                COALESCE(model_pipeline, ''), COALESCE(model_reading, ''),
                max_daily_calls, COALESCE(import_batch_size, 30),
                is_enabled, auto_explain_wrong, auto_generate_mnemonics,
                auto_generate_related, updated_at
            FROM ai_configs
        """))
        conn.execute(text("DROP TABLE ai_configs"))
        conn.execute(text("ALTER TABLE ai_configs_new RENAME TO ai_configs"))
        conn.execute(text("CREATE INDEX ix_ai_configs_user_id ON ai_configs(user_id)"))
        conn.commit()
        logger.info("Migration: removed UNIQUE constraint on ai_configs.user_id")
    except Exception as e:
        conn.rollback()
        logger.debug("ai_configs unique migration skipped: %s", e)


def _migrate_create_article_sources(conn):
    """Create article_sources table for source management."""
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS article_sources (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                source_type TEXT DEFAULT 'rss',
                category TEXT DEFAULT '时政热点',
                is_enabled BOOLEAN DEFAULT 1,
                description TEXT DEFAULT '',
                last_fetched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        logger.info("Migration: created article_sources table")
    except Exception as e:
        conn.rollback()
        logger.debug("article_sources migration skipped: %s", e)


def _migrate_create_prompt_configs(conn):
    """Create prompt_configs table for prompt management."""
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS prompt_configs (
                id INTEGER PRIMARY KEY,
                prompt_key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                content TEXT NOT NULL,
                model_override TEXT DEFAULT '',
                is_customized BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        logger.info("Migration: created prompt_configs table")
    except Exception as e:
        conn.rollback()
        logger.debug("prompt_configs migration skipped: %s", e)


def _migrate_create_ingestion_tables(conn):
    """Create ingestion_configs and ingestion_logs tables."""
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ingestion_configs (
                id INTEGER PRIMARY KEY,
                is_enabled BOOLEAN DEFAULT 0,
                schedule_hour INTEGER DEFAULT 6,
                schedule_minute INTEGER DEFAULT 0,
                max_articles_per_source INTEGER DEFAULT 5,
                quality_threshold INTEGER DEFAULT 7,
                auto_analyze BOOLEAN DEFAULT 1,
                auto_create_cards BOOLEAN DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ingestion_logs (
                id INTEGER PRIMARY KEY,
                run_type TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'running',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                sources_processed INTEGER DEFAULT 0,
                articles_fetched INTEGER DEFAULT 0,
                articles_analyzed INTEGER DEFAULT 0,
                articles_skipped INTEGER DEFAULT 0,
                cards_created INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                log_detail TEXT DEFAULT ''
            )
        """))
        conn.commit()
        logger.info("Migration: created ingestion tables")
    except Exception as e:
        conn.rollback()
        logger.debug("ingestion tables migration skipped: %s", e)


def get_session():
    with Session(engine) as session:
        yield session
