"""Shared FastAPI dependencies."""

from fastapi import Depends
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session
from app.models.user import User


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure user is active."""
    if not current_user.is_active:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure user is admin."""
    if not current_user.is_admin:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
