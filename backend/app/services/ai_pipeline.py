"""Shared AI pipeline functions for content cleanup, article analysis, and card generation.

These functions encapsulate the core AI operations used by both the ingestion pipeline
and the article reading (精读) feature, ensuring consistent behavior and avoiding
code duplication.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.services.ai_logger import log_ai_request, log_ai_response, log_ai_call_to_db
from app.services.json_repair import repair_json, robust_json_parse

logger = logging.getLogger("anki.ai_pipeline")

# ── RPM Rate Limiter (sliding window + concurrency semaphore, module-level) ──
#
# Two independent constraints enforced:
#   1. Sliding window: at most N requests *started* in any 60-second window.
#      Implemented via a list of monotonic timestamps.  A new request may only
#      proceed when fewer than N timestamps fall within the last 60 s.
#   2. Concurrency semaphore: at most N requests *in-flight* simultaneously.
#      Acquired after the window check, released as soon as the request ends.
#
# The RPM limit is always read fresh from the database so mid-pipeline changes
# take effect immediately.
#
_rpm_semaphore: asyncio.Semaphore | None = None
_rpm_window_lock = asyncio.Lock()
_rpm_timestamps: list[float] = []   # monotonic times of recent request starts
_rpm_limit: int = 0                 # 0 = unlimited


def _read_current_rpm_limit(config) -> int:
    """Read the latest RPM limit from the database.

    Falls back to the (possibly stale) config object if the DB read fails.
    """
    try:
        from app.database import engine as db_engine
        from app.models.ai_config import AIConfig

        with Session(db_engine) as session:
            user_id = getattr(config, "user_id", None)
            if user_id:
                db_config = session.exec(
                    select(AIConfig).where(
                        AIConfig.user_id == user_id,
                        AIConfig.is_enabled == True,
                    )
                ).first()
                if db_config:
                    return db_config.rpm_limit or 0
    except Exception:
        pass
    return getattr(config, "rpm_limit", 0) or 0


async def _rpm_acquire(config) -> bool:
    """Wait until both RPM-window and concurrency constraints allow a request.

    Returns True if rate limiting is active (caller MUST call ``_rpm_release``
    when the request finishes).  Returns False when rate limiting is disabled.
    """
    global _rpm_semaphore, _rpm_limit, _rpm_timestamps

    limit = _read_current_rpm_limit(config)
    if limit <= 0:
        return False  # No rate limit configured

    # Recreate state when limit changes
    if limit != _rpm_limit:
        _rpm_limit = limit
        _rpm_semaphore = asyncio.Semaphore(limit)
        _rpm_timestamps = []

    assert _rpm_semaphore is not None

    # ── Step 1: sliding-window check (at most N starts per 60 s) ──
    while True:
        # Re-read limit each iteration — user may change it while we wait
        limit = _read_current_rpm_limit(config)
        if limit <= 0:
            return False
        if limit != _rpm_limit:
            _rpm_limit = limit
            _rpm_semaphore = asyncio.Semaphore(limit)
            _rpm_timestamps = []

        wait_time = 0.0
        async with _rpm_window_lock:
            now = time.monotonic()
            # Purge timestamps older than 60 s
            _rpm_timestamps[:] = [t for t in _rpm_timestamps if now - t < 60.0]
            if len(_rpm_timestamps) < _rpm_limit:
                # Room in the window – claim a slot
                _rpm_timestamps.append(now)
                break
            # Window full – calculate how long until the oldest entry expires
            wait_time = 60.0 - (now - _rpm_timestamps[0]) + 0.1

        #logger.info("RPM rate limit: window full, waiting %.1fs (limit=%d/min)",
        #            wait_time, _rpm_limit)
        await asyncio.sleep(wait_time)

    # ── Step 2: concurrency check (at most N in-flight) ──
    await _rpm_semaphore.acquire()
    return True


def _rpm_release() -> None:
    """Release the concurrency semaphore after a request completes.

    The sliding-window timestamp is NOT removed — it stays until it naturally
    ages out (60 s), which is exactly what enforces the per-minute cap.
    """
    if _rpm_semaphore is not None:
        _rpm_semaphore.release()

# ── Fallback model cooldown state (module-level, shared across all requests) ──
_fallback_active_until: datetime | None = None
_fallback_reason: str = ""
_fallback_model_name: str = ""  # cached from config at activation time


def _should_use_fallback() -> bool:
    """Check if we should currently use the fallback model."""
    if _fallback_active_until is None:
        return False
    return datetime.now(timezone.utc) < _fallback_active_until


def _activate_fallback(config, reason: str) -> str | None:
    """Activate fallback model for the configured cooldown period.

    Returns the fallback model name if activated, or None if no fallback configured.
    """
    global _fallback_active_until, _fallback_reason, _fallback_model_name
    fallback = getattr(config, "fallback_model", "") or ""
    if not fallback:
        return None
    cooldown = getattr(config, "fallback_cooldown", 600) or 600
    _fallback_active_until = datetime.now(timezone.utc).replace(
        second=datetime.now(timezone.utc).second
    )
    from datetime import timedelta
    _fallback_active_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown)
    _fallback_reason = reason
    _fallback_model_name = fallback
    logger.warning(
        "Fallback model activated: %s (reason: %s, cooldown: %ds)",
        fallback, reason, cooldown,
    )
    return fallback


def _get_effective_model(config, intended_model: str) -> str:
    """Get the effective model to use, considering fallback state."""
    if _should_use_fallback() and _fallback_model_name:
        logger.info(
            "Using fallback model %s (until %s, reason: %s)",
            _fallback_model_name, _fallback_active_until, _fallback_reason,
        )
        return _fallback_model_name
    return intended_model


def get_fallback_status() -> dict:
    """Get current fallback status for API/UI inspection."""
    if _should_use_fallback():
        remaining = (_fallback_active_until - datetime.now(timezone.utc)).total_seconds()  # type: ignore
        return {
            "active": True,
            "fallback_model": _fallback_model_name,
            "reason": _fallback_reason,
            "remaining_seconds": max(0, int(remaining)),
        }
    return {"active": False}


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
    config=None,
) -> dict:
    """Make an AI API call with retry, exponential backoff, and automatic fallback.

    If config is provided and has a fallback_model, on 429/5xx errors the system
    will switch to the fallback model for a cooldown period. This affects all
    subsequent AI calls across the application.

    Returns the parsed JSON response dict.
    Raises on total failure after all retries.
    """
    last_error = None

    # Apply fallback model if active
    if config and _should_use_fallback() and _fallback_model_name:
        payload = {**payload, "model": _fallback_model_name}
        logger.info("%s: using fallback model %s", feature, _fallback_model_name)

    for attempt in range(max_retries):
        # Apply RPM rate limiting for EACH attempt — blocks until both
        # sliding window and concurrency semaphore allow a new request.
        rpm_active = False
        if config:
            rpm_active = await _rpm_acquire(config)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)

                # Check response body for quota exhaustion (may arrive on any status)
                if config:
                    try:
                        resp_text = resp.text
                        if len(resp_text) < 100 and "配额已用尽" in resp_text:
                            fallback_name = _activate_fallback(config, "配额已用尽")
                            if fallback_name and payload.get("model") != fallback_name:
                                payload = {**payload, "model": fallback_name}
                                logger.warning(
                                    "%s: quota exhausted (配额已用尽), switching to fallback model %s",
                                    feature, fallback_name,
                                )
                                continue
                    except Exception:
                        pass

                # Check for rate limit or server errors that warrant fallback
                if resp.status_code in (429, 500, 502, 503, 529) and config:
                    error_reason = f"HTTP {resp.status_code}"
                    try:
                        err_body = resp.json()
                        if "error" in err_body:
                            err_obj = err_body["error"]
                            error_reason = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)
                    except Exception:
                        pass

                    fallback_name = _activate_fallback(config, f"{error_reason} (HTTP {resp.status_code})")
                    if fallback_name and payload.get("model") != fallback_name:
                        # Retry with fallback model (RPM released in finally)
                        payload = {**payload, "model": fallback_name}
                        logger.warning(
                            "%s: HTTP %d, switching to fallback model %s and retrying",
                            feature, resp.status_code, fallback_name,
                        )
                        continue

                resp.raise_for_status()
            return resp.json()
        except Exception as err:
            last_error = err

            # Build a descriptive error string including HTTP status + body
            err_detail = ""
            if isinstance(err, httpx.HTTPStatusError):
                status_code = err.response.status_code
                try:
                    body_text = err.response.text[:500]
                except Exception:
                    body_text = "(unreadable)"
                err_detail = f"HTTP {status_code}: {body_text}"

                # Check if this is an error that warrants fallback activation
                if config and status_code in (429, 500, 502, 503, 529):
                    fallback_name = _activate_fallback(config, f"HTTP {status_code}")
                    if fallback_name and payload.get("model") != fallback_name:
                        payload = {**payload, "model": fallback_name}
                        logger.warning(
                            "%s: activated fallback model %s after HTTP %d",
                            feature, fallback_name, status_code,
                        )
            else:
                err_detail = f"{type(err).__name__}: {err}" if str(err) else type(err).__name__

            if attempt < max_retries - 1:
                logger.warning("%s attempt %d/%d failed: %s", feature, attempt + 1, max_retries, err_detail)
                await asyncio.sleep(2 * (attempt + 1))
            else:
                logger.error("%s failed after %d attempts: %s", feature, max_retries, err_detail)
        finally:
            # Release RPM slot after each attempt so the next attempt
            # re-acquires and respects the sliding-window rate limit.
            if rpm_active:
                _rpm_release()

    raise last_error  # type: ignore[misc]


def _extract_ai_content(result: dict) -> str:
    """Extract the content string from an AI API response.

    Validates that the response has the expected OpenAI-compatible structure.
    Raises ValueError with a descriptive message if the response is malformed.
    """
    if "choices" not in result:
        # Try to extract a meaningful error from the response
        err_msg = ""
        if "error" in result:
            err_obj = result["error"]
            if isinstance(err_obj, dict):
                err_msg = err_obj.get("message", "") or err_obj.get("code", "")
            else:
                err_msg = str(err_obj)
        if not err_msg:
            # Show first 200 chars of the response for debugging
            err_msg = f"unexpected response: {str(result)}"
        raise ValueError(f"AI API 未返回 choices: {err_msg}")

    choices = result["choices"]
    if not choices or not isinstance(choices, list):
        raise ValueError("AI API 返回了空的 choices 列表")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        # Check for refusal / content_filter
        finish = choices[0].get("finish_reason", "")
        if finish == "content_filter":
            raise ValueError("AI API 内容被过滤 (content_filter)")
        raise ValueError(f"AI API 返回的 message 无 content (finish_reason={finish})")

    return content


async def ai_cleanup_content(
    config,
    title: str,
    body_text: str,
    user_id: int,
    source: str = "",
) -> str:
    """Clean up raw article text using AI.

    Returns cleaned text, or original body_text on failure.
    """
    cleanup_model = _get_effective_model(config, config.model or "gpt-4o-mini")
    cleanup_sys = (
        "你是一个文本格式化助手。你的任务是将从网页抓取的原始文本整理成排版整洁、易于阅读的Markdown格式文本。\n"
        "规则：\n"
        "1. 保留文章的完整内容，不要删减、概括或改写任何实质内容\n"
        "2. 去除网页导航、广告、版权声明、编辑信息等非正文内容\n"
        "3. 正确分段：每个自然段之间用一个空行分隔\n"
        "4. 去除重复的标题、乱码、HTML残留\n"
        "5. 格式化要求：\n"
        "   - 所有格式来源于网页本身，严禁添加任何未在原文中出现的格式元素\n"
        "   - 文章标题用 # （一级标题）\n"
        "   - 小标题/子标题用 ## 或 ### （二级/三级标题）\n"
        "   - 作者、来源、日期等信息保留在标题下方，用 **加粗** 标注\n"
        "   - 列表项使用 - 或数字列表\n"
        "6. 直接输出整理后的Markdown格式文本，不要加任何说明、解释或额外标记"
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

    cleaned = body_text
    try:
        log_ai_request("content_cleanup", cleanup_model, payload["messages"], temp, max_tokens)
        t0 = time.time()
        result = await _ai_call_with_retry(
            url, payload, headers,
            max_retries=_cfg_max_retries(config),
            timeout=60.0,
            feature="content_cleanup",
            config=config,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        cleaned_result = _extract_ai_content(result).strip()
        tokens_used = result.get("usage", {}).get("total_tokens", 0)
        log_ai_response("content_cleanup", cleanup_model, cleaned_result, tokens_used, elapsed_ms)
        log_ai_call_to_db(
            feature="content_cleanup", model=cleanup_model,
            config_name=config.name, tokens_used=tokens_used,
            elapsed_ms=elapsed_ms, input_preview=cleanup_prompt[:200],
            output_length=len(cleaned_result), user_id=user_id,
            source=source,
        )
        if len(cleaned_result) > 80:
            cleaned = cleaned_result
    except Exception as e:
        logger.warning("AI content cleanup failed, using original text: %s", e)
        log_ai_response("content_cleanup", cleanup_model, "", error=str(e))
        log_ai_call_to_db(
            feature="content_cleanup", model=cleanup_model,
            config_name=config.name, status="error",
            error_message=str(e), input_preview=cleanup_prompt[:200],
            user_id=user_id, source=source,
            raw_response=str(e),
        )

    return cleaned


async def ai_analyze_article(
    session: Session,
    config,
    title: str,
    content: str,
    user_id: int,
    source: str = "",
) -> dict | None:
    """Analyze an article using AI. Returns analysis_data dict or None on failure."""
    from app.services.prompts import ARTICLE_ANALYSIS_SYSTEM_PROMPT, make_article_analysis_prompt
    from app.services.prompt_loader import get_prompt, get_prompt_model

    model = _get_effective_model(config, get_prompt_model(session, "article_analysis") or config.model_reading or config.model)
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
    ai_raw_response = ""

    for attempt in range(max_retries):
        try:
            t0 = time.time()
            result = await _ai_call_with_retry(
                url, payload, headers,
                max_retries=1,  # inner retry handled by outer loop for error logging
                timeout=120.0,
                feature="article_analysis",
                config=config,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            content_text = _extract_ai_content(result)
            tokens_used = result.get("usage", {}).get("total_tokens", 0)

            log_ai_response("article_analysis", model, content_text,
                            tokens_used=tokens_used, elapsed_ms=elapsed_ms)
            log_ai_call_to_db(
                feature="article_analysis", model=model,
                config_name=config.name, tokens_used=tokens_used,
                elapsed_ms=elapsed_ms, status="ok",
                input_preview=title[:200],
                output_length=len(content_text),
                user_id=user_id, source=source,
            )

            content_text = repair_json(content_text)
            analysis_data = json.loads(content_text)
            break
        except json.JSONDecodeError as e:
            ai_error_msg = f"AI返回格式错误 (attempt {attempt + 1}/{max_retries}): {e}"
            # content_text is available when JSON parse fails after successful AI call
            try:
                ai_raw_response = content_text  # type: ignore[possibly-undefined]
            except NameError:
                ai_raw_response = str(e)
            logger.warning(ai_error_msg)
        except Exception as e:
            ai_error_msg = f"AI分析失败 (attempt {attempt + 1}/{max_retries}): {e}"
            ai_raw_response = str(e)
            logger.warning(ai_error_msg)

        if attempt < max_retries - 1:
            await asyncio.sleep(2 * (attempt + 1))

    # Log failure to DB if all retries exhausted
    if analysis_data is None and ai_error_msg:
        log_ai_response("article_analysis", model, ai_raw_response, error=ai_error_msg)
        log_ai_call_to_db(
            feature="article_analysis", model=model,
            config_name=config.name, status="error",
            error_message=ai_error_msg, input_preview=title[:200],
            user_id=user_id, source=source,
            raw_response=ai_raw_response,
        )

    return analysis_data


async def ai_generate_cards(
    session: Session,
    config,
    title: str,
    content: str,
    source_url: str,
    user_id: int,
    source: str = "",
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

    model = _get_effective_model(config, get_prompt_model(session, "card_system") or config.model_pipeline or config.model)
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
    last_raw_response = ""
    cards_data: list[dict] = []

    for attempt in range(max_retries):
        try:
            t0 = time.time()
            result = await _ai_call_with_retry(
                url, payload, headers,
                max_retries=1,
                timeout=120.0,
                feature="card_generation",
                config=config,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            content_text = _extract_ai_content(result).strip()
            tokens_used = result.get("usage", {}).get("total_tokens", 0)

            log_ai_response("card_generation", model, content_text,
                            tokens_used=tokens_used, elapsed_ms=elapsed_ms)
            log_ai_call_to_db(
                feature="card_generation", model=model,
                config_name=config.name, tokens_used=tokens_used,
                elapsed_ms=elapsed_ms,
                status="ok", input_preview=title[:200],
                output_length=len(content_text),
                user_id=user_id, source=source,
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
            last_error = e
            last_raw_response = content_text if content_text else ""
            err_detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.warning("card_generation attempt %d/%d failed: %s", attempt + 1, max_retries, err_detail)
        if attempt < max_retries - 1:
            await asyncio.sleep(2 * (attempt + 1))

    if last_error is not None or content_text is None:
        err_msg = ""
        if last_error is not None:
            err_msg = f"{type(last_error).__name__}: {last_error}" if str(last_error) else type(last_error).__name__
        logger.error("Card generation failed after %d retries: %s (raw_response=%s)",
                     max_retries, err_msg, last_raw_response[:300] if last_raw_response else "(none)")
        log_ai_response("card_generation", model, last_raw_response, error=err_msg)
        log_ai_call_to_db(
            feature="card_generation", model=model,
            config_name=config.name, status="error",
            error_message=err_msg, input_preview=title[:200],
            user_id=user_id, source=source,
            raw_response=last_raw_response,
        )
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
            deck = Deck(
                name=deck_name,
                description=f"AI自动生成的{deck_name[3:]}卡片",
                category_id=category.id if category else None,
            )
            session.add(deck)
            session.commit()
            session.refresh(deck)
        elif category and not deck.category_id:
            # Backfill category_id for existing AI decks created without it
            deck.category_id = category.id
            session.add(deck)
            session.commit()

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
