"""Router for ingestion configuration and logs (自动抓取管理)."""

import asyncio as _asyncio
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models.ingestion import IngestionConfig, IngestionLog
from app.models.user import User

logger = logging.getLogger("anki.ingestion")

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


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
    # Fix stale running logs
    stale_cutoff = datetime.now(timezone.utc) - __import__('datetime').timedelta(minutes=30)
    stale_logs = session.exec(
        select(IngestionLog)
        .where(IngestionLog.status == "running")
        .where(IngestionLog.started_at < stale_cutoff)
    ).all()
    for sl in stale_logs:
        sl.status = "error"
        sl.finished_at = sl.finished_at or datetime.now(timezone.utc)
        # Append an entry to the log detail
        try:
            entries = json.loads(sl.log_detail) if sl.log_detail else []
        except (json.JSONDecodeError, TypeError):
            entries = []
        entries.append({
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": "error",
            "source": "系统",
            "message": "任务运行超时或服务器中断，已自动标记为错误",
        })
        sl.log_detail = json.dumps(entries, ensure_ascii=False)
        session.add(sl)
    if stale_logs:
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

async def _run_pipeline_internal(run_type: str = "manual"):
    """Run the ingestion pipeline. Can be called by the HTTP endpoint or the scheduler.

    This creates its own DB session so it works without auth context.
    """
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

            import re
            import time as _time

            total_fetched = 0
            total_analyzed = 0
            total_skipped = 0
            total_cards = 0
            total_errors = 0

            # ═══════════════════════════════════════════════════════════════
            # Phase 1: Gather all articles from ALL sources
            # ═══════════════════════════════════════════════════════════════
            all_articles: list[dict] = []

            db_sources = session.exec(
                select(ArticleSource).where(ArticleSource.is_enabled == True)
            ).all()

            system_sources = [s for s in db_sources if s.is_system]
            normal_sources = [s for s in db_sources if not s.is_system]

            for sys_src in system_sources:
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

            total_fetched = len(all_articles)
            add_entry("info", "系统", f"共发现 {total_fetched} 篇文章，开始逐篇处理...")

            # Persist fetched count immediately so the UI shows it
            log.articles_fetched = total_fetched
            log.log_detail = json.dumps(entries, ensure_ascii=False)
            session.add(log)
            session.commit()

            # ═══════════════════════════════════════════════════════════════
            # Phase 2: Process each article
            # ═══════════════════════════════════════════════════════════════

            admin_user = session.exec(select(User).where(User.is_admin == True)).first()
            if not admin_user:
                admin_user = session.exec(select(User)).first()

            for art in all_articles:
                if art["url"] in analyzed_urls:
                    add_entry("skip", art.get("section", art.get("source_name", "")),
                              f"已分析过，跳过: {art['title'][:40]}")
                    total_skipped += 1
                    continue

                source_label = art.get("section", art.get("source_name", ""))

                try:
                    fetch_result = await fetch_and_extract_url(art["url"])
                    body_text = fetch_result["content"]
                    extracted_title = fetch_result["title"]
                    title = art["title"] or extracted_title

                    publish_date = art.get("date", "") or ""
                    if not publish_date:
                        publish_date = fetch_result["publish_date"]

                    if len(body_text) < 100:
                        add_entry("skip", source_label,
                                  f"正文太短（{len(body_text)}字），跳过: {title[:40]}")
                        total_skipped += 1
                        continue

                    # ── AI Step 1: Content cleanup ──
                    from app.services.ai_pipeline import ai_cleanup_content, ai_analyze_article, ai_generate_cards
                    body_text = await ai_cleanup_content(
                        config, title, body_text,
                        user_id=admin_user.id if admin_user else 1,
                    )

                    add_entry("info", source_label, f"正在分析: {title}（{len(body_text)}字）")

                    # ── AI Step 2: Article analysis ──
                    analysis_data = await ai_analyze_article(
                        session, config, title, body_text,
                        user_id=admin_user.id if admin_user else 1,
                    )
                    if analysis_data is None:
                        add_entry("error", source_label, f"AI分析失败: {title[:40]}")
                        total_errors += 1
                        continue

                    quality = analysis_data.get("quality_score", 5)

                    if quality < cfg.quality_threshold:
                        add_entry("skip", source_label,
                                  f"质量 {quality} < 阈值 {cfg.quality_threshold}，跳过该篇文章（{title}，{art['url']}）")
                        total_skipped += 1
                        continue
                        
                    from app.routers.article_analysis import _build_analysis_html
                    analysis_html = _build_analysis_html(title, analysis_data)

                    analysis_item = ArticleAnalysis(
                        user_id=admin_user.id if admin_user else 1,
                        title=title,
                        source_url=art["url"],
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
                    analyzed_urls.add(art["url"])
                    total_analyzed += 1

                    add_entry("info", source_label, f"✅ 分析完成 质量={quality}/10: {title[:40]}")

                    # ── AI Step 3: Card generation ──
                    cards_created_this, _ = await ai_generate_cards(
                        session, config, title, body_text,
                        source_url=art["url"],
                        user_id=admin_user.id if admin_user else 1,
                    )
                    total_cards += cards_created_this
                    add_entry("info", source_label, f"🃏 生成 {cards_created_this} 张卡片")

                except json.JSONDecodeError as e:
                    add_entry("error", source_label, f"AI返回JSON解析失败: {str(e)[:100]}")
                    total_errors += 1
                except Exception as e:
                    add_entry("error", source_label, f"处理文章失败: {str(e)[:150]}")
                    total_errors += 1

                # Flush stats to DB after each article so frontend sees progress
                log.articles_analyzed = total_analyzed
                log.articles_skipped = total_skipped
                log.cards_created = total_cards
                log.errors_count = total_errors
                log.log_detail = json.dumps(entries, ensure_ascii=False)
                session.add(log)
                session.commit()

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
            total_errors += 1

        log.finished_at = datetime.now(timezone.utc)
        log.log_detail = json.dumps(entries, ensure_ascii=False)
        session.add(log)
        session.commit()


@router.post("/run")
async def run_ingestion(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Manually trigger the ingestion pipeline."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    await _run_pipeline_internal(run_type="manual")

    # Return the latest log
    latest_log = session.exec(
        select(IngestionLog).order_by(IngestionLog.started_at.desc()).limit(1)  # type: ignore[union-attr]
    ).first()
    if latest_log:
        return IngestionLogResponse.model_validate(latest_log)
    return {"status": "completed"}
