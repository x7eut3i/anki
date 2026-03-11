import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session

logger = logging.getLogger("anki.categories")
from app.models.category import Category
from app.models.user import User

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("")
def list_categories(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    from app.models.card import Card
    from app.models.deck import Deck
    from sqlmodel import func, col

    cats = session.exec(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order)
    ).all()

    # Get card counts for each category (exclude AI-deck cards to avoid double-counting)
    result = []
    for cat in cats:
        cat_dict = cat.model_dump()
        # Only count cards that are NOT in an AI-* deck
        count_query = (
            select(func.count(Card.id))
            .outerjoin(Deck, Card.deck_id == Deck.id)
            .where(
                Card.category_id == cat.id,
                col(Deck.name).not_like("AI-%") | (Card.deck_id == None),  # noqa: E711
            )
        )
        card_count = session.exec(count_query).one()
        cat_dict["card_count"] = card_count
        result.append(cat_dict)

    # Build a category ID -> name map for deck display
    cat_name_map = {cat.id: cat.name for cat in cats}

    # All decks with card counts and category_name
    all_decks = session.exec(select(Deck)).all()
    all_decks_result = []
    for deck in all_decks:
        deck_count = session.exec(
            select(func.count(Card.id)).where(Card.deck_id == deck.id)
        ).one()
        all_decks_result.append({
            "id": deck.id,
            "name": deck.name,
            "description": deck.description or "",
            "category_id": deck.category_id,
            "category_name": cat_name_map.get(deck.category_id, "") if deck.category_id else "",
            "card_count": deck_count,
            "is_ai": deck.name.startswith("AI-"),
        })

    # AI-generated decks as separate entries (kept for backward compatibility)
    ai_result = []
    for d in all_decks_result:
        if d["is_ai"] and d["card_count"] > 0:
            ai_result.append({
                "id": -(d["id"]),
                "name": d["name"],
                "description": d["description"] or f"AI生成的{d['name'][3:]}卡片",
                "icon": "🤖",
                "sort_order": 100,
                "is_active": True,
                "card_count": d["card_count"],
                "deck_id": d["id"],
            })

    # User-created custom decks (non-AI, non-empty)
    custom_result = []
    for d in all_decks_result:
        if not d["is_ai"] and d["card_count"] > 0:
            custom_result.append({
                "id": -(1000 + d["id"]),
                "name": d["name"],
                "description": d["description"] or "",
                "icon": "📚",
                "sort_order": 200,
                "is_active": True,
                "card_count": d["card_count"],
                "deck_id": d["id"],
            })

    return {
        "categories": result,
        "ai_categories": ai_result,
        "custom_decks": custom_result,
        "all_decks": all_decks_result,
    }


@router.get("/{category_id}")
def get_category(
    category_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat.model_dump()


@router.put("/{category_id}")
def update_category(
    category_id: int,
    data: dict,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    for key in ["name", "description", "icon", "sort_order", "is_active",
                "default_new_per_day", "default_reviews_per_day"]:
        if key in data:
            setattr(cat, key, data[key])

    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat.model_dump()
