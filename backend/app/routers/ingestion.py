"""Router for ingestion configuration and logs (自动抓取管理)."""

import asyncio as _asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models.ingestion import IngestionConfig, IngestionLog, IngestionUrlCache
from app.models.user import User

logger = logging.getLogger("anki.ingestion")

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])

# ── Singleton lock: only one ingestion job at a time ──
_running_lock = threading.Lock()
_running_log_id: int | None = None  # ID of the currently-running IngestionLog
_cancel_requested: bool = False  # Set to True to request cancellation


# ── Schemas ──

class IngestionConfigResponse(BaseModel):
    id: int
    is_enabled: bool
    schedule_hour: int
    schedule_minute: int
    schedule_type: str
    schedule_days: str
    cron_expression: str
    timezone: str
    quality_threshold: float
    auto_analyze: bool
    auto_create_cards: bool
    concurrency: int = 3
    updated_at: datetime
    model_config = {"from_attributes": True}


class IngestionConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    schedule_hour: int | None = None
    schedule_minute: int | None = None
    schedule_type: str | None = None
    schedule_days: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    quality_threshold: float | None = None
    auto_analyze: bool | None = None
    auto_create_cards: bool | None = None
    concurrency: int | None = None


class IngestionLogResponse(BaseModel):
    id: int
    run_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    sources_processed: int
    articles_fetched: int
    articles_analyzed: int
    articles_skipped: int
    cards_created: int
    errors_count: int
    log_detail: str  # JSON string with structured log entries
    timezone: str = "Asia/Shanghai"  # Timezone used for log entry times
    model_config = {"from_attributes": True}


# ── Config ──

@router.get("/config", response_model=IngestionConfigResponse)
def get_ingestion_config(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get ingestion config (creates default if none exists)."""
    cfg = session.exec(select(IngestionConfig)).first()
    if not cfg:
        cfg = IngestionConfig()
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    return IngestionConfigResponse.model_validate(cfg)


@router.put("/config", response_model=IngestionConfigResponse)
def update_ingestion_config(
    data: IngestionConfigUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update ingestion config."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    cfg = session.exec(select(IngestionConfig)).first()
    if not cfg:
        cfg = IngestionConfig()
        session.add(cfg)
        session.commit()
        session.refresh(cfg)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cfg, key, value)
    cfg.updated_at = datetime.now(timezone.utc)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)

    # Reschedule the ingestion job
    from app.services.scheduler import reschedule_ingestion
    reschedule_ingestion(cfg)

    return IngestionConfigResponse.model_validate(cfg)


# ── Logs ──

@router.get("/logs", response_model=list[IngestionLogResponse])
def list_ingestion_logs(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List recent ingestion logs (newest first).
    
    Automatically marks any 'running' logs older than 30 minutes as
    'error' (interrupted), since the pipeline must have crashed or
    the server restarted.
    """
    # Fix stale running logs — use updated_at (last activity) instead of started_at
    stale_cutoff = datetime.now(timezone.utc) - __import__('datetime').timedelta(minutes=30)
    stale_logs = session.exec(
        select(IngestionLog)
        .where(IngestionLog.status == "running")
        .where(IngestionLog.updated_at < stale_cutoff)
    ).all()
    if stale_logs:
        # Resolve configured timezone for log entry timestamps
        cfg = session.exec(select(IngestionConfig)).first()
        try:
            _stale_tz = ZoneInfo((cfg.timezone if cfg else None) or "Asia/Shanghai")
        except Exception:
            _stale_tz = ZoneInfo("Asia/Shanghai")
        for sl in stale_logs:
            sl.status = "error"
            sl.finished_at = sl.finished_at or datetime.now(timezone.utc)
            # Append an entry to the log detail
            try:
                entries = json.loads(sl.log_detail) if sl.log_detail else []
            except (json.JSONDecodeError, TypeError):
                entries = []
            entries.append({
                "time": datetime.now(_stale_tz).strftime("%H:%M:%S"),
                "level": "error",
                "source": "系统",
                "message": "任务运行超时或服务器中断，已自动标记为错误",
            })
            sl.log_detail = json.dumps(entries, ensure_ascii=False)
            session.add(sl)
        session.commit()

    logs = session.exec(
        select(IngestionLog)
        .order_by(IngestionLog.started_at.desc())  # type: ignore[union-attr]
        .limit(limit)
    ).all()

    # Get config timezone for display
    cfg = session.exec(select(IngestionConfig)).first()
    tz_name = cfg.timezone if cfg else "Asia/Shanghai"

    result = []
    for l in logs:
        resp = IngestionLogResponse.model_validate(l)
        resp.timezone = tz_name
        result.append(resp)
    return result


@router.get("/scheduler-status")
def get_scheduler_status(
    current_user: User = Depends(get_current_user),
):
    """Get scheduler debug information (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    from app.services.scheduler import get_scheduler_status
    return get_scheduler_status()


@router.delete("/logs")
def clear_ingestion_logs(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Clear all ingestion logs."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    logs = session.exec(select(IngestionLog)).all()
    for log in logs:
        session.delete(log)
    session.commit()
    return {"ok": True, "deleted": len(logs)}


# ── Trigger ──

def _is_running() -> bool:
    """Check if an ingestion job is currently running."""
    return _running_log_id is not None


def _is_cancel_requested() -> bool:
    """Check if cancellation has been requested for the current job."""
    return _cancel_requested


async def _run_pipeline_internal(run_type: str = "manual"):
    """Run the ingestion pipeline as a background task.

    Uses a singleton lock so only one job runs at a time.
    Checks _cancel_requested between each article to allow early stop.
    """
    global _running_log_id, _cancel_requested

    from sqlmodel import Session as SyncSession
    from app.database import engine as db_engine
    from app.models.article_source import ArticleSource
    from app.models.article_analysis import ArticleAnalysis
    from app.models.ai_config import AIConfig
    from app.models.user import User
    from app.services.source_crawlers import (
        crawl_rmrb, crawl_qiushi, crawl_normal_source,
        fetch_and_extract_url, extract_article_date,
    )

    # ── Singleton check ──
    acquired = _running_lock.acquire(blocking=False)
    if not acquired:
        # Another job is already running — create a cancelled log entry
        with SyncSession(db_engine) as session:
            cfg = session.exec(select(IngestionConfig)).first()
            try:
                _tz = ZoneInfo((cfg.timezone if cfg else None) or "Asia/Shanghai")
            except Exception:
                _tz = ZoneInfo("Asia/Shanghai")

            cancel_entries = [{
                "time": datetime.now(_tz).strftime("%H:%M:%S"),
                "level": "error",
                "source": "系统",
                "message": f"已有抓取任务正在运行（日志 #{_running_log_id}），本次{('定时' if run_type == 'scheduled' else '手动')}抓取被跳过",
            }]
            skip_log = IngestionLog(
                run_type=run_type,
                status="cancelled",
                finished_at=datetime.now(timezone.utc),
                log_detail=json.dumps(cancel_entries, ensure_ascii=False),
            )
            session.add(skip_log)
            session.commit()
            logger.info("Ingestion skipped: another job is already running (log #%s)", _running_log_id)
        return

    try:
        _cancel_requested = False

        with SyncSession(db_engine) as session:
            # Load config
            cfg = session.exec(select(IngestionConfig)).first()
            if not cfg:
                cfg = IngestionConfig()
                session.add(cfg)
                session.commit()
                session.refresh(cfg)

            # Create log entry
            log = IngestionLog(run_type=run_type, status="running")
            session.add(log)
            session.commit()
            session.refresh(log)
            _running_log_id = log.id

            entries: list[dict] = []

            # Resolve timezone for log entry timestamps
            try:
                _tz = ZoneInfo(cfg.timezone or "Asia/Shanghai")
            except Exception:
                _tz = ZoneInfo("Asia/Shanghai")

            def add_entry(level: str, source: str, message: str):
                entries.append({
                    "time": datetime.now(_tz).strftime("%H:%M:%S"),
                    "level": level,
                    "source": source,
                    "message": message,
                })

            try:
                # Check AI availability
                config = session.exec(
                    select(AIConfig).where(AIConfig.is_enabled == True)
                ).first()
                if not config or not config.api_key:
                    add_entry("error", "系统", "未配置AI服务，无法进行抓取分析")
                    log.status = "error"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                _max_retries = getattr(config, "max_retries", 3) or 3

                # Collect dedup URLs
                analyzed_urls = set()
                existing_analyses = session.exec(
                    select(ArticleAnalysis.source_url).where(ArticleAnalysis.source_url != "")
                ).all()
                for url in existing_analyses:
                    if url:
                        analyzed_urls.add(url.strip())

                # Load rejected URL cache (url → quality_score)
                _cache_rows = session.exec(select(IngestionUrlCache)).all()
                url_score_cache: dict[str, float] = {r.url: r.quality_score for r in _cache_rows}

                import re
                import time as _time

                total_fetched = 0
                total_analyzed = 0
                total_skipped = 0
                total_cards = 0
                total_errors = 0

                # ═══════════════════════════════════════════════════════════
                # Phase 1: Gather all articles from ALL sources
                # ═══════════════════════════════════════════════════════════
                all_articles: list[dict] = []

                db_sources = session.exec(
                    select(ArticleSource).where(ArticleSource.is_enabled == True)
                ).all()

                system_sources = [s for s in db_sources if s.is_system]
                normal_sources = [s for s in db_sources if not s.is_system]

                for sys_src in system_sources:
                    if _cancel_requested:
                        break
                    log.sources_processed += 1
                    try:
                        if "人民日报" in sys_src.name:
                            add_entry("info", "人民日报", "开始抓取今日人民日报电子版...")
                            rmrb_articles = await crawl_rmrb()
                            for art in rmrb_articles:
                                art["source_name"] = sys_src.name
                                art["category"] = sys_src.category
                            all_articles.extend(rmrb_articles)
                            add_entry("info", "人民日报", f"发现 {len(rmrb_articles)} 篇重要文章")
                        elif "求是" in sys_src.name:
                            add_entry("info", "求是杂志", "开始抓取求是杂志最新一期...")
                            qs_articles = await crawl_qiushi()
                            for art in qs_articles:
                                art["source_name"] = sys_src.name
                                art["category"] = sys_src.category
                            all_articles.extend(qs_articles)
                            add_entry("info", "求是杂志", f"发现 {len(qs_articles)} 篇文章")
                    except Exception as e:
                        add_entry("error", sys_src.name, f"特殊来源抓取失败: {str(e)[:150]}")
                        total_errors += 1

                for src in normal_sources:
                    if _cancel_requested:
                        break
                    log.sources_processed += 1
                    add_entry("info", src.name, f"开始抓取: {src.url}")
                    try:
                        src_articles = await crawl_normal_source(
                            src.name, src.url, src.source_type,
                        )
                        for art in src_articles:
                            art["source_name"] = src.name
                            art["category"] = src.category
                        all_articles.extend(src_articles)
                        add_entry("info", src.name, f"发现 {len(src_articles)} 篇文章")
                    except Exception as e:
                        add_entry("error", src.name, f"抓取来源失败: {str(e)[:150]}")
                        total_errors += 1

                # Check cancel after phase 1
                if _cancel_requested:
                    add_entry("warn", "系统", "⚠️ 用户取消了抓取任务")
                    log.status = "cancelled"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                total_fetched = len(all_articles)
                add_entry("info", "系统", f"共发现 {total_fetched} 篇文章，开始逐篇处理...")

                # Persist fetched count immediately so the UI shows it
                log.articles_fetched = total_fetched
                log.updated_at = datetime.now(timezone.utc)
                log.log_detail = json.dumps(entries, ensure_ascii=False)
                session.add(log)
                session.commit()

                # ═══════════════════════════════════════════════════════════
                # Phase 2: Process each article (concurrently)
                # ═══════════════════════════════════════════════════════════

                admin_user = session.exec(select(User).where(User.is_admin == True)).first()
                if not admin_user:
                    admin_user = session.exec(select(User)).first()

                concurrency = getattr(cfg, "concurrency", 3) or 3
                add_entry("info", "系统", f"并发处理数: {concurrency}")
                sem = _asyncio.Semaphore(concurrency)
                state_lock = _asyncio.Lock()

                from app.services.ai_pipeline import ai_cleanup_content, ai_analyze_article, ai_generate_cards
                from app.routers.article_analysis import _build_analysis_html

                async def _process_one_article(art: dict):
                    nonlocal total_analyzed, total_skipped, total_cards, total_errors

                    # ── Cancel check ──
                    if _cancel_requested:
                        return

                    url = art["url"]

                    async with state_lock:
                        if url in analyzed_urls:
                            add_entry("skip", art.get("section", art.get("source_name", "")),
                                      f"已分析过，跳过: {art['title'][:40]}")
                            total_skipped += 1
                            return
                        # Check rejected URL cache — skip if cached score still below threshold
                        if url in url_score_cache:
                            cached_score = url_score_cache[url]
                            if cached_score < cfg.quality_threshold:
                                add_entry("skip", art.get("section", art.get("source_name", "")),
                                          f"缓存评分 {cached_score} < 阈值 {cfg.quality_threshold}，跳过: {art['title'][:40]}")
                                total_skipped += 1
                                return
                            # Threshold lowered — cached score now qualifies, re-analyze
                            add_entry("info", art.get("section", art.get("source_name", "")),
                                      f"阈值已调低至 {cfg.quality_threshold}，重新分析（缓存评分 {cached_score}）: {art['title'][:40]}")
                        # Claim this URL to avoid duplicates from concurrent tasks
                        analyzed_urls.add(url)

                    source_label = art.get("section", art.get("source_name", ""))

                    async with sem:
                        if _cancel_requested:
                            return

                        try:
                            fetch_result = await fetch_and_extract_url(url)
                            body_text = fetch_result["content"]
                            extracted_title = fetch_result["title"]
                            title = art["title"] or extracted_title

                            publish_date = art.get("date", "") or ""
                            if not publish_date:
                                publish_date = fetch_result["publish_date"]

                            if len(body_text) < 500:
                                async with state_lock:
                                    add_entry("skip", source_label,
                                              f"正文太短（{len(body_text)}字），跳过: {title[:40]}")
                                    total_skipped += 1
                                    analyzed_urls.discard(url)  # wasn't actually analyzed
                                return
                            
                            # ── AI Step 1: Content cleanup ──
                            body_text = await ai_cleanup_content(
                                config, title, body_text,
                                user_id=admin_user.id if admin_user else 1,
                                source="crawl",
                            )

                            if _cancel_requested:
                                return

                            async with state_lock:
                                add_entry("info", source_label, f"正在分析: {title}（{len(body_text)}字）")
                            
                            # ── AI Step 2: Article analysis ──
                            analysis_data = await ai_analyze_article(
                                session, config, title, body_text,
                                user_id=admin_user.id if admin_user else 1,
                                source="crawl",
                            )
                            if analysis_data is None:
                                async with state_lock:
                                    add_entry("error", source_label, f"AI分析失败: {title[:40]}")
                                    total_errors += 1
                                    analyzed_urls.discard(url)
                                return

                            quality = analysis_data.get("quality_score", 5)

                            if quality < cfg.quality_threshold:
                                async with state_lock:
                                    add_entry("skip", source_label,
                                              f"质量 {quality} < 阈值 {cfg.quality_threshold}，跳过该篇文章（{title}，{art['url']}）")
                                    total_skipped += 1
                                    # Cache score so next run can skip without AI
                                    _prev = session.exec(
                                        select(IngestionUrlCache).where(IngestionUrlCache.url == url)
                                    ).first()
                                    if _prev:
                                        _prev.quality_score = quality
                                        _prev.title = title[:200]
                                        _prev.analyzed_at = datetime.now(timezone.utc)
                                    else:
                                        session.add(IngestionUrlCache(
                                            url=url, quality_score=quality, title=title[:200],
                                        ))
                                    session.commit()
                                    url_score_cache[url] = quality
                                return

                            analysis_html = _build_analysis_html(title, analysis_data)

                            # DB write under lock (SQLite single-writer)
                            async with state_lock:
                                # Remove from rejected cache if previously cached
                                _prev = session.exec(
                                    select(IngestionUrlCache).where(IngestionUrlCache.url == url)
                                ).first()
                                if _prev:
                                    session.delete(_prev)
                                    url_score_cache.pop(url, None)

                                analysis_item = ArticleAnalysis(
                                    user_id=admin_user.id if admin_user else 1,
                                    title=title,
                                    source_url=url,
                                    source_name=art.get("source_name", source_label),
                                    publish_date=publish_date[:20] if publish_date else "",
                                    content=body_text,
                                    analysis_html=analysis_html,
                                    analysis_json=json.dumps(analysis_data, ensure_ascii=False),
                                    quality_score=quality,
                                    quality_reason=analysis_data.get("quality_reason", ""),
                                    word_count=len(body_text),
                                    status="new",
                                )
                                session.add(analysis_item)
                                session.commit()
                                total_analyzed += 1
                                add_entry("info", source_label, f"✅ 分析完成 质量={quality}/10: {title[:40]}")

                            # ── AI Step 3: Card generation ──
                            if not _cancel_requested:
                                cards_created_this, _ = await ai_generate_cards(
                                    session, config, title, body_text,
                                    source_url=url,
                                    user_id=admin_user.id if admin_user else 1,
                                    source="crawl",
                                )
                                async with state_lock:
                                    total_cards += cards_created_this
                                    add_entry("info", source_label, f"🃏 生成 {cards_created_this} 张卡片")

                        except json.JSONDecodeError as e:
                            async with state_lock:
                                add_entry("error", source_label, f"AI返回JSON解析失败: {str(e)[:100]}")
                                total_errors += 1
                        except Exception as e:
                            async with state_lock:
                                add_entry("error", source_label, f"处理文章失败: {str(e)[:150]}")
                                total_errors += 1
                        finally:
                            # Flush stats to DB so frontend sees progress
                            async with state_lock:
                                log.articles_analyzed = total_analyzed
                                log.articles_skipped = total_skipped
                                log.cards_created = total_cards
                                log.errors_count = total_errors
                                log.updated_at = datetime.now(timezone.utc)
                                log.log_detail = json.dumps(entries, ensure_ascii=False)
                                session.add(log)
                                session.commit()

                # Launch all article tasks concurrently (semaphore limits parallelism)
                tasks = [_process_one_article(art) for art in all_articles]
                await _asyncio.gather(*tasks)

                if _cancel_requested:
                    add_entry("info", "系统",
                              f"抓取已取消: 发现{total_fetched}篇, 分析{total_analyzed}篇, "
                              f"跳过{total_skipped}篇, 生成{total_cards}张卡片, 错误{total_errors}个")
                    log.status = "cancelled"
                else:
                    add_entry("info", "系统",
                              f"✅ 抓取完成: 发现{total_fetched}篇, 分析{total_analyzed}篇, "
                              f"跳过{total_skipped}篇, 生成{total_cards}张卡片, 错误{total_errors}个")
                    log.status = "success"

                log.articles_fetched = total_fetched
                log.articles_analyzed = total_analyzed
                log.articles_skipped = total_skipped
                log.cards_created = total_cards
                log.errors_count = total_errors

            except Exception as e:
                add_entry("error", "系统", f"抓取过程异常: {str(e)[:200]}")
                log.status = "error"

            log.finished_at = datetime.now(timezone.utc)
            log.updated_at = datetime.now(timezone.utc)
            log.log_detail = json.dumps(entries, ensure_ascii=False)
            session.add(log)
            session.commit()

    finally:
        # Safety: ensure log status is updated even if the main commit failed
        log_id_to_fix = _running_log_id
        _running_log_id = None
        _cancel_requested = False
        _running_lock.release()
        if log_id_to_fix is not None:
            try:
                from sqlmodel import Session as SyncSession
                from app.database import engine as db_engine
                with SyncSession(db_engine) as fix_session:
                    stuck = fix_session.get(IngestionLog, log_id_to_fix)
                    if stuck and stuck.status == "running":
                        stuck.status = "error"
                        stuck.finished_at = datetime.now(timezone.utc)
                        fix_session.add(stuck)
                        fix_session.commit()
                        logger.warning("Safety: forced ingestion log #%d from 'running' to 'error'", log_id_to_fix)
            except Exception as e:
                logger.error("Failed to fix stuck ingestion log #%d: %s", log_id_to_fix, e)


async def _run_rmrb_backfill_internal(start_date_str: str, end_date_str: str):
    """Run RMRB backfill pipeline as a background task.

    Similar to _run_pipeline_internal but scoped to RMRB date range only.
    Reuses the same singleton lock, log entry, and article processing logic.
    """
    global _running_log_id, _cancel_requested

    from sqlmodel import Session as SyncSession
    from app.database import engine as db_engine
    from app.models.article_analysis import ArticleAnalysis
    from app.models.ai_config import AIConfig
    from app.models.user import User
    from app.services.source_crawlers import crawl_rmrb_range, fetch_and_extract_url

    acquired = _running_lock.acquire(blocking=False)
    if not acquired:
        logger.info("RMRB backfill skipped: another job is already running")
        return

    try:
        _cancel_requested = False

        with SyncSession(db_engine) as session:
            cfg = session.exec(select(IngestionConfig)).first()
            if not cfg:
                cfg = IngestionConfig()
                session.add(cfg)
                session.commit()
                session.refresh(cfg)

            log = IngestionLog(
                run_type="backfill",
                status="running",
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            _running_log_id = log.id

            entries: list[dict] = []

            try:
                _tz = ZoneInfo(cfg.timezone or "Asia/Shanghai")
            except Exception:
                _tz = ZoneInfo("Asia/Shanghai")

            def add_entry(level: str, source: str, message: str):
                entries.append({
                    "time": datetime.now(_tz).strftime("%H:%M:%S"),
                    "level": level,
                    "source": source,
                    "message": message,
                })

            try:
                # Check AI availability
                config = session.exec(
                    select(AIConfig).where(AIConfig.is_enabled == True)
                ).first()
                if not config or not config.api_key:
                    add_entry("error", "系统", "未配置AI服务，无法进行抓取分析")
                    log.status = "error"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                _max_retries = getattr(config, "max_retries", 3) or 3

                # Collect dedup URLs
                analyzed_urls = set()
                existing_analyses = session.exec(
                    select(ArticleAnalysis.source_url).where(ArticleAnalysis.source_url != "")
                ).all()
                for url in existing_analyses:
                    if url:
                        analyzed_urls.add(url.strip())

                # Load rejected URL cache
                _cache_rows = session.exec(select(IngestionUrlCache)).all()
                url_score_cache: dict[str, float] = {r.url: r.quality_score for r in _cache_rows}

                import re
                import time as _time

                total_fetched = 0
                total_analyzed = 0
                total_skipped = 0
                total_cards = 0
                total_errors = 0

                # ═══ Phase 1: Crawl RMRB for date range ═══
                add_entry("info", "人民日报", f"开始回溯抓取: {start_date_str} → {end_date_str}")

                start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")

                async def _progress_cb(date_str: str, count: int):
                    if _cancel_requested:
                        return
                    if count < 0:
                        add_entry("warn", "人民日报", f"{date_str}: 抓取失败")
                    elif count == 0:
                        add_entry("info", "人民日报", f"{date_str}: 无文章（可能是休刊日）")
                    else:
                        add_entry("info", "人民日报", f"{date_str}: 发现 {count} 篇新文章")
                    # Flush progress
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    log.updated_at = datetime.now(timezone.utc)
                    session.add(log)
                    session.commit()

                all_articles = await crawl_rmrb_range(
                    start_dt, end_dt, progress_callback=_progress_cb,
                )

                if _cancel_requested:
                    add_entry("warn", "系统", "⚠️ 用户取消了回溯任务")
                    log.status = "cancelled"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                # Tag all articles with source info
                for art in all_articles:
                    art["source_name"] = "人民日报"
                    art["category"] = "时政热点"

                total_fetched = len(all_articles)
                add_entry("info", "人民日报", f"回溯完成，共发现 {total_fetched} 篇文章，开始逐篇处理...")

                log.articles_fetched = total_fetched
                log.sources_processed = 1
                log.updated_at = datetime.now(timezone.utc)
                log.log_detail = json.dumps(entries, ensure_ascii=False)
                session.add(log)
                session.commit()

                # ═══ Phase 2: Process each article ═══
                admin_user = session.exec(select(User).where(User.is_admin == True)).first()
                if not admin_user:
                    admin_user = session.exec(select(User)).first()

                concurrency = getattr(cfg, "concurrency", 3) or 3
                sem = _asyncio.Semaphore(concurrency)
                state_lock = _asyncio.Lock()

                from app.services.ai_pipeline import ai_cleanup_content, ai_analyze_article, ai_generate_cards
                from app.routers.article_analysis import _build_analysis_html

                async def _process_one_article(art: dict):
                    nonlocal total_analyzed, total_skipped, total_cards, total_errors

                    if _cancel_requested:
                        return

                    url = art["url"]

                    async with state_lock:
                        if url in analyzed_urls:
                            add_entry("skip", "人民日报",
                                      f"已分析过，跳过: {art['title'][:40]}")
                            total_skipped += 1
                            return
                        if url in url_score_cache:
                            cached_score = url_score_cache[url]
                            if cached_score < cfg.quality_threshold:
                                add_entry("skip", "人民日报",
                                          f"缓存评分 {cached_score} < 阈值 {cfg.quality_threshold}，跳过: {art['title'][:40]}")
                                total_skipped += 1
                                return
                        analyzed_urls.add(url)

                    source_label = art.get("section", "人民日报")

                    async with sem:
                        if _cancel_requested:
                            return

                        try:
                            fetch_result = await fetch_and_extract_url(url)
                            body_text = fetch_result["content"]
                            extracted_title = fetch_result["title"]
                            title = art["title"] or extracted_title

                            publish_date = art.get("date", "") or ""
                            if not publish_date:
                                publish_date = fetch_result["publish_date"]

                            if len(body_text) < 600:
                                async with state_lock:
                                    add_entry("skip", source_label,
                                              f"正文太短（{len(body_text)}字），跳过: {title[:40]}")
                                    total_skipped += 1
                                    analyzed_urls.discard(url)
                                return

                            body_text = await ai_cleanup_content(
                                config, title, body_text,
                                user_id=admin_user.id if admin_user else 1,
                                source="crawl",
                            )

                            if _cancel_requested:
                                return

                            async with state_lock:
                                add_entry("info", source_label, f"正在分析: {title}（{len(body_text)}字）")

                            analysis_data = await ai_analyze_article(
                                session, config, title, body_text,
                                user_id=admin_user.id if admin_user else 1,
                                source="crawl",
                            )
                            if analysis_data is None:
                                async with state_lock:
                                    add_entry("error", source_label, f"AI分析失败: {title[:40]}")
                                    total_errors += 1
                                    analyzed_urls.discard(url)
                                return

                            quality = analysis_data.get("quality_score", 5)

                            if quality < cfg.quality_threshold:
                                async with state_lock:
                                    add_entry("skip", source_label,
                                              f"质量 {quality} < 阈值 {cfg.quality_threshold}，跳过: {title[:40]}")
                                    total_skipped += 1
                                    _prev = session.exec(
                                        select(IngestionUrlCache).where(IngestionUrlCache.url == url)
                                    ).first()
                                    if _prev:
                                        _prev.quality_score = quality
                                        _prev.title = title[:200]
                                        _prev.analyzed_at = datetime.now(timezone.utc)
                                    else:
                                        session.add(IngestionUrlCache(
                                            url=url, quality_score=quality, title=title[:200],
                                        ))
                                    session.commit()
                                    url_score_cache[url] = quality
                                return

                            analysis_html = _build_analysis_html(title, analysis_data)

                            async with state_lock:
                                _prev = session.exec(
                                    select(IngestionUrlCache).where(IngestionUrlCache.url == url)
                                ).first()
                                if _prev:
                                    session.delete(_prev)
                                    url_score_cache.pop(url, None)

                                analysis_item = ArticleAnalysis(
                                    user_id=admin_user.id if admin_user else 1,
                                    title=title,
                                    source_url=url,
                                    source_name=art.get("source_name", source_label),
                                    publish_date=publish_date[:20] if publish_date else "",
                                    content=body_text,
                                    analysis_html=analysis_html,
                                    analysis_json=json.dumps(analysis_data, ensure_ascii=False),
                                    quality_score=quality,
                                    quality_reason=analysis_data.get("quality_reason", ""),
                                    word_count=len(body_text),
                                    status="new",
                                )
                                session.add(analysis_item)
                                session.commit()
                                total_analyzed += 1
                                add_entry("info", source_label, f"✅ 分析完成 质量={quality}/10: {title[:40]}")

                            cards_created_this = 0
                            if not _cancel_requested:
                                cards_created_this, _ = await ai_generate_cards(
                                    session, config, title, body_text,
                                    source_url=url,
                                    user_id=admin_user.id if admin_user else 1,
                                    source="crawl",
                                )
                            async with state_lock:
                                total_cards += cards_created_this
                                if cards_created_this:
                                    add_entry("info", source_label, f"🃏 生成 {cards_created_this} 张卡片")

                        except json.JSONDecodeError as e:
                            async with state_lock:
                                add_entry("error", source_label, f"AI返回JSON解析失败: {str(e)[:100]}")
                                total_errors += 1
                        except Exception as e:
                            async with state_lock:
                                add_entry("error", source_label, f"处理文章失败: {str(e)[:150]}")
                                total_errors += 1
                        finally:
                            async with state_lock:
                                log.articles_analyzed = total_analyzed
                                log.articles_skipped = total_skipped
                                log.cards_created = total_cards
                                log.errors_count = total_errors
                                log.updated_at = datetime.now(timezone.utc)
                                log.log_detail = json.dumps(entries, ensure_ascii=False)
                                session.add(log)
                                session.commit()

                tasks = [_process_one_article(art) for art in all_articles]
                await _asyncio.gather(*tasks)

                if _cancel_requested:
                    add_entry("info", "系统",
                              f"回溯已取消: 发现{total_fetched}篇, 分析{total_analyzed}篇, "
                              f"跳过{total_skipped}篇, 生成{total_cards}张卡片, 错误{total_errors}个")
                    log.status = "cancelled"
                else:
                    add_entry("info", "系统",
                              f"✅ 回溯完成: 发现{total_fetched}篇, 分析{total_analyzed}篇, "
                              f"跳过{total_skipped}篇, 生成{total_cards}张卡片, 错误{total_errors}个")
                    log.status = "success"

                log.articles_fetched = total_fetched
                log.articles_analyzed = total_analyzed
                log.articles_skipped = total_skipped
                log.cards_created = total_cards
                log.errors_count = total_errors

            except Exception as e:
                add_entry("error", "系统", f"回溯过程异常: {str(e)[:200]}")
                log.status = "error"

            log.finished_at = datetime.now(timezone.utc)
            log.updated_at = datetime.now(timezone.utc)
            log.log_detail = json.dumps(entries, ensure_ascii=False)
            session.add(log)
            session.commit()

    finally:
        # Safety: ensure log status is updated even if the main commit failed
        log_id_to_fix = _running_log_id
        _running_log_id = None
        _cancel_requested = False
        _running_lock.release()
        if log_id_to_fix is not None:
            try:
                with SyncSession(db_engine) as fix_session:
                    stuck = fix_session.get(IngestionLog, log_id_to_fix)
                    if stuck and stuck.status == "running":
                        stuck.status = "error"
                        stuck.finished_at = datetime.now(timezone.utc)
                        fix_session.add(stuck)
                        fix_session.commit()
                        logger.warning("Safety: forced RMRB backfill log #%d from 'running' to 'error'", log_id_to_fix)
            except Exception as e:
                logger.error("Failed to fix stuck RMRB log #%d: %s", log_id_to_fix, e)


async def _run_qiushi_backfill_internal(issues: list[dict]):
    """Run 求是杂志 backfill pipeline for one or more issues.

    Each dict in issues must contain 'issue_url' and 'issue_name'.
    Issues are crawled sequentially, then all articles are processed together.
    """
    global _running_log_id, _cancel_requested

    from sqlmodel import Session as SyncSession
    from app.database import engine as db_engine
    from app.models.article_analysis import ArticleAnalysis
    from app.models.ai_config import AIConfig
    from app.models.user import User
    from app.services.source_crawlers import crawl_qiushi_issue, fetch_and_extract_url

    acquired = _running_lock.acquire(blocking=False)
    if not acquired:
        logger.info("Qiushi backfill skipped: another job is already running")
        return

    try:
        _cancel_requested = False

        with SyncSession(db_engine) as session:
            cfg = session.exec(select(IngestionConfig)).first()
            if not cfg:
                cfg = IngestionConfig()
                session.add(cfg)
                session.commit()
                session.refresh(cfg)

            log = IngestionLog(
                run_type="backfill",
                status="running",
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            _running_log_id = log.id

            entries: list[dict] = []

            try:
                _tz = ZoneInfo(cfg.timezone or "Asia/Shanghai")
            except Exception:
                _tz = ZoneInfo("Asia/Shanghai")

            def add_entry(level: str, source: str, message: str):
                entries.append({
                    "time": datetime.now(_tz).strftime("%H:%M:%S"),
                    "level": level,
                    "source": source,
                    "message": message,
                })

            try:
                config = session.exec(
                    select(AIConfig).where(AIConfig.is_enabled == True)
                ).first()
                if not config or not config.api_key:
                    add_entry("error", "系统", "未配置AI服务，无法进行抓取分析")
                    log.status = "error"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                _max_retries = getattr(config, "max_retries", 3) or 3

                analyzed_urls = set()
                existing_analyses = session.exec(
                    select(ArticleAnalysis.source_url).where(ArticleAnalysis.source_url != "")
                ).all()
                for url in existing_analyses:
                    if url:
                        analyzed_urls.add(url.strip())

                _cache_rows = session.exec(select(IngestionUrlCache)).all()
                url_score_cache: dict[str, float] = {r.url: r.quality_score for r in _cache_rows}

                import re
                import time as _time

                total_fetched = 0
                total_analyzed = 0
                total_skipped = 0
                total_cards = 0
                total_errors = 0

                # ═══ Phase 1: Crawl all selected Qiushi issues ═══
                issue_names = "、".join(iss["issue_name"] for iss in issues)
                add_entry("info", "求是杂志", f"开始回溯抓取 ({len(issues)} 期): {issue_names}")

                all_articles = []
                for iss in issues:
                    if _cancel_requested:
                        break
                    try:
                        arts = await crawl_qiushi_issue(iss["issue_url"], iss["issue_name"])
                        add_entry("info", "求是杂志", f"{iss['issue_name']}: 发现 {len(arts)} 篇文章")
                        all_articles.extend(arts)
                    except Exception as crawl_err:
                        add_entry("error", "求是杂志", f"{iss['issue_name']} 抓取失败: {str(crawl_err)[:150]}")
                        logger.error("Qiushi issue crawl raised for %s: %s", iss["issue_name"], crawl_err)

                for art in all_articles:
                    art["source_name"] = "求是杂志"
                    art["category"] = "政治理论"

                total_fetched = len(all_articles)

                if total_fetched == 0:
                    add_entry("warn", "求是杂志",
                              f"所有期刊共未发现文章，请检查期刊URL是否有效")
                    log.status = "error"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                add_entry("info", "求是杂志", f"共发现 {total_fetched} 篇文章，开始逐篇处理...")

                log.articles_fetched = total_fetched
                log.sources_processed = len(issues)
                log.updated_at = datetime.now(timezone.utc)
                log.log_detail = json.dumps(entries, ensure_ascii=False)
                session.add(log)
                session.commit()

                if _cancel_requested:
                    add_entry("warn", "系统", "⚠️ 用户取消了回溯任务")
                    log.status = "cancelled"
                    log.finished_at = datetime.now(timezone.utc)
                    log.updated_at = datetime.now(timezone.utc)
                    log.log_detail = json.dumps(entries, ensure_ascii=False)
                    session.add(log)
                    session.commit()
                    return

                # ═══ Phase 2: Process each article ═══
                admin_user = session.exec(select(User).where(User.is_admin == True)).first()
                if not admin_user:
                    admin_user = session.exec(select(User)).first()

                concurrency = getattr(cfg, "concurrency", 3) or 3
                sem = _asyncio.Semaphore(concurrency)
                state_lock = _asyncio.Lock()

                from app.services.ai_pipeline import ai_cleanup_content, ai_analyze_article, ai_generate_cards
                from app.routers.article_analysis import _build_analysis_html

                async def _process_one_article(art: dict):
                    nonlocal total_analyzed, total_skipped, total_cards, total_errors

                    if _cancel_requested:
                        return

                    url = art["url"]

                    async with state_lock:
                        if url in analyzed_urls:
                            add_entry("skip", "求是杂志",
                                      f"已分析过，跳过: {art['title'][:40]}")
                            total_skipped += 1
                            return
                        if url in url_score_cache:
                            cached_score = url_score_cache[url]
                            if cached_score < cfg.quality_threshold:
                                add_entry("skip", "求是杂志",
                                          f"缓存评分 {cached_score} < 阈值 {cfg.quality_threshold}，跳过: {art['title'][:40]}")
                                total_skipped += 1
                                return
                        analyzed_urls.add(url)

                    source_label = art.get("section", "求是杂志")

                    async with sem:
                        if _cancel_requested:
                            return

                        try:
                            fetch_result = await fetch_and_extract_url(url)
                            body_text = fetch_result["content"]
                            extracted_title = fetch_result["title"]
                            title = art["title"] or extracted_title

                            publish_date = art.get("date", "") or ""
                            if not publish_date:
                                publish_date = fetch_result["publish_date"]

                            if len(body_text) < 600:
                                async with state_lock:
                                    add_entry("skip", source_label,
                                              f"正文太短（{len(body_text)}字），跳过: {title[:40]}")
                                    total_skipped += 1
                                    analyzed_urls.discard(url)
                                return

                            body_text = await ai_cleanup_content(
                                config, title, body_text,
                                user_id=admin_user.id if admin_user else 1,
                                source="crawl",
                            )

                            if _cancel_requested:
                                return

                            async with state_lock:
                                add_entry("info", source_label, f"正在分析: {title}（{len(body_text)}字）")

                            analysis_data = await ai_analyze_article(
                                session, config, title, body_text,
                                user_id=admin_user.id if admin_user else 1,
                                source="crawl",
                            )
                            if analysis_data is None:
                                async with state_lock:
                                    add_entry("error", source_label, f"AI分析失败: {title[:40]}")
                                    total_errors += 1
                                    analyzed_urls.discard(url)
                                return

                            quality = analysis_data.get("quality_score", 5)

                            if quality < cfg.quality_threshold:
                                async with state_lock:
                                    add_entry("skip", source_label,
                                              f"质量 {quality} < 阈值 {cfg.quality_threshold}，跳过: {title[:40]}")
                                    total_skipped += 1
                                    _prev = session.exec(
                                        select(IngestionUrlCache).where(IngestionUrlCache.url == url)
                                    ).first()
                                    if _prev:
                                        _prev.quality_score = quality
                                        _prev.title = title[:200]
                                        _prev.analyzed_at = datetime.now(timezone.utc)
                                    else:
                                        session.add(IngestionUrlCache(
                                            url=url, quality_score=quality, title=title[:200],
                                        ))
                                    session.commit()
                                    url_score_cache[url] = quality
                                return

                            analysis_html = _build_analysis_html(title, analysis_data)

                            async with state_lock:
                                _prev = session.exec(
                                    select(IngestionUrlCache).where(IngestionUrlCache.url == url)
                                ).first()
                                if _prev:
                                    session.delete(_prev)
                                    url_score_cache.pop(url, None)

                                analysis_item = ArticleAnalysis(
                                    user_id=admin_user.id if admin_user else 1,
                                    title=title,
                                    source_url=url,
                                    source_name=art.get("source_name", source_label),
                                    publish_date=publish_date[:20] if publish_date else "",
                                    content=body_text,
                                    analysis_html=analysis_html,
                                    analysis_json=json.dumps(analysis_data, ensure_ascii=False),
                                    quality_score=quality,
                                    quality_reason=analysis_data.get("quality_reason", ""),
                                    word_count=len(body_text),
                                    status="new",
                                )
                                session.add(analysis_item)
                                session.commit()
                                total_analyzed += 1
                                add_entry("info", source_label, f"✅ 分析完成 质量={quality}/10: {title[:40]}")

                            cards_created_this = 0
                            if not _cancel_requested:
                                cards_created_this, _ = await ai_generate_cards(
                                    session, config, title, body_text,
                                    source_url=url,
                                    user_id=admin_user.id if admin_user else 1,
                                    source="crawl",
                                )
                            async with state_lock:
                                total_cards += cards_created_this
                                if cards_created_this:
                                    add_entry("info", source_label, f"🃏 生成 {cards_created_this} 张卡片")

                        except json.JSONDecodeError as e:
                            async with state_lock:
                                add_entry("error", source_label, f"AI返回JSON解析失败: {str(e)[:100]}")
                                total_errors += 1
                        except Exception as e:
                            async with state_lock:
                                add_entry("error", source_label, f"处理文章失败: {str(e)[:150]}")
                                total_errors += 1
                        finally:
                            async with state_lock:
                                log.articles_analyzed = total_analyzed
                                log.articles_skipped = total_skipped
                                log.cards_created = total_cards
                                log.errors_count = total_errors
                                log.updated_at = datetime.now(timezone.utc)
                                log.log_detail = json.dumps(entries, ensure_ascii=False)
                                session.add(log)
                                session.commit()

                tasks = [_process_one_article(art) for art in all_articles]
                await _asyncio.gather(*tasks)

                if _cancel_requested:
                    add_entry("info", "系统",
                              f"回溯已取消: 发现{total_fetched}篇, 分析{total_analyzed}篇, "
                              f"跳过{total_skipped}篇, 生成{total_cards}张卡片, 错误{total_errors}个")
                    log.status = "cancelled"
                else:
                    add_entry("info", "系统",
                              f"✅ 求是回溯完成: 发现{total_fetched}篇, 分析{total_analyzed}篇, "
                              f"跳过{total_skipped}篇, 生成{total_cards}张卡片, 错误{total_errors}个")
                    log.status = "success"

                log.articles_fetched = total_fetched
                log.articles_analyzed = total_analyzed
                log.articles_skipped = total_skipped
                log.cards_created = total_cards
                log.errors_count = total_errors

            except Exception as e:
                add_entry("error", "系统", f"求是回溯过程异常: {str(e)[:200]}")
                log.status = "error"

            log.finished_at = datetime.now(timezone.utc)
            log.updated_at = datetime.now(timezone.utc)
            log.log_detail = json.dumps(entries, ensure_ascii=False)
            session.add(log)
            session.commit()

    finally:
        # Safety: ensure log status is updated even if the main commit failed
        log_id_to_fix = _running_log_id
        _running_log_id = None
        _cancel_requested = False
        _running_lock.release()
        if log_id_to_fix is not None:
            try:
                with SyncSession(db_engine) as fix_session:
                    stuck = fix_session.get(IngestionLog, log_id_to_fix)
                    if stuck and stuck.status == "running":
                        stuck.status = "error"
                        stuck.finished_at = datetime.now(timezone.utc)
                        fix_session.add(stuck)
                        fix_session.commit()
                        logger.warning("Safety: forced Qiushi backfill log #%d from 'running' to 'error'", log_id_to_fix)
            except Exception as e:
                logger.error("Failed to fix stuck Qiushi log #%d: %s", log_id_to_fix, e)


@router.post("/run")
async def run_ingestion(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Manually trigger the ingestion pipeline (runs in background)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Check if already running
    if _is_running():
        raise HTTPException(
            status_code=409,
            detail=f"已有抓取任务正在运行（日志 #{_running_log_id}），请等待完成或取消后再试",
        )

    # Launch in background — return immediately
    _asyncio.get_event_loop().create_task(_run_pipeline_internal(run_type="manual"))

    # Give the task a moment to create the log entry
    await _asyncio.sleep(0.3)

    # Return the latest log (should be the just-created "running" entry)
    latest_log = session.exec(
        select(IngestionLog).order_by(IngestionLog.started_at.desc()).limit(1)  # type: ignore[union-attr]
    ).first()
    if latest_log:
        return IngestionLogResponse.model_validate(latest_log)
    return {"status": "started"}


@router.post("/cancel/{log_id}")
async def cancel_ingestion(
    log_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Cancel a running ingestion job."""
    global _cancel_requested

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if _running_log_id != log_id:
        raise HTTPException(status_code=404, detail="该任务未在运行中")

    _cancel_requested = True
    logger.info("Cancel requested for ingestion log #%d", log_id)
    return {"ok": True, "message": f"已请求取消任务 #{log_id}，任务将在处理完当前文章后停止"}
