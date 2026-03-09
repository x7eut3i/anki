from datetime import datetime
from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    card_id: int
    rating: int = Field(ge=1, le=4)  # 1=Again, 2=Hard, 3=Good, 4=Easy
    review_duration_ms: int = Field(default=0, ge=0)


class ReviewResponse(BaseModel):
    card_id: int
    new_due: datetime
    new_stability: float
    new_difficulty: float
    new_state: int
    reps: int
    lapses: int

    model_config = {"from_attributes": True}


class SchedulingPreview(BaseModel):
    """Shows the next due date for each possible rating."""
    again: datetime
    hard: datetime
    good: datetime
    easy: datetime
    again_days: int
    hard_days: int
    good_days: int
    easy_days: int


class DueCardsRequest(BaseModel):
    category_ids: list[int] | None = None  # None = all categories
    deck_id: int | None = None
    deck_ids: list[int] | None = None  # Filter by multiple deck IDs (mix mode)
    tag_ids: list[int] | None = None  # Filter by tags
    exclude_ai_decks: bool = False  # Exclude cards in AI-* decks
    limit: int = Field(default=50, ge=1, le=200)
    card_ids: list[int] | None = None  # If set, return these cards directly (bypass SRS)


class DueCardsResponse(BaseModel):
    cards: list["CardResponse"]
    total_due: int
    new_count: int
    review_count: int
    relearning_count: int


# Import here to avoid circular
from app.schemas.card import CardResponse
DueCardsResponse.model_rebuild()


class StudySessionCreate(BaseModel):
    mode: str = "review"  # review, mix, quiz
    category_ids: list[int] | None = None
    deck_id: int | None = None
    deck_ids: list[int] | None = None  # Filter by multiple deck IDs (mix mode)
    exclude_ai_decks: bool = False  # Exclude cards in AI-* decks
    card_limit: int = Field(default=50, ge=1, le=500)
    quiz_time_limit: int = Field(default=0, ge=0)  # seconds
    question_mode: str = "custom"  # all_qa, all_choice, custom
    custom_ratio: int = 60  # QA percentage (0-100)


class StudySessionResponse(BaseModel):
    id: int
    mode: str
    total_cards: int
    cards_reviewed: int
    cards_correct: int
    cards_again: int
    quiz_score: int
    started_at: datetime
    finished_at: datetime | None
    is_completed: bool
    remaining_card_ids: str
    all_card_ids: str
    question_mode: str
    custom_ratio: int

    model_config = {"from_attributes": True}


class StudyStatsResponse(BaseModel):
    total_cards: int
    cards_due_today: int
    new_today: int
    reviewed_today: int
    streak_days: int
    retention_rate: float
    time_studied_today_ms: int
    cards_by_state: dict[str, int]
    category_stats: list[dict]
    daily_reviews: list[dict]  # Last 30 days
