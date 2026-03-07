"""Router for user management (admin only)."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, hash_password
from app.database import get_session
from app.models.user import User

logger = logging.getLogger("anki.users")

router = APIRouter(prefix="/api/users", tags=["users"])


# ── Schemas ──

class UserListItem(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False


class UserToggleActiveRequest(BaseModel):
    is_active: bool


class UserResetPasswordRequest(BaseModel):
    new_password: str


# ── Endpoints ──

@router.get("", response_model=list[UserListItem])
def list_users(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List all users (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    users = session.exec(select(User).order_by(User.created_at)).all()
    return [UserListItem.model_validate(u) for u in users]


@router.post("", response_model=UserListItem, status_code=201)
def create_user(
    data: UserCreateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a new user (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6个字符")

    existing = session.exec(
        select(User).where(User.username == data.username)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    existing_email = session.exec(
        select(User).where(User.email == data.email)
    ).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="邮箱已被使用")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        is_admin=data.is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Auto-create AI config for the new user
    from app.models.ai_config import AIConfig
    config = AIConfig(user_id=user.id)
    session.add(config)
    session.commit()

    logger.info("Admin %s created user %s", current_user.username, data.username)
    return UserListItem.model_validate(user)


@router.put("/{user_id}/toggle-active")
def toggle_user_active(
    user_id: int,
    data: UserToggleActiveRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Toggle user active status (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.is_active = data.is_active
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    action = "启用" if data.is_active else "禁用"
    logger.info("Admin %s %s user %s", current_user.username, action, user.username)
    return {"ok": True, "message": f"已{action}用户 {user.username}"}


@router.put("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    data: UserResetPasswordRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Reset a user's password (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6个字符")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = hash_password(data.new_password)
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    logger.info("Admin %s reset password for user %s", current_user.username, user.username)
    return {"ok": True, "message": f"已重置用户 {user.username} 的密码"}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete a user and all associated data (admin only, cannot delete self)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    username = user.username

    # Delete associated data in dependent tables
    from sqlmodel import text
    dependent_tables = [
        "user_card_progress",
        "study_sessions",
        "study_presets",
        "review_log",
        "article_analysis",
        "ai_jobs",
        "ai_configs",
        "ai_prompt_configs",
    ]
    for table in dependent_tables:
        try:
            session.exec(text(f"DELETE FROM {table} WHERE user_id = :uid"), params={"uid": user_id})
        except Exception:
            pass  # Table may not exist in older schemas

    session.delete(user)
    session.commit()

    logger.info("Admin %s deleted user %s (id=%d)", current_user.username, username, user_id)
    return {"ok": True, "message": f"已删除用户 {username}"}
