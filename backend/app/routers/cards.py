import logging
import json
import asyncio
import time as _time
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
from app.models.ai_config import AIConfig
from app.services.ai_logger import log_ai_call_to_db
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


# ──────────────────────────────────────────────────────────────────────
# Regenerate alternate questions via AI
# ──────────────────────────────────────────────────────────────────────

_REGEN_SYSTEM_PROMPT = """\
你是公务员考试闪卡的出题专家。用户会给你一张现有卡片的信息，请为该卡片重新生成2到3个变体选择题（alternate_questions）。

要求：
1. 每个变体题必须从不同角度考察同一知识点
2. 每个变体题必须包含: type("choice"), question(题面), answer(正确答案), distractors(3个错误选项)
3. 【自包含原则】question必须完全独立、自包含，能作为问答题独立使用
4. 严禁出现"下列""以下""哪个""哪种"等指代性词语
5. question应该可以用一句话直接回答
6. distractors是错误的答案/释义，要有一定迷惑性但明确是错误的

只返回JSON数组，不要markdown代码块标记。格式：
[
  {"type": "choice", "question": "...", "answer": "...", "distractors": ["...", "...", "..."]},
  {"type": "choice", "question": "...", "answer": "...", "distractors": ["...", "...", "..."]}
]
"""


@router.post("/{card_id}/regenerate-questions")
async def regenerate_questions(
    card_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Use AI to regenerate alternate_questions for a card. Returns the
    generated questions for user review (does NOT save automatically)."""

    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    config = session.exec(
        select(AIConfig).where(
            AIConfig.user_id == current_user.id,
            AIConfig.is_enabled == True,
            AIConfig.is_active == True,
        )
    ).first()
    if not config:
        raise HTTPException(status_code=400, detail="请先在设置中配置AI服务")

    # Build user prompt with card context
    meta = {}
    try:
        meta = json.loads(card.meta_info) if card.meta_info else {}
    except Exception:
        pass

    user_prompt = (
        f"请为以下卡片重新生成2-3个变体选择题：\n\n"
        f"题面(front): {card.front}\n"
        f"答案(back): {card.back}\n"
        f"解析(explanation): {card.explanation or '无'}\n"
    )
    if meta.get("knowledge_type"):
        user_prompt += f"知识类型: {meta['knowledge_type']}\n"
    if meta.get("subject"):
        user_prompt += f"主题: {meta['subject']}\n"
    knowledge = meta.get("knowledge", {})
    if knowledge.get("key_points"):
        pts = knowledge["key_points"]
        user_prompt += f"核心考点: {', '.join(pts) if isinstance(pts, list) else pts}\n"

    # Make AI call
    import httpx
    from app.services.json_repair import repair_json, robust_json_parse

    model = config.model_pipeline or config.model or "gpt-4o-mini"
    url = f"{config.api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _REGEN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
    }

    try:
        _t0 = _time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        _elapsed = int((_time.time() - _t0) * 1000)

        content = data["choices"][0]["message"]["content"]
        _tokens = data.get("usage", {}).get("total_tokens", 0)
        questions = robust_json_parse(repair_json(content))

        if not isinstance(questions, list):
            raise ValueError("AI returned non-array response")

        # Validate structure
        validated = []
        for q in questions:
            if not isinstance(q, dict):
                continue
            if not q.get("question") or not q.get("answer"):
                continue
            validated.append({
                "type": q.get("type", "choice"),
                "question": q["question"],
                "answer": q["answer"],
                "distractors": q.get("distractors", [])[:3],
            })

        if not validated:
            raise ValueError("No valid questions generated")

        log_ai_call_to_db(
            feature="regenerate_questions", model=model,
            config_name=config.name, tokens_used=_tokens,
            elapsed_ms=_elapsed, status="ok",
            input_preview=card.front[:200],
            output_length=len(content),
            user_id=current_user.id,
        )
        return {"questions": validated}

    except httpx.HTTPStatusError as e:
        logger.error("AI call failed for regenerate-questions: HTTP %d", e.response.status_code)
        log_ai_call_to_db(
            feature="regenerate_questions", model=model,
            config_name=config.name, status="error",
            error_message=f"HTTP {e.response.status_code}",
            input_preview=card.front[:200],
            user_id=current_user.id,
        )
        raise HTTPException(
            status_code=502, detail=f"AI服务调用失败: HTTP {e.response.status_code}"
        )
    except Exception as e:
        logger.error("regenerate-questions failed: %s", e)
        log_ai_call_to_db(
            feature="regenerate_questions", model=model,
            config_name=config.name, status="error",
            error_message=str(e)[:500],
            input_preview=card.front[:200],
            user_id=current_user.id,
        )
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)[:200]}")
