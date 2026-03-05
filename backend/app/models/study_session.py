from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class StudySession(SQLModel, table=True):
    __tablename__ = "study_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    mode: str = Field(default="review")  # review, mix, quiz
    category_ids: str = Field(default="")  # Comma-separated category IDs for mix mode
    deck_id: int | None = Field(default=None, foreign_key="decks.id")

    total_cards: int = Field(default=0)
    cards_reviewed: int = Field(default=0)
    cards_correct: int = Field(default=0)
    cards_again: int = Field(default=0)

    # Quiz mode fields
    quiz_score: int = Field(default=0)
    quiz_time_limit: int = Field(default=0)  # seconds, 0 = no limit

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = Field(default=None)
    is_completed: bool = Field(default=False)

    # Remaining card IDs (JSON array) for session recovery
    remaining_card_ids: str = Field(default="[]")

    # Dynamic question answer map: JSON {"question_id": "correct_answer", ...}
    quiz_answer_map: str = Field(default="{}")
