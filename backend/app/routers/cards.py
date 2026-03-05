import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func, col

logger = logging.getLogger("anki.cards")

from app.auth import get_current_user
from app.database import get_session
from app.models.card import Card
from app.models.deck import Deck
from app.models.user import User
from app.models.user_card_progress import UserCardProgress
from app.schemas.card import (
    CardCreate,
    CardUpdate,
    CardResponse,
    CardBulkCreate,
    CardListResponse,
)
from app.services.dedup_service import DedupService

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.post("/dedup-check")
def check_duplicates(
    data: dict,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Check if cards with the given front texts already exist."""
    dedup = DedupService(session, current_user.id)
    fronts = data.get("fronts", [])
    category_id = data.get("category_id")
    results = dedup.check_duplicates(fronts, category_id)
    return {"duplicates": results}


@router.post("", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
def create_card(
    data: CardCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Verify deck exists
    deck = session.get(Deck, data.deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    # Dedup check: skip if an identical front already exists in same category
    dedup_svc = DedupService(session)
    existing = dedup_svc.find_duplicate(data.front, category_id=data.category_id)
    if existing:
        logger.debug("Dedup: skipping duplicate card front=%r existing_id=%d", data.front[:60], existing.id)
        # Return the existing card instead of creating a duplicate
        return CardResponse.model_validate(existing)

    card = Card(
        **data.model_dump(),
    )
    session.add(card)

    # Update deck card count
    deck.card_count += 1
    session.add(deck)
    session.commit()
    session.refresh(card)
    logger.debug("Card created: id=%d deck=%s ai=%s", card.id, deck.name, card.is_ai_generated)
    return CardResponse.model_validate(card)


@router.post("/bulk", response_model=dict)
def create_cards_bulk(
    data: CardBulkCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    created = 0
    skipped = 0
    errors = []
    dedup_svc = DedupService(session)
    for i, card_data in enumerate(data.cards):
        try:
            deck = session.get(Deck, card_data.deck_id)
            if not deck:
                errors.append(f"Card {i}: Deck not found")
                continue

            # Dedup check
            existing = dedup_svc.find_duplicate(card_data.front, category_id=card_data.category_id)
            if existing:
                skipped += 1
                continue

            card = Card(**card_data.model_dump())
            session.add(card)
            deck.card_count += 1
            session.add(deck)
            created += 1
        except Exception as e:
            errors.append(f"Card {i}: {str(e)}")

    session.commit()
    logger.debug("Bulk card create: created=%d skipped=%d errors=%d", created, skipped, len(errors))
    return {"created": created, "skipped": skipped, "errors": errors}


@router.get("", response_model=CardListResponse)
def list_cards(
    deck_id: int | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
    search: str | None = None,
    source: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    query = select(Card)

    if deck_id is not None:
        query = query.where(Card.deck_id == deck_id)
    if category_id is not None:
        query = query.where(Card.category_id == category_id)
    if tag_id is not None:
        from app.models.tag import CardTag
        tagged_card_ids = select(CardTag.card_id).where(CardTag.tag_id == tag_id)
        query = query.where(col(Card.id).in_(tagged_card_ids))
    if source is not None:
        query = query.where(Card.source == source)
    if search:
        query = query.where(
            Card.front.contains(search)
            | Card.back.contains(search)
            | Card.explanation.contains(search)
            | Card.meta_info.contains(search)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Card.created_at.desc())
    cards = session.exec(query).all()

    # Merge per-user progress for all cards
    card_responses = []
    card_ids = [c.id for c in cards]
    progress_map: dict[int, UserCardProgress] = {}
    if card_ids:
        progresses = session.exec(
            select(UserCardProgress).where(
                UserCardProgress.user_id == current_user.id,
                col(UserCardProgress.card_id).in_(card_ids),
            )
        ).all()
        progress_map = {p.card_id: p for p in progresses}

    # Fetch tags for all cards in one query
    from app.models.tag import CardTag, Tag
    tag_map: dict[int, list[dict]] = {}
    if card_ids:
        tag_rows = session.exec(
            select(CardTag.card_id, Tag.id, Tag.name, Tag.color)
            .join(Tag, Tag.id == CardTag.tag_id)
            .where(col(CardTag.card_id).in_(card_ids))
        ).all()
        for card_id, tag_id, tag_name, tag_color in tag_rows:
            tag_map.setdefault(card_id, []).append({"id": tag_id, "name": tag_name, "color": tag_color})

    # Fetch category names
    from app.models.category import Category
    cat_ids = list({c.category_id for c in cards if c.category_id})
    cat_map: dict[int, str] = {}
    if cat_ids:
        cat_rows = session.exec(select(Category).where(col(Category.id).in_(cat_ids))).all()
        cat_map = {cat.id: cat.name for cat in cat_rows}

    for c in cards:
        resp = CardResponse.model_validate(c)
        progress = progress_map.get(c.id)
        if progress:
            resp.is_suspended = progress.is_suspended
            resp.due = progress.due
            resp.stability = progress.stability
            resp.difficulty = progress.difficulty
            resp.state = progress.state
            resp.reps = progress.reps
            resp.lapses = progress.lapses
        # Attach tags and category_name
        resp.tags_list = tag_map.get(c.id, [])
        resp.category_name = cat_map.get(c.category_id, "") if c.category_id else ""
        card_responses.append(resp)

    return CardListResponse(
        cards=card_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{card_id}", response_model=CardResponse)
def get_card(
    card_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    resp = CardResponse.model_validate(card)
    # Merge per-user progress if available
    progress = session.exec(
        select(UserCardProgress).where(
            UserCardProgress.user_id == current_user.id,
            UserCardProgress.card_id == card_id,
        )
    ).first()
    if progress:
        resp.is_suspended = progress.is_suspended
        resp.due = progress.due
        resp.stability = progress.stability
        resp.difficulty = progress.difficulty
        resp.state = progress.state
        resp.reps = progress.reps
        resp.lapses = progress.lapses
    return resp


@router.put("/{card_id}", response_model=CardResponse)
def update_card(
    card_id: int,
    data: CardUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle is_suspended: update UserCardProgress instead of Card
    if "is_suspended" in update_data:
        is_suspended = update_data.pop("is_suspended")
        progress = session.exec(
            select(UserCardProgress).where(
                UserCardProgress.user_id == current_user.id,
                UserCardProgress.card_id == card_id,
            )
        ).first()
        if not progress:
            progress = UserCardProgress(
                user_id=current_user.id,
                card_id=card_id,
            )
        progress.is_suspended = is_suspended
        progress.updated_at = datetime.now(timezone.utc)
        session.add(progress)

    for key, value in update_data.items():
        setattr(card, key, value)
    card.updated_at = datetime.now(timezone.utc)

    session.add(card)
    session.commit()
    session.refresh(card)

    # Build response with progress info
    progress = session.exec(
        select(UserCardProgress).where(
            UserCardProgress.user_id == current_user.id,
            UserCardProgress.card_id == card_id,
        )
    ).first()
    resp = CardResponse.model_validate(card)
    if progress:
        resp.is_suspended = progress.is_suspended
        resp.due = progress.due
        resp.stability = progress.stability
        resp.difficulty = progress.difficulty
        resp.state = progress.state
        resp.reps = progress.reps
        resp.lapses = progress.lapses
    return resp


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    card_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    deck_id = card.deck_id
    logger.debug("Card deleted: id=%d deck_id=%d", card_id, deck_id)
    session.delete(card)
    session.commit()

    # Recalculate deck card count from DB
    deck = session.get(Deck, deck_id)
    if deck:
        actual_count = session.exec(
            select(func.count()).select_from(Card).where(Card.deck_id == deck_id)
        ).one()
        deck.card_count = actual_count
        session.add(deck)
        session.commit()
