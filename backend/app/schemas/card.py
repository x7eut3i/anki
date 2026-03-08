from datetime import datetime
from pydantic import BaseModel, Field


class CardCreate(BaseModel):
    deck_id: int
    category_id: int | None = None
    front: str = Field(max_length=5000)
    back: str = Field(default="", max_length=5000)
    explanation: str = Field(default="", max_length=5000)
    distractors: str = Field(default="")  # JSON array of wrong answers
    tags: str = Field(default="")
    meta_info: str = Field(default="")  # JSON-encoded structured knowledge
    source: str = Field(default="")
    expires_at: datetime | None = None


class CardUpdate(BaseModel):
    front: str | None = None
    back: str | None = None
    explanation: str | None = None
    distractors: str | None = None
    tags: str | None = None
    meta_info: str | None = None
    source: str | None = None
    category_id: int | None = None
    is_suspended: bool | None = None  # Updates UserCardProgress for the current user
    expires_at: datetime | None = None


class CardResponse(BaseModel):
    id: int
    deck_id: int
    category_id: int | None
    category_name: str = ""
    front: str
    back: str
    explanation: str
    distractors: str
    tags: str
    meta_info: str
    source: str
    expires_at: datetime | None
    is_ai_generated: bool
    created_at: datetime
    updated_at: datetime
    # Per-user progress fields (populated from UserCardProgress when available)
    due: datetime | None = None
    stability: float = 0.0
    difficulty: float = 0.0
    state: int = 0
    reps: int = 0
    lapses: int = 0
    is_suspended: bool = False
    # Tags (populated from CardTag junction)
    tags_list: list[dict] = []

    model_config = {"from_attributes": True}


class CardBulkCreate(BaseModel):
    cards: list[CardCreate]


class CardListResponse(BaseModel):
    cards: list[CardResponse]
    total: int
    page: int
    page_size: int
