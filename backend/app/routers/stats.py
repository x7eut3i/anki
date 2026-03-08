"""Comprehensive statistics API for AI, study, and content metrics."""

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func, col, text

from app.auth import get_current_user
from app.database import get_session
from app.models.user import User
from app.models.card import Card
from app.models.review_log import ReviewLog
from app.models.study_session import StudySession
from app.models.article_analysis import ArticleAnalysis
from app.models.ai_interaction_log import AIInteractionLog
from app.models.ingestion import IngestionLog

logger = logging.getLogger("anki.stats")

router = APIRouter(prefix="/api/stats", tags=["statistics"])


def _date_range(days: int | None, start: str | None, end: str | None, tz: ZoneInfo | None = None):
    """Compute start/end datetimes from params.

    When tz is provided, boundaries are computed in the user's local timezone
    and then converted to UTC for database queries.
    """
    if tz:
        now_local = datetime.now(tz)
    else:
        now_local = datetime.now(timezone.utc)

    if start:
        try:
            dt_start = datetime.strptime(start, "%Y-%m-%d")
            if tz:
                dt_start = dt_start.replace(tzinfo=tz)
            else:
                dt_start = dt_start.replace(tzinfo=timezone.utc)
        except ValueError:
            dt_start = now_local - timedelta(days=30)
    elif days:
        dt_start = now_local - timedelta(days=days)
    else:
        dt_start = now_local - timedelta(days=30)

    if end:
        try:
            dt_end = datetime.strptime(end, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            if tz:
                dt_end = dt_end.replace(tzinfo=tz)
            else:
                dt_end = dt_end.replace(tzinfo=timezone.utc)
        except ValueError:
            dt_end = now_local
    else:
        dt_end = now_local

    # Convert to UTC for database queries
    dt_start_utc = dt_start.astimezone(timezone.utc)
    dt_end_utc = dt_end.astimezone(timezone.utc)

    return dt_start_utc, dt_end_utc


def _to_local_date(utc_dt: datetime, tz: ZoneInfo | None) -> str:
    """Convert a UTC datetime to a local date string."""
    if tz:
        return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz).strftime("%Y-%m-%d")
    return utc_dt.strftime("%Y-%m-%d")


def _to_local_datetime(utc_dt: datetime, tz: ZoneInfo | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Convert a UTC datetime to a local datetime string."""
    if tz:
        return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz).strftime(fmt)
    return utc_dt.strftime(fmt)


def _fill_date_series(data_dict: dict, start: datetime, end: datetime, tz: ZoneInfo | None = None) -> list[dict]:
    """Fill missing dates with zeros.

    When tz is provided, iterates over local dates instead of UTC dates.
    """
    result = []
    if tz:
        local_start = start.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = end.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        current = local_start
        while current <= local_end:
            key = current.strftime("%Y-%m-%d")
            result.append({"date": key, **data_dict.get(key, {"count": 0})})
            current += timedelta(days=1)
    else:
        current = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = end.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= end_day:
            key = current.strftime("%Y-%m-%d")
            result.append({"date": key, **data_dict.get(key, {"count": 0})})
            current += timedelta(days=1)
    return result


def _parse_tz(tz_str: str | None) -> ZoneInfo | None:
    """Parse a timezone string, returning None if invalid or not provided."""
    if not tz_str:
        return None
    try:
        return ZoneInfo(tz_str)
    except Exception:
        logger.warning("Invalid timezone: %s, falling back to UTC", tz_str)
        return None


# ── AI Statistics ────────────────────────────────────────────────────

@router.get("/ai")
def get_ai_stats(
    days: int = Query(30, ge=1, le=365),
    start: str | None = None,
    end: str | None = None,
    tz: str | None = Query(None, description="IANA timezone, e.g. Asia/Shanghai"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Comprehensive AI interaction statistics from DB."""
    user_tz = _parse_tz(tz)
    dt_start, dt_end = _date_range(days, start, end, user_tz)

    # All logs in range
    logs = session.exec(
        select(AIInteractionLog).where(
            AIInteractionLog.created_at >= dt_start,
            AIInteractionLog.created_at <= dt_end,
        ).order_by(AIInteractionLog.created_at)
    ).all()

    total_calls = len(logs)
    ok_logs = [l for l in logs if l.status == "ok"]
    err_logs = [l for l in logs if l.status == "error"]
    total_tokens = sum(l.tokens_used for l in logs)
    latencies = [l.elapsed_ms for l in ok_logs if l.elapsed_ms > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0

    # Daily trend (bucket by user's local date)
    daily_data: dict[str, dict] = {}
    for log in logs:
        day = _to_local_date(log.created_at, user_tz)
        if day not in daily_data:
            daily_data[day] = {"count": 0, "tokens": 0, "errors": 0}
        daily_data[day]["count"] += 1
        daily_data[day]["tokens"] += log.tokens_used
        if log.status == "error":
            daily_data[day]["errors"] += 1
    daily = _fill_date_series(daily_data, dt_start, dt_end, user_tz)

    # By feature
    feature_map: dict[str, dict] = {}
    for log in logs:
        f = log.feature
        if f not in feature_map:
            feature_map[f] = {"count": 0, "errors": 0, "total_tokens": 0, "total_ms": 0}
        feature_map[f]["count"] += 1
        feature_map[f]["total_tokens"] += log.tokens_used
        feature_map[f]["total_ms"] += log.elapsed_ms
        if log.status == "error":
            feature_map[f]["errors"] += 1
    by_feature = [
        {"feature": k, **v, "avg_ms": round(v["total_ms"] / v["count"]) if v["count"] else 0}
        for k, v in sorted(feature_map.items(), key=lambda x: -x[1]["count"])
    ]

    # By model + config
    model_map: dict[str, dict] = {}
    for log in logs:
        key = f"{log.model}|{log.config_name}" if log.config_name else log.model
        if key not in model_map:
            model_map[key] = {
                "model": log.model, "config_name": log.config_name,
                "count": 0, "total_tokens": 0, "total_ms": 0, "errors": 0,
            }
        model_map[key]["count"] += 1
        model_map[key]["total_tokens"] += log.tokens_used
        model_map[key]["total_ms"] += log.elapsed_ms
        if log.status == "error":
            model_map[key]["errors"] += 1
    by_model = [
        {**v, "avg_ms": round(v["total_ms"] / v["count"]) if v["count"] else 0}
        for v in sorted(model_map.values(), key=lambda x: -x["count"])
    ]

    return {
        "total_calls": total_calls,
        "total_errors": len(err_logs),
        "total_tokens": total_tokens,
        "avg_latency_ms": round(avg_latency),
        "max_latency_ms": max_latency,
        "daily": daily,
        "by_feature": by_feature,
        "by_model": by_model,
        "range": {"start": _to_local_date(dt_start, user_tz), "end": _to_local_date(dt_end, user_tz)},
    }


# ── Content / Article Statistics ─────────────────────────────────────

@router.get("/content")
def get_content_stats(
    days: int = Query(30, ge=1, le=365),
    start: str | None = None,
    end: str | None = None,
    tz: str | None = Query(None, description="IANA timezone, e.g. Asia/Shanghai"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Articles crawled and cards generated statistics."""
    user_tz = _parse_tz(tz)
    dt_start, dt_end = _date_range(days, start, end, user_tz)

    # Articles by source per day
    articles = session.exec(
        select(ArticleAnalysis).where(
            ArticleAnalysis.created_at >= dt_start,
            ArticleAnalysis.created_at <= dt_end,
        )
    ).all()

    # Daily articles (bucket by user's local date)
    daily_articles: dict[str, dict] = {}
    source_totals: dict[str, dict] = {}
    for a in articles:
        day = _to_local_date(a.created_at, user_tz)
        if day not in daily_articles:
            daily_articles[day] = {"count": 0, "avg_quality": 0, "total_quality": 0}
        daily_articles[day]["count"] += 1
        daily_articles[day]["total_quality"] += a.quality_score or 0

        src = a.source_name or "未知"
        if src not in source_totals:
            source_totals[src] = {"articles": 0, "avg_quality": 0, "total_quality": 0}
        source_totals[src]["articles"] += 1
        source_totals[src]["total_quality"] += a.quality_score or 0

    for d in daily_articles.values():
        d["avg_quality"] = round(d["total_quality"] / d["count"], 1) if d["count"] else 0
        del d["total_quality"]
    for s in source_totals.values():
        s["avg_quality"] = round(s["total_quality"] / s["articles"], 1) if s["articles"] else 0
        del s["total_quality"]

    # Cards generated per day (AI-generated)
    ai_cards = session.exec(
        select(Card).where(
            Card.is_ai_generated == True,
            Card.created_at >= dt_start,
            Card.created_at <= dt_end,
        )
    ).all()

    daily_cards: dict[str, int] = {}
    for c in ai_cards:
        day = _to_local_date(c.created_at, user_tz)
        daily_cards[day] = daily_cards.get(day, 0) + 1

    # Merge daily data
    all_days: set[str] = set(daily_articles.keys()) | set(daily_cards.keys())
    daily_merged = []
    for day in sorted(all_days):
        art_data = daily_articles.get(day, {"count": 0, "avg_quality": 0})
        daily_merged.append({
            "date": day,
            "articles": art_data["count"],
            "avg_quality": art_data.get("avg_quality", 0),
            "cards": daily_cards.get(day, 0),
        })

    # By source
    by_source = [
        {"source": k, **v}
        for k, v in sorted(source_totals.items(), key=lambda x: -x[1]["articles"])
    ]

    # Ingestion runs
    ingestion_runs = session.exec(
        select(IngestionLog).where(
            IngestionLog.started_at >= dt_start,
            IngestionLog.started_at <= dt_end,
        ).order_by(IngestionLog.started_at.desc()).limit(20)
    ).all()
    recent_runs = [{
        "date": _to_local_datetime(r.started_at, user_tz),
        "status": r.status,
        "articles_fetched": r.articles_fetched,
        "articles_analyzed": r.articles_analyzed,
        "cards_created": r.cards_created,
        "errors": r.errors_count,
    } for r in ingestion_runs]

    return {
        "total_articles": len(articles),
        "total_ai_cards": len(ai_cards),
        "daily": daily_merged,
        "by_source": by_source,
        "recent_runs": recent_runs,
        "range": {"start": _to_local_date(dt_start, user_tz), "end": _to_local_date(dt_end, user_tz)},
    }


# ── Study Statistics ─────────────────────────────────────────────────

@router.get("/study")
def get_study_stats(
    days: int = Query(30, ge=1, le=365),
    start: str | None = None,
    end: str | None = None,
    period: str = Query("day", pattern="^(day|week|month)$"),
    tz: str | None = Query(None, description="IANA timezone, e.g. Asia/Shanghai"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Comprehensive study statistics with aggregation."""
    user_tz = _parse_tz(tz)
    dt_start, dt_end = _date_range(days, start, end, user_tz)

    # All reviews in range
    reviews = session.exec(
        select(ReviewLog).where(
            ReviewLog.user_id == current_user.id,
            ReviewLog.reviewed_at >= dt_start,
            ReviewLog.reviewed_at <= dt_end,
        ).order_by(ReviewLog.reviewed_at)
    ).all()

    total_reviews = len(reviews)
    total_time_ms = sum(r.review_duration_ms for r in reviews)
    again_count = sum(1 for r in reviews if r.rating == 1)
    hard_count = sum(1 for r in reviews if r.rating == 2)
    good_count = sum(1 for r in reviews if r.rating == 3)
    easy_count = sum(1 for r in reviews if r.rating == 4)
    retention_rate = (total_reviews - again_count) / total_reviews if total_reviews else 0

    # Daily data (bucket by user's local date)
    daily_data: dict[str, dict] = {}
    for r in reviews:
        day = _to_local_date(r.reviewed_at, user_tz)
        if day not in daily_data:
            daily_data[day] = {
                "count": 0, "again": 0, "hard": 0, "good": 0, "easy": 0,
                "time_ms": 0, "new_cards": 0,
            }
        daily_data[day]["count"] += 1
        daily_data[day]["time_ms"] += r.review_duration_ms
        if r.rating == 1:
            daily_data[day]["again"] += 1
        elif r.rating == 2:
            daily_data[day]["hard"] += 1
        elif r.rating == 3:
            daily_data[day]["good"] += 1
        elif r.rating == 4:
            daily_data[day]["easy"] += 1
        if r.state == 0:  # New card
            daily_data[day]["new_cards"] += 1

    # Fill missing dates
    daily = _fill_date_series(daily_data, dt_start, dt_end, user_tz)
    # Add default fields for filled days
    for d in daily:
        d.setdefault("again", 0)
        d.setdefault("hard", 0)
        d.setdefault("good", 0)
        d.setdefault("easy", 0)
        d.setdefault("time_ms", 0)
        d.setdefault("new_cards", 0)
        # Compute daily retention
        d["retention"] = round((d["count"] - d["again"]) / d["count"], 3) if d["count"] else 0

    # Aggregate by period
    def _aggregate(items: list[dict], period: str) -> list[dict]:
        if period == "day":
            # Skip dates with no study activity
            return [item for item in items if item.get("count", 0) > 0]
        buckets: dict[str, dict] = {}
        for item in items:
            dt = datetime.strptime(item["date"], "%Y-%m-%d")
            if period == "week":
                # ISO week start (Monday)
                iso = dt.isocalendar()
                key = f"{iso.year}-W{iso.week:02d}"
            else:  # month
                key = dt.strftime("%Y-%m")
            if key not in buckets:
                buckets[key] = {
                    "period": key, "count": 0, "again": 0, "hard": 0,
                    "good": 0, "easy": 0, "time_ms": 0, "new_cards": 0, "days_studied": 0,
                }
            b = buckets[key]
            b["count"] += item["count"]
            b["again"] += item["again"]
            b["hard"] += item["hard"]
            b["good"] += item["good"]
            b["easy"] += item["easy"]
            b["time_ms"] += item["time_ms"]
            b["new_cards"] += item["new_cards"]
            if item["count"] > 0:
                b["days_studied"] += 1
        result = []
        for b in buckets.values():
            b["retention"] = round((b["count"] - b["again"]) / b["count"], 3) if b["count"] else 0
            result.append(b)
        return sorted(result, key=lambda x: x["period"])

    aggregated = _aggregate(daily, period)

    # By category (join review_logs with cards)
    from app.models.category import Category
    cat_rows = session.exec(
        select(
            Category.name,
            func.count(ReviewLog.id),
            func.sum(ReviewLog.review_duration_ms),
        )
        .select_from(ReviewLog)
        .join(Card, Card.id == ReviewLog.card_id)
        .outerjoin(Category, Category.id == Card.category_id)
        .where(
            ReviewLog.user_id == current_user.id,
            ReviewLog.reviewed_at >= dt_start,
            ReviewLog.reviewed_at <= dt_end,
        )
        .group_by(Category.name)
    ).all()

    by_category = []
    for cat_name, count, time_ms in cat_rows:
        # Get rating breakdown for this category
        cat_again = session.exec(
            select(func.count())
            .select_from(ReviewLog)
            .join(Card, Card.id == ReviewLog.card_id)
            .outerjoin(Category, Category.id == Card.category_id)
            .where(
                ReviewLog.user_id == current_user.id,
                ReviewLog.reviewed_at >= dt_start,
                ReviewLog.reviewed_at <= dt_end,
                Category.name == cat_name,
                ReviewLog.rating == 1,
            )
        ).one()
        retention = (count - cat_again) / count if count else 0
        by_category.append({
            "category": cat_name or "未分类",
            "reviews": count,
            "time_ms": time_ms or 0,
            "retention": round(retention, 3),
        })
    by_category.sort(key=lambda x: -x["reviews"])

    # Study sessions
    sessions = session.exec(
        select(StudySession).where(
            StudySession.user_id == current_user.id,
            StudySession.started_at >= dt_start,
            StudySession.started_at <= dt_end,
            StudySession.is_completed == True,
        )
    ).all()
    total_sessions = len(sessions)
    avg_session_cards = sum(s.cards_reviewed for s in sessions) / total_sessions if total_sessions else 0

    # Streak
    from app.services.review_service import ReviewService
    rs = ReviewService(session, current_user.id)
    streak = rs._calculate_streak()

    # Card state counts
    from app.models.user_card_progress import UserCardProgress
    state_counts = session.exec(
        select(UserCardProgress.state, func.count()).where(
            UserCardProgress.user_id == current_user.id,
        ).group_by(UserCardProgress.state)
    ).all()
    state_names = {0: "new", 1: "learning", 2: "review", 3: "relearning"}
    cards_by_state = {v: 0 for v in state_names.values()}
    for state_val, count in state_counts:
        name = state_names.get(state_val, "new")
        cards_by_state[name] = count

    # Total cards
    total_cards = session.exec(select(func.count()).select_from(Card)).one()
    cards_with_progress = session.exec(
        select(func.count()).where(UserCardProgress.user_id == current_user.id)
    ).one()
    cards_by_state["unseen"] = max(0, total_cards - cards_with_progress)

    return {
        "summary": {
            "total_reviews": total_reviews,
            "total_time_ms": total_time_ms,
            "retention_rate": round(retention_rate, 4),
            "streak_days": streak,
            "total_sessions": total_sessions,
            "avg_session_cards": round(avg_session_cards, 1),
            "rating_distribution": {
                "again": again_count, "hard": hard_count,
                "good": good_count, "easy": easy_count,
            },
            "cards_by_state": cards_by_state,
        },
        "daily": daily,
        "aggregated": aggregated,
        "by_category": by_category,
        "range": {"start": _to_local_date(dt_start, user_tz), "end": _to_local_date(dt_end, user_tz)},
    }
