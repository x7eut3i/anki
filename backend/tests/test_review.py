"""Tests for review endpoints and review service."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.card import Card
from app.models.review_log import ReviewLog
from app.models.user import User
from app.models.user_card_progress import UserCardProgress
from app.models.deck import Deck
from app.services.review_service import ReviewService


class TestDueCards:
    def test_get_due_cards(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.post("/api/review/due", headers=auth_headers, json={
            "limit": 50,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_due"] >= 1
        assert len(data["cards"]) >= 1

    def test_due_cards_filter_by_category(
        self, client: TestClient, auth_headers: dict, sample_cards, categories
    ):
        response = client.post("/api/review/due", headers=auth_headers, json={
            "category_ids": [categories[0].id],
            "limit": 50,
        })
        assert response.status_code == 200
        data = response.json()
        # Only 成语 category cards
        for card in data["cards"]:
            assert card["category_id"] == categories[0].id

    def test_due_cards_filter_by_deck(
        self, client: TestClient, auth_headers: dict, sample_cards, test_deck
    ):
        response = client.post("/api/review/due", headers=auth_headers, json={
            "deck_id": test_deck.id,
            "limit": 50,
        })
        assert response.status_code == 200
        data = response.json()
        for card in data["cards"]:
            assert card["deck_id"] == test_deck.id

    def test_suspended_cards_excluded(
        self, client: TestClient, auth_headers: dict, sample_cards, session: Session, test_user: User
    ):
        # Suspend a card via UserCardProgress
        card = sample_cards[0]
        progress = UserCardProgress(
            user_id=test_user.id,
            card_id=card.id,
            is_suspended=True,
        )
        session.add(progress)
        session.commit()

        response = client.post("/api/review/due", headers=auth_headers, json={
            "limit": 50,
        })
        data = response.json()
        card_ids = [c["id"] for c in data["cards"]]
        assert card.id not in card_ids


class TestReviewAnswer:
    def test_review_good(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        card = sample_cards[0]
        response = client.post("/api/review/answer", headers=auth_headers, json={
            "card_id": card.id,
            "rating": 3,  # Good
            "review_duration_ms": 5000,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["card_id"] == card.id
        assert data["reps"] == 1
        assert data["new_stability"] > 0

    def test_review_again(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        card = sample_cards[0]
        response = client.post("/api/review/answer", headers=auth_headers, json={
            "card_id": card.id,
            "rating": 1,  # Again
        })
        assert response.status_code == 200
        data = response.json()
        assert data["reps"] == 1

    def test_review_invalid_card(self, client: TestClient, auth_headers: dict):
        response = client.post("/api/review/answer", headers=auth_headers, json={
            "card_id": 9999,
            "rating": 3,
        })
        assert response.status_code == 404

    def test_review_invalid_rating(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.post("/api/review/answer", headers=auth_headers, json={
            "card_id": sample_cards[0].id,
            "rating": 5,  # Invalid
        })
        assert response.status_code == 422


class TestPreviewRatings:
    def test_preview(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        card = sample_cards[0]
        response = client.get(
            f"/api/review/preview/{card.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "again" in data
        assert "hard" in data
        assert "good" in data
        assert "easy" in data


class TestStudySession:
    def test_create_session(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.post("/api/review/session", headers=auth_headers, json={
            "mode": "review",
            "card_limit": 10,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "review"
        assert data["total_cards"] >= 1
        assert data["is_completed"] is False

    def test_get_active_session(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        # Create a session first
        client.post("/api/review/session", headers=auth_headers, json={
            "mode": "review",
            "card_limit": 10,
        })

        response = client.get("/api/review/session/active", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data["is_completed"] is False

    def test_no_active_session(
        self, client: TestClient, auth_headers: dict, categories
    ):
        response = client.get("/api/review/session/active", headers=auth_headers)
        assert response.status_code == 200
        # Should be null/None
        assert response.json() is None


class TestStats:
    def test_get_stats(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.get("/api/review/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_cards" in data
        assert "cards_due_today" in data
        assert "retention_rate" in data
        assert "streak_days" in data
        assert "cards_by_state" in data
        assert "category_stats" in data
        assert "daily_reviews" in data

    def test_stats_after_review(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        # Review a card
        client.post("/api/review/answer", headers=auth_headers, json={
            "card_id": sample_cards[0].id,
            "rating": 3,
            "review_duration_ms": 3000,
        })

        response = client.get("/api/review/stats", headers=auth_headers)
        data = response.json()
        assert data["reviewed_today"] >= 1
        assert data["time_studied_today_ms"] >= 3000


class TestReviewServiceDirect:
    """Direct tests on ReviewService (not via HTTP)."""

    def test_streak_calculation(
        self, session: Session, test_user: User, sample_cards
    ):
        service = ReviewService(session, test_user.id)

        # No reviews = 0 streak
        streak = service._calculate_streak()
        assert streak == 0

    def test_category_stats(
        self, session: Session, test_user: User, sample_cards, categories
    ):
        service = ReviewService(session, test_user.id)
        stats = service._get_category_stats()
        assert len(stats) > 0
        assert any(s["name"] == "成语" for s in stats)
