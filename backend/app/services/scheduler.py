"""APScheduler integration for scheduled ingestion jobs.

Handles:
- Creating / updating the scheduled ingestion job based on IngestionConfig
- Starting the scheduler in the FastAPI lifespan
- Graceful shutdown
- Timezone-aware scheduling
"""

import logging
from datetime import datetime, timezone as _tz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.database import engine

logger = logging.getLogger("anki.scheduler")

# Module-level scheduler instance
_scheduler: AsyncIOScheduler | None = None

JOB_ID = "ingestion_pipeline"


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def get_scheduler_status() -> dict:
    """Get scheduler debug information."""
    if not _scheduler:
        return {"running": False, "message": "Scheduler not initialized"}

    jobs = _scheduler.get_jobs()
    job_info = []
    for job in jobs:
        job_info.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return {
        "running": _scheduler.running,
        "job_count": len(jobs),
        "jobs": job_info,
    }


async def _run_ingestion_job():
    """Internal job function — runs the ingestion pipeline without auth context.

    Creates its own DB session and finds an admin user to act as the owner.
    Checks for already-running jobs before starting.
    """
    logger.info("⏰ Scheduled ingestion job triggered at %s", datetime.now(_tz.utc).isoformat())

    from app.models.user import User
    from app.models.ingestion import IngestionConfig

    with Session(engine) as session:
        cfg = session.exec(select(IngestionConfig)).first()
        if not cfg or not cfg.is_enabled:
            logger.info("Ingestion is disabled, skipping scheduled run")
            return

    # Import the pipeline runner (lazy to avoid circular imports)
    from app.routers.ingestion import _run_pipeline_internal
    try:
        logger.info("🚀 Starting scheduled ingestion pipeline...")
        await _run_pipeline_internal(run_type="scheduled")
        logger.info("✅ Scheduled ingestion pipeline completed")
    except Exception as e:
        logger.error("❌ Scheduled ingestion failed: %s", e, exc_info=True)
    finally:
        import gc; gc.collect()


def _build_trigger(cfg) -> CronTrigger | None:
    """Build an APScheduler CronTrigger from IngestionConfig."""
    if not cfg.is_enabled:
        return None

    tz = cfg.timezone or "Asia/Shanghai"
    schedule_type = cfg.schedule_type or "daily"

    if schedule_type == "off":
        return None

    if cfg.cron_expression:
        # Advanced: user-supplied cron expression
        try:
            return CronTrigger.from_crontab(cfg.cron_expression, timezone=tz)
        except Exception as e:
            logger.warning("Invalid cron expression '%s': %s", cfg.cron_expression, e)
            return None

    hour = cfg.schedule_hour
    minute = cfg.schedule_minute

    if schedule_type == "daily":
        return CronTrigger(hour=hour, minute=minute, timezone=tz)
    elif schedule_type == "weekly":
        days = cfg.schedule_days or ""
        if not days:
            return None
        # Convert "1,2,5" → "mon,tue,fri"
        day_map = {"0": "sun", "1": "mon", "2": "tue", "3": "wed",
                   "4": "thu", "5": "fri", "6": "sat", "7": "sun"}
        cron_days = ",".join(day_map.get(d.strip(), d.strip()) for d in days.split(",") if d.strip())
        if not cron_days:
            return None
        return CronTrigger(day_of_week=cron_days, hour=hour, minute=minute, timezone=tz)

    return None


async def setup_scheduler():
    """Initialize the scheduler and add the ingestion job if configured."""
    global _scheduler

    _scheduler = AsyncIOScheduler(
        job_defaults={
            "misfire_grace_time": 3600,  # Allow 1 hour grace for misfired jobs
            "coalesce": True,            # Coalesce multiple misfired runs into one
        }
    )
    _scheduler.start()
    logger.info("✅ APScheduler started")

    # Load current config and schedule if enabled
    from app.models.ingestion import IngestionConfig

    with Session(engine) as session:
        cfg = session.exec(select(IngestionConfig)).first()

    if cfg:
        trigger = _build_trigger(cfg)
        if trigger:
            _scheduler.add_job(
                _run_ingestion_job,
                trigger=trigger,
                id=JOB_ID,
                replace_existing=True,
                name="自动抓取",
                misfire_grace_time=3600,
            )
            # Log next run time
            job = _scheduler.get_job(JOB_ID)
            next_run = job.next_run_time if job else "unknown"
            logger.info("📅 Ingestion job scheduled: type=%s, hour=%s:%02d, tz=%s, next_run=%s",
                        cfg.schedule_type, cfg.schedule_hour, cfg.schedule_minute,
                        cfg.timezone, next_run)
        else:
            logger.info("📅 Ingestion not scheduled (disabled or schedule_type=off)")
    else:
        logger.info("📅 No ingestion config found, skipping schedule")


def reschedule_ingestion(cfg):
    """Update or remove the scheduled ingestion job based on new config.

    Call this after saving IngestionConfig changes.
    """
    global _scheduler
    if _scheduler is None:
        logger.warning("Scheduler not initialized, cannot reschedule")
        return

    # Remove existing job
    try:
        _scheduler.remove_job(JOB_ID)
    except Exception:
        pass  # Job might not exist

    trigger = _build_trigger(cfg)
    if trigger:
        _scheduler.add_job(
            _run_ingestion_job,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            name="自动抓取",
            misfire_grace_time=3600,
        )
        # Log next run time
        job = _scheduler.get_job(JOB_ID)
        next_run = job.next_run_time if job else "unknown"
        logger.info("📅 Ingestion job rescheduled: type=%s, hour=%s:%02d, tz=%s, next_run=%s",
                    cfg.schedule_type, cfg.schedule_hour, cfg.schedule_minute,
                    cfg.timezone, next_run)
    else:
        logger.info("📅 Ingestion job removed (disabled or schedule_type=off)")


async def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("👋 APScheduler shut down")
        _scheduler = None
