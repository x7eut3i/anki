from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class Deck(SQLModel, table=True):
    __tablename__ = "decks"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=200)
    description: str = Field(default="", max_length=1000)
    category_id: int | None = Field(default=None, foreign_key="categories.id", index=True)
    is_public: bool = Field(default=False)
    card_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
