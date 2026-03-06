from pydantic import BaseModel, Field


class QuizCreate(BaseModel):
    category_ids: list[int] | None = None  # None = all
    deck_ids: list[int] | None = None  # Filter by specific deck IDs (e.g. AI decks)
    card_count: int = Field(default=20, ge=5, le=100)
    time_limit: int = Field(default=0, ge=0)  # seconds per question, 0 = no limit
    include_types: list[str] = ["choice", "qa"]


class QuizQuestion(BaseModel):
    question_id: int
    card_id: int
    question_type: str  # choice, qa
    question: str
    choices: list[str] | None = None  # For choice type (4 options including correct)
    category_name: str
    tags_list: list[dict] = []  # [{id, name, color}]    source: str = ""  # Card source URL (for article source display)    time_limit: int = 0


class QuizAnswer(BaseModel):
    question_id: int
    card_id: int
    answer: str
    time_spent_ms: int = 0


class QuizResult(BaseModel):
    question_id: int
    card_id: int
    correct: bool
    correct_answer: str
    user_answer: str
    explanation: str
    source: str = ""


class QuizSessionResponse(BaseModel):
    session_id: int
    questions: list[QuizQuestion]
    total_questions: int
    time_limit: int


class QuizSubmitResponse(BaseModel):
    session_id: int
    score: int
    total: int
    accuracy: float
    time_spent_ms: int
    results: list[QuizResult]
    category_scores: dict[str, dict]  # {category: {correct: n, total: n}}
