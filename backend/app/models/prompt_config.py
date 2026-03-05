"""Prompt configuration model for prompt management."""

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class PromptConfig(SQLModel, table=True):
    __tablename__ = "prompt_configs"

    id: int | None = Field(default=None, primary_key=True)
    prompt_key: str = Field(unique=True, max_length=100)  # e.g. "card_system", "article_analysis", etc.
    display_name: str = Field(max_length=200)
    description: str = Field(default="")
    content: str = Field(default="")
    model_override: str = Field(default="")  # Optional model override for this specific prompt
    is_customized: bool = Field(default=False)  # True if user has edited the default prompt
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
