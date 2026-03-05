"""Tag models for custom tagging of cards and articles."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    color: str = Field(default="#3b82f6", max_length=20)  # Hex color
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CardTag(SQLModel, table=True):
    __tablename__ = "card_tags"

    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    tag_id: int = Field(foreign_key="tags.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArticleTag(SQLModel, table=True):
    __tablename__ = "article_tags"

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="article_analyses.id", index=True)
    tag_id: int = Field(foreign_key="tags.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
