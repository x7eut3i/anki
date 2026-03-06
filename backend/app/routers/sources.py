"""Router for article source management (配置管理 - 文章来源)."""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models.article_source import ArticleSource
from app.models.user import User

logger = logging.getLogger("anki.sources")

router = APIRouter(prefix="/api/sources", tags=["sources"])


# ── Schemas ──

class SourceCreate(BaseModel):
    name: str
    url: str
    source_type: str = "rss"
    category: str = "时政热点"
    is_enabled: bool = True
    description: str = ""


class SourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    source_type: str | None = None
    category: str | None = None
    is_enabled: bool | None = None
    description: str | None = None


class SourceResponse(BaseModel):
    id: int
    name: str
    url: str
    source_type: str
    category: str
    is_enabled: bool
    is_system: bool = False
    description: str
    last_fetched_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ──

@router.get("", response_model=list[SourceResponse])
def list_sources(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List all article sources (shared across users)."""
    sources = session.exec(
        select(ArticleSource).order_by(
            ArticleSource.is_system.desc(),  # system sources first
            ArticleSource.created_at,
        )
    ).all()

    # If no sources exist, seed from system + normal defaults
    if not sources:
        from app.services.source_crawlers import SYSTEM_SOURCES, NORMAL_SOURCES
        for s in SYSTEM_SOURCES:
            source = ArticleSource(
                name=s["name"], url=s["url"],
                source_type=s.get("type", "special"),
                category=s.get("category", "时政热点"),
                is_system=True,
            )
            session.add(source)
        for s in NORMAL_SOURCES:
            source = ArticleSource(
                name=s["name"], url=s["url"],
                source_type=s.get("type", "html"),
                category=s.get("category", "时政热点"),
                is_system=False,
            )
            session.add(source)
        session.commit()
        sources = session.exec(
            select(ArticleSource).order_by(
                ArticleSource.is_system.desc(),
                ArticleSource.created_at,
            )
        ).all()

    # Ensure system sources exist (in case DB was migrated from old schema)
    existing_names = {s.name for s in sources}
    from app.services.source_crawlers import SYSTEM_SOURCES
    for s in SYSTEM_SOURCES:
        if s["name"] not in existing_names:
            source = ArticleSource(
                name=s["name"], url=s["url"],
                source_type=s.get("type", "special"),
                category=s.get("category", "时政热点"),
                is_system=True,
            )
            session.add(source)
    session.commit()
    sources = session.exec(
        select(ArticleSource).order_by(
            ArticleSource.is_system.desc(),
            ArticleSource.created_at,
        )
    ).all()

    return [SourceResponse.model_validate(s) for s in sources]


@router.post("", response_model=SourceResponse, status_code=201)
def create_source(
    data: SourceCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a new article source."""
    source = ArticleSource(**data.model_dump())
    session.add(source)
    session.commit()
    session.refresh(source)
    return SourceResponse.model_validate(source)


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int,
    data: SourceUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update an article source."""
    source = session.get(ArticleSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="来源不存在")

    updates = data.model_dump(exclude_unset=True)
    if source.is_system:
        # System sources only allow toggling is_enabled
        allowed = {"is_enabled"}
        if set(updates.keys()) - allowed:
            raise HTTPException(status_code=403, detail="系统来源仅可启用/禁用")
        updates = {k: v for k, v in updates.items() if k in allowed}

    for key, value in updates.items():
        setattr(source, key, value)

    session.add(source)
    session.commit()
    session.refresh(source)
    return SourceResponse.model_validate(source)


@router.delete("/{source_id}")
def delete_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete an article source."""
    source = session.get(ArticleSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="来源不存在")
    if source.is_system:
        raise HTTPException(status_code=403, detail="系统来源不可删除")

    session.delete(source)
    session.commit()
    return {"ok": True}


@router.post("/reset-defaults")
def reset_sources_to_defaults(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete all existing sources and re-seed from latest defaults."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Delete all existing sources
    existing = session.exec(select(ArticleSource)).all()
    for s in existing:
        session.delete(s)
    session.commit()

    # Re-seed from system + normal sources
    from app.services.source_crawlers import SYSTEM_SOURCES, NORMAL_SOURCES
    for s in SYSTEM_SOURCES:
        source = ArticleSource(
            name=s["name"], url=s["url"],
            source_type=s.get("type", "special"),
            category=s.get("category", "时政热点"),
            is_system=True,
        )
        session.add(source)
    for s in NORMAL_SOURCES:
        source = ArticleSource(
            name=s["name"], url=s["url"],
            source_type=s.get("type", "html"),
            category=s.get("category", "时政热点"),
            is_system=False,
        )
        session.add(source)
    session.commit()

    sources = session.exec(select(ArticleSource).order_by(ArticleSource.created_at)).all()
    return {
        "ok": True,
        "count": len(sources),
        "sources": [SourceResponse.model_validate(s) for s in sources],
    }


@router.post("/{source_id}/test")
async def test_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Test fetching an article source: list articles AND parse the first article fully."""
    source = session.get(ArticleSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="来源不存在")

    from app.services.source_crawlers import (
        crawl_normal_source, crawl_rmrb, crawl_qiushi,
        fetch_and_extract_url,
    )

    try:
        # Gather articles — special sources use dedicated crawlers
        if source.is_system and "人民日报" in source.name:
            articles = await crawl_rmrb()
        elif source.is_system and "求是" in source.name:
            articles = await crawl_qiushi()
        else:
            articles = await crawl_normal_source(
                source.name, source.url, source.source_type, max_articles=5,
            )

        sample_titles = [a["title"][:60] for a in articles[:5]]

        first_article = None
        if articles:
            art = articles[0]
            first_body = ""
            try:
                fetch_result = await fetch_and_extract_url(art["url"])
                first_body = fetch_result["content"]

                # AI cleanup if available
                try:
                    from app.models.ai_config import AIConfig
                    ai_config = session.exec(
                        select(AIConfig).where(
                            AIConfig.user_id == current_user.id,
                            AIConfig.is_enabled == True,
                        )
                    ).first()
                    if ai_config and first_body:
                        from app.services.ai_pipeline import ai_cleanup_content
                        first_body = await ai_cleanup_content(
                            ai_config, art["title"], first_body,
                            current_user.id,
                        )
                except Exception as ai_err:
                    logger.warning("AI cleanup skipped in test_source: %s", ai_err)
            except Exception as fetch_err:
                first_body = f"(无法获取正文: {str(fetch_err)[:100]})"

            first_article = {
                "title": art["title"],
                "url": art["url"],
                "date": art.get("date", ""),
                "body_preview": first_body if first_body else "(无法提取正文)",
            }

        source.last_fetched_at = datetime.now(timezone.utc)
        session.add(source)
        session.commit()

        label = "特殊抓取" if source.is_system else "连接成功"
        return {
            "success": True,
            "message": f"{label}，发现 {len(articles)} 篇文章",
            "article_count": len(articles),
            "sample_titles": sample_titles,
            "first_article": first_article,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)[:200]}",
            "article_count": 0,
            "sample_titles": [],
            "first_article": None,
        }


class RmrbBackfillRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


@router.post("/rmrb-backfill")
async def rmrb_backfill(
    data: RmrbBackfillRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Trigger 人民日报 backfill for a date range.

    Launches a background pipeline that crawls RMRB for each day in
    the range, then processes all articles (dedup, analyze, generate cards).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Parse dates
    try:
        start = datetime.strptime(data.start_date, "%Y-%m-%d")
        end = datetime.strptime(data.end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD")

    if start > end:
        start, end = end, start

    day_count = (end - start).days + 1
    if day_count > 60:
        raise HTTPException(status_code=400, detail="最多支持回溯60天")

    # Check if ingestion is already running
    from app.routers.ingestion import _is_running, _running_log_id
    if _is_running():
        raise HTTPException(
            status_code=409,
            detail=f"已有抓取任务正在运行（日志 #{_running_log_id}），请等待完成或取消后再试",
        )

    # Launch backfill in background
    import asyncio
    from app.routers.ingestion import _run_rmrb_backfill_internal
    asyncio.get_event_loop().create_task(
        _run_rmrb_backfill_internal(data.start_date, data.end_date)
    )

    return {
        "ok": True,
        "message": f"已启动人民日报回溯抓取: {data.start_date} → {data.end_date} ({day_count}天)",
    }


@router.get("/qiushi-issues")
async def list_qiushi_issues(
    year: int,
    current_user: User = Depends(get_current_user),
):
    """List all issues of 求是杂志 for a given year."""
    from app.services.source_crawlers import crawl_qiushi_issues

    if year < 2010 or year > 2099:
        raise HTTPException(status_code=400, detail="年份范围: 2010-2099")

    issues = await crawl_qiushi_issues(year)
    return {
        "year": year,
        "issues": issues,
    }


class QiushiBackfillRequest(BaseModel):
    issue_url: str
    issue_name: str  # e.g. "2026年 第5期"


@router.post("/qiushi-backfill")
async def qiushi_backfill(
    data: QiushiBackfillRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Trigger 求是杂志 backfill for a specific issue.

    Crawls all articles from the selected issue, then processes them
    through the full pipeline (dedup, analyze, generate cards).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if not data.issue_url or "qstheory.cn" not in data.issue_url:
        raise HTTPException(status_code=400, detail="无效的求是期刊URL")

    from app.routers.ingestion import _is_running, _running_log_id
    if _is_running():
        raise HTTPException(
            status_code=409,
            detail=f"已有抓取任务正在运行（日志 #{_running_log_id}），请等待完成或取消后再试",
        )

    import asyncio
    from app.routers.ingestion import _run_qiushi_backfill_internal
    asyncio.get_event_loop().create_task(
        _run_qiushi_backfill_internal(data.issue_url, data.issue_name)
    )

    return {
        "ok": True,
        "message": f"已启动求是杂志回溯抓取: {data.issue_name}",
    }


@router.post("/test-url")
async def test_url(
    data: SourceCreate,
    current_user: User = Depends(get_current_user),
):
    """Test a URL without saving it as a source."""
    from app.services.source_crawlers import crawl_normal_source

    try:
        articles = await crawl_normal_source(
            data.name or "测试", data.url, data.source_type, max_articles=5,
        )
        sample_titles = [a["title"][:60] for a in articles[:5]]
        return {
            "success": True,
            "message": f"连接成功，发现 {len(articles)} 篇文章",
            "article_count": len(articles),
            "sample_titles": sample_titles,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)[:200]}",
            "article_count": 0,
            "sample_titles": [],
        }
