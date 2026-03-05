"""Tests for dedup service."""

import pytest
from sqlmodel import Session

from app.models.card import Card
from app.models.category import Category
from app.models.deck import Deck
from app.models.user import User
from app.services.dedup_service import DedupService, normalize_text


class TestNormalizeText:
    """Test text normalization for dedup."""

    def test_strip_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_collapse_whitespace(self):
        assert normalize_text("hello   world") == "hello world"

    def test_normalize_punctuation(self):
        assert normalize_text("你好，世界！") == "你好,世界!"
        assert normalize_text("问题？回答。") == "问题?回答."

    def test_lowercase(self):
        assert normalize_text("Hello World") == "hello world"

    def test_empty_string(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""


class TestDedupService:
    """Test DedupService methods."""

    def test_find_duplicate_exact(
        self, session: Session, test_user: User, test_deck: Deck, categories
    ):
        """Find exact duplicate by front text."""
        card = Card(
            front="这是一道测试题",
            back="这是答案",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(card)
        session.commit()

        dedup = DedupService(session, test_user.id)
        result = dedup.find_duplicate("这是一道测试题")
        assert result is not None
        assert result.id == card.id

    def test_find_duplicate_normalized(
        self, session: Session, test_user: User, test_deck: Deck, categories
    ):
        """Find duplicate even with whitespace/punctuation differences."""
        card = Card(
            front="什么是依法治国？",
            back="答案",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(card)
        session.commit()

        dedup = DedupService(session, test_user.id)
        # Should match with normalized punctuation
        result = dedup.find_duplicate("什么是依法治国?")
        assert result is not None

    def test_find_no_duplicate(
        self, session: Session, test_user: User, test_deck: Deck, categories
    ):
        """Return None when no duplicate exists."""
        dedup = DedupService(session, test_user.id)
        result = dedup.find_duplicate("完全不存在的问题内容")
        assert result is None

    def test_find_duplicate_with_category(
        self, session: Session, test_user: User, test_deck: Deck, categories
    ):
        """Filter duplicates by category."""
        card = Card(
            front="分类测试题",
            back="答案",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(card)
        session.commit()

        dedup = DedupService(session, test_user.id)
        # Same category → found
        result = dedup.find_duplicate("分类测试题", category_id=categories[0].id)
        assert result is not None

        # Different category → not found
        result = dedup.find_duplicate("分类测试题", category_id=categories[1].id)
        assert result is None

    def test_find_duplicate_exclude_card(
        self, session: Session, test_user: User, test_deck: Deck, categories
    ):
        """Exclude a specific card ID from dedup check."""
        card = Card(
            front="排除测试题",
            back="答案",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(card)
        session.commit()
        session.refresh(card)

        dedup = DedupService(session, test_user.id)
        # Without exclude → found
        result = dedup.find_duplicate("排除测试题")
        assert result is not None

        # With exclude → not found
        result = dedup.find_duplicate("排除测试题", exclude_card_id=card.id)
        assert result is None

    def test_check_duplicates_batch(
        self, session: Session, test_user: User, test_deck: Deck, categories
    ):
        """Batch check multiple fronts for duplicates."""
        card = Card(
            front="已存在的题目",
            back="答案",
            deck_id=test_deck.id,
            category_id=categories[0].id,
        )
        session.add(card)
        session.commit()

        dedup = DedupService(session, test_user.id)
        results = dedup.check_duplicates([
            "已存在的题目",
            "不存在的新题目",
        ])
        assert len(results) == 2
        assert results[0]["is_duplicate"] is True
        assert results[1]["is_duplicate"] is False
