from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class StudyPreset(SQLModel, table=True):
    __tablename__ = "study_presets"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    icon: str = Field(default="📋", max_length=10)
    # JSON array of category IDs, e.g. [1, 4, 5]
    category_ids: str = Field(default="[]")
    # JSON array of deck IDs (for AI-* decks), e.g. [3, 7]
    deck_ids: str = Field(default="[]")
    card_count: int = Field(default=20)  # default question count
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
