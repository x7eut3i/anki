from datetime import datetime
from pydantic import BaseModel, Field


class AIConfigUpdate(BaseModel):
    name: str | None = None
    api_base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    model_pipeline: str | None = None
    model_reading: str | None = None
    max_daily_calls: int | None = None
    import_batch_size: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    max_retries: int | None = None
    ai_timeout: int | None = None
    fallback_model: str | None = None
    fallback_cooldown: int | None = None
    rpm_limit: int | None = None
    is_enabled: bool | None = None
    auto_explain_wrong: bool | None = None
    auto_generate_mnemonics: bool | None = None
    auto_generate_related: bool | None = None


class AIConfigResponse(BaseModel):
    id: int
    name: str = "默认"
    api_base_url: str
    api_key_set: bool  # Don't expose actual key
    model: str
    model_pipeline: str = ""
    model_reading: str = ""
    fallback_model: str = ""
    fallback_cooldown: int = 600
    rpm_limit: int = 0
    max_daily_calls: int
    import_batch_size: int = 30
    max_tokens: int = 8192
    temperature: float = 0.3
    max_retries: int = 3
    ai_timeout: int = 300
    is_enabled: bool
    is_active: bool = True
    auto_explain_wrong: bool
    auto_generate_mnemonics: bool
    auto_generate_related: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class AIConfigCreate(BaseModel):
    name: str = "新配置"
    api_base_url: str = ""
    api_key: str = ""
    model: str = ""
    model_pipeline: str = ""
    model_reading: str = ""
    fallback_model: str = ""
    fallback_cooldown: int = 600
    rpm_limit: int = 0
    max_daily_calls: int = 50
    import_batch_size: int = 30
    max_tokens: int = 8192
    temperature: float = 0.3
    max_retries: int = 3
    ai_timeout: int = 300


class AITestRequest(BaseModel):
    api_base_url: str
    api_key: str = ""  # Optional — if empty, uses stored key
    model: str = ""


class AITestResponse(BaseModel):
    success: bool
    message: str
    response_time_ms: int = 0


class AIExplainRequest(BaseModel):
    card_id: int
    user_answer: str = ""


class AIExplainResponse(BaseModel):
    explanation: str
    mnemonic: str | None = None
    related_concepts: list[str] = []


class AIChatRequest(BaseModel):
    message: str = Field(max_length=2000)
    card_id: int | None = None  # Optional card context
    history: list[dict] = []  # Previous messages


class AIChatResponse(BaseModel):
    reply: str
    tokens_used: int = 0


class AIGenerateCardsRequest(BaseModel):
    text: str = Field(max_length=10000)
    category_id: int | None = None
    deck_id: int
    card_type: str = "qa"
    count: int = Field(default=5, ge=1, le=20)


class AIGenerateCardsResponse(BaseModel):
    cards: list[dict]  # Generated card data
    tokens_used: int = 0


class AIUsageResponse(BaseModel):
    today_calls: int
    max_daily_calls: int


class AIBatchEnrichRequest(BaseModel):
    card_ids: list[int] = []        # Specific card IDs, or empty = all cards in deck
    deck_id: int | None = None      # Enrich all cards in this deck
    batch_size: int = Field(default=50, ge=10, le=200)


class AIBatchEnrichResponse(BaseModel):
    total: int = 0
    enriched: int = 0
    skipped: int = 0
    errors: int = 0
    message: str = ""
