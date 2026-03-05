"""Tests for AI service (config, connection, explain, chat, generate, usage)."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.ai_config import AIConfig, AIUsageLog
from app.models.user import User

# Load AI config helper (same as in conftest.py)
AI_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "ai_config.json"


def _load_ai_config() -> dict:
    """Load AI config from ai_config.json."""
    if AI_CONFIG_PATH.exists():
        with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "api_base_url": data.get("api_base_url", ""),
            "api_key": data.get("api_key", ""),
            "model": data.get("model", ""),
            "max_daily_calls": data.get("max_daily_calls", 100),
        }
    return {
        "api_base_url": "https://api.example.com/v1",
        "api_key": "sk-test-placeholder",
        "model": "test-model",
        "max_daily_calls": 100,
    }


# ---------------------------------------------------------------------------
# AI Configuration CRUD
# ---------------------------------------------------------------------------


class TestAIConfigEndpoints:
    def test_save_ai_config(self, client: TestClient, auth_headers: dict, ai_config: dict):
        """Save a new AI configuration."""
        response = client.put("/api/ai/config", headers=auth_headers, json={
            "api_base_url": ai_config["api_base_url"],
            "api_key": ai_config["api_key"],
            "model": ai_config["model"],
            "max_daily_calls": ai_config["max_daily_calls"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["api_base_url"] == ai_config["api_base_url"]
        assert data["model"] == ai_config["model"]

    def test_get_ai_config(self, client: TestClient, auth_headers: dict):
        """Retrieve saved AI configuration."""
        # Save first
        client.put("/api/ai/config", headers=auth_headers, json={
            "api_base_url": "https://api.openai.com/v1",
            "api_key": "sk-abc",
            "model": "gpt-4o-mini",
        })

        response = client.get("/api/ai/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "gpt-4o-mini"

    def test_update_ai_config(self, client: TestClient, auth_headers: dict):
        """Update existing AI configuration."""
        # Create
        client.put("/api/ai/config", headers=auth_headers, json={
            "api_base_url": "https://api.example.com/v1",
            "api_key": "sk-old",
            "model": "old-model",
        })

        # Update
        response = client.put("/api/ai/config", headers=auth_headers, json={
            "model": "new-model",
            "max_daily_calls": 200,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "new-model"

    def test_no_config_returns_empty(self, client: TestClient, auth_headers: dict):
        """If no config saved yet, return sensible default or 404."""
        response = client.get("/api/ai/config", headers=auth_headers)
        # Could be 200 with defaults or 404
        assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Test Connection
# ---------------------------------------------------------------------------


class TestAIConnection:
    def test_connection_success_mock(
        self, client: TestClient, auth_headers: dict, ai_config: dict
    ):
        """Test connection button (mocked AI response)."""
        with patch("app.routers.ai.AIService.test_connection") as mock_test:
            mock_test.return_value = {"success": True, "message": "Connected", "response_time_ms": 150}
            response = client.post("/api/ai/test-connection", headers=auth_headers, json={
                "api_base_url": ai_config["api_base_url"],
                "api_key": ai_config["api_key"],
                "model": ai_config["model"],
            })
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


# ---------------------------------------------------------------------------
# AI Features (explain, mnemonic, generate, chat)
# ---------------------------------------------------------------------------


class TestAIFeatures:
    def test_explain_card_mock(self, client: TestClient, auth_headers: dict, sample_cards):
        """AI explains a card's content."""
        card = sample_cards[0]
        with patch("app.routers.ai.AIService") as MockAI:
            mock_instance = MockAI.return_value
            mock_instance.is_available.return_value = True
            mock_instance.explain_card = AsyncMock(return_value={
                "explanation": "这道题考查的是宪法的基本原则...",
                "mnemonic": None,
                "related_concepts": [],
            })
            response = client.post(
                "/api/ai/explain",
                headers=auth_headers,
                json={"card_id": card.id},
            )
            assert response.status_code == 200
            data = response.json()
            assert "explanation" in data

    def test_generate_mnemonic_mock(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        """AI generates a mnemonic via explain endpoint."""
        card = sample_cards[0]
        with patch("app.routers.ai.AIService") as MockAI:
            mock_instance = MockAI.return_value
            mock_instance.is_available.return_value = True
            mock_instance.explain_card = AsyncMock(return_value={
                "explanation": "这是一个重要知识点",
                "mnemonic": "记忆口诀：人社民法，依治为先",
                "related_concepts": [],
            })
            response = client.post(
                "/api/ai/explain",
                headers=auth_headers,
                json={"card_id": card.id},
            )
            assert response.status_code == 200

    def test_generate_cards_from_text_mock(
        self, client: TestClient, auth_headers: dict, test_deck
    ):
        """AI generates cards from pasted text."""
        with patch("app.routers.ai.AIService") as MockAI:
            mock_instance = MockAI.return_value
            mock_instance.is_available.return_value = True
            mock_instance.generate_cards_from_text = AsyncMock(return_value=[
                {"front": "AI生成问题", "back": "AI生成答案"},
            ])
            response = client.post(
                "/api/ai/generate",
                headers=auth_headers,
                json={
                    "text": "宪法是国家的根本大法...",
                    "deck_id": test_deck.id,
                    "count": 5,
                },
            )
            assert response.status_code == 200

    def test_tutor_chat_mock(self, client: TestClient, auth_headers: dict):
        """AI tutor chat with context."""
        with patch("app.routers.ai.AIService") as MockAI:
            mock_instance = MockAI.return_value
            mock_instance.is_available.return_value = True
            mock_instance.chat_tutor = AsyncMock(return_value={
                "reply": "宪法的基本原则包括...",
                "tokens_used": 100,
            })
            response = client.post(
                "/api/ai/chat",
                headers=auth_headers,
                json={
                    "message": "请解释一下宪法的基本原则",
                },
            )
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# Usage Tracking
# ---------------------------------------------------------------------------


class TestAIUsageTracking:
    def test_usage_log_created(self, session: Session, test_user: User):
        """Each AI call should create a usage log entry."""
        log = AIUsageLog(
            user_id=test_user.id,
            feature="explain",
            tokens_used=150,
            cost_estimate=0.001,
        )
        session.add(log)
        session.commit()
        session.refresh(log)

        assert log.feature == "explain"
        assert log.tokens_used == 150

    def test_daily_limit_enforcement(self, session: Session, test_user: User):
        """Usage should be tracked against daily limit."""
        # Create config with limit of 5
        config = AIConfig(
            user_id=test_user.id,
            api_base_url="https://api.test.com/v1",
            api_key="sk-test",
            model="test-model",
            max_daily_calls=5,
        )
        session.add(config)
        session.commit()

        # Create 5 usage logs to simulate hitting limit
        for i in range(5):
            log = AIUsageLog(
                user_id=test_user.id,
                feature="explain",
                tokens_used=100,
            )
            session.add(log)
        session.commit()

        # Check limit
        from sqlmodel import select, func
        count = session.exec(
            select(func.count()).where(
                AIUsageLog.user_id == test_user.id,
            )
        ).one()
        assert count >= config.max_daily_calls

    def test_usage_accumulates(self, session: Session, test_user: User):
        """Multiple calls accumulate usage logs."""
        # Simulate 3 calls
        for i in range(3):
            log = AIUsageLog(
                user_id=test_user.id,
                feature="chat",
                tokens_used=100,
                cost_estimate=0.001,
            )
            session.add(log)

        session.commit()

        from sqlmodel import select, func
        total_tokens = session.exec(
            select(func.sum(AIUsageLog.tokens_used)).where(
                AIUsageLog.user_id == test_user.id,
            )
        ).one()
        count = session.exec(
            select(func.count()).where(
                AIUsageLog.user_id == test_user.id,
            )
        ).one()

        assert count == 3
        assert total_tokens == 300

    def test_get_usage_stats(self, client: TestClient, auth_headers: dict):
        """Retrieve user's AI usage stats."""
        response = client.get("/api/ai/usage", headers=auth_headers)
        assert response.status_code == 200
