"""Tests for deck CRUD endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.models.deck import Deck
from app.models.card import Card
from app.models.user import User


class TestCreateDeck:
    def test_create_deck(self, client: TestClient, auth_headers: dict, categories):
        response = client.post("/api/decks", headers=auth_headers, json={
            "name": "成语专练",
            "description": "成语类型题目集合",
            "category_id": categories[0].id,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "成语专练"
        assert data["card_count"] == 0

    def test_create_deck_no_auth(self, client: TestClient):
        response = client.post("/api/decks", json={"name": "test"})
        assert response.status_code == 401


class TestListDecks:
    def test_list_decks(self, client: TestClient, auth_headers: dict, test_deck: Deck):
        response = client.get("/api/decks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(d["name"] == test_deck.name for d in data["decks"])

    def test_list_empty(self, client: TestClient, auth_headers: dict, categories):
        # test_user has no decks (categories fixture runs but no deck fixture)
        response = client.get("/api/decks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestGetDeck:
    def test_get_deck(self, client: TestClient, auth_headers: dict, test_deck: Deck):
        response = client.get(f"/api/decks/{test_deck.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == test_deck.name

    def test_get_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.get("/api/decks/9999", headers=auth_headers)
        assert response.status_code == 404


class TestUpdateDeck:
    def test_update_deck(self, client: TestClient, auth_headers: dict, test_deck: Deck):
        response = client.put(f"/api/decks/{test_deck.id}", headers=auth_headers, json={
            "name": "Updated Name",
            "description": "Updated desc",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated desc"


class TestDeleteDeck:
    def test_delete_deck_with_cards(
        self, client: TestClient, auth_headers: dict, test_deck, sample_cards
    ):
        response = client.delete(f"/api/decks/{test_deck.id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deck deleted
        response = client.get(f"/api/decks/{test_deck.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.delete("/api/decks/9999", headers=auth_headers)
        assert response.status_code == 404
