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


@router.post("/save/{session_id}")
def save_quiz_progress(
    session_id: int,
    data: dict,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Save quiz progress (暂存) — persists user answers to server for session recovery."""
    import json as _json
    from app.models.study_session import StudySession

    study_session = session.get(StudySession, session_id)
    if not study_session or study_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if study_session.is_completed:
        raise HTTPException(status_code=400, detail="Session already completed")

    answers = data.get("answers", {})
    current_q = data.get("current_q", 0)

    study_session.quiz_user_answers = _json.dumps(answers, ensure_ascii=False)
    study_session.cards_reviewed = len(answers)
    study_session.current_question = current_q
    session.add(study_session)
    session.commit()

    return {"saved": len(answers), "session_id": session_id}
