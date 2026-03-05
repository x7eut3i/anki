from datetime import datetime
from pydantic import BaseModel, Field


class DeckCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    category_id: int | None = None
    is_public: bool = False


class DeckUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    is_public: bool | None = None


class DeckResponse(BaseModel):
    id: int
    name: str
    description: str
    category_id: int | None
    is_public: bool
    card_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeckListResponse(BaseModel):
    decks: list[DeckResponse]
    total: int
