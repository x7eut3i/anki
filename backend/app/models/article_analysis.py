"""Article analysis model for deep reading feature."""

from datetime import datetime, timezone
from enum import IntFlag
from sqlmodel import SQLModel, Field


class ArticleErrorState(IntFlag):
    """Bit flags for article processing error states.

    Each bit represents a failed processing stage. Multiple bits can be set.
    0 = no errors (all stages succeeded or not yet attempted).
    """
    NONE = 0
    CLEANUP_FAILED = 1       # bit 0: content_cleanup failed
    ANALYSIS_FAILED = 2      # bit 1: AI article analysis failed
    CARD_GEN_FAILED = 4      # bit 2: card generation failed


class ArticleAnalysis(SQLModel, table=True):
    __tablename__ = "article_analyses"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # Article source
    title: str = Field(max_length=500)
    source_url: str = Field(default="", max_length=2000)
    source_name: str = Field(default="", max_length=100)  # e.g. 人民日报评论
    publish_date: str = Field(default="", max_length=20)  # YYYY-MM-DD

    # Original content
    content: str = Field(default="")  # Full article text

    # AI analysis result — stored as rich HTML
    analysis_html: str = Field(default="")  # Rich HTML with highlights, annotations
    analysis_json: str = Field(default="")  # Structured JSON for programmatic access

    # Quality & metadata
    quality_score: float = Field(default=0.0)  # 0-10, AI-assessed quality (0=ads/spam, decimals OK)
    quality_reason: str = Field(default="")  # Why this score
    word_count: int = Field(default=0)

    # Reading status
    status: str = Field(default="new")  # new, reading, finished, archived
    is_starred: bool = Field(default=False)

    # Error state — bit flags (0 = no errors)
    error_state: int = Field(default=0)  # ArticleErrorState flags

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = Field(default=None)
    last_read_at: datetime | None = Field(default=None)  # last time user opened this article
