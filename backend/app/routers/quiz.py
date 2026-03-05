import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session

logger = logging.getLogger("anki.quiz")
from app.models.user import User
from app.schemas.quiz import (
    QuizCreate,
    QuizSessionResponse,
    QuizAnswer,
    QuizSubmitResponse,
)
from app.services.quiz_service import QuizService

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate", response_model=QuizSessionResponse)
def generate_quiz(
    data: QuizCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = QuizService(session, current_user.id)
    result = service.generate_quiz(
        category_ids=data.category_ids,
        deck_ids=data.deck_ids,
        card_count=data.card_count,
        time_limit=data.time_limit,
        include_types=data.include_types,
    )
    return QuizSessionResponse(**result)


@router.post("/submit/{session_id}", response_model=QuizSubmitResponse)
def submit_quiz(
    session_id: int,
    answers: list[QuizAnswer],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = QuizService(session, current_user.id)
    try:
        result = service.score_quiz(
            session_id=session_id,
            answers=[a.model_dump() for a in answers],
        )
        return QuizSubmitResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
