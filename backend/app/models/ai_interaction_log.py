"""AI interaction log model for tracking AI API calls in the database."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class AIInteractionLog(SQLModel, table=True):
    __tablename__ = "ai_interaction_logs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, index=True)
    feature: str = Field(index=True)  # article_analysis, card_generation, ingestion, etc.
    model: str = Field(default="")
    config_name: str = Field(default="")  # AI config name for grouping
    tokens_used: int = Field(default=0)
    elapsed_ms: int = Field(default=0)
    status: str = Field(default="ok")  # ok, error
    error_message: str = Field(default="")
    input_preview: str = Field(default="")  # First ~200 chars of user prompt
    output_length: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
