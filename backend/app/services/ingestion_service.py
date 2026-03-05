"""Ingestion service: fetches and parses external sources into flashcards."""

import json
import logging
from datetime import datetime, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlmodel import Session

from app.models.card import Card
from app.models.deck import Deck
from app.services.ai_service import AIService
from app.services.dedup_service import DedupService

logger = logging.getLogger(__name__)

# Import from the new source_crawlers module for backward compatibility
from app.services.source_crawlers import NORMAL_SOURCES as RSS_SOURCES


class IngestionService:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        self.user_id = user_id

    async def run_daily_ingestion(self) -> dict:
        """Run the daily content ingestion pipeline."""
        results = {"fetched": 0, "parsed": 0, "created": 0, "errors": []}

        # Try to load sources from database first, fall back to hardcoded RSS_SOURCES
        from sqlmodel import select as sel
        try:
            from app.models.article_source import ArticleSource
            db_sources = self.session.exec(
                sel(ArticleSource).where(ArticleSource.is_enabled == True)
            ).all()
            if db_sources:
                sources = [
                    {"name": s.name, "url": s.url, "category": s.category, "type": s.source_type}
                    for s in db_sources
                ]
            else:
                sources = RSS_SOURCES
        except Exception:
            sources = RSS_SOURCES

        for source in sources:
            try:
                articles = await self._fetch_source(source)
                results["fetched"] += len(articles)

                for article in articles[:5]:  # Limit per source
                    cards = await self._parse_article_to_cards(
                        article, source["category"]
                    )
                    results["parsed"] += len(cards)

                    for card_data in cards:
                        await self._save_card(card_data, source)
                        results["created"] += 1

            except Exception as e:
                error_msg = f"Error fetching {source['name']}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        return results

    async def _fetch_source(self, source: dict) -> list[dict]:
        """Fetch articles from a source."""
        if source["type"] == "rss":
            return await self._fetch_rss(source["url"])
        elif source["type"] == "html":
            return await self._fetch_html(source["url"])
        return []

    async def _fetch_rss(self, url: str) -> list[dict]:
        """Fetch and parse an RSS feed."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

            feed = feedparser.parse(response.text)
            articles = []
            for entry in feed.entries[:10]:
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
            return articles
        except Exception as e:
            logger.error(f"RSS fetch error for {url}: {e}")
            return []

    async def _fetch_html(self, url: str) -> list[dict]:
        """Fetch and parse an HTML page for articles."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            articles = []

            # Generic article extraction
            for item in soup.find_all("a", href=True)[:20]:
                title = item.get_text(strip=True)
                if len(title) > 10:  # Filter noise
                    articles.append({
                        "title": title,
                        "summary": "",
                        "link": item["href"],
                        "published": "",
                    })

            return articles[:10]
        except Exception as e:
            logger.error(f"HTML fetch error for {url}: {e}")
            return []

    async def _parse_article_to_cards(
        self, article: dict, category_name: str
    ) -> list[dict]:
        """Use AI to parse an article into flashcards."""
        ai = AIService(self.session, self.user_id)
        if not ai.is_available():
            logger.warning("AI not available, skipping card generation")
            return []

        # Collect available category names so AI can classify each card
        from app.models.category import Category
        from sqlmodel import select
        categories = self.session.exec(select(Category)).all()
        available_categories = [c.name for c in categories]

        text = f"标题：{article['title']}\n内容：{article.get('summary', '')}"
        try:
            cards = await ai.generate_cards_from_text(
                text=text,
                category_name=category_name,
                card_type="qa",
                count=3,
                available_categories=available_categories,
            )
            return cards
        except Exception as e:
            logger.error(f"AI parsing error: {e}")
            return []

    async def _save_card(self, card_data: dict, source: dict) -> Card | None:
        """Save a generated card to the database with dedup check."""
        # Dedup check
        front = card_data.get("front", "")
        if not front:
            return None

        dedup = DedupService(self.session, self.user_id)
        existing = dedup.find_duplicate(front)
        if existing:
            logger.debug(f"  Skipping duplicate: {front[:40]}...")
            return None

        # Find or create an ingestion deck
        from sqlmodel import select
        deck = self.session.exec(
            select(Deck).where(
                Deck.name == f"AI-{source['category']}",
            )
        ).first()

        if not deck:
            deck = Deck(
                name=f"AI-{source['category']}",
                description=f"AI自动生成的{source['category']}卡片",
            )
            self.session.add(deck)
            self.session.commit()
            self.session.refresh(deck)

        # Find category — prefer AI-suggested category from card_data, fall
        # back to the source's default category.
        from app.models.category import Category
        card_category = card_data.get("category", "") or source["category"]
        cat = self.session.exec(
            select(Category).where(Category.name == card_category)
        ).first()
        if not cat:
            # AI may have returned an unknown category; fall back to source
            cat = self.session.exec(
                select(Category).where(Category.name == source["category"])
            ).first()

        # Process meta_info
        meta_info = card_data.get("meta_info", "")
        if isinstance(meta_info, dict):
            meta_info = json.dumps(meta_info, ensure_ascii=False)

        # Process distractors
        distractors = card_data.get("distractors", "")
        if isinstance(distractors, list):
            distractors = json.dumps(distractors, ensure_ascii=False)

        card = Card(
            deck_id=deck.id,
            category_id=cat.id if cat else None,
            front=card_data.get("front", ""),
            back=card_data.get("back", ""),
            explanation=card_data.get("explanation", ""),
            distractors=distractors,
            tags=card_data.get("tags", ""),
            meta_info=meta_info,
            source=source.get("url", ""),
            is_ai_generated=True,
        )
        self.session.add(card)

        # Update deck card count
        deck.card_count += 1
        self.session.add(deck)
        self.session.commit()
        self.session.refresh(card)
        return card
