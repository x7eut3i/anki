"""Per-user FSRS scheduling progress for shared cards."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, UniqueConstraint


class UserCardProgress(SQLModel, table=True):
    __tablename__ = "user_card_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_user_card"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    card_id: int = Field(foreign_key="cards.id", index=True)

    # FSRS scheduling fields
    due: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )
    stability: float = Field(default=0.0)
    difficulty: float = Field(default=0.0)
    step: int = Field(default=0)
    reps: int = Field(default=0)
    lapses: int = Field(default=0)
    state: int = Field(default=0)  # CardState: 0=NEW, 1=LEARNING, 2=REVIEW, 3=RELEARNING
    last_review: datetime | None = Field(default=None)

    # Per-user card status
    is_suspended: bool = Field(default=False)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
