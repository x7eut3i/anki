"""Router for custom tag management."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func, col

from app.auth import get_current_user
from app.database import get_session
from app.models.tag import Tag, CardTag, ArticleTag
from app.models.user import User

logger = logging.getLogger("anki.tags")

router = APIRouter(prefix="/api/tags", tags=["tags"])


# ── Schemas ──

class TagCreate(BaseModel):
    name: str
    color: str = "#3b82f6"


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    card_count: int = 0
    article_count: int = 0
    created_at: datetime
    model_config = {"from_attributes": True}


class TagAssign(BaseModel):
    tag_ids: list[int]


# ── Tag CRUD ──

@router.get("/{tag_id}/detail")
def get_tag_detail(
    tag_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get tag with its associated cards and articles."""
    from app.models.card import Card
    from app.models.article_analysis import ArticleAnalysis
    from app.models.deck import Deck
    from app.models.category import Category

    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    # Get cards with this tag
    card_tag_rows = session.exec(select(CardTag).where(CardTag.tag_id == tag_id)).all()
    card_ids = [ct.card_id for ct in card_tag_rows]
    cards = []
    if card_ids:
        card_objs = session.exec(select(Card).where(col(Card.id).in_(card_ids))).all()
        # Batch fetch decks and categories
        deck_ids = list({c.deck_id for c in card_objs if c.deck_id})
        cat_ids_list = list({c.category_id for c in card_objs if c.category_id})
        deck_map = {}
        cat_map = {}
        if deck_ids:
            decks = session.exec(select(Deck).where(col(Deck.id).in_(deck_ids))).all()
            deck_map = {d.id: d.name for d in decks}
        if cat_ids_list:
            cats = session.exec(select(Category).where(col(Category.id).in_(cat_ids_list))).all()
            cat_map = {c.id: c.name for c in cats}

        # Batch fetch tags for all cards
        card_tags_map: dict[int, list[dict]] = {}
        all_ct = session.exec(
            select(CardTag.card_id, Tag.id, Tag.name, Tag.color)
            .join(Tag, Tag.id == CardTag.tag_id)
            .where(col(CardTag.card_id).in_(card_ids))
        ).all()
        for cid, tid, tname, tcolor in all_ct:
            card_tags_map.setdefault(cid, []).append({"id": tid, "name": tname, "color": tcolor})

        for c in card_objs:
            cards.append({
                "id": c.id,
                "front": c.front,
                "back": c.back,
                "explanation": c.explanation or "",
                "distractors": c.distractors or "",
                "meta_info": c.meta_info or "",
                "tags": c.tags or "",
                "tags_list": card_tags_map.get(c.id, []),
                "deck_name": deck_map.get(c.deck_id, ""),
                "category_name": cat_map.get(c.category_id, "") if c.category_id else "",
                "is_ai_generated": c.is_ai_generated,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            })

    # Get articles with this tag
    article_tag_rows = session.exec(select(ArticleTag).where(ArticleTag.tag_id == tag_id)).all()
    article_ids = [at.article_id for at in article_tag_rows]
    articles = []
    if article_ids:
        article_objs = session.exec(
            select(ArticleAnalysis).where(col(ArticleAnalysis.id).in_(article_ids))
        ).all()
        for a in article_objs:
            articles.append({
                "id": a.id,
                "title": a.title,
                "content": a.content or "",
                "analysis_html": a.analysis_html or "",
                "source_url": a.source_url or "",
                "source_name": a.source_name or "",
                "publish_date": a.publish_date or "",
                "quality_score": a.quality_score,
                "quality_reason": a.quality_reason or "",
                "word_count": a.word_count,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            })

    return {
        "tag": {"id": tag.id, "name": tag.name, "color": tag.color},
        "cards": cards,
        "articles": articles,
    }


@router.get("", response_model=list[TagResponse])
def list_tags(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List all tags with usage counts."""
    tags = session.exec(select(Tag).order_by(Tag.name)).all()
    result = []
    for tag in tags:
        card_count = session.exec(
            select(func.count()).where(CardTag.tag_id == tag.id)
        ).one()
        article_count = session.exec(
            select(func.count()).where(ArticleTag.tag_id == tag.id)
        ).one()
        result.append(TagResponse(
            id=tag.id,
            name=tag.name,
            color=tag.color,
            card_count=card_count,
            article_count=article_count,
            created_at=tag.created_at,
        ))
    return result


@router.post("", response_model=TagResponse, status_code=201)
def create_tag(
    data: TagCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a new tag."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标签名称不能为空")
    # Check duplicate
    existing = session.exec(select(Tag).where(Tag.name == name)).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"标签「{name}」已存在")
    tag = Tag(name=name, color=data.color)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, created_at=tag.created_at)


@router.put("/{tag_id}", response_model=TagResponse)
def update_tag(
    tag_id: int,
    data: TagUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Rename or re-color a tag."""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="标签名称不能为空")
        dup = session.exec(select(Tag).where(Tag.name == new_name, Tag.id != tag_id)).first()
        if dup:
            raise HTTPException(status_code=409, detail=f"标签「{new_name}」已存在")
        tag.name = new_name
    if data.color is not None:
        tag.color = data.color
    session.add(tag)
    session.commit()
    session.refresh(tag)
    card_count = session.exec(select(func.count()).where(CardTag.tag_id == tag.id)).one()
    article_count = session.exec(select(func.count()).where(ArticleTag.tag_id == tag.id)).one()
    return TagResponse(
        id=tag.id, name=tag.name, color=tag.color,
        card_count=card_count, article_count=article_count,
        created_at=tag.created_at,
    )


@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    clean_references: bool = Query(False, description="Also remove tag references from cards/articles"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete a tag. Optionally clean references from cards/articles."""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    # Always clean up junction table references
    card_tags = session.exec(select(CardTag).where(CardTag.tag_id == tag_id)).all()
    for ct in card_tags:
        session.delete(ct)
    article_tags = session.exec(select(ArticleTag).where(ArticleTag.tag_id == tag_id)).all()
    for at in article_tags:
        session.delete(at)

    session.delete(tag)
    session.commit()
    return {"ok": True, "cleaned_cards": len(card_tags), "cleaned_articles": len(article_tags)}


# ── Card tag operations ──

@router.get("/card/{card_id}")
def get_card_tags(
    card_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get tags for a specific card."""
    card_tags = session.exec(select(CardTag).where(CardTag.card_id == card_id)).all()
    tag_ids = [ct.tag_id for ct in card_tags]
    tags = []
    for tid in tag_ids:
        tag = session.get(Tag, tid)
        if tag:
            tags.append({"id": tag.id, "name": tag.name, "color": tag.color})
    return tags


@router.put("/card/{card_id}")
def set_card_tags(
    card_id: int,
    data: TagAssign,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Set tags for a card (replace all)."""
    # Remove existing
    existing = session.exec(select(CardTag).where(CardTag.card_id == card_id)).all()
    for ct in existing:
        session.delete(ct)
    # Add new
    for tid in data.tag_ids:
        tag = session.get(Tag, tid)
        if tag:
            session.add(CardTag(card_id=card_id, tag_id=tid))
    session.commit()
    return {"ok": True}


@router.post("/card/{card_id}/add/{tag_id}")
def add_tag_to_card(
    card_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Add a single tag to a card."""
    existing = session.exec(
        select(CardTag).where(CardTag.card_id == card_id, CardTag.tag_id == tag_id)
    ).first()
    if not existing:
        session.add(CardTag(card_id=card_id, tag_id=tag_id))
        session.commit()
    return {"ok": True}


@router.delete("/card/{card_id}/remove/{tag_id}")
def remove_tag_from_card(
    card_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Remove a tag from a card."""
    ct = session.exec(
        select(CardTag).where(CardTag.card_id == card_id, CardTag.tag_id == tag_id)
    ).first()
    if ct:
        session.delete(ct)
        session.commit()
    return {"ok": True}


# ── Article tag operations ──

@router.get("/article/{article_id}")
def get_article_tags(
    article_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get tags for a specific article."""
    article_tags = session.exec(select(ArticleTag).where(ArticleTag.article_id == article_id)).all()
    tags = []
    for at in article_tags:
        tag = session.get(Tag, at.tag_id)
        if tag:
            tags.append({"id": tag.id, "name": tag.name, "color": tag.color})
    return tags


@router.put("/article/{article_id}")
def set_article_tags(
    article_id: int,
    data: TagAssign,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Set tags for an article (replace all)."""
    existing = session.exec(select(ArticleTag).where(ArticleTag.article_id == article_id)).all()
    for at in existing:
        session.delete(at)
    for tid in data.tag_ids:
        tag = session.get(Tag, tid)
        if tag:
            session.add(ArticleTag(article_id=article_id, tag_id=tid))
    session.commit()
    return {"ok": True}


@router.post("/article/{article_id}/add/{tag_id}")
def add_tag_to_article(
    article_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Add a single tag to an article."""
    existing = session.exec(
        select(ArticleTag).where(ArticleTag.article_id == article_id, ArticleTag.tag_id == tag_id)
    ).first()
    if not existing:
        session.add(ArticleTag(article_id=article_id, tag_id=tag_id))
        session.commit()
    return {"ok": True}


@router.delete("/article/{article_id}/remove/{tag_id}")
def remove_tag_from_article(
    article_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Remove a tag from an article."""
    at = session.exec(
        select(ArticleTag).where(ArticleTag.article_id == article_id, ArticleTag.tag_id == tag_id)
    ).first()
    if at:
        session.delete(at)
        session.commit()
    return {"ok": True}
