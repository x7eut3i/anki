"""Tests for card CRUD endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.card import Card
from app.models.category import Category
from app.models.deck import Deck
from app.models.user import User


class TestCreateCard:
    def test_create_basic_card(
        self, client: TestClient, auth_headers: dict, test_deck: Deck, categories
    ):
        response = client.post("/api/cards", headers=auth_headers, json={
            "deck_id": test_deck.id,
            "category_id": categories[0].id,
            "front": "守株待兔的含义",
            "back": "比喻不主动努力，存在侥幸心理",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["front"] == "守株待兔的含义"
        assert data["state"] == 0  # NEW

    def test_create_choice_card(
        self, client: TestClient, auth_headers: dict, test_deck: Deck, categories
    ):
        response = client.post("/api/cards", headers=auth_headers, json={
            "deck_id": test_deck.id,
            "front": "以下哪个成语形容骄傲自满？",
            "back": "目中无人",
            "distractors": '["\u865a\u6000\u82e5\u8c37","\u95fb\u9e21\u8d77\u821e","\u5367\u85aa\u5c1d\u80c6"]',
        })
        assert response.status_code == 201
        data = response.json()
        assert "目中无人" in data["back"]
        assert "虚怀若谷" in data["distractors"]

    def test_create_card_invalid_deck(self, client: TestClient, auth_headers: dict):
        response = client.post("/api/cards", headers=auth_headers, json={
            "deck_id": 9999,
            "front": "test",
            "back": "test",
        })
        assert response.status_code == 404

    def test_create_card_no_auth(self, client: TestClient, test_deck: Deck):
        response = client.post("/api/cards", json={
            "deck_id": test_deck.id,
            "front": "test",
            "back": "test",
        })
        assert response.status_code == 401


class TestBulkCreate:
    def test_bulk_create(
        self, client: TestClient, auth_headers: dict, test_deck: Deck, categories
    ):
        response = client.post("/api/cards/bulk", headers=auth_headers, json={
            "cards": [
                {"deck_id": test_deck.id, "front": f"Q{i}", "back": f"A{i}"}
                for i in range(5)
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 5
        assert data["errors"] == []


class TestListCards:
    def test_list_all_cards(
        self, client: TestClient, auth_headers: dict, sample_cards: list[Card]
    ):
        response = client.get("/api/cards", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["cards"]) == 5

    def test_list_by_deck(
        self, client: TestClient, auth_headers: dict, sample_cards, test_deck
    ):
        response = client.get(
            f"/api/cards?deck_id={test_deck.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5

    def test_list_by_category(
        self, client: TestClient, auth_headers: dict, sample_cards, categories
    ):
        response = client.get(
            f"/api/cards?category_id={categories[0].id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1  # Only 成语 card

    def test_search_cards(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.get(
            "/api/cards?search=画蛇添足", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_pagination(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.get(
            "/api/cards?page=1&page_size=2", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["cards"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestGetCard:
    def test_get_card(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        card = sample_cards[0]
        response = client.get(f"/api/cards/{card.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["front"] == card.front

    def test_get_nonexistent_card(self, client: TestClient, auth_headers: dict):
        response = client.get("/api/cards/9999", headers=auth_headers)
        assert response.status_code == 404


class TestUpdateCard:
    def test_update_card(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        card = sample_cards[0]
        response = client.put(f"/api/cards/{card.id}", headers=auth_headers, json={
            "front": "Updated question",
            "tags": "成语,常考",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["front"] == "Updated question"
        assert data["tags"] == "成语,常考"

    def test_suspend_card(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        card = sample_cards[0]
        response = client.put(f"/api/cards/{card.id}", headers=auth_headers, json={
            "is_suspended": True,
        })
        assert response.status_code == 200
        assert response.json()["is_suspended"] is True


class TestDeleteCard:
    def test_delete_card(
        self, client: TestClient, auth_headers: dict, sample_cards, session
    ):
        card = sample_cards[0]
        response = client.delete(f"/api/cards/{card.id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = client.get(f"/api/cards/{card.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.delete("/api/cards/9999", headers=auth_headers)
        assert response.status_code == 404
