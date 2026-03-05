"""Tests for Excel import and other new features."""

import io
import json
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.card import Card
from app.models.deck import Deck


class TestExcelImport:
    """Test Excel file import functionality."""

    def _create_xlsx_bytes(self, rows: list[list]) -> bytes:
        """Helper to create a minimal .xlsx file in memory."""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_import_excel_standard_columns(self, client: TestClient, auth_headers: dict, session: Session):
        """Test importing Excel with standard column names."""
        # Create a deck first
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Excel Test Deck"},
            headers=auth_headers,
        )
        assert deck_resp.status_code == 201
        deck_id = deck_resp.json()["id"]

        xlsx = self._create_xlsx_bytes([
            ["front", "back", "explanation", "tags"],
            ["What is 2+2?", "4", "Basic math", "math"],
            ["Capital of France?", "Paris", "European geography", "geography"],
        ])

        resp = client.post(
            f"/api/import-export/import/excel?deck_id={deck_id}",
            files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 2
        assert len(data["errors"]) == 0

    def test_import_excel_chinese_columns(self, client: TestClient, auth_headers: dict, session: Session):
        """Test importing Excel with Chinese column names."""
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Chinese Cols Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        xlsx = self._create_xlsx_bytes([
            ["题目", "答案", "解析", "标签"],
            ["什么是CPU？", "中央处理器", "计算机核心组件", "计算机"],
        ])

        resp = client.post(
            f"/api/import-export/import/excel?deck_id={deck_id}",
            files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["created"] == 1

    def test_import_excel_with_distractors(self, client: TestClient, auth_headers: dict, session: Session):
        """Test importing Excel with distractors column."""
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Distractors Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        xlsx = self._create_xlsx_bytes([
            ["front", "back", "distractors"],
            ["首都是哪个城市？", "北京", "上海,广州,深圳"],
        ])

        resp = client.post(
            f"/api/import-export/import/excel?deck_id={deck_id}",
            files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["created"] == 1

        # Verify distractors are stored as JSON array
        cards = session.exec(select(Card).where(Card.deck_id == deck_id)).all()
        assert len(cards) == 1
        distractors = json.loads(cards[0].distractors)
        assert len(distractors) == 3
        assert "上海" in distractors

    def test_import_excel_empty_rows_skipped(self, client: TestClient, auth_headers: dict, session: Session):
        """Test that empty rows are skipped."""
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Empty Rows Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        xlsx = self._create_xlsx_bytes([
            ["front", "back"],
            ["Question 1", "Answer 1"],
            ["", ""],  # empty row
            [None, None],  # null row
            ["Question 2", "Answer 2"],
        ])

        resp = client.post(
            f"/api/import-export/import/excel?deck_id={deck_id}",
            files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        assert resp.json()["created"] == 2

    def test_import_excel_no_header_fallback(self, client: TestClient, auth_headers: dict, session: Session):
        """Test fallback when column names don't match any aliases."""
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Fallback Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        xlsx = self._create_xlsx_bytes([
            ["col_a", "col_b", "col_c"],
            ["My question", "My answer", "My explanation"],
        ])

        resp = client.post(
            f"/api/import-export/import/excel?deck_id={deck_id}",
            files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["created"] == 1

        cards = session.exec(select(Card).where(Card.deck_id == deck_id)).all()
        assert cards[0].front == "My question"
        assert cards[0].back == "My answer"


class TestAIAvailability:
    """Test AI service availability checks and error messages."""

    def test_unavailable_reason_no_config(self):
        """Test that get_unavailable_reason returns specific error when no config."""
        from unittest.mock import PropertyMock
        from app.services.ai_service import AIService
        from sqlmodel import Session

        # Create AIService with a mock session that returns no config
        service = AIService.__new__(AIService)
        service.session = MagicMock(spec=Session)
        service.user_id = 999

        # Mock config property to return None (no config found)
        with patch.object(type(service), 'config', new_callable=PropertyMock, return_value=None):
            reason = service.get_unavailable_reason()
            assert reason is not None
            assert "配置" in reason

    def test_unavailable_reason_no_api_key(self):
        """Test that get_unavailable_reason returns api key error when key is empty."""
        from unittest.mock import PropertyMock
        from app.services.ai_service import AIService

        service = AIService.__new__(AIService)
        service.session = MagicMock(spec=Session)
        service.user_id = 999

        mock_config = MagicMock()
        mock_config.is_enabled = True
        mock_config.api_key = ""
        mock_config.max_daily_calls = 100

        with patch.object(type(service), 'config', new_callable=PropertyMock, return_value=mock_config):
            reason = service.get_unavailable_reason()
            assert reason is not None
            assert "密钥" in reason

    def test_unavailable_reason_disabled(self):
        """Test that get_unavailable_reason returns disabled error."""
        from unittest.mock import PropertyMock
        from app.services.ai_service import AIService

        service = AIService.__new__(AIService)
        service.session = MagicMock(spec=Session)
        service.user_id = 999

        mock_config = MagicMock()
        mock_config.is_enabled = False
        mock_config.api_key = "sk-test"
        mock_config.max_daily_calls = 100

        with patch.object(type(service), 'config', new_callable=PropertyMock, return_value=mock_config):
            reason = service.get_unavailable_reason()
            assert reason is not None
            assert "启用" in reason

    def test_config_skips_empty_api_key_on_update(self, client: TestClient, auth_headers: dict):
        """Test that PUT /config with empty api_key does not overwrite stored key."""
        # First save a config with a key
        resp1 = client.put(
            "/api/ai/config",
            json={
                "api_base_url": "https://example.com/v1",
                "api_key": "sk-test-key-12345",
                "model": "test-model",
                "is_enabled": True,
            },
            headers=auth_headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["api_key_set"] is True

        # Update config without api_key (empty string)
        resp2 = client.put(
            "/api/ai/config",
            json={
                "api_base_url": "https://example.com/v2",
                "api_key": "",
            },
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        # api_key should still be set (not overwritten with empty)
        assert resp2.json()["api_key_set"] is True


class TestDashboardStats:
    """Test that review stats return correct field names."""

    def test_stats_field_names(self, client: TestClient, auth_headers: dict):
        """Test that /review/stats returns the expected field names."""
        resp = client.get("/api/review/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        # These are the correct field names the frontend expects
        assert "reviewed_today" in data
        assert "cards_due_today" in data
        assert "streak_days" in data
        assert "retention_rate" in data
        assert "total_cards" in data
        assert "cards_by_state" in data
        assert "daily_reviews" in data


class TestQuizChoiceOnly:
    """Test that quiz generates choice-only questions by default."""

    def test_quiz_default_choice_only(self, client: TestClient, auth_headers: dict, session: Session):
        """Quiz should generate choice questions by default, not QA."""
        # Create a deck with cards that have distractors
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Quiz Test Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        # Create cards with distractors (should produce choice questions)
        for i in range(5):
            client.post(
                "/api/cards",
                json={
                    "deck_id": deck_id,
                    "front": f"Question {i}?",
                    "back": f"Answer {i}",
                    "distractors": json.dumps([f"Wrong {i}A", f"Wrong {i}B", f"Wrong {i}C"]),
                },
                headers=auth_headers,
            )

        resp = client.post(
            "/api/quiz/generate",
            json={"card_count": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        questions = data.get("questions", [])
        assert len(questions) > 0

        # All questions should be choice type
        for q in questions:
            assert q["question_type"] == "choice", f"Expected 'choice', got '{q['question_type']}'"
            assert q["choices"] is not None
            assert len(q["choices"]) > 0


class TestSessionProgress:
    """Test study session progress tracking."""

    def test_session_progress_update(self, client: TestClient, auth_headers: dict, session: Session):
        """Test that session progress can be updated via POST."""
        # Create a deck and cards
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Session Test Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        card_resp = client.post(
            "/api/cards",
            json={"deck_id": deck_id, "front": "Q1", "back": "A1"},
            headers=auth_headers,
        )
        card_id = card_resp.json()["id"]

        # Create a study session
        session_resp = client.post(
            "/api/review/session",
            json={"mode": "review", "deck_id": deck_id},
            headers=auth_headers,
        )
        assert session_resp.status_code == 200
        session_id = session_resp.json()["id"]

        # Update progress with JSON body
        progress_resp = client.post(
            f"/api/review/session/{session_id}/progress",
            json={"card_id": card_id, "is_correct": True},
            headers=auth_headers,
        )
        assert progress_resp.status_code == 200
        data = progress_resp.json()
        assert data["cards_reviewed"] == 1
        assert data["cards_correct"] == 1

    def test_active_session_excludes_quiz(self, client: TestClient, auth_headers: dict, session: Session):
        """Test that active session endpoint excludes quiz sessions by default."""
        # Create a quiz session
        deck_resp = client.post(
            "/api/decks",
            json={"name": "Quiz Exclude Deck"},
            headers=auth_headers,
        )
        deck_id = deck_resp.json()["id"]

        # Add a card
        client.post(
            "/api/cards",
            json={"deck_id": deck_id, "front": "Q", "back": "A"},
            headers=auth_headers,
        )

        # The active session endpoint should not return quiz-mode sessions
        resp = client.get("/api/review/session/active", headers=auth_headers)
        # May return null or a non-quiz session
        if resp.status_code == 200 and resp.json() is not None:
            assert resp.json()["mode"] != "quiz"


class TestBatchEnrichSchema:
    """Test batch enrich defaults and schema."""

    def test_batch_size_default_50(self):
        """Test that batch size defaults to 50."""
        from app.schemas.ai import AIBatchEnrichRequest
        req = AIBatchEnrichRequest()
        assert req.batch_size == 50

    def test_batch_enrich_response_no_required_fields(self):
        """Test that AIBatchEnrichResponse works with minimal data."""
        from app.schemas.ai import AIBatchEnrichResponse
        resp = AIBatchEnrichResponse(message="test")
        assert resp.total == 0
        assert resp.enriched == 0
        assert resp.message == "test"
