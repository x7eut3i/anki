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
    """Log an outgoing AI API request (summary only — no full body)."""
    try:
        # Only log a concise summary line; full message bodies are omitted to
        # keep the log file slim.  On failure the response logger will record
        # the full payload.
        total_chars = sum(len(m.get("content", "")) for m in messages)
        ai_logger.info(f"[{feature}] REQUEST | model={model} | msgs={len(messages)} | "
                       f"temp={temperature} | max_tokens={max_tokens} | input_chars={total_chars}")
    except Exception as e:
        ai_logger.error(f"Failed to log AI request: {e}")


def _is_debug_response() -> bool:
    """Check if full AI response logging is enabled via AI_DEBUG_RESPONSE env var."""
    return os.getenv("AI_DEBUG_RESPONSE", "").lower() in ("1", "true", "yes")


def log_ai_response(
    feature: str,
    model: str,
    content: str,
    tokens_used: int = 0,
    elapsed_ms: int = 0,
    error: str | None = None,
) -> None:
    """Log an incoming AI API response.

    Full response body is logged at DEBUG level when there is an error,
    or when AI_DEBUG_RESPONSE is enabled.
    """
    try:
        status = "ERROR" if error else "OK"
        ai_logger.info(f"[{feature}] RESPONSE {status} | model={model} | "
                       f"tokens={tokens_used} | {elapsed_ms}ms | "
                       f"content_len={len(content) if content else 0}"
                       + (f" | error={error}" if error else ""))

        # Dump full response body on failure or when debug mode is enabled
        if error or _is_debug_response():
            entry = {
                "direction": "RESPONSE_ERROR" if error else "RESPONSE_DEBUG",
                "feature": feature,
                "model": model,
                "tokens_used": tokens_used,
                "elapsed_ms": elapsed_ms,
                "content_length": len(content) if content else 0,
                "content": _truncate(content) if content else "",
            }
            if error:
                entry["error"] = error
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
    source: str = "",
    raw_response: str = "",
) -> None:
    """Log an AI interaction to the database for reliable statistics.

    Args:
        source: Caller context, e.g. "crawl", "reading", "manual", "regenerate".
                Used to filter crawl failures out of AI stats.
        raw_response: Full raw AI response body. Stored on failures, or on
                      success when AI_DEBUG_RESPONSE is enabled.
    """
    try:
        from app.database import engine as db_engine
        from sqlmodel import Session as SyncSession
        from app.models.ai_interaction_log import AIInteractionLog

        # Store raw_response on failure, or on success if debug mode is on
        store_raw = raw_response if (status != "ok" or _is_debug_response()) else ""

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
            source=source,
            raw_response=store_raw[:10000] if store_raw else "",
        )
        with SyncSession(db_engine) as session:
            session.add(log_entry)
            session.commit()
    except Exception as e:
        ai_logger.error(f"Failed to log AI call to DB: {e}")
