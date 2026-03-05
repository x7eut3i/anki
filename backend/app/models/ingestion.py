"""Models for ingestion configuration and logs."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class IngestionConfig(SQLModel, table=True):
    __tablename__ = "ingestion_configs"

    id: int | None = Field(default=None, primary_key=True)
    is_enabled: bool = Field(default=False)
    schedule_hour: int = Field(default=6)         # Hour to run (0-23)
    schedule_minute: int = Field(default=0)       # Minute to run (0-59)
    schedule_type: str = Field(default="daily")   # daily, weekly, custom
    schedule_days: str = Field(default="")        # Comma-separated days for weekly: 1=Mon,...,7=Sun
    cron_expression: str = Field(default="")      # Optional cron expression (overrides hour/minute if set)
    timezone: str = Field(default="Asia/Shanghai")  # IANA timezone for schedule
    quality_threshold: float = Field(default=7.0)  # Min quality score to create cards (1-10, decimals OK)
    auto_analyze: bool = Field(default=True)      # Auto deep-reading analysis for high-quality articles
    auto_create_cards: bool = Field(default=True) # Auto create flashcards from articles
    concurrency: int = Field(default=3)             # Number of articles processed concurrently
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionLog(SQLModel, table=True):
    __tablename__ = "ingestion_logs"

    id: int | None = Field(default=None, primary_key=True)
    run_type: str = Field(default="manual")  # manual, scheduled
    status: str = Field(default="running")   # running, success, error, cancelled
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = Field(default=None)
    sources_processed: int = Field(default=0)
    articles_fetched: int = Field(default=0)
    articles_analyzed: int = Field(default=0)
    articles_skipped: int = Field(default=0)
    cards_created: int = Field(default=0)
    errors_count: int = Field(default=0)
    log_detail: str = Field(default="")  # JSON-formatted detailed log


class IngestionUrlCache(SQLModel, table=True):
    """Cache of analyzed article URLs with quality scores.

    Stores URLs of articles that were analyzed by AI but rejected due to
    low quality. On subsequent runs, if the cached score is still below
    the current threshold the article is skipped without calling AI.
    If the threshold has been lowered and the cached score now qualifies,
    the article is re-analyzed.
    """
    __tablename__ = "ingestion_url_cache"

    id: int | None = Field(default=None, primary_key=True)
    url: str = Field(index=True)
    quality_score: float = Field(default=0.0)
    title: str = Field(default="")
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
