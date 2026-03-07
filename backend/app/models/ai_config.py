from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class AIConfig(SQLModel, table=True):
    __tablename__ = "ai_configs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(default="默认")
    is_active: bool = Field(default=True)
    api_base_url: str = Field(default="https://api.openai.com/v1")
    api_key: str = Field(default="")
    model: str = Field(default="gpt-4o-mini")  # Default model
    model_pipeline: str = Field(default="")  # Model for article pipeline card gen (empty = use default)
    model_reading: str = Field(default="")   # Model for deep reading analysis (empty = use default)
    fallback_model: str = Field(default="")  # Fallback model when primary model hits 429/errors
    fallback_cooldown: int = Field(default=600)  # Cooldown in seconds before retrying primary model (default 10min)
    rpm_limit: int = Field(default=0)  # Requests per minute limit (0 = unlimited)
    max_daily_calls: int = Field(default=50)
    import_batch_size: int = Field(default=30)
    import_concurrency: int = Field(default=3)  # Number of batches processed concurrently during AI import
    max_tokens: int = Field(default=8192)
    temperature: float = Field(default=0.3)
    max_retries: int = Field(default=3)  # AI call retry count
    is_enabled: bool = Field(default=False)

    # Feature toggles
    auto_explain_wrong: bool = Field(default=True)
    auto_generate_mnemonics: bool = Field(default=False)
    auto_generate_related: bool = Field(default=False)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIUsageLog(SQLModel, table=True):
    __tablename__ = "ai_usage_logs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    feature: str = Field()  # explain, mnemonic, generate, ingest, chat
    tokens_used: int = Field(default=0)
    cost_estimate: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
