"""AI service: OpenAI-compatible API client for card explanations, mnemonics, and generation."""

import json
import time
from datetime import datetime, timezone, timedelta

import httpx
from sqlmodel import Session, select, func

from app.models.ai_config import AIConfig, AIUsageLog
from app.services.ai_logger import log_ai_request, log_ai_response, log_ai_call_to_db


class AIService:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        self.user_id = user_id
        self._config: AIConfig | None = None

    @property
    def config(self) -> AIConfig | None:
        if self._config is None:
            self._config = self.session.exec(
                select(AIConfig).where(AIConfig.user_id == self.user_id)
            ).first()
            if self._config is None:
                # Auto-seed from ai_config.json if available
                try:
                    from app.main import _load_ai_config_file
                    defaults = _load_ai_config_file()
                    if defaults and defaults.get("api_key"):
                        self._config = AIConfig(
                            user_id=self.user_id,
                            api_base_url=defaults["api_base_url"],
                            api_key=defaults["api_key"],
                            model=defaults["model"],
                            max_daily_calls=defaults.get("max_daily_calls", 100),
                            is_enabled=True,
                        )
                        self.session.add(self._config)
                        self.session.commit()
                        self.session.refresh(self._config)
                except Exception:
                    pass
        return self._config

    def is_available(self) -> bool:
        """Check if AI is configured and within daily limit."""
        cfg = self.config
        if not cfg or not cfg.is_enabled or not cfg.api_key:
            return False
        return self._get_today_usage() < cfg.max_daily_calls

    def get_unavailable_reason(self) -> str:
        """Return a specific Chinese error message explaining why AI is unavailable."""
        cfg = self.config
        if cfg is None:
            return "AI 配置未找到，请先在设置页面配置 AI"
        if not cfg.api_key:
            return "API 密钥未配置，请在设置页面填写 API Key"
        if not cfg.is_enabled:
            return "AI 功能未启用，请在设置页面开启"
        if self._get_today_usage() >= cfg.max_daily_calls:
            return "今日 AI 调用已达上限"
        return "AI 服务不可用"

    def _get_today_usage(self) -> int:
        """Count today's AI API calls."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return self.session.exec(
            select(func.count()).where(
                AIUsageLog.user_id == self.user_id,
                AIUsageLog.created_at >= today_start,
            )
        ).one()

    def get_usage_stats(self) -> dict:
        """Get AI usage statistics."""
        cfg = self.config
        today_calls = self._get_today_usage()
        total_calls = self.session.exec(
            select(func.count()).where(AIUsageLog.user_id == self.user_id)
        ).one()
        total_tokens = self.session.exec(
            select(func.sum(AIUsageLog.tokens_used)).where(
                AIUsageLog.user_id == self.user_id
            )
        ).one() or 0

        return {
            "today_calls": today_calls,
            "max_daily_calls": cfg.max_daily_calls if cfg else 50,
            "total_calls": total_calls,
            "total_tokens": total_tokens,
        }

    @property
    def max_retries(self) -> int:
        """Get configured max retries (default 3)."""
        cfg = self.config
        return getattr(cfg, "max_retries", 3) or 3

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        feature: str = "chat",
    ) -> dict:
        """Call OpenAI-compatible chat completion API with configurable retries."""
        cfg = self.config
        if not cfg or not cfg.is_enabled:
            raise ValueError("AI is not configured")

        if self._get_today_usage() >= cfg.max_daily_calls:
            raise ValueError("Daily AI call limit reached")

        # Use config values if not explicitly specified
        if max_tokens is None:
            max_tokens = getattr(cfg, "max_tokens", 8192) or 8192
        if temperature is None:
            temperature = getattr(cfg, "temperature", 0.3) or 0.3

        url = f"{cfg.api_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Log request
        log_ai_request(feature, cfg.model, messages, temperature, max_tokens)

        retries = self.max_retries
        last_error = None

        for attempt in range(retries):
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                break  # Success
            except Exception as e:
                last_error = e
                elapsed_ms = int((time.time() - start_time) * 1000)
                log_ai_response(feature, cfg.model, "", 0, elapsed_ms, error=f"attempt {attempt+1}/{retries}: {e}")
                log_ai_call_to_db(
                    feature=feature,
                    model=cfg.model,
                    tokens_used=0,
                    elapsed_ms=elapsed_ms,
                    status="error",
                    error_message=f"attempt {attempt+1}/{retries}: {e}",
                    user_id=self.user_id,
                )
                if attempt < retries - 1:
                    import asyncio
                    await asyncio.sleep(2 * (attempt + 1))  # Exponential backoff
                    continue
                raise

        elapsed_ms = int((time.time() - start_time) * 1000)
        result = response.json()

        # Log usage
        tokens = result.get("usage", {}).get("total_tokens", 0)
        content = result["choices"][0]["message"]["content"] or ""

        # Log response
        log_ai_response(feature, cfg.model, content, tokens, elapsed_ms)

        # Log to DB for AI stats dashboard
        log_ai_call_to_db(
            feature=feature,
            model=cfg.model,
            tokens_used=tokens,
            elapsed_ms=elapsed_ms,
            status="ok",
            user_id=self.user_id,
        )

        # Write usage log with a *separate* session so we don't commit the
        # caller's session as a side-effect.  Background tasks keep their
        # main session open for a long time; an unexpected mid-task commit
        # can corrupt the session's identity-map and cause subtle bugs or
        # SQLite locking issues.
        try:
            from app.database import engine as _db_engine
            from sqlmodel import Session as _SyncSession
            with _SyncSession(_db_engine) as _log_sess:
                _log_sess.add(AIUsageLog(
                    user_id=self.user_id,
                    feature=feature,
                    tokens_used=tokens,
                ))
                _log_sess.commit()
        except Exception:
            pass  # Don't fail the AI call just because logging failed

        return {"content": content, "tokens_used": tokens, "elapsed_ms": elapsed_ms}

    async def explain_card(
        self, card_front: str, card_back: str, user_answer: str = ""
    ) -> dict:
        """Generate an explanation for a flashcard."""
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位专业的学习辅导助手。请用简洁明了的中文解释以下知识点。"
                    "包含：1. 详细解释 2. 记忆技巧/口诀 3. 相关知识点。"
                    "回复格式为JSON: {\"explanation\": \"...\", \"mnemonic\": \"...\", \"related\": [\"...\"]}"
                ),
            },
            {
                "role": "user",
                "content": f"题目：{card_front}\n正确答案：{card_back}"
                + (f"\n用户回答：{user_answer}" if user_answer else ""),
            },
        ]
        result = await self.chat_completion(messages, feature="explain")

        try:
            from app.services.json_repair import repair_json
            parsed = json.loads(repair_json(result["content"]))
        except (json.JSONDecodeError, KeyError):
            parsed = {
                "explanation": result["content"],
                "mnemonic": None,
                "related": [],
            }

        # Update usage log feature
        return {
            "explanation": parsed.get("explanation", result["content"]),
            "mnemonic": parsed.get("mnemonic"),
            "related_concepts": parsed.get("related", []),
        }

    async def generate_cards_from_text(
        self,
        text: str,
        category_name: str = "",
        card_type: str = "qa",
        count: int = 5,
        available_categories: list[str] | None = None,
    ) -> list[dict]:
        """Generate flashcards from text content using the standard pipeline prompt."""
        from app.services.prompts import CARD_SYSTEM_PROMPT, make_pipeline_user_prompt
        from app.models.prompt_config import PromptConfig
        from sqlmodel import select as sel

        # Use same prompt system as pipeline / import / article card gen
        # Get customized system prompt if available
        system_prompt = CARD_SYSTEM_PROMPT
        try:
            cfg = self.session.exec(
                sel(PromptConfig).where(PromptConfig.prompt_key == "card_system")
            ).first()
            if cfg and cfg.content:
                system_prompt = cfg.content
        except Exception:
            pass

        # Build category list
        cat_list = ""
        if available_categories:
            cat_list = "、".join(available_categories)
        elif category_name:
            cat_list = category_name

        # Use the standard pipeline user prompt
        user_prompt = make_pipeline_user_prompt(
            title=f"用户输入 ({category_name or '综合'})",
            content=text,
            category_list=cat_list,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = await self.chat_completion(messages,
                                            feature="card_generation")

        try:
            from app.services.json_repair import repair_json, robust_json_parse
            content = repair_json(result["content"])
            parsed = robust_json_parse(content)
            if parsed is None:
                raise json.JSONDecodeError("all strategies failed", content, 0)
            # Pipeline prompt returns {"article_quality_score": N, "cards": [...]}
            if isinstance(parsed, dict):
                cards = parsed.get("cards", [])
            elif isinstance(parsed, list):
                cards = parsed
            else:
                cards = []
        except (json.JSONDecodeError, IndexError):
            cards = []

        return cards

    async def chat_tutor(
        self,
        message: str,
        history: list[dict] | None = None,
        card_context: str = "",
    ) -> dict:
        """AI tutor chat for study topics."""
        system_msg = (
            "你是一位经验丰富的学习辅导助手。"
            "请耐心解答学习者的问题，使用简洁准确的中文回答。"
            "如果涉及具体知识点，请给出记忆技巧。"
        )
        if card_context:
            system_msg += f"\n\n当前学习的卡片内容：{card_context}"

        messages = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        result = await self.chat_completion(messages)
        return {
            "reply": result["content"],
            "tokens_used": result["tokens_used"],
        }

    @staticmethod
    async def list_models(api_base_url: str, api_key: str) -> dict:
        """Fetch available models from an OpenAI-compatible API."""
        url = f"{api_base_url.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
            data = response.json()
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id:
                    models.append(model_id)
            models.sort()
            return {"success": True, "models": models}
        except Exception as e:
            return {"success": False, "models": [], "error": str(e)[:200]}

    @staticmethod
    async def test_connection(
        api_base_url: str, api_key: str, model: str
    ) -> dict:
        """Test AI API connection."""
        url = f"{api_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello, respond with OK."}],
            "max_tokens": 10,
        }

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "message": "Connection successful",
                "response_time_ms": elapsed_ms,
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "message": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                "response_time_ms": 0,
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)[:200],
                "response_time_ms": 0,
            }
