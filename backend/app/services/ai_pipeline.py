"""Shared AI pipeline functions for content cleanup, article analysis, and card generation.

These functions encapsulate the core AI operations used by both the ingestion pipeline
and the article reading (精读) feature, ensuring consistent behavior and avoiding
code duplication.
"""

import asyncio
import json
import logging
import time

import httpx
from sqlmodel import Session, select

from app.services.ai_logger import log_ai_request, log_ai_response, log_ai_call_to_db
from app.services.json_repair import repair_json, robust_json_parse

logger = logging.getLogger("anki.ai_pipeline")


def _cfg_temp(config) -> float:
    return getattr(config, "temperature", 0.3) or 0.3

def _cfg_max_tokens(config) -> int:
    return getattr(config, "max_tokens", 8192) or 8192

def _cfg_max_retries(config) -> int:
    return getattr(config, "max_retries", 3) or 3


async def _ai_call_with_retry(
    url: str,
    payload: dict,
    headers: dict,
    *,
    max_retries: int = 3,
    timeout: float = 120.0,
    feature: str = "ai_call",
) -> dict:
    """Make an AI API call with retry and exponential backoff.

    Returns the parsed JSON response dict.
    Raises on total failure after all retries.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            return resp.json()
        except Exception as err:
            last_error = err
            if attempt < max_retries - 1:
                logger.warning("%s attempt %d/%d failed: %s", feature, attempt + 1, max_retries, err)
                await asyncio.sleep(2 * (attempt + 1))
            else:
                logger.error("%s failed after %d attempts: %s", feature, max_retries, err)
    raise last_error  # type: ignore[misc]


async def ai_cleanup_content(
    config,
    title: str,
    body_text: str,
    user_id: int,
) -> str:
    """Clean up raw article text using AI.

    Returns cleaned text string, or original body_text on failure.
    """
    cleanup_model = config.model or "gpt-4o-mini"
    cleanup_sys = (
        "你是一个文本格式化助手。你的任务是将从网页抓取的原始文本整理成排版整洁、易于阅读的纯文本。\n"
        "规则：\n"
        "1. 保留文章的完整内容，不要删减、概括或改写任何实质内容\n"
        "2. 去除网页导航、广告、版权声明、编辑信息等非正文内容\n"
        "3. 正确分段：每个自然段之间用一个空行分隔\n"
        "4. 去除重复的标题、乱码、HTML残留\n"
        "5. 如果有小标题/子标题，保留并用独立行显示\n"
        "6. 直接输出整理后的纯文本，不要加任何说明或标记"
    )
    cleanup_prompt = f"请整理以下从网页抓取的文章文本：\n\n标题：{title}\n\n原始文本：\n{body_text}"

    url = f"{config.api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    temp = _cfg_temp(config)
    max_tokens = _cfg_max_tokens(config)
    payload = {
        "model": cleanup_model,
        "messages": [
            {"role": "system", "content": cleanup_sys},
            {"role": "user", "content": cleanup_prompt},
        ],
        "temperature": temp,
        "max_tokens": max_tokens,
    }

    try:
        log_ai_request("content_cleanup", cleanup_model, payload["messages"], temp, max_tokens)
        t0 = time.time()
        result = await _ai_call_with_retry(
            url, payload, headers,
            max_retries=_cfg_max_retries(config),
            timeout=60.0,
            feature="content_cleanup",
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        cleaned = result["choices"][0]["message"]["content"].strip()
        tokens_used = result.get("usage", {}).get("total_tokens", 0)
        log_ai_response("content_cleanup", cleanup_model, cleaned, tokens_used, elapsed_ms)
        log_ai_call_to_db(
            feature="content_cleanup", model=cleanup_model,
            config_name=config.name, tokens_used=tokens_used,
            elapsed_ms=elapsed_ms, input_preview=cleanup_prompt[:200],
            output_length=len(cleaned), user_id=user_id,
        )
        return cleaned if len(cleaned) > 80 else body_text
    except Exception as e:
        logger.warning("AI content cleanup failed, using original text: %s", e)
        return body_text


async def ai_analyze_article(
    session: Session,
    config,
    title: str,
    content: str,
    user_id: int,
) -> dict | None:
    """Analyze an article using AI. Returns analysis_data dict or None on failure."""
    from app.services.prompts import ARTICLE_ANALYSIS_SYSTEM_PROMPT, make_article_analysis_prompt
    from app.services.prompt_loader import get_prompt, get_prompt_model

    model = get_prompt_model(session, "article_analysis") or config.model_reading or config.model
    system_prompt = get_prompt(session, "article_analysis", ARTICLE_ANALYSIS_SYSTEM_PROMPT)
    user_prompt = make_article_analysis_prompt(title, content)

    url = f"{config.api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    temp = _cfg_temp(config)
    max_tokens = _cfg_max_tokens(config)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temp,
        "max_tokens": max_tokens,
    }

    log_ai_request("article_analysis", model, payload["messages"],
                   temperature=temp, max_tokens=max_tokens)

    max_retries = _cfg_max_retries(config)
    analysis_data = None
    ai_error_msg = ""

    for attempt in range(max_retries):
        try:
            t0 = time.time()
            result = await _ai_call_with_retry(
                url, payload, headers,
                max_retries=1,  # inner retry handled by outer loop for error logging
                timeout=120.0,
                feature="article_analysis",
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            content_text = result["choices"][0]["message"]["content"]
            tokens_used = result.get("usage", {}).get("total_tokens", 0)

            log_ai_response("article_analysis", model, content_text,
                            tokens_used=tokens_used, elapsed_ms=elapsed_ms)
            log_ai_call_to_db(
                feature="article_analysis", model=model,
                config_name=config.name, tokens_used=tokens_used,
                elapsed_ms=elapsed_ms, status="ok",
                input_preview=title[:200],
                output_length=len(content_text),
                user_id=user_id,
            )

            content_text = repair_json(content_text)
            analysis_data = json.loads(content_text)
            break
        except json.JSONDecodeError as e:
            ai_error_msg = f"AI返回格式错误 (attempt {attempt + 1}/{max_retries}): {e}"
            logger.warning(ai_error_msg)
        except Exception as e:
            ai_error_msg = f"AI分析失败 (attempt {attempt + 1}/{max_retries}): {e}"
            logger.warning(ai_error_msg)

        if attempt < max_retries - 1:
            await asyncio.sleep(2 * (attempt + 1))

    return analysis_data


async def ai_generate_cards(
    session: Session,
    config,
    title: str,
    content: str,
    source_url: str,
    user_id: int,
) -> tuple[int, list[dict]]:
    """Generate flashcards from article content using AI.

    Returns (cards_created_count, cards_data_list).
    """
    from app.models.card import Card
    from app.models.deck import Deck
    from app.models.category import Category
    from app.services.prompts import CARD_SYSTEM_PROMPT, make_pipeline_user_prompt
    from app.services.prompt_loader import get_prompt, get_prompt_model
    from app.services.dedup_service import DedupService

    model = get_prompt_model(session, "card_system") or config.model_pipeline or config.model
    system_prompt = get_prompt(session, "card_system", CARD_SYSTEM_PROMPT)

    cats = session.exec(select(Category).where(Category.is_active == True)).all()
    cat_list = "、".join(c.name for c in cats)
    cat_map = {c.name: c for c in cats}

    user_prompt = make_pipeline_user_prompt(
        title=title,
        content=content,
        category_list=cat_list,
    )

    url = f"{config.api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    temp = _cfg_temp(config)
    max_tokens = _cfg_max_tokens(config)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temp,
        "max_tokens": max_tokens,
    }

    log_ai_request("card_generation", model, payload["messages"],
                   temperature=temp, max_tokens=max_tokens)

    max_retries = _cfg_max_retries(config)
    content_text = None
    last_error = None

    for attempt in range(max_retries):
        try:
            t0 = time.time()
            result = await _ai_call_with_retry(
                url, payload, headers,
                max_retries=1,
                timeout=120.0,
                feature="card_generation",
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            content_text = result["choices"][0]["message"]["content"].strip()
            tokens_used = result.get("usage", {}).get("total_tokens", 0)

            log_ai_response("card_generation", model, content_text,
                            tokens_used=tokens_used, elapsed_ms=elapsed_ms)
            log_ai_call_to_db(
                feature="card_generation", model=model,
                config_name=config.name, tokens_used=tokens_used,
                elapsed_ms=elapsed_ms,
                status="ok", input_preview=title[:200],
                output_length=len(content_text),
                user_id=user_id,
            )
            
            # Parse JSON with repair
            content_text = repair_json(content_text)
            parsed = robust_json_parse(content_text)
            if parsed is None:
                raise ValueError("AI返回的JSON格式错误，且修复失败")

            if isinstance(parsed, dict):
                cards_data = parsed.get("cards", [])
            elif isinstance(parsed, list):
                cards_data = parsed
            else:
                raise ValueError("AI返回的JSON格式不正确，应该是包含cards字段的对象或卡片列表")
            
            last_error = None
            break
        except Exception as e:
            last_error = str(e)
            logger.warning("card_generation attempt %d/%d failed: %s", attempt + 1, max_retries, e)
        if attempt < max_retries - 1:
            await asyncio.sleep(2 * (attempt + 1))

    if last_error or content_text is None:
        logger.error("Card generation failed after retries: %s", last_error)
        return 0, []

    # Create cards with dedup
    imported = 0
    for card_data in cards_data:
        front_text = card_data.get("front", "")
        if not front_text:
            continue

        dedup_svc = DedupService(session, user_id)
        cat_name = card_data.get("category", "时政热点")
        category = cat_map.get(cat_name) or next(iter(cat_map.values()), None)

        if dedup_svc.find_duplicate(front_text, category_id=category.id if category else None):
            continue

        deck_name = f"AI-{category.name}" if category else "AI-时政热点"
        deck = session.exec(select(Deck).where(Deck.name == deck_name)).first()
        if not deck:
            deck = Deck(name=deck_name, description=f"AI自动生成的{deck_name[3:]}卡片")
            session.add(deck)
            session.commit()
            session.refresh(deck)

        distractors = card_data.get("distractors", "")
        if isinstance(distractors, list):
            distractors = json.dumps(distractors, ensure_ascii=False)
        meta_info = card_data.get("meta_info", "")
        if isinstance(meta_info, dict):
            meta_info = json.dumps(meta_info, ensure_ascii=False)

        card = Card(
            deck_id=deck.id,
            category_id=category.id if category else None,
            front=front_text,
            back=card_data.get("back", ""),
            explanation=card_data.get("explanation", ""),
            distractors=distractors,
            tags=card_data.get("tags", ""),
            meta_info=meta_info,
            source=source_url,
            is_ai_generated=True,
        )
        session.add(card)
        deck.card_count = (deck.card_count or 0) + 1
        session.add(deck)
        imported += 1

    if imported > 0:
        session.commit()

    return imported, cards_data
