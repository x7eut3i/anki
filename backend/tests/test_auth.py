"""Tests for authentication endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User


class TestRegister:
    def test_register_short_username(self, client: TestClient):
        response = client.post("/api/auth/register", json={
            "username": "ab",
            "email": "ab@example.com",
            "password": "password123",
        })
        assert response.status_code == 422

    def test_register_short_password(self, client: TestClient):
        response = client.post("/api/auth/register", json={
            "username": "validuser",
            "email": "valid@example.com",
            "password": "12345",
        })
        assert response.status_code == 422


class TestLogin:
    def test_login_success(self, client: TestClient, test_user: User):
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "testpassword",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]
        assert data["user"]["username"] == "testuser"

    def test_login_wrong_password(self, client: TestClient, test_user: User):
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "wrongpassword",
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient):
        response = client.post("/api/auth/login", json={
            "username": "nobody",
            "password": "password123",
        })
        assert response.status_code == 401


class TestMe:
    def test_get_me(self, client: TestClient, auth_headers: dict, test_user: User):
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"

    def test_get_me_no_auth(self, client: TestClient):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_get_me_invalid_token(self, client: TestClient):
        response = client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid-token"
        })
        assert response.status_code == 401

    def test_update_me(self, client: TestClient, auth_headers: dict):
        response = client.put("/api/auth/me", headers=auth_headers, json={
            "session_card_limit": 30,
            "desired_retention": 0.85,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["session_card_limit"] == 30
        assert data["desired_retention"] == 0.85
