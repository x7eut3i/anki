"""Tests for quiz endpoints and service."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.card import Card
from app.models.user import User
from app.services.quiz_service import QuizService


class TestQuizGeneration:
    def test_generate_quiz(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        response = client.post("/api/quiz/generate", headers=auth_headers, json={
            "card_count": 5,
            "include_types": ["choice", "qa"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_questions"] >= 1
        assert data["session_id"] > 0

    def test_generate_quiz_by_category(
        self, client: TestClient, auth_headers: dict, sample_cards, categories
    ):
        response = client.post("/api/quiz/generate", headers=auth_headers, json={
            "category_ids": [categories[0].id],
            "card_count": 5,
        })
        assert response.status_code == 200
        data = response.json()
        for q in data["questions"]:
            assert q["category_name"] == "成语"

    def test_generate_quiz_empty(
        self, client: TestClient, auth_headers: dict, categories
    ):
        # No cards exist
        response = client.post("/api/quiz/generate", headers=auth_headers, json={
            "card_count": 5,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_questions"] == 0


class TestQuizSubmit:
    def test_submit_quiz(
        self, client: TestClient, auth_headers: dict, sample_cards
    ):
        # Generate quiz first
        gen_resp = client.post("/api/quiz/generate", headers=auth_headers, json={
            "card_count": 5,
            "include_types": ["qa"],
        })
        quiz_data = gen_resp.json()

        if quiz_data["total_questions"] == 0:
            pytest.skip("No quiz questions generated")

        # Submit answers
        answers = []
        for q in quiz_data["questions"]:
            answers.append({
                "question_id": q["question_id"],
                "card_id": q["card_id"],
                "answer": "test answer",
                "time_spent_ms": 5000,
            })

        response = client.post(
            f"/api/quiz/submit/{quiz_data['session_id']}",
            headers=auth_headers,
            json=answers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(answers)
        assert "accuracy" in data
        assert "category_scores" in data

    def test_submit_invalid_session(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/quiz/submit/9999",
            headers=auth_headers,
            json=[],
        )
        assert response.status_code == 404


class TestQuizServiceDirect:
    """Direct tests on QuizService."""

    def test_generate_distractors(
        self, session: Session, test_user: User, sample_cards
    ):
        service = QuizService(session, test_user.id)
        distractors = service._generate_distractors(
            sample_cards[0], sample_cards, count=3
        )
        # May or may not have enough, but should not include the card itself
        for d in distractors:
            assert d != sample_cards[0].back

    def test_correct_answer_from_card(
        self, session: Session, test_user: User, sample_cards
    ):
        service = QuizService(session, test_user.id)
        # Card with distractors (choice card)
        choice_card = sample_cards[2]
        assert service._get_correct_answer(choice_card) == "人民代表大会制度"

        # Card without distractors (Q&A card, uses back)
        qa_card = sample_cards[0]
        assert service._get_correct_answer(qa_card) == qa_card.back
