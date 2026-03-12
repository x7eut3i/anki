from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Index


class ReviewLog(SQLModel, table=True):
    __tablename__ = "review_logs"
    __table_args__ = (
        Index("ix_rl_user_reviewed", "user_id", "reviewed_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    rating: int = Field()  # 1=Again, 2=Hard, 3=Good, 4=Easy
    state: int = Field()  # Card state before review
    due: datetime = Field()  # Due date before review
    stability: float = Field()
    difficulty: float = Field()
    elapsed_days: int = Field()
    scheduled_days: int = Field()
    review_duration_ms: int = Field(default=0)  # Time spent on card

    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
