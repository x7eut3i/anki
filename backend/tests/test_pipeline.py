"""Tests for the article pipeline (article_pipeline.py).

Tests the fetch → analyze → dedup → import flow with mocked HTTP/AI calls.
"""

import json
import re
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, select

from app.models.card import Card
from app.models.category import Category
from app.models.deck import Deck
from app.models.user import User
from app.models.ai_config import AIConfig


# We need to import from the project root
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from article_pipeline import (
    ArticlePipeline,
    SOURCES,
)


# ── Mock Data ──

MOCK_PEOPLE_DAILY_HTML = """
<html><body>
<a href="http://opinion.people.com.cn/n1/2024/0601/c123-456.html">
  深入推进全面依法治国的重要论述——评论文章标题
</a>
<a href="http://opinion.people.com.cn/n1/2024/0602/c123-789.html">
  论新时代经济体制改革的战略方向与实践路径
</a>
<a href="/short">短</a>
</body></html>
"""

MOCK_ARTICLE_CONTENT = """
<html><body>
<div class="rm_txt_con">
  <p>全面依法治国是坚持和发展中国特色社会主义的本质要求和重要保障。</p>
  <p>习近平总书记强调，要坚持走中国特色社会主义法治道路。</p>
  <p>第一，深入推进科学立法、严格执法、公正司法、全民守法。</p>
  <p>第二，加强宪法实施和监督，推进合宪性审查工作。</p>
</div>
</body></html>
"""

MOCK_AI_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    [
                        {
                            "front": "全面依法治国的'十六字方针'是什么？",
                            "back": "科学立法、严格执法、公正司法、全民守法",
                            "explanation": "科学立法、严格执法、公正司法、全民守法",
                            "distractors": ["民主立法、依法执法、公正司法、全民守法", "科学立法、严格执法、公正司法、依法守法", "民主立法、依法执法、公正司法、依法守法"],
                            "tags": "法律常识,依法治国",
                            "meta_info": {
                                "knowledge_type": "law",
                                "subject": "全面依法治国",
                                "distractors": ["民主立法", "依法执法", "依法守法"],
                                "knowledge": {
                                    "synonyms": ["法治方针", "十六字方针"],
                                    "antonyms": [],
                                    "related": ["中国特色社会主义法治"],
                                    "key_points": ["科学立法、严格执法、公正司法、全民守法"],
                                    "memory_tips": "科严公全",
                                },
                                "alternate_questions": ["全面依法治国的基本方针包含哪些内容？"],
                            },
                        },
                        {
                            "front": "全面依法治国是坚持和发展中国特色社会主义的本质要求。请问这个说法正确吗？",
                            "back": "正确。全面依法治国是坚持和发展中国特色社会主义的本质要求和重要保障。",
                            "explanation": "原文：全面依法治国是坚持和发展中国特色社会主义的本质要求和重要保障。",
                            "tags": "法律常识",
                        },
                    ],
                    ensure_ascii=False,
                )
            }
        }
    ],
    "usage": {"total_tokens": 500},
}


class TestArticlePipelineSourceParsers:
    """Test source HTML parsers."""

    def test_parse_people_daily_list(self):
        """Parse People's Daily article list from HTML."""
        from bs4 import BeautifulSoup

        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        soup = BeautifulSoup(MOCK_PEOPLE_DAILY_HTML, "html.parser")
        articles = pipeline._parse_people_daily_list(
            soup, "http://opinion.people.com.cn/GB/159301/index.html"
        )
        # Should find 2 articles matching /n1/YYYY/MMDD/cNNN-NNN.html pattern
        assert len(articles) == 2
        assert any("依法治国" in a["title"] for a in articles)

    def test_parse_guangming_list(self):
        """Parse 光明网理论 article list from HTML."""
        from bs4 import BeautifulSoup

        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        html = """<html><body>
        <a href="https://theory.gmw.cn/2024-06/01/content_38012345.htm">深入学习贯彻新时代中国特色社会主义思想</a>
        <a href="https://theory.gmw.cn/2024-06/02/content_38012346.htm">推动高质量发展的理论与实践创新</a>
        <a href="/short">短</a>
        </body></html>"""
        soup = BeautifulSoup(html, "html.parser")
        articles = pipeline._parse_guangming_list(
            soup, "https://theory.gmw.cn/"
        )
        assert len(articles) == 2
        assert articles[0]["date"] == "2024-06-01"

    def test_parse_qiushi_list(self):
        """Parse 求是网 article list from HTML."""
        from bs4 import BeautifulSoup

        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        html = """<html><body>
        <a href="https://www.qstheory.cn/20240601/abc123def456/c.html">坚持和发展中国特色社会主义</a>
        <a href="https://www.qstheory.cn/20240602/789abc012def/c.html">推进国家治理体系和治理能力现代化</a>
        <a href="https://www.qstheory.cn/20240601/abc123def456/c.html">坚持和发展中国特色社会主义</a>
        </body></html>"""
        soup = BeautifulSoup(html, "html.parser")
        articles = pipeline._parse_qiushi_list(
            soup, "https://www.qstheory.cn/"
        )
        # Should deduplicate
        assert len(articles) == 2

    def test_parse_generic_list(self):
        """Generic parser extracts articles by link length."""
        from bs4 import BeautifulSoup

        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        html = '<html><body><a href="/long-article">这是一篇足够长的标题文章用于测试</a><a href="/s">短</a></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        articles = pipeline._parse_generic_list(
            soup, "http://example.com/"
        )
        assert len(articles) == 1
        assert articles[0]["title"] == "这是一篇足够长的标题文章用于测试"

    def test_extract_date_from_url(self):
        """Extract dates from various URL patterns."""
        pipeline = ArticlePipeline.__new__(ArticlePipeline)

        assert pipeline._extract_date_from_url("/2024/0601/article.html") == "2024-06-01"
        assert pipeline._extract_date_from_url("/2024-06-01/news.html") == "2024-06-01"
        assert pipeline._extract_date_from_url("/20240601.htm") == "2024-06-01"
        # Fallback: returns today's date
        result = pipeline._extract_date_from_url("/no-date-here")
        assert re.match(r"\d{4}-\d{2}-\d{2}", result)


class TestArticlePipelineContent:
    """Test article content fetching."""

    @pytest.mark.asyncio
    async def test_fetch_article_content(self):
        """Fetch and parse article body."""
        pipeline = ArticlePipeline.__new__(ArticlePipeline)

        with patch("httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.text = MOCK_ARTICLE_CONTENT
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            content = await pipeline._fetch_article_content(
                {"title": "Test", "url": "http://example.com/article"}
            )
            assert "依法治国" in content or "全面" in content

    @pytest.mark.asyncio
    async def test_fetch_article_content_fallback(self):
        """When content fetch fails, use title as fallback."""
        pipeline = ArticlePipeline.__new__(ArticlePipeline)

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            content = await pipeline._fetch_article_content(
                {"title": "这是标题", "url": "http://example.com/fail"}
            )
            assert content == "这是标题"


class TestArticlePipelineCardGeneration:
    """Test AI card generation and fallback."""

    @pytest.mark.asyncio
    async def test_ai_generate_cards(self):
        """AI generates cards from article content."""
        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        pipeline.stats = {"errors": []}

        # Mock the session with AI config
        mock_session = MagicMock()
        mock_config = MagicMock()
        mock_config.api_base_url = "https://api.test.com/v1"
        mock_config.api_key = "sk-test"
        mock_config.model = "test-model"
        mock_config.is_enabled = True
        mock_session.exec.return_value.first.return_value = mock_config

        pipeline.engine = MagicMock()

        with patch("article_pipeline.Session") as MockSession:
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_session)
            MockSession.return_value.__exit__ = MagicMock(return_value=None)

            with patch("httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.json.return_value = MOCK_AI_RESPONSE
                mock_resp.status_code = 200
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_client

                source = {"name": "test", "category": "时政热点"}
                cards, quality_score = await pipeline._ai_generate_cards(
                    "测试标题", "测试内容" * 10, source
                )
                assert len(cards) == 2
                assert "front" in cards[0]

    def test_fallback_card_generation(self):
        """Fallback generates basic cards without AI."""
        pipeline = ArticlePipeline.__new__(ArticlePipeline)

        content = (
            "第一段足够长的内容用于测试fallback card generation的功能是否正常工作。\n"
            "第二段也需要足够长以满足长度过滤条件，确保能被提取出来作为卡片。\n"
            "短"
        )
        source = {"name": "人民日报评论"}
        cards = pipeline._fallback_card_generation("测试标题", content, source)

        assert len(cards) == 2  # Only paragraphs > 30 chars
        assert cards[0]["distractors"] == []
        assert "测试标题" in cards[0]["back"]


class TestArticlePipelineDedupImport:
    """Test dedup and import into DB."""

    def test_dedup_and_import_skips_duplicates(
        self, session: Session, test_user: User, categories
    ):
        """Duplicate cards (same front) should be skipped."""
        # Create the admin user and category
        test_user.is_admin = True
        session.add(test_user)
        session.commit()

        hot_cat = next((c for c in categories if c.name == "时政热点"), categories[0])

        # Create a deck
        deck = Deck(name="AI-时政热点", category_id=hot_cat.id)
        session.add(deck)
        session.commit()
        session.refresh(deck)

        # Add existing card
        existing = Card(
            front="全面依法治国的'十六字方针'是什么？",
            back="科学立法、严格执法、公正司法、全民守法",
            deck_id=deck.id,
            category_id=hot_cat.id,
        )
        session.add(existing)
        session.commit()

        # Try to import cards with one duplicate
        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        pipeline.dry_run = False
        pipeline.stats = {
            "cards_generated": 0,
            "cards_duplicated": 0,
            "cards_imported": 0,
            "errors": [],
        }
        pipeline.engine = session.get_bind()

        cards = [
            {
                "front": "全面依法治国的'十六字方针'是什么？",
                "back": "科学立法、严格执法、公正司法、全民守法",
                "distractors": [],
            },
            {
                "front": "全新的不重复的问题",
                "back": "新答案",
                "distractors": [],
            },
        ]

        article = {"url": "http://example.com/article1", "date": "2024-06-01"}
        source = {"name": "test", "category": "时政热点", "url": "http://example.com"}

        imported = pipeline._dedup_and_import(session, cards, article, source)
        assert imported == 1  # Only the new one

    def test_dedup_dry_run(self, session: Session, test_user: User, categories):
        """In dry run mode, no cards are saved."""
        pipeline = ArticlePipeline.__new__(ArticlePipeline)
        pipeline.dry_run = True
        pipeline.stats = {
            "cards_generated": 0,
            "cards_duplicated": 0,
            "cards_imported": 0,
            "errors": [],
        }

        cards = [
            {"front": "Dry run question", "back": "answer", "distractors": []},
        ]
        article = {"url": "http://example.com/article1", "date": "2024-06-01"}
        source = {"name": "test", "category": "时政热点", "url": "http://example.com"}

        imported = pipeline._dedup_and_import(session, cards, article, source)
        assert imported == 0


class TestArticlePipelineConfig:
    """Test pipeline configuration."""

    def test_sources_defined(self):
        """All expected sources are defined."""
        assert "people_opinion" in SOURCES
        assert "people_theory" in SOURCES
        assert "guangming_theory" in SOURCES
        assert "qiushi" in SOURCES

    def test_source_has_required_fields(self):
        """Each source has name, base_url, category, parser."""
        for key, source in SOURCES.items():
            assert "name" in source, f"{key} missing 'name'"
            assert "base_url" in source, f"{key} missing 'base_url'"
            assert "category" in source, f"{key} missing 'category'"
            assert "parser" in source, f"{key} missing 'parser'"
