"""AI interaction logger: logs full request/response payloads to a dedicated file.

This module provides structured logging of all AI API calls (request payloads
and response bodies) to a separate log file for debugging and auditing.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# Create dedicated logger for AI interactions
ai_logger = logging.getLogger("anki.ai_interactions")

# Only configure if not already set up
if not ai_logger.handlers:
    log_dir = Path(__file__).resolve().parent.parent.parent / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ai_interactions.log"

    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    ai_logger.addHandler(handler)
    ai_logger.setLevel(logging.DEBUG)
    # Don't propagate to root logger
    ai_logger.propagate = False


def _truncate(text: str, max_len: int = 50000) -> str:
    """Truncate extremely long text for logging. High limit to preserve full payloads."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return f"{text[:half]}\n... ({len(text) - max_len} chars truncated) ...\n{text[-half:]}"


def log_ai_request(
    feature: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1000,
    extra: dict | None = None,
) -> None:
    """Log an outgoing AI API request."""
    try:
        # Log full message content (no truncation for debugging)
        logged_messages = []
        for msg in messages:
            logged_msg = {**msg}
            logged_messages.append(logged_msg)

        entry = {
            "direction": "REQUEST",
            "feature": feature,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "message_count": len(messages),
            "messages": logged_messages,
        }
        if extra:
            entry["extra"] = extra

        ai_logger.info(f"[{feature}] REQUEST | model={model} | msgs={len(messages)} | "
                       f"temp={temperature} | max_tokens={max_tokens}")
        ai_logger.debug(json.dumps(entry, ensure_ascii=False, indent=2))
    except Exception as e:
        ai_logger.error(f"Failed to log AI request: {e}")


def log_ai_response(
    feature: str,
    model: str,
    content: str,
    tokens_used: int = 0,
    elapsed_ms: int = 0,
    error: str | None = None,
) -> None:
    """Log an incoming AI API response."""
    try:
        entry = {
            "direction": "RESPONSE",
            "feature": feature,
            "model": model,
            "tokens_used": tokens_used,
            "elapsed_ms": elapsed_ms,
            "content_length": len(content) if content else 0,
            "content": content or "",
        }
        if error:
            entry["error"] = error

        status = "ERROR" if error else "OK"
        ai_logger.info(f"[{feature}] RESPONSE {status} | model={model} | "
                       f"tokens={tokens_used} | {elapsed_ms}ms | "
                       f"content_len={len(content) if content else 0}")
        ai_logger.debug(json.dumps(entry, ensure_ascii=False, indent=2))
    except Exception as e:
        ai_logger.error(f"Failed to log AI response: {e}")


def log_ai_call_to_db(
    feature: str,
    model: str,
    config_name: str = "",
    tokens_used: int = 0,
    elapsed_ms: int = 0,
    status: str = "ok",
    error_message: str = "",
    input_preview: str = "",
    output_length: int = 0,
    user_id: int | None = None,
) -> None:
    """Log an AI interaction to the database for reliable statistics."""
    try:
        from app.database import engine as db_engine
        from sqlmodel import Session as SyncSession
        from app.models.ai_interaction_log import AIInteractionLog

        log_entry = AIInteractionLog(
            user_id=user_id,
            feature=feature,
            model=model,
            config_name=config_name,
            tokens_used=tokens_used,
            elapsed_ms=elapsed_ms,
            status=status,
            error_message=error_message[:500] if error_message else "",
            input_preview=input_preview[:200] if input_preview else "",
            output_length=output_length,
        )
        with SyncSession(db_engine) as session:
            session.add(log_entry)
            session.commit()
    except Exception as e:
        ai_logger.error(f"Failed to log AI call to DB: {e}")
