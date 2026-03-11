"""Router for article deep reading (文章精读) feature."""

import json
import logging
import re
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File, status
from pydantic import BaseModel
from sqlmodel import Session, select, func, col

from app.auth import get_current_user
from app.database import get_session
from app.models.article_analysis import ArticleAnalysis
from app.models.ai_config import AIConfig
from app.models.user import User
from app.services.prompts import (
    ARTICLE_ANALYSIS_SYSTEM_PROMPT,
    make_article_analysis_prompt,
)
from app.services.prompt_loader import get_prompt, get_prompt_model
from app.services.ai_logger import log_ai_request, log_ai_response, log_ai_call_to_db
from app.services.json_repair import repair_json as _repair_json, robust_json_parse as _robust_json_parse

logger = logging.getLogger("anki.reading")

router = APIRouter(prefix="/api/reading", tags=["reading"])


def _cfg_temp(config: AIConfig) -> float:
    """Get configured temperature or default."""
    return getattr(config, "temperature", 0.3) or 0.3


def _cfg_max_tokens(config: AIConfig) -> int:
    """Get configured max_tokens or default."""
    return getattr(config, "max_tokens", 8192) or 8192

def _cfg_max_retries(config: AIConfig) -> int:
    """Get configured max_tokens or default."""
    return getattr(config, "max_retries", 3) or 3


# ── Schemas ──

class AnalysisCreate(BaseModel):
    title: str
    content: str
    source_url: str = ""
    source_name: str = ""
    publish_date: str = ""
    create_cards: bool = False  # If True, also generate flashcards from the article


class AnalysisStatusUpdate(BaseModel):
    status: str  # new, reading, finished, archived


class AnalysisStarUpdate(BaseModel):
    is_starred: bool


# ── Endpoints ──

@router.get("")
def list_analyses(
    status_filter: str | None = Query(None, alias="status"),
    is_starred: bool | None = None,
    min_quality: int | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    search: str | None = None,
    tag_id: int | None = None,
    sort_by: str | None = Query(None),  # created_at, publish_date, quality_score, word_count
    sort_dir: str | None = Query(None),  # asc, desc
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List article analyses (shared across users)."""
    query = select(ArticleAnalysis)

    if status_filter:
        query = query.where(ArticleAnalysis.status == status_filter)
    if is_starred is not None:
        query = query.where(ArticleAnalysis.is_starred == is_starred)
    if min_quality is not None:
        query = query.where(ArticleAnalysis.quality_score >= min_quality)
    if source_name:
        query = query.where(ArticleAnalysis.source_name == source_name)
    if source_url:
        query = query.where(ArticleAnalysis.source_url == source_url)
    if search:
        query = query.where(ArticleAnalysis.title.contains(search))
    if tag_id is not None:
        from app.models.tag import ArticleTag
        tagged_ids = select(ArticleTag.article_id).where(ArticleTag.tag_id == tag_id)
        query = query.where(col(ArticleAnalysis.id).in_(tagged_ids))

    # Count total
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total = session.exec(count_query).one()

    # Sorting
    sort_column = col(ArticleAnalysis.created_at)
    if sort_by == "publish_date":
        sort_column = col(ArticleAnalysis.publish_date)
    elif sort_by == "quality_score":
        sort_column = col(ArticleAnalysis.quality_score)
    elif sort_by == "word_count":
        sort_column = col(ArticleAnalysis.word_count)
    elif sort_by == "last_read_at":
        sort_column = col(ArticleAnalysis.last_read_at)

    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Paginate
    items = session.exec(
        query.offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # Get distinct source names for filter dropdown
    source_names_query = select(ArticleAnalysis.source_name).where(
        ArticleAnalysis.source_name != None,
        ArticleAnalysis.source_name != "",
    ).distinct()
    source_names = [s for s in session.exec(source_names_query).all() if s]

    # Return list without full content/analysis to save bandwidth
    # Pre-load article tags
    from app.models.tag import ArticleTag, Tag
    article_ids = [item.id for item in items]
    article_tag_map: dict[int, list[dict]] = {}
    if article_ids:
        tag_rows = session.exec(
            select(ArticleTag.article_id, Tag.id, Tag.name, Tag.color)
            .join(Tag, Tag.id == ArticleTag.tag_id)
            .where(col(ArticleTag.article_id).in_(article_ids))
        ).all()
        for art_id, tag_id, tag_name, tag_color in tag_rows:
            article_tag_map.setdefault(art_id, []).append({"id": tag_id, "name": tag_name, "color": tag_color})

    # Count related cards per article (by source_url match)
    from app.models.card import Card
    card_count_map: dict[str, int] = {}
    article_urls = [item.source_url for item in items if item.source_url]
    if article_urls:
        card_counts = session.exec(
            select(Card.source, func.count(Card.id))
            .where(col(Card.source).in_(article_urls))
            .group_by(Card.source)
        ).all()
        card_count_map = {url: count for url, count in card_counts}

    result = []
    for item in items:
        result.append({
            "id": item.id,
            "title": item.title,
            "source_url": item.source_url,
            "source_name": item.source_name,
            "publish_date": item.publish_date,
            "quality_score": item.quality_score,
            "quality_reason": item.quality_reason,
            "word_count": item.word_count,
            "status": item.status,
            "is_starred": item.is_starred,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "last_read_at": item.last_read_at.isoformat() if item.last_read_at else None,
            "tags_list": article_tag_map.get(item.id, []),
            "card_count": card_count_map.get(item.source_url, 0),
            "error_state": item.error_state or 0,
        })

    return {"items": result, "total": total, "page": page, "page_size": page_size, "source_names": source_names}


@router.get("/daily-recommendation")
def daily_recommendation(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Return a deterministic daily article recommendation.

    Uses today's date as hash seed so the same article is shown all day.
    Tries quality >= 8.5, then >= 7.5, then any non-archived article.
    """
    from datetime import date
    import hashlib

    for min_score in (8.5, 7.5, 0):
        query = (
            select(ArticleAnalysis.id, ArticleAnalysis.title,
                   ArticleAnalysis.source_name, ArticleAnalysis.quality_score,
                   ArticleAnalysis.word_count, ArticleAnalysis.publish_date,
                   ArticleAnalysis.status)
            .where(ArticleAnalysis.status != "archived")
        )
        if min_score > 0:
            query = query.where(ArticleAnalysis.quality_score >= min_score)
        articles = session.exec(query).all()
        if articles:
            break

    if not articles:
        return {"id": None, "title": None}

    seed = int(hashlib.md5(date.today().isoformat().encode()).hexdigest(), 16)
    pick = articles[seed % len(articles)]
    return {
        "id": pick[0],
        "title": pick[1],
        "source_name": pick[2],
        "quality_score": pick[3],
        "word_count": pick[4],
        "publish_date": pick[5],
        "status": pick[6],
    }


@router.post("/batch-lookup")
def batch_lookup_by_urls(
    data: dict,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Batch lookup articles by source URLs.

    Accepts: { "source_urls": ["url1", "url2", ...] }
    Returns: { "url1": { "id": 1, "title": "...", "quality_score": 8.5, "source_name": "..." }, ... }
    """
    source_urls = data.get("source_urls", [])
    if not source_urls:
        return {}
    # Limit to 200 URLs
    source_urls = source_urls[:200]
    items = session.exec(
        select(ArticleAnalysis).where(col(ArticleAnalysis.source_url).in_(source_urls))
    ).all()
    result: dict[str, dict] = {}
    for item in items:
        if item.source_url and item.source_url not in result:
            result[item.source_url] = {
                "id": item.id,
                "title": item.title,
                "quality_score": item.quality_score,
                "source_name": item.source_name or "",
            }
    return result


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get full article analysis detail."""
    from datetime import datetime, timezone
    item = session.get(ArticleAnalysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Track last read time
    item.last_read_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()

    # Parse analysis_json for structured access
    analysis_data = {}
    if item.analysis_json:
        try:
            analysis_data = json.loads(item.analysis_json)
        except json.JSONDecodeError:
            pass

    return {
        "id": item.id,
        "title": item.title,
        "source_url": item.source_url,
        "source_name": item.source_name,
        "publish_date": item.publish_date,
        "content": item.content,
        "analysis_html": item.analysis_html,
        "analysis_json": analysis_data,
        "quality_score": item.quality_score,
        "quality_reason": item.quality_reason,
        "word_count": item.word_count,
        "status": item.status,
        "is_starred": item.is_starred,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "last_read_at": item.last_read_at.isoformat() if item.last_read_at else None,
        "error_state": item.error_state or 0,
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    data: AnalysisCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a new article analysis (triggers AI analysis as async job)."""
    from app.routers.ai_jobs import create_job, update_job_status

    # Deduplication: check if article with same URL or title already exists
    if data.source_url:
        existing = session.exec(
            select(ArticleAnalysis).where(ArticleAnalysis.source_url == data.source_url)
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"该文章已存在：「{existing.title}」(ID: {existing.id})",
            )
    # Also check by title (fuzzy match)
    existing_title = session.exec(
        select(ArticleAnalysis).where(ArticleAnalysis.title == data.title)
    ).first()
    if existing_title:
        raise HTTPException(
            status_code=409,
            detail=f"同名文章已存在：「{existing_title.title}」(ID: {existing_title.id})",
        )

    # Get AI config (validate before creating job)
    config = session.exec(
        select(AIConfig).where(
            AIConfig.user_id == current_user.id,
            AIConfig.is_enabled == True,
            AIConfig.is_active == True,
        )
    ).first()
    if not config:
        raise HTTPException(
            status_code=400,
            detail="请先在设置中配置AI服务",
        )

    # Save article immediately (so user sees it in the list)
    item = ArticleAnalysis(
        user_id=current_user.id,
        title=data.title,
        source_url=data.source_url,
        source_name=data.source_name,
        publish_date=data.publish_date,
        content=data.content,
        analysis_html=(
            '<section class="analysis-summary">'
            '<h3>⏳ AI分析进行中...</h3>'
            '<p>文章已保存，AI正在分析中，请稍后刷新查看结果。</p>'
            '</section>'
        ),
        analysis_json="",
        quality_score=0,
        quality_reason="分析中...",
        word_count=len(data.content),
        status="new",
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    # Create an AI job for tracking
    job_title = f"分析文章: {data.title[:60]}"
    if data.create_cards:
        job_title += " + 生成卡片"
    job = create_job(session, current_user.id, "add_article", job_title)

    # Run AI analysis in background
    background_tasks.add_task(
        _bg_analyze_article,
        article_id=item.id,
        job_id=job.id,
        user_id=current_user.id,
        config_id=config.id,
        create_cards=data.create_cards,
        title=data.title,
        content=data.content,
        source_url=data.source_url,
        source_name=data.source_name,
        publish_date=data.publish_date,
    )

    return {
        "id": item.id,
        "title": item.title,
        "quality_score": 0,
        "quality_reason": "分析中...",
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "cards_created": 0,
        "ai_failed": False,
        "job_id": job.id,
    }


@router.put("/{analysis_id}/status")
def update_status(
    analysis_id: int,
    data: AnalysisStatusUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update reading status."""
    from datetime import datetime, timezone

    item = session.get(ArticleAnalysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if data.status not in ("new", "reading", "finished", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")

    item.status = data.status
    item.updated_at = datetime.now(timezone.utc)
    if data.status == "finished":
        item.finished_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()
    return {"ok": True}


@router.put("/{analysis_id}/star")
def update_star(
    analysis_id: int,
    data: AnalysisStarUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Toggle star status."""
    from datetime import datetime, timezone

    item = session.get(ArticleAnalysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis not found")

    item.is_starred = data.is_starred
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()
    return {"ok": True}


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: int,
    delete_cards: bool = Query(False, description="Also delete associated flashcards"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete an article analysis, optionally deleting associated cards."""
    item = session.get(ArticleAnalysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Optionally delete associated cards
    if delete_cards and item.source_url:
        from app.models.card import Card
        cards = session.exec(
            select(Card).where(Card.source == item.source_url)
        ).all()
        for card in cards:
            session.delete(card)

    session.delete(item)
    session.commit()


class BatchIdsRequest(BaseModel):
    ids: list[int]
    delete_cards: bool = False


# ── One-click repair ──

@router.post("/repair")
async def repair_failed_articles(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Find all articles with error_state flags and re-process them in background.

    Uses error_state bit flags to determine what repair is needed:
    - CLEANUP_FAILED (bit 0): re-run cleanup → re-analyze → generate cards
    - ANALYSIS_FAILED (bit 1, no CLEANUP_FAILED): re-analyze only → generate cards
    - CARD_GEN_FAILED (bit 2, no other flags): only generate cards
    """
    from app.models.article_analysis import ArticleErrorState
    from app.routers.ai_jobs import create_job

    config = session.exec(
        select(AIConfig).where(
            AIConfig.user_id == current_user.id,
            AIConfig.is_enabled == True,
            AIConfig.is_active == True,
        )
    ).first()
    if not config:
        raise HTTPException(status_code=400, detail="请先在设置中配置AI服务")

    # Find all articles with error_state flags set
    all_error_articles = session.exec(
        select(ArticleAnalysis).where(
            col(ArticleAnalysis.error_state) > 0,  # type: ignore
        )
    ).all()

    # ONE task per article — mode = earliest failed step (cascades forward)
    # Count per-bit for display (an article may have multiple bits set)
    repair_items: list[tuple[int, str]] = []  # (article_id, mode)
    count_cleanup = 0
    count_analysis = 0
    count_cards = 0

    for a in all_error_articles:
        es = a.error_state or 0
        # Count per-bit for display
        if es & ArticleErrorState.CLEANUP_FAILED:
            count_cleanup += 1
        if es & ArticleErrorState.ANALYSIS_FAILED:
            count_analysis += 1
        if es & ArticleErrorState.CARD_GEN_FAILED:
            count_cards += 1
        # Determine ONE repair mode — earliest failed step
        if es & ArticleErrorState.CLEANUP_FAILED:
            repair_items.append((a.id, "cleanup"))
        elif es & ArticleErrorState.ANALYSIS_FAILED:
            repair_items.append((a.id, "reanalyze"))
        elif es & ArticleErrorState.CARD_GEN_FAILED:
            repair_items.append((a.id, "cards_only"))

    if not repair_items:
        return {
            "message": "没有需要修复的文章",
            "total": 0,
            "count_cleanup": 0,
            "count_analysis": 0,
            "count_cards": 0,
            "job_id": None,
        }

    # Create a tracking job
    parts = []
    if count_cleanup:
        parts.append(f"{count_cleanup} 篇清洗失败")
    if count_analysis:
        parts.append(f"{count_analysis} 篇分析失败")
    if count_cards:
        parts.append(f"{count_cards} 篇卡片生成失败")
    job = create_job(
        session, current_user.id, "batch_repair",
        f"一键修复: {', '.join(parts)}",
    )

    background_tasks.add_task(
        _bg_repair_articles,
        job_id=job.id,
        user_id=current_user.id,
        config_id=config.id,
        repair_items=repair_items,
    )

    return {
        "message": "修复任务已启动",
        "total": len(repair_items),
        "count_cleanup": count_cleanup,
        "count_analysis": count_analysis,
        "count_cards": count_cards,
        "job_id": job.id,
    }


def _bg_repair_articles(
    job_id: int,
    user_id: int,
    config_id: int,
    repair_items: list[tuple[int, str]],
):
    """Background thread: repair all failed articles."""
    import asyncio
    asyncio.run(_bg_repair_articles_async(
        job_id, user_id, config_id, repair_items,
    ))


async def _bg_repair_articles_async(
    job_id: int,
    user_id: int,
    config_id: int,
    repair_items: list[tuple[int, str]],
):
    """Async implementation for batch repair.

    Each article gets exactly ONE task based on its earliest failed step:
    - cleanup: re-run cleanup → re-analyze → generate cards
    - reanalyze: re-analyze → generate cards (content already clean)
    - cards_only: only generate cards (analysis already done)

    Processes articles concurrently — each task gets its own DB session
    so SQLite is never accessed concurrently from the same connection.
    """
    import asyncio as _asyncio
    from app.database import engine
    from app.routers.ai_jobs import update_job_status, is_job_cancelled
    from app.services.ai_pipeline import ai_cleanup_content, ai_analyze_article, ai_generate_cards
    from app.models.article_analysis import ArticleErrorState
    from datetime import datetime as dt_, timezone as tz_

    total = len(repair_items)
    success_analyze = 0
    success_cards = 0
    failed_count = 0
    processed = 0

    update_job_status(job_id, "running", progress=5)

    state_lock = _asyncio.Lock()

    # Read rpm_limit once for semaphore sizing
    with Session(engine) as _init_session:
        _init_config = _init_session.get(AIConfig, config_id)
        _rpm = (_init_config.rpm_limit if _init_config else 0) or 0
    _concurrency = max(_rpm * 2, 8)

    try:
        async def _repair_one(aid: int, mode: str):
            """Repair a single article.

            mode: 'cleanup' | 'reanalyze' | 'cards_only'
            """
            nonlocal success_analyze, success_cards, failed_count, processed
            if is_job_cancelled(job_id):
                return
            try:
                with Session(engine) as task_session:
                    config = task_session.get(AIConfig, config_id)
                    article = task_session.get(ArticleAnalysis, aid)
                    if not config or not article:
                        async with state_lock:
                            failed_count += 1
                            processed += 1
                        return

                    art_title = article.title
                    art_content = article.content
                    art_source_url = article.source_url or ""

                    if mode == 'cleanup':
                        # Step 1: Re-run content cleanup
                        cleaned_content, cleanup_ok = await ai_cleanup_content(
                            config, art_title, art_content,
                            user_id=user_id, source="repair",
                        )
                        if cleanup_ok:
                            article.content = cleaned_content
                            art_content = cleaned_content
                            article.error_state = (article.error_state or 0) & ~ArticleErrorState.CLEANUP_FAILED
                            article.updated_at = dt_.now(tz_.utc)
                            task_session.add(article)
                            task_session.commit()
                        else:
                            # Cleanup still failed
                            async with state_lock:
                                failed_count += 1
                            return

                        # Fall through to re-analyze with cleaned content
                        mode = 'reanalyze'

                    if mode == 'reanalyze':
                        # Step 2: Re-run analysis
                        analysis_data = await ai_analyze_article(
                            task_session, config,
                            title=art_title, content=art_content,
                            user_id=user_id, source="repair",
                        )

                        if analysis_data:
                            article.analysis_html = _build_analysis_html(art_title, analysis_data)
                            article.analysis_json = json.dumps(analysis_data, ensure_ascii=False)
                            article.quality_score = analysis_data.get("quality_score", 0)
                            article.quality_reason = analysis_data.get("quality_reason", "")
                            article.error_state = (article.error_state or 0) & ~ArticleErrorState.ANALYSIS_FAILED
                            article.updated_at = dt_.now(tz_.utc)
                            task_session.add(article)
                            task_session.commit()
                            async with state_lock:
                                success_analyze += 1
                        else:
                            # Analysis still failed
                            async with state_lock:
                                failed_count += 1
                            return

                        # Fall through to generate cards
                        mode = 'cards_only'

                    if mode == 'cards_only':
                        # Step 3: Generate cards
                        try:
                            cards_created, _ = await ai_generate_cards(
                                task_session, config,
                                title=art_title, content=art_content,
                                source_url=art_source_url,
                                user_id=user_id, source="repair",
                            )
                            if cards_created > 0:
                                article.error_state = (article.error_state or 0) & ~ArticleErrorState.CARD_GEN_FAILED
                                task_session.add(article)
                                task_session.commit()
                                async with state_lock:
                                    success_cards += cards_created
                            else:
                                async with state_lock:
                                    failed_count += 1
                        except Exception as e:
                            logger.error("Card generation failed for article %d: %s", aid, e)
                            async with state_lock:
                                failed_count += 1

            except Exception as e:
                logger.error("Repair failed for article %d: %s", aid, e, exc_info=True)
                async with state_lock:
                    failed_count += 1
            finally:
                async with state_lock:
                    processed += 1
                    progress = int(5 + (processed / total) * 90)
                update_job_status(job_id, "running", progress=progress)

        _sem = _asyncio.Semaphore(_concurrency)

        async def _throttled(aid: int, mode: str):
            async with _sem:
                await _repair_one(aid, mode)

        tasks = [_throttled(aid, mode) for aid, mode in repair_items]
        await _asyncio.gather(*tasks)

        # Final status
        result_msg = f"修复完成: {success_analyze} 篇成功, {failed_count} 篇失败, 共生成 {success_cards} 张卡片"
        update_job_status(job_id, "completed", progress=100,
                          result_json=json.dumps({
                              "success_articles": success_analyze,
                              "failed": failed_count,
                              "cards_created": success_cards,
                              "message": result_msg,
                          }))
    except Exception as e:
        logger.error("Batch repair crashed: %s", e, exc_info=True)
        update_job_status(job_id, "failed",
                          error_message=f"修复任务异常终止: {type(e).__name__}: {e}")


@router.post("/batch-delete")
def batch_delete(
    data: BatchIdsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Batch delete multiple articles, optionally deleting associated cards."""
    from app.models.card import Card

    count = 0
    for aid in data.ids:
        item = session.get(ArticleAnalysis, aid)
        if item:
            if data.delete_cards and item.source_url:
                cards = session.exec(
                    select(Card).where(Card.source == item.source_url)
                ).all()
                for card in cards:
                    session.delete(card)
            session.delete(item)
            count += 1
    session.commit()
    return {"deleted": count}


@router.post("/batch-reanalyze")
async def batch_reanalyze(
    data: BatchIdsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Batch re-run AI analysis on multiple articles."""
    import httpx

    config = session.exec(
        select(AIConfig).where(
            AIConfig.user_id == current_user.id,
            AIConfig.is_enabled == True,
            AIConfig.is_active == True,
        )
    ).first()
    if not config:
        raise HTTPException(status_code=400, detail="请先在设置中配置AI服务")

    model = get_prompt_model(session, "article_analysis") or config.model_reading or config.model
    url = f"{config.api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    success = 0
    failed = 0
    for aid in data.ids:
        item = session.get(ArticleAnalysis, aid)
        if not item:
            failed += 1
            continue
        try:
            prompt = make_article_analysis_prompt(item.title, item.content)
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": get_prompt(session, "article_analysis", ARTICLE_ANALYSIS_SYSTEM_PROMPT)},
                    {"role": "user", "content": prompt},
                ],
                "temperature": _cfg_temp(config),
                "max_tokens": _cfg_max_tokens(config),
            }
            log_ai_request("batch_reanalyze", model, payload["messages"],
                           temperature=_cfg_temp(config), max_tokens=_cfg_max_tokens(config))

            t0 = time.time()
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()

            elapsed_ms = int((time.time() - t0) * 1000)
            result = resp.json()
            content_text = result["choices"][0]["message"]["content"].strip()
            tokens_used = result.get("usage", {}).get("total_tokens", 0)
            log_ai_response("batch_reanalyze", model, content_text,
                            tokens_used=tokens_used, elapsed_ms=elapsed_ms)
            log_ai_call_to_db(
                feature="batch_reanalyze", model=model,
                config_name=config.name, tokens_used=tokens_used,
                elapsed_ms=elapsed_ms, status="ok",
                input_preview=item.title[:200],
                output_length=len(content_text),
                user_id=current_user.id,
            )

            content_text = _repair_json(content_text)
            analysis_data = json.loads(content_text)

            from datetime import datetime, timezone
            item.analysis_html = _build_analysis_html(item.title, analysis_data)
            item.analysis_json = json.dumps(analysis_data, ensure_ascii=False)
            item.quality_score = analysis_data.get("quality_score", 0)
            item.quality_reason = analysis_data.get("quality_reason", "")
            item.updated_at = datetime.now(timezone.utc)
            session.add(item)
            session.commit()
            success += 1
        except Exception as e:
            logger.error("Batch reanalyze failed for %d: %s", aid, e)
            log_ai_call_to_db(
                feature="batch_reanalyze", model=model,
                config_name=config.name, status="error",
                error_message=str(e)[:500],
                input_preview=(item.title or "")[:200],
                user_id=current_user.id,
            )
            failed += 1

    return {"success": success, "failed": failed, "total": len(data.ids)}


@router.post("/batch-archive")
def batch_archive(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    days: int = Query(7, ge=1, description="Auto-archive articles finished more than N days ago"),
):
    """Auto-archive articles that have been finished for more than N days."""
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = session.exec(
        select(ArticleAnalysis).where(
            ArticleAnalysis.status == "finished",
            ArticleAnalysis.is_starred == False,
            ArticleAnalysis.finished_at != None,
            ArticleAnalysis.finished_at < cutoff,
        )
    ).all()

    count = 0
    for item in items:
        item.status = "archived"
        item.updated_at = datetime.now(timezone.utc)
        session.add(item)
        count += 1
    session.commit()
    return {"archived": count}


@router.post("/{analysis_id}/reanalyze")
async def reanalyze_article(
    analysis_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Re-run AI analysis on an existing article (async job)."""
    from app.routers.ai_jobs import create_job

    item = session.get(ArticleAnalysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis not found")

    config = session.exec(
        select(AIConfig).where(
            AIConfig.user_id == current_user.id,
            AIConfig.is_enabled == True,
            AIConfig.is_active == True,
        )
    ).first()
    if not config:
        raise HTTPException(status_code=400, detail="请先在设置中配置AI服务")

    # Update article status to show re-analysis is in progress
    item.analysis_html = (
        '<section class="analysis-summary">'
        '<h3>⏳ AI正在重新分析...</h3>'
        '<p>请稍后刷新查看结果。</p>'
        '</section>'
    )
    session.add(item)
    session.commit()

    # Create tracking job
    job = create_job(session, current_user.id, "reanalyze", f"重新分析: {item.title[:60]}")

    background_tasks.add_task(
        _bg_analyze_article,
        article_id=item.id,
        job_id=job.id,
        user_id=current_user.id,
        config_id=config.id,
        create_cards=False,
        title=item.title,
        content=item.content,
        source_url=item.source_url,
        source_name=item.source_name,
        publish_date=item.publish_date,
    )

    return {
        "id": item.id,
        "message": "重新分析任务已创建",
        "job_id": job.id,
    }


# ── HTML Builder ──

def _esc(text) -> str:
    """HTML-escape a string to prevent XSS."""
    if not isinstance(text, str):
        text = str(text) if text else ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _build_analysis_html(title: str, data: dict) -> str:
    """Build rich HTML from structured analysis JSON."""
    parts = []

    # Summary
    summary = data.get("summary", "")
    if summary:
        parts.append(
            f'<section class="analysis-summary">'
            f'<h3>📋 文章概述</h3>'
            f'<p>{_esc(summary)}</p>'
            f'</section>'
        )

    # Overall analysis
    overall = data.get("overall_analysis", {})
    if overall:
        parts.append('<section class="analysis-overall">')
        parts.append('<h3>🔍 整体分析</h3>')
        if overall.get("theme"):
            parts.append(f'<p><strong>主题：</strong>{_esc(overall["theme"])}</p>')
        if overall.get("structure"):
            parts.append(f'<p><strong>结构：</strong>{_esc(overall["structure"])}</p>')
        if overall.get("writing_style"):
            parts.append(f'<p><strong>写作特点：</strong>{_esc(overall["writing_style"])}</p>')
        if overall.get("core_arguments"):
            parts.append('<p><strong>核心论点：</strong></p><ul>')
            for arg in overall["core_arguments"]:
                parts.append(f'<li>{_esc(arg)}</li>')
            parts.append('</ul>')
        if overall.get("logical_chain"):
            parts.append(f'<p><strong>论证逻辑：</strong>{_esc(overall["logical_chain"])}</p>')
        if overall.get("shenglun_guidance"):
            parts.append(
                f'<div style="margin:8px 0;padding:10px 14px;background:#ecfdf5;border-left:3px solid #10b981;border-radius:4px;">'
                f'<p><strong>📖 申论写作指导：</strong></p>'
                f'<p style="font-size:13px;line-height:1.8;white-space:pre-wrap;">{_esc(overall["shenglun_guidance"])}</p>'
                f'</div>'
            )
        parts.append('</section>')

    # Highlights
    highlights = data.get("highlights", [])
    if highlights:
        parts.append('<section class="analysis-highlights">')
        parts.append('<h3>✨ 重点标注</h3>')
        color_map = {
            "red": "#ef4444", "orange": "#f97316", "blue": "#3b82f6",
            "green": "#22c55e", "purple": "#a855f7",
        }
        type_labels = {
            "key_point": "核心观点", "policy": "政策要点", "data": "数据支撑",
            "quote": "金句", "terminology": "术语", "exam_focus": "考点",
        }
        for h in highlights:
            color = color_map.get(h.get("color", "blue"), "#3b82f6")
            type_label = type_labels.get(h.get("type", ""), h.get("type", ""))
            parts.append(
                f'<div class="highlight-item" style="border-left:4px solid {color};padding:8px 12px;margin:8px 0;background:{color}10;border-radius:4px;">'
                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">'
                f'<span style="font-size:11px;background:{color};color:white;padding:1px 6px;border-radius:8px;">{_esc(type_label)}</span>'
                f'</div>'
                f'<p style="font-weight:600;color:{color};margin:4px 0;">"{_esc(h.get("text", ""))}"</p>'
                f'<p style="font-size:13px;color:#64748b;margin:4px 0;">{_esc(h.get("annotation", ""))}</p>'
                f'</div>'
            )
        parts.append('</section>')

    # Exam points
    exam = data.get("exam_points", {})
    if exam:
        parts.append('<section class="analysis-exam">')
        parts.append('<h3>🎯 考试要点</h3>')

        # Essay angles (list of dicts with angle + reference_answer)
        essay_angles = exam.get("essay_angles", [])
        if essay_angles:
            parts.append('<div style="margin:8px 0;"><strong>📝 申论角度</strong>')
            for item in essay_angles:
                if isinstance(item, dict):
                    parts.append(
                        f'<div style="margin:6px 0;padding:8px 12px;background:#fffbeb;border-left:3px solid #f59e0b;border-radius:4px;">'
                        f'<p style="font-weight:600;color:#b45309;">{_esc(item.get("angle", ""))}</p>'
                    )
                    if item.get("reference_answer"):
                        parts.append(
                            f'<details style="margin-top:4px;"><summary style="cursor:pointer;color:#92400e;font-size:13px;">📄 参考答案</summary>'
                            f'<p style="font-size:13px;color:#44403c;line-height:1.8;margin:4px 0;white-space:pre-wrap;">{_esc(item["reference_answer"])}</p>'
                            f'</details>'
                        )
                    parts.append('</div>')
                else:
                    parts.append(f'<div style="margin:4px 0;padding:4px 8px;"><li>{_esc(item)}</li></div>')
            parts.append('</div>')

        # Formal terms (list of strings)
        formal_terms = exam.get("formal_terms", [])
        if formal_terms:
            parts.append('<div style="margin:8px 0;"><strong>📋 规范表述</strong><ul>')
            for item in formal_terms:
                parts.append(f'<li>{_esc(item if isinstance(item, str) else str(item))}</li>')
            parts.append('</ul></div>')

        # Golden quotes (list of strings)
        golden_quotes = exam.get("golden_quotes", [])
        if golden_quotes:
            parts.append('<div style="margin:8px 0;"><strong>💬 金句</strong><ul>')
            for item in golden_quotes:
                parts.append(f'<li>{_esc(item if isinstance(item, str) else str(item))}</li>')
            parts.append('</ul></div>')

        # Background knowledge (list of strings)
        bg_knowledge = exam.get("background_knowledge", [])
        if bg_knowledge:
            parts.append('<div style="margin:8px 0;"><strong>📚 背景知识</strong><ul>')
            for item in bg_knowledge:
                parts.append(f'<li>{_esc(item if isinstance(item, str) else str(item))}</li>')
            parts.append('</ul></div>')

        # Possible questions (list of dicts with question, question_type, reference_answer)
        possible_questions = exam.get("possible_questions", [])
        if possible_questions:
            parts.append('<div style="margin:8px 0;"><strong>❓ 可能考法</strong>')
            for item in possible_questions:
                if isinstance(item, dict):
                    qtype = item.get("question_type", "")
                    parts.append(
                        f'<div style="margin:6px 0;padding:8px 12px;background:#fef2f2;border-left:3px solid #ef4444;border-radius:4px;">'
                    )
                    if qtype:
                        parts.append(f'<span style="display:inline-block;font-size:11px;background:#fee2e2;color:#991b1b;padding:1px 6px;border-radius:8px;margin-bottom:4px;">题型：{_esc(qtype)}</span>')
                    parts.append(
                        f'<p style="font-weight:600;color:#b91c1c;margin:0;">{_esc(item.get("question", ""))}</p>'
                    )
                    if item.get("reference_answer"):
                        parts.append(
                            f'<details style="margin-top:4px;"><summary style="cursor:pointer;color:#991b1b;font-size:13px;">📄 参考答案</summary>'
                            f'<p style="font-size:13px;color:#44403c;line-height:1.8;margin:4px 0;white-space:pre-wrap;">{_esc(item["reference_answer"])}</p>'
                            f'</details>'
                        )
                    parts.append('</div>')
                else:
                    parts.append(f'<div style="margin:4px 0;padding:4px 8px;"><li>{_esc(item)}</li></div>')
            parts.append('</div>')

        parts.append('</section>')

    # Vocabulary
    vocab = data.get("vocabulary", [])
    if vocab:
        parts.append('<section class="analysis-vocab">')
        parts.append('<h3>📖 重要术语</h3>')
        for v in vocab:
            parts.append(
                f'<div style="margin:6px 0;padding:6px 10px;background:#f8fafc;border-radius:6px;">'
                f'<strong style="color:#6366f1;">{_esc(v.get("term", ""))}</strong>'
                f'<span style="margin-left:8px;color:#64748b;">{_esc(v.get("explanation", ""))}</span>'
                f'</div>'
            )
        parts.append('</section>')

    # Reading notes
    notes = data.get("reading_notes", "")
    if notes:
        parts.append(
            f'<section class="analysis-notes">'
            f'<h3>📝 阅读笔记</h3>'
            f'<div style="background:#fef3c7;padding:12px 16px;border-radius:8px;line-height:1.8;">{_esc(notes)}</div>'
            f'</section>'
        )

    return "\n".join(parts)


# ── Background task for async article analysis ──

def _bg_analyze_article(
    article_id: int,
    job_id: int,
    user_id: int,
    config_id: int,
    create_cards: bool,
    title: str,
    content: str,
    source_url: str | None,
    source_name: str | None,
    publish_date: str | None,
):
    """Run article analysis + optional card generation in background thread."""
    import asyncio
    asyncio.run(_bg_analyze_article_async(
        article_id, job_id, user_id, config_id, create_cards,
        title, content, source_url, source_name, publish_date,
    ))


async def _bg_analyze_article_async(
    article_id: int,
    job_id: int,
    user_id: int,
    config_id: int,
    create_cards: bool,
    title: str,
    content: str,
    source_url: str | None,
    source_name: str | None,
    publish_date: str | None,
):
    """Async inner implementation for background article analysis."""
    from app.database import engine
    from app.routers.ai_jobs import update_job_status, is_job_cancelled, is_job_cancelled

    with Session(engine) as session:
        try:
            if is_job_cancelled(job_id):
                return
            update_job_status(job_id, "running", progress=10)

            config = session.get(AIConfig, config_id)
            if not config:
                update_job_status(job_id, "failed", error_message="AI配置不存在")
                return

            # Delegate to shared AI analysis pipeline
            from app.services.ai_pipeline import ai_analyze_article

            if is_job_cancelled(job_id):
                return
            update_job_status(job_id, "running", progress=20)

            analysis_data = await ai_analyze_article(
                session, config,
                title=title, content=content,
                user_id=user_id,
                source="reading",
            )

            ai_error_msg = "" if analysis_data else "AI分析失败"

            if is_job_cancelled(job_id):
                return
            update_job_status(job_id, "running", progress=60)

            # Update the article with analysis results
            article = session.get(ArticleAnalysis, article_id)
            if not article:
                update_job_status(job_id, "failed", error_message="文章记录不存在")
                return

            if analysis_data:
                article.analysis_html = _build_analysis_html(title, analysis_data)
                article.analysis_json = json.dumps(analysis_data, ensure_ascii=False)
                article.quality_score = analysis_data.get("quality_score", 0)
                article.quality_reason = analysis_data.get("quality_reason", "")
            else:
                article.analysis_html = (
                    '<section class="analysis-summary">'
                    '<h3>⚠️ AI分析失败</h3>'
                    f'<p>原因：{_esc(ai_error_msg)}</p>'
                    '<p>您可以稍后点击"重新分析"按钮再次尝试。</p>'
                    '</section>'
                )
                article.quality_score = 0
                article.quality_reason = "AI分析失败，待重试"

            session.add(article)
            session.commit()

            # Card generation
            cards_created = 0
            if create_cards and analysis_data:
                update_job_status(job_id, "running", progress=70)
                try:
                    from app.services.ai_pipeline import ai_generate_cards

                    cards_created, _ = await ai_generate_cards(
                        session, config,
                        title=title,
                        content=content,
                        source_url=source_url or "",
                        user_id=user_id,
                        source="reading",
                    )
                except Exception as e:
                    logger.warning("Card generation failed in background: %s", e)
                    log_ai_call_to_db(
                        feature="card_generation", model=config.model_pipeline or config.model,
                        config_name=config.name, status="error",
                        error_message=str(e)[:500], input_preview=title[:200],
                        user_id=user_id,
                    )

            # Mark job as completed
            result_msg = f"文章分析完成"
            if analysis_data:
                result_msg += f"，质量评分: {analysis_data.get('quality_score', 'N/A')}"
            if cards_created:
                result_msg += f"，生成{cards_created}张卡片"
            if not analysis_data:
                update_job_status(job_id, "failed",
                                  error_message=ai_error_msg or "AI分析失败",
                                  result_json=json.dumps({"article_id": article_id}))
            else:
                update_job_status(job_id, "completed", progress=100,
                                  result_json=json.dumps({
                                      "article_id": article_id,
                                      "cards_created": cards_created,
                                      "quality_score": analysis_data.get("quality_score", 0),
                                      "message": result_msg,
                                  }))
        except Exception as e:
            logger.exception("Background article analysis failed: %s", e)
            try:
                update_job_status(job_id, "failed",
                                  error_message=f"分析异常: {str(e)[:300]}")
            except Exception:
                pass


# ── URL Content Fetching ──

class URLFetchRequest(BaseModel):
    url: str


@router.post("/fetch-url")
async def fetch_url_content(
    data: URLFetchRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Fetch article content from a URL — extract title, content, source, date.

    Uses the shared fetch_and_extract_url + AI cleanup pipeline.
    """
    from app.services.source_crawlers import fetch_and_extract_url

    url = data.url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    try:
        result = await fetch_and_extract_url(url, ssrf_check=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法访问该URL: {str(e)}")

    title = result["title"]
    content = result["content"]

    # Clean up content using AI (if user has AI config enabled)
    try:
        config = session.exec(
            select(AIConfig).where(
                AIConfig.user_id == current_user.id,
                AIConfig.is_enabled == True,
            )
        ).first()
        if config and content:
            from app.services.ai_pipeline import ai_cleanup_content
            content, _ = await ai_cleanup_content(
                config, title, content, current_user.id,
                source="reading",
            )
    except Exception as e:
        logger.warning("AI content cleanup skipped in fetch_url_content: %s", e)

    return {
        "title": title,
        "content": content,
        "source_url": url,
        "source_name": result["source_name"],
        "publish_date": result["publish_date"],
    }


# ── Card Creation from Selection ──

class CardFromSelectionRequest(BaseModel):
    selected_text: str
    article_title: str
    article_content: str = ""
    source_url: str = ""
    category_id: int | None = None  # None = AI auto-select
    preview: bool = True  # True = return preview, False = save directly


class SavePreviewCardRequest(BaseModel):
    """Save a previously previewed card (user may have edited fields)."""
    front: str
    back: str
    explanation: str = ""
    distractors: list[str] = []
    tags: str = ""
    category_id: int | None = None
    meta_info: dict | None = None
    source_url: str = ""


@router.post("/create-card")
async def create_card_from_selection(
    data: CardFromSelectionRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a flashcard from selected text in an article, using AI."""
    from app.models.card import Card
    from app.models.deck import Deck
    from app.models.category import Category
    from app.services.prompts import CARD_SYSTEM_PROMPT

    config = session.exec(
        select(AIConfig).where(
            AIConfig.user_id == current_user.id,
            AIConfig.is_enabled == True,
            AIConfig.is_active == True,
        )
    ).first()
    if not config:
        raise HTTPException(status_code=400, detail="请先在设置中配置AI服务")

    # card_from_selection prompt; model override takes priority
    model = get_prompt_model(session, "card_from_selection") or config.model_reading or config.model
    card_from_sel_prompt = get_prompt(session, "card_from_selection", CARD_SYSTEM_PROMPT)

    # Get available categories
    cats = session.exec(select(Category).where(Category.is_active == True)).all()
    cat_list = "、".join(c.name for c in cats)
    cat_map = {c.name: c for c in cats}

    # Build prompt
    context = data.article_content[:2000] if data.article_content else ""
    prompt = (
        f"请根据以下选中的文本，生成一张高质量的学习卡片（JSON对象）。\n\n"
        f"文章标题：{data.article_title}\n"
        f"选中文本：{data.selected_text}\n"
    )
    if context:
        prompt += f"文章上下文（前2000字）：\n{context}\n\n"
    if data.category_id:
        cat = session.get(Category, data.category_id)
        if cat:
            prompt += f"指定分类：{cat.name}\n"
            prompt += "根据此分类的特点，选择最合适的卡片格式。\n"
    else:
        prompt += (
            f"根据选中文本的内容，从以下分类中选择最合适的：{cat_list}\n"
            f"在JSON中用category字段指定分类名。\n"
        )
    prompt += (
        "\n回复一个JSON对象，包含: front, back, explanation, distractors(数组), "
        "tags, category(分类名), meta_info(对象)\n"
        "按照system prompt中对应类型的卡片格式生成。"
    )

    import httpx
    import time as _time
    from app.services.ai_logger import log_ai_request, log_ai_response
    try:
        url = f"{config.api_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": card_from_sel_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": _cfg_temp(config),
            "max_tokens": _cfg_max_tokens(config),
        }

        log_ai_request("card_from_selection", model, payload["messages"], _cfg_temp(config), _cfg_max_tokens(config))
        _t0 = _time.time()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
        _t1 = int((_time.time() - _t0) * 1000)

        content_text = result["choices"][0]["message"]["content"]
        _tokens = result.get("usage", {}).get("total_tokens", 0)
        log_ai_response("card_from_selection", model, content_text, _tokens, _t1)
        log_ai_call_to_db(
            feature="card_from_selection", model=model,
            config_name=config.name, tokens_used=_tokens,
            elapsed_ms=_t1, status="ok",
            input_preview=data.selected_text[:200],
            output_length=len(content_text),
            user_id=current_user.id,
        )
        content_text = _repair_json(content_text)
        card_data = json.loads(content_text)
        # Handle if AI returns array instead of object
        if isinstance(card_data, list):
            card_data = card_data[0] if card_data else {}

    except json.JSONDecodeError as e:
        logger.error("AI response JSON parse error: %s", e)
        log_ai_call_to_db(
            feature="card_from_selection", model=model,
            config_name=config.name, status="error",
            error_message=f"JSON parse error: {str(e)[:400]}",
            input_preview=data.selected_text[:200],
            user_id=current_user.id,
        )
        raise HTTPException(status_code=500, detail="AI返回格式错误，请重试")
    except Exception as e:
        logger.error("AI card creation failed: %s", e)
        log_ai_call_to_db(
            feature="card_from_selection", model=model,
            config_name=config.name, status="error",
            error_message=str(e)[:500],
            input_preview=data.selected_text[:200],
            user_id=current_user.id,
        )
        raise HTTPException(status_code=500, detail=f"AI生成卡片失败: {str(e)}")

    # Resolve category
    cat_name = card_data.get("category", "")
    category = cat_map.get(cat_name) if cat_name else None
    if data.category_id:
        category = session.get(Category, data.category_id) or category

    # Process distractors
    distractors_raw = card_data.get("distractors", [])
    if isinstance(distractors_raw, str):
        try:
            distractors_raw = json.loads(distractors_raw)
        except json.JSONDecodeError:
            distractors_raw = []

    # Process meta_info
    meta_info_raw = card_data.get("meta_info", {})
    if isinstance(meta_info_raw, str):
        try:
            meta_info_raw = json.loads(meta_info_raw)
        except json.JSONDecodeError:
            meta_info_raw = {}

    # Preview mode: return card data without saving
    if data.preview:
        return {
            "preview": True,
            "front": card_data.get("front", data.selected_text),
            "back": card_data.get("back", ""),
            "explanation": card_data.get("explanation", ""),
            "distractors": distractors_raw if isinstance(distractors_raw, list) else [],
            "tags": card_data.get("tags", ""),
            "category_id": category.id if category else None,
            "category_name": category.name if category else "",
            "meta_info": meta_info_raw if isinstance(meta_info_raw, dict) else {},
            "categories": [{"id": c.id, "name": c.name} for c in cats],
        }

    # Direct save mode
    distractors = json.dumps(distractors_raw, ensure_ascii=False) if isinstance(distractors_raw, list) else ""
    meta_info = json.dumps(meta_info_raw, ensure_ascii=False) if isinstance(meta_info_raw, dict) else ""

    # Find or create deck
    deck_name = f"AI-{category.name}" if category else "AI-时政热点"
    deck = session.exec(select(Deck).where(Deck.name == deck_name)).first()
    if not deck:
        deck = Deck(name=deck_name, description=f"AI自动生成的{deck_name[3:]}卡片")
        session.add(deck)
        session.commit()
        session.refresh(deck)

    # Dedup check
    from app.services.dedup_service import DedupService
    dedup_svc = DedupService(session)
    front_text = card_data.get("front", data.selected_text)
    existing = dedup_svc.find_duplicate(front_text, category_id=category.id if category else None)
    if existing:
        return {
            "id": existing.id,
            "front": existing.front,
            "back": existing.back,
            "explanation": existing.explanation or "",
            "category": category.name if category else "",
            "deck": deck.name,
            "duplicate": True,
        }

    card = Card(
        deck_id=deck.id,
        category_id=category.id if category else None,
        front=front_text,
        back=card_data.get("back", ""),
        explanation=card_data.get("explanation", ""),
        distractors=distractors,
        tags=card_data.get("tags", ""),
        meta_info=meta_info,
        source=data.source_url,
        is_ai_generated=True,
    )
    session.add(card)
    deck.card_count = (deck.card_count or 0) + 1
    session.add(deck)
    session.commit()
    session.refresh(card)

    return {
        "id": card.id,
        "front": card.front,
        "back": card.back,
        "explanation": card.explanation,
        "category": category.name if category else "",
        "deck": deck.name,
    }


@router.post("/save-preview-card")
async def save_preview_card(
    data: SavePreviewCardRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Save a card that was previously previewed and potentially edited by the user."""
    from app.models.card import Card
    from app.models.deck import Deck
    from app.models.category import Category

    # Resolve category
    category = None
    if data.category_id:
        category = session.get(Category, data.category_id)

    # Find or create deck
    deck_name = f"AI-{category.name}" if category else "AI-时政热点"
    deck = session.exec(select(Deck).where(Deck.name == deck_name)).first()
    if not deck:
        deck = Deck(name=deck_name, description=f"AI自动生成的{deck_name[3:]}卡片")
        session.add(deck)
        session.commit()
        session.refresh(deck)

    distractors = json.dumps(data.distractors, ensure_ascii=False) if data.distractors else ""
    meta_info = json.dumps(data.meta_info, ensure_ascii=False) if data.meta_info else ""

    # Dedup check
    from app.services.dedup_service import DedupService
    dedup_svc = DedupService(session)
    existing = dedup_svc.find_duplicate(data.front, category_id=data.category_id)
    if existing:
        return {
            "id": existing.id,
            "front": existing.front,
            "back": existing.back,
            "explanation": existing.explanation or "",
            "category": category.name if category else "",
            "deck": deck.name,
            "duplicate": True,
        }

    card = Card(
        deck_id=deck.id,
        category_id=category.id if category else None,
        front=data.front,
        back=data.back,
        explanation=data.explanation,
        distractors=distractors,
        tags=data.tags,
        meta_info=meta_info,
        source=data.source_url,
        is_ai_generated=True,
    )
    session.add(card)
    deck.card_count = (deck.card_count or 0) + 1
    session.add(deck)
    session.commit()
    session.refresh(card)

    return {
        "id": card.id,
        "front": card.front,
        "back": card.back,
        "explanation": card.explanation,
        "category": category.name if category else "",
        "deck": deck.name,
    }


# ── Article Import / Export (no AI involved) ──

@router.get("/export/articles")
def export_articles_json(
    ids: str = Query(default="", description="Comma-separated article IDs to export; empty = all"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Export articles as JSON for backup/import elsewhere. Includes associated cards."""
    from fastapi.responses import Response
    from app.models.card import Card

    query = select(ArticleAnalysis).where(
        ArticleAnalysis.user_id == current_user.id
    )
    if ids:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
        if id_list:
            query = query.where(col(ArticleAnalysis.id).in_(id_list))
    query = query.order_by(ArticleAnalysis.created_at.desc())

    articles = session.exec(query).all()
    export_data = []
    for a in articles:
        # Parse analysis_json string to dict for clean export
        analysis_json_parsed = None
        if a.analysis_json:
            try:
                analysis_json_parsed = json.loads(a.analysis_json) if isinstance(a.analysis_json, str) else a.analysis_json
            except (json.JSONDecodeError, TypeError):
                analysis_json_parsed = a.analysis_json

        # Find associated cards by source_url
        cards_data = []
        if a.source_url:
            linked_cards = session.exec(
                select(Card).where(Card.source == a.source_url)
            ).all()
            for c in linked_cards:
                cards_data.append({
                    "front": c.front,
                    "back": c.back,
                    "explanation": c.explanation,
                    "distractors": c.distractors,
                    "tags": c.tags,
                    "meta_info": c.meta_info,
                    "is_ai_generated": c.is_ai_generated,
                    "category_id": c.category_id,
                    "deck_id": c.deck_id,
                })

        article_entry = {
            "title": a.title,
            "source_url": a.source_url,
            "source_name": a.source_name,
            "publish_date": a.publish_date,
            "content": a.content,
            "quality_score": a.quality_score,
            "quality_reason": a.quality_reason,
            "word_count": a.word_count,
            "status": a.status,
            "is_starred": a.is_starred,
            "analysis_json": analysis_json_parsed,
            "analysis_html": a.analysis_html,
            "error_state": a.error_state,
        }
        if cards_data:
            article_entry["cards"] = cards_data
        export_data.append(article_entry)
    content_str = json.dumps(
        {"articles": export_data, "version": 1, "total": len(export_data)},
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    return Response(
        content=content_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=articles_export.json"},
    )


@router.post("/import/articles")
def import_articles_json(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Import articles from JSON file. Dedup by source_url, then title. No AI involved.
    Also imports associated cards if present."""
    import io
    from app.models.card import Card
    from app.models.deck import Deck

    try:
        raw = file.file.read()
        text = raw.decode("utf-8")
        payload = json.loads(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析JSON文件: {str(e)}")

    articles_list = payload.get("articles", payload) if isinstance(payload, dict) else payload
    if not isinstance(articles_list, list):
        raise HTTPException(status_code=400, detail="JSON格式错误：需要 {\"articles\": [...]} 或 [...]")

    imported = 0
    skipped = 0
    cards_imported = 0
    errors = []

    for i, article_data in enumerate(articles_list):
        try:
            title = article_data.get("title", "").strip()
            source_url = article_data.get("source_url", "").strip()
            content = article_data.get("content", "").strip()

            if not title or not content:
                skipped += 1
                continue

            # Dedup by source_url
            if source_url:
                existing = session.exec(
                    select(ArticleAnalysis).where(ArticleAnalysis.source_url == source_url)
                ).first()
                if existing:
                    skipped += 1
                    continue

            # Dedup by title
            existing = session.exec(
                select(ArticleAnalysis).where(ArticleAnalysis.title == title)
            ).first()
            if existing:
                skipped += 1
                continue

            # Handle analysis_json: convert dict back to string for storage
            analysis_json_val = article_data.get("analysis_json", "")
            if isinstance(analysis_json_val, dict):
                analysis_json_val = json.dumps(analysis_json_val, ensure_ascii=False)

            item = ArticleAnalysis(
                user_id=current_user.id,
                title=title,
                source_url=source_url,
                source_name=article_data.get("source_name", ""),
                publish_date=article_data.get("publish_date", ""),
                content=content,
                analysis_html=article_data.get("analysis_html", ""),
                analysis_json=analysis_json_val,
                quality_score=article_data.get("quality_score", 0),
                quality_reason=article_data.get("quality_reason", ""),
                word_count=article_data.get("word_count", len(content)),
                status=article_data.get("status", "new"),
                is_starred=article_data.get("is_starred", False),
                error_state=article_data.get("error_state", 0),
            )
            session.add(item)
            session.flush()  # Get the item.id
            imported += 1

            # Import associated cards
            cards_list = article_data.get("cards", [])
            for card_data in cards_list:
                front = card_data.get("front", "").strip()
                back = card_data.get("back", "").strip()
                if not front or not back:
                    continue

                # Resolve deck: use provided deck_id if the deck exists
                deck_id = card_data.get("deck_id")
                if deck_id:
                    deck = session.get(Deck, deck_id)
                    if not deck:
                        deck_id = None

                # If no valid deck, find or create a default "精读卡片" deck
                if not deck_id:
                    default_deck = session.exec(
                        select(Deck).where(Deck.name == "精读卡片")
                    ).first()
                    if not default_deck:
                        default_deck = Deck(
                            name="精读卡片",
                            description="从精读文章生成的卡片",
                            category_id=card_data.get("category_id"),
                        )
                        session.add(default_deck)
                        session.flush()
                    deck_id = default_deck.id

                card = Card(
                    deck_id=deck_id,
                    category_id=card_data.get("category_id"),
                    front=front,
                    back=back,
                    explanation=card_data.get("explanation", ""),
                    distractors=card_data.get("distractors", ""),
                    tags=card_data.get("tags", ""),
                    meta_info=card_data.get("meta_info", ""),
                    source=source_url,
                    is_ai_generated=card_data.get("is_ai_generated", False),
                )
                session.add(card)
                cards_imported += 1

        except Exception as e:
            errors.append(f"Article {i}: {str(e)}")

    session.commit()
    msg = f"导入完成：{imported} 篇文章已导入，{skipped} 篇跳过"
    if cards_imported > 0:
        msg += f"，{cards_imported} 张关联卡片已导入"
    return {
        "imported": imported,
        "skipped": skipped,
        "cards_imported": cards_imported,
        "errors": errors,
        "message": msg,
    }


# ── Article-linked card management ──

@router.get("/{analysis_id}/cards")
def get_article_cards(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get cards generated from this article (matched by source_url)."""
    from app.models.card import Card

    item = session.get(ArticleAnalysis, analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis not found")

    cards = []
    if item.source_url:
        cards = list(session.exec(
            select(Card).where(Card.source == item.source_url)
        ).all())

    # Enrich with category names and tags
    from app.models.category import Category
    from app.models.tag import CardTag, Tag

    cat_ids = list({c.category_id for c in cards if c.category_id})
    cat_map: dict[int, str] = {}
    if cat_ids:
        cat_rows = session.exec(select(Category).where(col(Category.id).in_(cat_ids))).all()
        cat_map = {cat.id: cat.name for cat in cat_rows}

    card_ids = [c.id for c in cards]
    tag_map: dict[int, list[dict]] = {}
    if card_ids:
        tag_rows = session.exec(
            select(CardTag.card_id, Tag.id, Tag.name, Tag.color)
            .join(Tag, Tag.id == CardTag.tag_id)
            .where(col(CardTag.card_id).in_(card_ids))
        ).all()
        for cid, tid, tname, tcolor in tag_rows:
            tag_map.setdefault(cid, []).append({"id": tid, "name": tname, "color": tcolor})

    return [{
        "id": c.id,
        "front": c.front,
        "back": c.back,
        "explanation": c.explanation or "",
        "distractors": c.distractors,
        "deck_id": c.deck_id,
        "category_id": c.category_id,
        "category_name": cat_map.get(c.category_id, "") if c.category_id else "",
        "tags": c.tags,
        "tags_list": tag_map.get(c.id, []),
        "meta_info": c.meta_info,
        "source": c.source,
        "is_ai_generated": c.is_ai_generated,
    } for c in cards]


@router.delete("/{analysis_id}/cards/{card_id}")
def delete_article_card(
    analysis_id: int,
    card_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete a specific card linked to this article."""
    from app.models.card import Card
    from app.models.deck import Deck

    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    deck_id = card.deck_id
    session.delete(card)
    session.commit()

    # Update deck card count
    from sqlmodel import func as sqlfunc
    deck = session.get(Deck, deck_id)
    if deck:
        actual_count = session.exec(
            select(sqlfunc.count()).select_from(Card).where(Card.deck_id == deck_id)
        ).one()
        deck.card_count = actual_count
        session.add(deck)
        session.commit()

    return {"ok": True}
