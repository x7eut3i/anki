"""AI Job model for tracking async AI operations."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class AIJob(SQLModel, table=True):
    __tablename__ = "ai_jobs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # Job type: upload, create_card, add_article, auto_fetch, reanalyze, batch_enrich, smart_import, complete_cards, generate_cards
    job_type: str = Field(max_length=50)
    title: str = Field(default="", max_length=500)  # Human-readable description

    # Status: pending, running, completed, failed
    status: str = Field(default="pending", max_length=20)
    progress: int = Field(default=0)  # 0-100

    # Result
    result_json: str = Field(default="")  # JSON result on completion
    error_message: str = Field(default="", max_length=2000)

    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
