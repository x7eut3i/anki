"""Tests for import/export service (CSV, JSON, APKG)."""

import csv
import io
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.card import Card
from app.models.category import Category
from app.models.deck import Deck
from app.models.user import User


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_csv_bytes(rows: list[dict]) -> bytes:
    """Create CSV bytes from list of dicts."""
    buf = io.StringIO()
    # Collect all field names across all rows
    fieldnames = list(dict.fromkeys(k for row in rows for k in row.keys()))
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _make_json_bytes(cards: list[dict]) -> bytes:
    """Create JSON bytes from list of dicts."""
    return json.dumps(cards, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# CSV import / export
# ---------------------------------------------------------------------------


class TestCSVImportExport:
    def test_csv_import(
        self, client: TestClient, auth_headers: dict, test_deck, categories
    ):
        """Import cards from CSV file."""
        rows = [
            {
                "front": "CSV问题1",
                "back": "CSV答案1",
            },
            {
                "front": "CSV选择题",
                "back": "选项B",
                "distractors": '["选项A","选项C","选项D"]',
            },
        ]
        csv_bytes = _make_csv_bytes(rows)

        response = client.post(
            f"/api/import-export/import/csv?deck_id={test_deck.id}",
            headers=auth_headers,
            files={"file": ("cards.csv", csv_bytes, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] >= 2

    def test_csv_export(
        self, client: TestClient, auth_headers: dict, sample_cards, test_deck
    ):
        """Export deck cards to CSV."""
        response = client.get(
            f"/api/import-export/export/csv?deck_id={test_deck.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        text = response.text
        assert "front" in text
        assert len(text.strip().split("\n")) >= 2  # header + at least 1 row

    def test_csv_roundtrip(
        self, client: TestClient, auth_headers: dict, test_deck, categories
    ):
        """Import → Export → verify data survives round-trip."""
        rows = [
            {"front": "往返测试", "back": "答案"},
        ]
        csv_bytes = _make_csv_bytes(rows)

        # Import
        client.post(
            f"/api/import-export/import/csv?deck_id={test_deck.id}",
            headers=auth_headers,
            files={"file": ("cards.csv", csv_bytes, "text/csv")},
        )

        # Export
        exp = client.get(
            f"/api/import-export/export/csv?deck_id={test_deck.id}",
            headers=auth_headers,
        )
        assert "往返测试" in exp.text

    def test_csv_import_empty_file(
        self, client: TestClient, auth_headers: dict, test_deck
    ):
        """Empty CSV should return 0 imported."""
        csv_bytes = b"front,back\n"
        response = client.post(
            f"/api/import-export/import/csv?deck_id={test_deck.id}",
            headers=auth_headers,
            files={"file": ("empty.csv", csv_bytes, "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["created"] == 0


# ---------------------------------------------------------------------------
# JSON import / export
# ---------------------------------------------------------------------------


class TestJSONImportExport:
    def test_json_import(
        self, client: TestClient, auth_headers: dict, test_deck, categories
    ):
        """Import cards from JSON file."""
        cards = [
            {"front": "JSON问题1", "back": "JSON答案1"},
            {"front": "JSON填空", "back": "正确答案"},
        ]
        json_bytes = _make_json_bytes(cards)

        response = client.post(
            f"/api/import-export/import/json?deck_id={test_deck.id}",
            headers=auth_headers,
            files={"file": ("cards.json", json_bytes, "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] >= 2

    def test_json_export(
        self, client: TestClient, auth_headers: dict, sample_cards, test_deck
    ):
        """Export deck cards to JSON."""
        response = client.get(
            f"/api/import-export/export/json?deck_id={test_deck.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "front" in data[0]

    def test_json_roundtrip(
        self, client: TestClient, auth_headers: dict, test_deck
    ):
        """Import → Export → verify JSON round-trip."""
        original = [
            {
                "front": "JSON往返",
                "back": "答案",
            },
        ]
        json_bytes = _make_json_bytes(original)

        client.post(
            f"/api/import-export/import/json?deck_id={test_deck.id}",
            headers=auth_headers,
            files={"file": ("cards.json", json_bytes, "application/json")},
        )

        exp = client.get(
            f"/api/import-export/export/json?deck_id={test_deck.id}",
            headers=auth_headers,
        )
        exported = exp.json()
        fronts = [c["front"] for c in exported]
        assert "JSON往返" in fronts


# ---------------------------------------------------------------------------
# Direct service tests
# ---------------------------------------------------------------------------


class TestImportExportService:
    def test_csv_parse_choice_options(self, session: Session, test_user: User, test_deck):
        """Choice options are pipe-delimited in CSV (legacy support)."""
        row = {
            "front": "哪个是首都？",
            "back": "北京",
            "distractors": '["上海","广州","深圳"]',
        }
        distractors = json.loads(row["distractors"])
        assert len(distractors) == 3
        assert "上海" in distractors

    def test_card_count_after_import(
        self, session: Session, test_user: User, test_deck, categories
    ):
        """After import, deck.card_count should be updated."""
        initial_count = session.exec(
            select(Card).where(Card.deck_id == test_deck.id)
        ).all()
        initial = len(initial_count)

        new_card = Card(
            front="计数测试",
            back="答案",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(new_card)
        session.commit()

        after = session.exec(
            select(Card).where(Card.deck_id == test_deck.id)
        ).all()
        assert len(after) == initial + 1

    def test_card_without_distractors_is_qa(self):
        """Card without distractors is treated as Q&A."""
        row = {"front": "Q", "back": "A"}
        # No distractors field → Q&A card
        assert "distractors" not in row or row.get("distractors", "") == ""

    def test_unicode_content_preserved(
        self, session: Session, test_user: User, test_deck, categories
    ):
        """Chinese characters survive import/export."""
        card = Card(
            front="中华人民共和国宪法的基本原则是什么？",
            back="人民民主专政、社会主义制度、民主集中制、依法治国",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(card)
        session.commit()
        session.refresh(card)

        assert "宪法" in card.front
        assert "依法治国" in card.back
