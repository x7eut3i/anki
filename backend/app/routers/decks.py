import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func

logger = logging.getLogger("anki.decks")

from app.auth import get_current_user
from app.database import get_session
from app.models.deck import Deck
from app.models.user import User
from app.schemas.deck import DeckCreate, DeckUpdate, DeckResponse, DeckListResponse

router = APIRouter(prefix="/api/decks", tags=["decks"])


@router.post("", response_model=DeckResponse, status_code=status.HTTP_201_CREATED)
def create_deck(
    data: DeckCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Check for duplicate name
    existing = session.exec(
        select(Deck).where(Deck.name == data.name)
    ).first()
    if existing:
        # Return the existing deck instead of creating a duplicate
        return DeckResponse.model_validate(existing)

    deck = Deck(**data.model_dump())
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return DeckResponse.model_validate(deck)


@router.get("", response_model=DeckListResponse)
def list_decks(
    search: str | None = Query(default=None, description="Search across deck names and card content"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    from app.models.card import Card

    decks = session.exec(
        select(Deck)
        .order_by(Deck.updated_at.desc())
    ).all()

    # Compute actual card counts from DB
    deck_responses = []
    # If search query is provided, also find decks containing matching cards
    matching_deck_ids: set[int] | None = None
    if search and search.strip():
        q = search.strip()
        # Find deck IDs that have cards matching the search
        card_deck_ids = session.exec(
            select(Card.deck_id).where(
                Card.front.contains(q)
                | Card.back.contains(q)
                | Card.explanation.contains(q)
                | Card.meta_info.contains(q)
            ).distinct()
        ).all()
        # Also include decks whose name/description matches
        matching_deck_ids = set(card_deck_ids)
        for d in decks:
            if q.lower() in (d.name or "").lower() or q.lower() in (d.description or "").lower():
                matching_deck_ids.add(d.id)

    for d in decks:
        if matching_deck_ids is not None and d.id not in matching_deck_ids:
            continue
        actual_count = session.exec(
            select(func.count()).select_from(Card).where(Card.deck_id == d.id)
        ).one()
        # Sync stale count if needed
        if d.card_count != actual_count:
            d.card_count = actual_count
            session.add(d)
        deck_responses.append(DeckResponse.model_validate(d))
    session.commit()

    return DeckListResponse(
        decks=deck_responses,
        total=len(deck_responses),
    )


@router.get("/{deck_id}", response_model=DeckResponse)
def get_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckResponse.model_validate(deck)


@router.put("/{deck_id}", response_model=DeckResponse)
def update_deck(
    deck_id: int,
    data: DeckUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(deck, key, value)
    deck.updated_at = datetime.now(timezone.utc)

    session.add(deck)
    session.commit()
    session.refresh(deck)
    return DeckResponse.model_validate(deck)


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    # Delete all cards in this deck
    from app.models.card import Card
    cards = session.exec(select(Card).where(Card.deck_id == deck_id)).all()
    for card in cards:
        session.delete(card)

    session.delete(deck)
    session.commit()


@router.post("/batch-delete-cards", status_code=status.HTTP_200_OK)
def batch_delete_cards(
    data: dict,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete multiple cards by their IDs."""
    card_ids = data.get("card_ids", [])
    if not card_ids:
        raise HTTPException(status_code=400, detail="No card IDs provided")

    from app.models.card import Card
    from app.models.user_card_progress import UserCardProgress

    # Collect affected deck IDs BEFORE deleting
    deck_ids_affected = set()
    for card_id in card_ids:
        card = session.get(Card, card_id)
        if card and card.deck_id:
            deck_ids_affected.add(card.deck_id)

    deleted = 0
    for card_id in card_ids:
        card = session.get(Card, card_id)
        if card:
            # Also delete progress records
            progresses = session.exec(
                select(UserCardProgress).where(UserCardProgress.card_id == card_id)
            ).all()
            for p in progresses:
                session.delete(p)
            session.delete(card)
            deleted += 1

    session.commit()

    # Recalculate card counts for affected decks
    for did in deck_ids_affected:
        d = session.get(Deck, did)
        if d:
            count = session.exec(
                select(func.count()).select_from(Card).where(Card.deck_id == did)
            ).one()
            d.card_count = count
            session.add(d)
    session.commit()

    return {"deleted": deleted, "total_requested": len(card_ids)}
