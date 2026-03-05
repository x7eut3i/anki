"""Load prompt content from DB (PromptConfig table) with fallback to hardcoded defaults.

Usage:
    from app.services.prompt_loader import get_prompt

    # In any endpoint / service that has a SQLModel session:
    system_prompt = get_prompt(session, "card_system")
    model_override = get_prompt_model(session, "card_system")
"""

import logging
from typing import Optional

from sqlmodel import Session, select

from app.models.prompt_config import PromptConfig

logger = logging.getLogger("anki.prompt_loader")


def get_prompt(session: Session, prompt_key: str, fallback: str = "") -> str:
    """Return the prompt content for *prompt_key*.

    1. Try to load from the ``prompt_configs`` DB table.
    2. If not found, return *fallback* (which the caller should set to the
       hardcoded constant so behaviour is unchanged when the table is empty).
    """
    try:
        row = session.exec(
            select(PromptConfig).where(PromptConfig.prompt_key == prompt_key)
        ).first()
        if row and row.content:
            return row.content
    except Exception as exc:
        logger.warning("Failed to load prompt '%s' from DB: %s", prompt_key, exc)

    return fallback


def get_prompt_model(session: Session, prompt_key: str) -> Optional[str]:
    """Return the model_override for *prompt_key*, or None if not set."""
    try:
        row = session.exec(
            select(PromptConfig).where(PromptConfig.prompt_key == prompt_key)
        ).first()
        if row and row.model_override:
            return row.model_override
    except Exception as exc:
        logger.warning("Failed to load prompt model for '%s': %s", prompt_key, exc)

    return None
