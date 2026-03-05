"""Article source model for source management."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class ArticleSource(SQLModel, table=True):
    __tablename__ = "article_sources"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    url: str = Field(max_length=2000)
    source_type: str = Field(default="html")  # rss, html
    category: str = Field(default="时政热点")
    is_enabled: bool = Field(default=True)
    is_system: bool = Field(default=False)  # True = special rule (人民日报/求是), cannot be deleted
    description: str = Field(default="")
    last_fetched_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
