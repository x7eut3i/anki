import enum
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class CardState(int, enum.Enum):
    NEW = 0
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: int | None = Field(default=None, primary_key=True)
    deck_id: int = Field(foreign_key="decks.id", index=True)
    category_id: int | None = Field(default=None, foreign_key="categories.id", index=True)

    # Card content — simplified two-type design:
    #   - Q&A:    front + back (distractors empty)
    #   - Choice: front + back + distractors (3 wrong answers)
    # Type is determined dynamically by presence of distractors.
    front: str = Field(max_length=5000)       # Question / prompt
    back: str = Field(max_length=5000)        # THE answer (always the correct answer text)
    explanation: str = Field(default="", max_length=5000)  # Detailed explanation
    distractors: str = Field(default="")      # JSON array of wrong answers, e.g. ["X","Y","Z"]. Empty = Q&A card.
    tags: str = Field(default="")             # Comma-separated tags
    meta_info: str = Field(default="")        # JSON: knowledge, alternate_questions, exam_focus, etc.
    source: str = Field(default="")           # Source URL or reference
    expires_at: datetime | None = Field(default=None)  # Auto-retire date for 时政热点

    # Metadata
    is_ai_generated: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
