from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=50)
    email: str = Field(index=True, unique=True, max_length=255)
    hashed_password: str
    is_active: bool = Field(default=True)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Study preferences
    daily_new_card_limit: int = Field(default=20)
    daily_review_limit: int = Field(default=200)
    session_card_limit: int = Field(default=50)
    desired_retention: float = Field(default=0.9)

    # AI import preferences
    ai_import_batch_size: int = Field(default=30)

    # Display preferences
    timezone: str = Field(default="Asia/Shanghai")
