"""Router for AI async job management."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlmodel import Session, select, col

from app.auth import get_current_user
from app.database import get_session, engine
from app.models.ai_job import AIJob
from app.models.user import User

logger = logging.getLogger("anki.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── Schemas ──

class JobResponse(BaseModel):
    id: int
    job_type: str
    title: str
    status: str
    progress: int
    result_json: str
    error_message: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    model_config = {"from_attributes": True}


# ── Endpoints ──

@router.get("", response_model=list[JobResponse])
def list_jobs(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List AI jobs for the current user."""
    query = select(AIJob).where(AIJob.user_id == current_user.id)
    if status_filter:
        query = query.where(AIJob.status == status_filter)
    query = query.order_by(AIJob.created_at.desc()).limit(limit)
    jobs = session.exec(query).all()
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get a specific job's status."""
    job = session.get(AIJob, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JobResponse.model_validate(job)


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete a completed/failed job."""
    job = session.get(AIJob, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status in ("pending", "running"):
        raise HTTPException(status_code=400, detail="无法删除正在进行的任务")
    session.delete(job)
    session.commit()
    return {"ok": True}


@router.delete("")
def clear_completed_jobs(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Clear all completed/failed jobs."""
    jobs = session.exec(
        select(AIJob).where(
            AIJob.user_id == current_user.id,
            col(AIJob.status).in_(["completed", "failed"]),
        )
    ).all()
    count = len(jobs)
    for j in jobs:
        session.delete(j)
    session.commit()
    return {"ok": True, "cleared": count}


# ── Job creation helpers (used by other routers) ──

def create_job(session: Session, user_id: int, job_type: str, title: str) -> AIJob:
    """Create a new pending job."""
    job = AIJob(
        user_id=user_id,
        job_type=job_type,
        title=title,
        status="pending",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def update_job_status(
    job_id: int,
    status: str,
    progress: int = 0,
    result_json: str = "",
    error_message: str = "",
):
    """Update job status. Creates its own session since this runs in background.

    Wrapped in try/except because the caller's main session may hold a
    SHARED lock that blocks this writer (even with WAL + busy_timeout the
    write can occasionally time-out under heavy load).  A logging failure
    must never crash the background task.
    """
    try:
        from sqlmodel import Session as SyncSession
        with SyncSession(engine) as session:
            job = session.get(AIJob, job_id)
            if not job:
                return
            job.status = status
            job.progress = progress
            if status == "running" and not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            if status in ("completed", "failed"):
                job.completed_at = datetime.now(timezone.utc)
                job.progress = 100 if status == "completed" else job.progress
            if result_json:
                job.result_json = result_json
            if error_message:
                job.error_message = error_message[:2000]
            session.add(job)
            session.commit()
    except Exception as exc:
        logger.warning("update_job_status(%s, %s) failed: %s", job_id, status, exc)
