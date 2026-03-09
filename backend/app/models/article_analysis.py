"""Article analysis model for deep reading feature."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


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

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = Field(default=None)
    last_read_at: datetime | None = Field(default=None)  # last time user opened this article
