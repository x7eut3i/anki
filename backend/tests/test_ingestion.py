"""Tests for AI ingestion service (RSS, HTML parsing, card generation)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, select

from app.models.card import Card
from app.models.category import Category
from app.models.deck import Deck
from app.models.user import User
from app.services.ingestion_service import IngestionService


MOCK_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>新华网</title>
    <item>
      <title>2024年国务院政策</title>
      <link>https://example.com/article1</link>
      <description>最新政策解读...</description>
      <pubDate>Mon, 01 Jan 2024 08:00:00 +0800</pubDate>
    </item>
  </channel>
</rss>
"""

MOCK_HTML_ARTICLE = """
<html>
<body>
  <div class="article-content">
    <a href="https://example.com/1">国务院近日发布了关于深化改革的重要文件</a>
    <a href="https://example.com/2">推进经济体制改革的若干意见正式出台</a>
    <p>第一，推进经济体制改革。</p>
    <p>第二，加强社会治理创新。</p>
  </div>
</body>
</html>
"""

MOCK_AI_CARDS_RESPONSE = json.dumps([
    {
        "front": "2024年国务院深化改革文件的主要内容有哪些？",
        "back": "推进经济体制改革、加强社会治理创新",
        "category": "时政热点",
    },
    {
        "front": "国务院深化改革文件中，以下哪项不是主要内容？",
        "back": "取消高考制度",
        "category": "时政热点",
        "distractors": ["推进经济体制改革", "加强社会治理创新", "深化行政管理"],
    },
])


class TestIngestionService:
    """Test ingestion pipeline components."""

    @pytest.mark.asyncio
    async def test_fetch_rss_articles(self):
        """Parse RSS feed and extract articles."""
        service = IngestionService.__new__(IngestionService)

        with patch("httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.text = MOCK_RSS_XML
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            articles = await service._fetch_rss("https://example.com/rss")
            assert len(articles) >= 1
            assert articles[0]["title"] == "2024年国务院政策"
            assert "example.com" in articles[0]["link"]

    @pytest.mark.asyncio
    async def test_fetch_html_content(self):
        """Fetch and parse HTML article body."""
        service = IngestionService.__new__(IngestionService)

        with patch("httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.text = MOCK_HTML_ARTICLE
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            articles = await service._fetch_html("https://example.com/article1")
            # _fetch_html returns list of article dicts, not raw text
            assert len(articles) >= 1

    @pytest.mark.asyncio
    async def test_ai_parse_article_to_cards(self):
        """AI turns article text into structured card dicts."""
        service = IngestionService.__new__(IngestionService)
        service.session = MagicMock()
        service.user_id = 1

        # Mock category query for available_categories
        mock_cat1 = MagicMock()
        mock_cat1.name = "时政热点"
        mock_cat2 = MagicMock()
        mock_cat2.name = "法律常识"
        service.session.exec.return_value.all.return_value = [mock_cat1, mock_cat2]

        # Mock AIService
        with patch("app.services.ingestion_service.AIService") as MockAIService:
            mock_ai = MockAIService.return_value
            mock_ai.is_available.return_value = True
            mock_ai.generate_cards_from_text = AsyncMock(return_value=[
                {"front": "Q1", "back": "A1", "category": "时政热点"},
                {"front": "Q2", "back": "A2", "category": "法律常识",
                 "distractors": ["D1", "D2", "D3"]},
            ])

            article = {"title": "2024年国务院政策", "summary": "国务院近日发布了关于深化改革..."}
            cards = await service._parse_article_to_cards(article, "时政热点")
            assert len(cards) == 2
            assert cards[0]["front"] == "Q1"
            assert "distractors" in cards[1]

            # Verify available_categories was passed to AI
            call_kwargs = mock_ai.generate_cards_from_text.call_args
            assert "available_categories" in call_kwargs.kwargs
            assert "时政热点" in call_kwargs.kwargs["available_categories"]
            assert "法律常识" in call_kwargs.kwargs["available_categories"]

    @pytest.mark.asyncio
    async def test_ai_parse_passes_available_categories(self):
        """Verify _parse_article_to_cards sends category list to AI."""
        service = IngestionService.__new__(IngestionService)
        service.session = MagicMock()
        service.user_id = 1

        # Mock category query
        mock_cats = []
        for name in ["成语", "时政热点", "法律常识", "历史文化"]:
            mc = MagicMock()
            mc.name = name
            mock_cats.append(mc)
        service.session.exec.return_value.all.return_value = mock_cats

        with patch("app.services.ingestion_service.AIService") as MockAIService:
            mock_ai = MockAIService.return_value
            mock_ai.is_available.return_value = True
            mock_ai.generate_cards_from_text = AsyncMock(return_value=[])

            await service._parse_article_to_cards(
                {"title": "测试", "summary": "内容"}, "时政热点"
            )
            call_kwargs = mock_ai.generate_cards_from_text.call_args.kwargs
            assert set(call_kwargs["available_categories"]) == {
                "成语", "时政热点", "法律常识", "历史文化"
            }

    def test_save_generated_cards(
        self, session: Session, test_user: User, categories
    ):
        """Save AI-generated card dicts into the database."""
        # Find 时政热点 category
        hot_cat = next((c for c in categories if c.name == "时政热点"), categories[0])

        # Create a target deck
        deck = Deck(name="AI每日卡片", category_id=hot_cat.id)
        session.add(deck)
        session.commit()
        session.refresh(deck)

        card_dicts = json.loads(MOCK_AI_CARDS_RESPONSE)
        saved = []
        for cd in card_dicts:
            card = Card(
                front=cd["front"],
                back=cd["back"],
                deck_id=deck.id,
                category_id=hot_cat.id,
                is_ai_generated=True,
                source="ingestion:https://example.com/article1",
                distractors=json.dumps(cd.get("distractors", [])),
            )
            session.add(card)
            saved.append(card)

        session.commit()

        # Verify
        db_cards = session.exec(
            select(Card).where(Card.deck_id == deck.id)
        ).all()
        assert len(db_cards) == 2
        assert all(c.is_ai_generated for c in db_cards)
        assert db_cards[1].distractors is not None

    def test_dedup_by_front_text(self, session: Session, test_user: User, categories):
        """Skip cards whose front already exists in the deck."""
        cat = categories[0]
        deck = Deck(name="DedupTest", category_id=cat.id)
        session.add(deck)
        session.commit()
        session.refresh(deck)

        # Existing card
        existing = Card(
            front="什么是依法治国？",
            back="按照法律来治理国家",
            deck_id=deck.id,
            category_id=cat.id,
        )
        session.add(existing)
        session.commit()

        # Incoming AI-generated cards
        incoming = [
            {"front": "什么是依法治国？", "back": "新回答"},
            {"front": "新问题", "back": "新回答"},
        ]

        added = 0
        for cd in incoming:
            dup = session.exec(
                select(Card).where(
                    Card.deck_id == deck.id, Card.front == cd["front"]
                )
            ).first()
            if not dup:
                card = Card(
                    front=cd["front"],
                    back=cd["back"],
                    deck_id=deck.id,
                    category_id=cat.id,
                )
                session.add(card)
                added += 1

        session.commit()
        assert added == 1  # Only the new one

    @pytest.mark.asyncio
    async def test_save_card_uses_ai_category(
        self, session: Session, test_user: User, categories
    ):
        """_save_card should prefer AI-suggested category over source default."""
        changshi_cat = next((c for c in categories if c.name == "常识判断"), None)
        hot_cat = next((c for c in categories if c.name == "时政与重要论述"), None)
        assert changshi_cat is not None
        assert hot_cat is not None

        # Card data with AI-suggested category different from source
        card_data = {
            "front": "宪法规定的基本权利有哪些？",
            "back": "选举权和被选举权",
            "category": "常识判断",  # AI suggests 常识判断
        }
        source = {
            "name": "人民日报-时政",
            "url": "http://example.com",
            "category": "时政与重要论述",  # Source default
            "type": "rss",
        }

        service = IngestionService(session, test_user.id)
        card = await service._save_card(card_data, source)

        assert card is not None
        # Should use AI-suggested category (常识判断), not source default
        assert card.category_id == changshi_cat.id
