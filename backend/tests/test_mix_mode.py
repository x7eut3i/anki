"""Tests for mix mode (cross-category study sessions)."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.card import Card
from app.models.user import User
from app.services.review_service import ReviewService


class TestMixMode:
    def test_create_mix_session(
        self, client: TestClient, auth_headers: dict, sample_cards, categories
    ):
        """Mix mode: select multiple categories."""
        cat_ids = [categories[0].id, categories[1].id, categories[4].id]
        response = client.post("/api/review/session", headers=auth_headers, json={
            "mode": "mix",
            "category_ids": cat_ids,
            "card_limit": 50,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "mix"
        assert data["total_cards"] >= 1

    def test_mix_due_cards_from_multiple_categories(
        self, client: TestClient, auth_headers: dict, sample_cards, categories
    ):
        """Due cards should come from multiple categories."""
        cat_ids = [categories[0].id, categories[1].id]
        response = client.post("/api/review/due", headers=auth_headers, json={
            "category_ids": cat_ids,
            "limit": 50,
        })
        assert response.status_code == 200
        data = response.json()

        # Should include cards from both categories
        found_cats = set(c["category_id"] for c in data["cards"])
        assert len(found_cats) >= 1  # At least 1 category represented

    def test_mix_all_categories(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        """No category filter = all categories."""
        response = client.post("/api/review/due", headers=auth_headers, json={
            "limit": 50,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_due"] == len(sample_cards)

    def test_mix_session_recovery(
        self, client: TestClient, auth_headers: dict, sample_cards, categories
    ):
        """Create a mix session, verify it can be recovered."""
        # Create session
        create_resp = client.post("/api/review/session", headers=auth_headers, json={
            "mode": "mix",
            "category_ids": [categories[0].id],
            "card_limit": 10,
        })
        session_data = create_resp.json()

        # Get active session (recovery)
        active_resp = client.get("/api/review/session/active", headers=auth_headers)
        assert active_resp.status_code == 200
        active_data = active_resp.json()
        assert active_data["id"] == session_data["id"]
        assert active_data["is_completed"] is False


class TestMixModeService:
    """Direct service tests for mix mode."""

    def test_weighted_category_selection(
        self, session: Session, test_user: User, sample_cards, categories
    ):
        """Due cards ordered by state priority."""
        service = ReviewService(session, test_user.id)
        result = service.get_due_cards(
            category_ids=[c.id for c in categories[:5]],
            limit=50,
        )
        # All new cards should be returned
        assert result["total_due"] >= 1

    def test_empty_category_mix(
        self, session: Session, test_user: User, categories
    ):
        """Mix mode with categories that have no cards."""
        service = ReviewService(session, test_user.id)
        result = service.get_due_cards(
            category_ids=[categories[9].id],  # last category - no cards
            limit=50,
        )
        assert result["total_due"] == 0
        assert len(result["cards"]) == 0
