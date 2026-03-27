import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from zoneinfo import ZoneInfo

from app.auth import get_current_user
from app.database import get_session

logger = logging.getLogger("anki.review")
from app.models.user import User
from app.schemas.review import (
    ReviewRequest,
    ReviewResponse,
    BatchAnswerRequest,
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
    # If card_ids provided, return those cards directly (for session resume with history)
    if data.card_ids:
        cards = service.get_cards_by_ids(data.card_ids)
        from app.schemas.card import CardResponse
        return {
            "cards": [CardResponse(**c) for c in cards],
            "total_due": 0, "new_count": 0,
            "review_count": 0, "relearning_count": 0,
        }
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


@router.post("/batch-answer")
def batch_submit_reviews(
    data: BatchAnswerRequest,
    service: ReviewService = Depends(_get_review_service),
):
    """Submit multiple card reviews in a single request.

    Accepts a BatchAnswerRequest {answers: [...], session_id?: N}.
    Also updates the study session remaining_card_ids when session_id is provided.
    """
    answers = data.answers
    session_id = data.session_id

    results = []
    errors = []
    reviewed_card_ids = []
    for ans in answers:
        try:
            result = service.review_card(
                card_id=ans.card_id,
                rating=ans.rating,
                duration_ms=ans.review_duration_ms,
            )
            results.append(result)
            reviewed_card_ids.append(ans.card_id)
        except Exception as e:
            # Rollback so subsequent cards in the batch can still proceed
            service.session.rollback()
            errors.append({"card_id": ans.card_id, "error": str(e)})

    # Update study session if provided
    if session_id and reviewed_card_ids:
        try:
            service.batch_update_session_progress(
                session_id, reviewed_card_ids,
                [ans.rating >= 3 for ans in answers if ans.card_id in reviewed_card_ids],
            )
        except Exception as e:
            logger.warning("Failed to update session %d: %s", session_id, e)

    return {"results": results, "errors": errors, "processed": len(results)}


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


@router.post("/preview/batch")
def batch_preview_ratings(
    data: dict,
    service: ReviewService = Depends(_get_review_service),
):
    """Get scheduling previews for multiple cards at once.

    Returns a dict keyed by card_id string, with human-readable interval labels.
    """
    card_ids = data.get("card_ids", [])
    results = {}
    for cid in card_ids:
        try:
            p = service.preview_ratings(cid)
            results[str(cid)] = {
                "1": f"{p['again_days']}天" if p.get('again_days', 0) > 0 else "<1天",
                "2": f"{p['hard_days']}天" if p.get('hard_days', 0) > 0 else "<1天",
                "3": f"{p['good_days']}天" if p.get('good_days', 0) > 0 else "<1天",
                "4": f"{p['easy_days']}天" if p.get('easy_days', 0) > 0 else "<1天",
            }
        except ValueError:
            pass
    return results


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
        question_mode=data.question_mode,
        custom_ratio=data.custom_ratio,
    )
    logger.debug("Study session created: id=%d mode=%s cards=%d",
                session_obj.id, data.mode, session_obj.total_cards)
    return StudySessionResponse.model_validate(session_obj)


@router.get("/session/active", response_model=StudySessionResponse | None)
def get_active_session(
    mode: str | None = None,
    service: ReviewService = Depends(_get_review_service),
):
    if mode == "quiz":
        # Return only quiz sessions
        session_obj = service.get_active_session(only_mode="quiz")
    else:
        # Exclude quiz sessions by default
        session_obj = service.get_active_session(exclude_modes=["quiz"])
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
    tz: str | None = Query(None, description="IANA timezone, e.g. Asia/Shanghai"),
    service: ReviewService = Depends(_get_review_service),
):
    user_tz: ZoneInfo | None = None
    if tz:
        try:
            user_tz = ZoneInfo(tz)
        except Exception:
            pass
    stats = service.get_study_stats(tz=user_tz)
    return StudyStatsResponse(**stats)


@router.get("/dashboard")
def get_dashboard(
    tz: str | None = Query(None, description="IANA timezone, e.g. Asia/Shanghai"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Aggregated dashboard data — returns stats, categories, active sessions,
    daily recommendation, and active quiz session in a single request."""
    from app.routers.categories import list_categories
    from app.routers.article_analysis import daily_recommendation

    # 1. Stats
    service = ReviewService(
        session=session,
        user_id=current_user.id,
        desired_retention=current_user.desired_retention,
    )
    user_tz: ZoneInfo | None = None
    if tz:
        try:
            user_tz = ZoneInfo(tz)
        except Exception:
            pass
    stats = service.get_study_stats(tz=user_tz)

    # 2. Categories (reuse existing function logic)
    cat_data = list_categories(session=session, current_user=current_user)

    # 3. Active study session (exclude quiz)
    active_session = None
    try:
        session_obj = service.get_active_session(exclude_modes=["quiz"])
        if session_obj:
            active_session = StudySessionResponse.model_validate(session_obj).model_dump()
    except Exception:
        pass

    # 4. Daily recommendation
    rec = None
    try:
        rec_data = daily_recommendation(current_user=current_user, session=session)
        if rec_data and rec_data.get("id"):
            rec = rec_data
    except Exception:
        pass

    # 5. Active quiz session
    quiz_session = None
    try:
        quiz_obj = service.get_active_session(only_mode="quiz")
        if quiz_obj:
            quiz_session = StudySessionResponse.model_validate(quiz_obj).model_dump()
    except Exception:
        pass

    return {
        "stats": stats,
        "categories": cat_data.get("categories", []),
        "ai_categories": cat_data.get("ai_categories", []),
        "custom_decks": cat_data.get("custom_decks", []),
        "all_decks": cat_data.get("all_decks", []),
        "active_session": active_session,
        "recommendation": rec,
        "quiz_session": quiz_session,
    }


@router.post("/reset/all")
def reset_all(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Reset ALL study progress. All cards return to NEW state."""
    service = ReviewService(session=session, user_id=current_user.id)
    result = service.reset_all()
    logger.info("User %d reset ALL progress: %d progress deleted, %d reviews deleted",
                current_user.id, result["progress_deleted"], result["reviews_deleted"])
    return result
