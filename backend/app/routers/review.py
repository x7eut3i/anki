import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session

logger = logging.getLogger("anki.review")
from app.models.user import User
from app.schemas.review import (
    ReviewRequest,
    ReviewResponse,
    SchedulingPreview,
    DueCardsRequest,
    StudySessionCreate,
    StudySessionResponse,
    StudyStatsResponse,
)
from app.services.review_service import ReviewService

router = APIRouter(prefix="/api/review", tags=["review"])


def _get_review_service(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReviewService:
    return ReviewService(
        session=session,
        user_id=current_user.id,
        desired_retention=current_user.desired_retention,
    )


@router.post("/due")
def get_due_cards(
    data: DueCardsRequest,
    service: ReviewService = Depends(_get_review_service),
):
    result = service.get_due_cards(
        category_ids=data.category_ids,
        deck_id=data.deck_id,
        deck_ids=data.deck_ids,
        tag_ids=data.tag_ids,
        exclude_ai_decks=data.exclude_ai_decks,
        limit=data.limit,
    )
    logger.debug("Due cards: total=%d new=%d review=%d relearning=%d",
                result["total_due"], result["new_count"],
                result["review_count"], result["relearning_count"])
    from app.schemas.card import CardResponse
    return {
        "cards": [CardResponse(**c) for c in result["cards"]],
        "total_due": result["total_due"],
        "new_count": result["new_count"],
        "review_count": result["review_count"],
        "relearning_count": result["relearning_count"],
    }


@router.post("/answer", response_model=ReviewResponse)
def submit_review(
    data: ReviewRequest,
    service: ReviewService = Depends(_get_review_service),
):
    import traceback
    try:
        result = service.review_card(
            card_id=data.card_id,
            rating=data.rating,
            duration_ms=data.review_duration_ms,
        )
        logger.debug("Review card=%d rating=%d -> state=%d due=%s",
                    data.card_id, data.rating, result["new_state"], result["new_due"])
        return ReviewResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Log detailed error for debugging
        print(f"ERROR in submit_review: {type(e).__name__}: {str(e)}")
        print(f"Card ID: {data.card_id}, Rating: {data.rating}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")


@router.get("/preview/{card_id}", response_model=SchedulingPreview)
def preview_ratings(
    card_id: int,
    service: ReviewService = Depends(_get_review_service),
):
    try:
        result = service.preview_ratings(card_id)
        return SchedulingPreview(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session", response_model=StudySessionResponse)
def create_session(
    data: StudySessionCreate,
    service: ReviewService = Depends(_get_review_service),
):
    session_obj = service.create_study_session(
        mode=data.mode,
        category_ids=data.category_ids,
        deck_id=data.deck_id,
        deck_ids=data.deck_ids,
        exclude_ai_decks=data.exclude_ai_decks,
        card_limit=data.card_limit,
        quiz_time_limit=data.quiz_time_limit,
    )
    logger.debug("Study session created: id=%d mode=%s cards=%d",
                session_obj.id, data.mode, session_obj.total_cards)
    return StudySessionResponse.model_validate(session_obj)


@router.get("/session/active", response_model=StudySessionResponse | None)
def get_active_session(
    mode: str | None = None,
    service: ReviewService = Depends(_get_review_service),
):
    exclude_modes = ["quiz"] if mode != "quiz" else None
    session_obj = service.get_active_session(exclude_modes=exclude_modes)
    if session_obj:
        return StudySessionResponse.model_validate(session_obj)
    return None


@router.post("/session/{session_id}/progress")
def update_session_progress(
    session_id: int,
    data: dict,
    service: ReviewService = Depends(_get_review_service),
):
    try:
        session_obj = service.update_session_progress(
            session_id, data["card_id"], data.get("is_correct", False)
        )
        return StudySessionResponse.model_validate(session_obj)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stats", response_model=StudyStatsResponse)
def get_stats(
    service: ReviewService = Depends(_get_review_service),
):
    stats = service.get_study_stats()
    return StudyStatsResponse(**stats)
