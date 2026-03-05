"""AI Article Analysis Pipeline

Fetches commentary articles from People's Daily and other sources,
uses AI to analyze and generate flashcards, deduplicates against
existing cards, and imports with meta_info for dynamic question generation.

Usage:
    python article_pipeline.py                       # Run pipeline
    python article_pipeline.py --dry-run             # Preview only
    python article_pipeline.py --source people_daily # Specific source
    python article_pipeline.py --max-articles 3      # Limit articles

The pipeline can also be scheduled as a cron job:
    0 6 * * * cd /app && python article_pipeline.py >> /var/log/pipeline.log 2>&1
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from sqlmodel import Session, create_engine, select
from app.models.card import Card
from app.models.category import Category
from app.models.deck import Deck
from app.models.user import User
from app.models.ai_config import AIConfig
from app.services.dedup_service import DedupService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("article_pipeline")

# ── Source Definitions ──

SOURCES = {
    "people_opinion": {
        "name": "人民网观点",
        "base_url": "http://opinion.people.com.cn/GB/159301/index.html",
        "category": "时政热点",
        "parser": "people_daily",
    },
    "people_theory": {
        "name": "人民网理论",
        "base_url": "http://theory.people.com.cn/GB/49150/index.html",
        "category": "政治理论",
        "parser": "people_daily",
    },
    "guangming_theory": {
        "name": "光明网理论",
        "base_url": "https://theory.gmw.cn/node_97034.htm",
        "category": "政治理论",
        "parser": "guangming",
    },
    "qiushi": {
        "name": "求是网评",
        "base_url": "https://www.qstheory.cn/qswp.htm",
        "category": "政治理论",
        "parser": "qiushi",
    },
}

# ── AI Prompt Templates ──

# System prompt is imported from the shared module for consistency
# and AI-provider cache optimization (same system prompt = cache hit)
from app.services.prompts import CARD_SYSTEM_PROMPT, make_pipeline_user_prompt
from app.services.prompts import (
    ARTICLE_ANALYSIS_SYSTEM_PROMPT,
    make_article_analysis_prompt,
)
from app.services.prompt_loader import get_prompt, get_prompt_model
from app.models.article_analysis import ArticleAnalysis


class ArticlePipeline:
    """Fetch → Analyze → Generate → Dedup → Import pipeline."""

    PROCESSED_URLS_FILE = Path(__file__).parent / "backend" / "data" / "processed_articles.json"

    def __init__(
        self,
        db_path: str | None = None,
        dry_run: bool = False,
    ):
        self.dry_run = dry_run
        db_file = db_path or os.environ.get(
            "DATABASE_URL",
            str(Path(__file__).parent / "backend" / "data" / "flashcards.db"),
        )
        if not db_file.startswith("sqlite"):
            db_file = f"sqlite:///{db_file}"
        self.engine = create_engine(db_file)
        self.stats = {
            "articles_fetched": 0,
            "articles_skipped": 0,
            "cards_generated": 0,
            "cards_duplicated": 0,
            "cards_imported": 0,
            "errors": [],
        }
        self._processed_urls: dict[str, str] = self._load_processed_urls()

    def _load_processed_urls(self) -> dict[str, str]:
        """Load the set of already-processed article URLs with their processing dates."""
        if self.PROCESSED_URLS_FILE.exists():
            try:
                data = json.loads(self.PROCESSED_URLS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
                # Migrate from old list format
                if isinstance(data, list):
                    return {url: "" for url in data}
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_processed_urls(self):
        """Persist the processed URLs to disk."""
        self.PROCESSED_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.PROCESSED_URLS_FILE.write_text(
            json.dumps(self._processed_urls, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _mark_url_processed(self, url: str):
        """Mark an article URL as processed."""
        self._processed_urls[url] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _is_url_processed(self, url: str) -> bool:
        """Check if an article URL has already been processed."""
        return url in self._processed_urls

    async def run(
        self,
        source_keys: list[str] | None = None,
        max_articles: int = 5,
    ) -> dict:
        """Run the full pipeline."""
        sources = source_keys or list(SOURCES.keys())

        for key in sources:
            source = SOURCES.get(key)
            if not source:
                logger.warning(f"Unknown source: {key}")
                continue

            logger.info(f"📰 Processing source: {source['name']}")

            try:
                articles = await self._fetch_articles(source, max_articles)
                self.stats["articles_fetched"] += len(articles)
                logger.debug(f"  Fetched {len(articles)} articles")

                # Filter out already-processed URLs
                new_articles = []
                for article in articles:
                    if self._is_url_processed(article["url"]):
                        self.stats["articles_skipped"] += 1
                        logger.debug(f"  ⏭ Skipping (already processed): {article['title'][:50]}")
                    else:
                        new_articles.append(article)

                if not new_articles:
                    logger.debug(f"  No new articles to process")
                    continue

                logger.debug(f"  {len(new_articles)} new articles to process")

                for article in new_articles:
                    await self._process_article(article, source)
                    # Mark as processed even if no cards were generated
                    if not self.dry_run:
                        self._mark_url_processed(article["url"])

            except Exception as e:
                error = f"Source {source['name']}: {e}"
                logger.error(f"  ❌ {error}")
                self.stats["errors"].append(error)

        # Persist processed URLs to disk
        if not self.dry_run:
            self._save_processed_urls()

        return self.stats

    # ── Article Fetching ──

    async def _fetch_articles(
        self, source: dict, max_count: int
    ) -> list[dict]:
        """Fetch article list from a source."""
        parser = source.get("parser", "generic")
        url = source["base_url"]

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AnkiBot/1.0)"
                },
                follow_redirects=True,
                verify=False,  # Some sources (e.g. theory.people.com.cn) have cert issues
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            logger.error(f"  Fetch failed: {e}")
            return []

        # Parse article links
        soup = BeautifulSoup(html, "html.parser")
        articles = []

        if parser == "people_daily":
            articles = self._parse_people_daily_list(soup, url)
        elif parser == "xinhua":
            articles = self._parse_xinhua_list(soup, url)
        elif parser == "guangming":
            articles = self._parse_guangming_list(soup, url)
        elif parser == "qiushi":
            articles = self._parse_qiushi_list(soup, url)
        else:
            articles = self._parse_generic_list(soup, url)

        return articles[:max_count]

    def _parse_people_daily_list(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[dict]:
        """Parse People's Daily opinion/theory article list.

        Works for both opinion.people.com.cn and theory.people.com.cn.
        Article URLs follow: /n1/YYYY/MMDD/cNNN-NNN.html
        """
        articles = []
        from urllib.parse import urljoin

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(base_url, href)

            # Match People's Daily article URL pattern
            if not re.search(r"people\.com\.cn/n1/\d{4}/\d{4}/c\d+-\d+\.html", href):
                continue

            title = a.get_text(strip=True)
            if len(title) < 8:
                continue

            articles.append({
                "title": title,
                "url": href,
                "content": "",
                "date": self._extract_date_from_url(href),
            })

        # Deduplicate by URL
        seen = set()
        unique = []
        for a in articles:
            if a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)
        return unique

    def _parse_guangming_list(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[dict]:
        """Parse 光明网理论 article list.

        Article URLs follow: theory.gmw.cn/YYYY-MM/DD/content_NNN.htm
        """
        articles = []
        from urllib.parse import urljoin

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(base_url, href)

            # Match Guangming article URL pattern (theory.gmw.cn or news.gmw.cn)
            if not re.search(r"gmw\.cn/\d{4}-\d{2}/\d{2}/content_\d+\.htm", href):
                continue

            title = a.get_text(strip=True)
            if len(title) < 8:
                continue

            articles.append({
                "title": title,
                "url": href,
                "content": "",
                "date": self._extract_date_from_url(href),
            })

        # Deduplicate by URL
        seen = set()
        unique = []
        for a in articles:
            if a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)
        return unique

    def _parse_xinhua_list(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[dict]:
        """Parse Xinhua News commentary list."""
        articles = []
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if len(title) > 10:
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                articles.append({
                    "title": title,
                    "url": href,
                    "content": "",
                    "date": self._extract_date_from_url(href),
                })
        return articles

    def _parse_generic_list(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[dict]:
        """Generic article list parser."""
        articles = []
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) > 10:
                href = a["href"]
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                articles.append({
                    "title": title,
                    "url": href,
                    "content": "",
                    "date": "",
                })
        return articles[:20]

    def _parse_qiushi_list(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[dict]:
        """Parse 求是网 article list.

        Article URLs follow: qstheory.cn/YYYYMMDD/<uuid>/c.html
        """
        articles = []
        from urllib.parse import urljoin

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(base_url, href)

            # Match Qiushi article URL pattern
            if not re.search(r"qstheory\.cn/\d{8}/[a-f0-9]+/c\.html", href):
                continue

            title = a.get_text(strip=True)
            if len(title) < 8:
                continue

            articles.append({
                "title": title,
                "url": href,
                "content": "",
                "date": self._extract_date_from_url(href),
            })

        # Deduplicate by URL
        seen = set()
        unique = []
        for a in articles:
            if a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)
        return unique

    def _extract_date_from_url(self, url: str) -> str:
        """Extract date from URL patterns like /2024/0115/, /2024-06/01/, etc."""
        m = re.search(r"/(\d{4})/(\d{2})(\d{2})/", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = re.search(r"/(\d{4})-(\d{2})/(\d{2})/", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = re.search(r"/(\d{4})-(\d{2})-(\d{2})/", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = re.search(r"/(\d{4})(\d{2})(\d{2})", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return datetime.now().strftime("%Y-%m-%d")

    async def _fetch_article_content(self, article: dict) -> str:
        """Fetch full article content."""
        if article.get("content"):
            return article["content"]

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AnkiBot/1.0)"
                },
                follow_redirects=True,
                verify=False,
            ) as client:
                resp = await client.get(article["url"])
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove scripts, styles, nav
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()

            # Try common content selectors
            content_el = (
                soup.find("div", class_="rm_txt_con")  # People's Daily
                or soup.find("div", id="p-detail")  # Xinhua
                or soup.find("div", class_="u-mainText")  # 光明网
                or soup.find("article")
                or soup.find("div", class_="content")
                or soup.find("div", class_="article")
            )

            if content_el:
                text = content_el.get_text(separator="\n", strip=True)
            else:
                # Fallback: get all paragraph text
                paragraphs = soup.find_all("p")
                text = "\n".join(p.get_text(strip=True) for p in paragraphs)

            # Clean up
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text[:5000]  # Cap at 5000 chars for AI context

        except Exception as e:
            logger.warning(f"  Content fetch failed for {article['url']}: {e}")
            return article.get("title", "")

    # ── Article Processing ──

    async def _process_article(self, article: dict, source: dict):
        """Process a single article: fetch content → AI analyze → dedup → save."""
        logger.debug(f"  📄 {article['title'][:60]}")

        # Fetch full content
        content = await self._fetch_article_content(article)
        if len(content) < 50:
            logger.warning(f"    ⚠ Content too short, skipping")
            return

        # Generate cards via AI (also returns quality score)
        cards, quality_score = await self._ai_generate_cards(article["title"], content, source)
        if not cards:
            logger.warning(f"    ⚠ No cards generated")
            return

        self.stats["cards_generated"] += len(cards)
        logger.debug(f"    🤖 Generated {len(cards)} cards (quality: {quality_score}/10)")

        # Dedup and import
        with Session(self.engine) as session:
            imported = self._dedup_and_import(session, cards, article, source)
            self.stats["cards_imported"] += imported
            logger.debug(
                f"    ✅ Imported {imported} cards "
                f"(skipped {len(cards) - imported} duplicates)"
            )

        # Trigger deep reading analysis only for high-quality articles (≥6)
        # This avoids a separate AI call for low-quality articles
        if quality_score >= 6 and len(content) >= 300:
            await self._maybe_create_analysis(article, content, source)
        elif quality_score < 6:
            logger.debug(f"    📖 Skipping deep reading (quality {quality_score}/10 < 6)")

    async def _ai_generate_cards(
        self, title: str, content: str, source: dict
    ) -> tuple[list[dict], int]:
        """Use AI to analyze article and generate cards.

        Returns (cards_list, article_quality_score).
        The quality_score (1-10) is used to gate deep reading analysis.
        """
        with Session(self.engine) as session:
            # Find a user with AI configured
            config = session.exec(
                select(AIConfig).where(AIConfig.is_enabled == True)
            ).first()

            if not config:
                logger.warning("    ⚠ No AI config found, using fallback")
                return self._fallback_card_generation(title, content, source), 0

            # Use pipeline-specific model if configured, else default
            model = getattr(config, 'model_pipeline', '') or config.model

            prompt = make_pipeline_user_prompt(
                title=title,
                content=content,
                category_list="、".join(
                    c.name for c in session.exec(
                        select(Category)
                    ).all()
                ),
            )

            try:
                url = f"{config.api_base_url.rstrip('/')}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": get_prompt(session, "card_system", CARD_SYSTEM_PROMPT)},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4000,
                }

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()

                result = resp.json()
                content_text = result["choices"][0]["message"]["content"]

                # Parse JSON from response
                content_text = content_text.strip()
                if content_text.startswith("```"):
                    # Remove markdown code blocks
                    content_text = re.sub(r"^```(?:json)?\s*", "", content_text)
                    content_text = re.sub(r"\s*```$", "", content_text)

                parsed = json.loads(content_text)

                # Handle both new wrapper format and legacy array format
                if isinstance(parsed, dict):
                    quality_score = parsed.get("article_quality_score", 5)
                    cards = parsed.get("cards", [])
                elif isinstance(parsed, list):
                    # Legacy: AI returned plain array
                    quality_score = 5
                    cards = parsed
                else:
                    quality_score = 0
                    cards = []

                return cards, quality_score

            except json.JSONDecodeError as e:
                logger.error(f"    ❌ JSON parse error: {e}")
                self.stats["errors"].append(f"JSON parse: {e}")
                return [], 0
            except Exception as e:
                logger.error(f"    ❌ AI error: {e}")
                self.stats["errors"].append(f"AI: {e}")
                return self._fallback_card_generation(title, content, source), 0

    async def _maybe_create_analysis(self, article: dict, content: str, source: dict):
        """Trigger deep reading analysis for high-quality articles.

        Called only when article_quality_score >= 6 (gated in _process_article),
        so we skip the quality check here and go straight to analysis.
        """
        with Session(self.engine) as session:
            # Check if analysis already exists for this URL
            if article.get("url"):
                existing = session.exec(
                    select(ArticleAnalysis).where(
                        ArticleAnalysis.source_url == article["url"]
                    )
                ).first()
                if existing:
                    logger.debug(f"    ⏭ Analysis already exists, skipping")
                    return

            # Get AI config
            config = session.exec(
                select(AIConfig).where(AIConfig.is_enabled == True)
            ).first()
            if not config:
                return

            # Use reading-specific model if configured, else default
            model = getattr(config, 'model_reading', '') or config.model

            # Find user — use first user (pipeline always uses first/admin user)
            user = session.exec(
                select(User).where(User.is_admin == True)
            ).first()
            if not user:
                user = session.exec(select(User)).first()
            if not user:
                return

            # Call AI for analysis
            prompt = make_article_analysis_prompt(article["title"], content)
            try:
                url = f"{config.api_base_url.rstrip('/')}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": get_prompt(session, "article_analysis", ARTICLE_ANALYSIS_SYSTEM_PROMPT)},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 6000,
                }

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()

                result = resp.json()
                content_text = result["choices"][0]["message"]["content"]
                content_text = content_text.strip()
                if content_text.startswith("```"):
                    content_text = re.sub(r"^```(?:json)?\s*", "", content_text)
                    content_text = re.sub(r"\s*```$", "", content_text)

                analysis_data = json.loads(content_text)
            except Exception as e:
                logger.error(f"    ❌ Deep reading analysis failed: {e}")
                return

            quality_score = analysis_data.get("quality_score", 0)

            # Build HTML
            from app.routers.article_analysis import _build_analysis_html
            analysis_html = _build_analysis_html(article["title"], analysis_data)

            item = ArticleAnalysis(
                user_id=user.id,
                title=article["title"],
                source_url=article.get("url", ""),
                source_name=source.get("name", ""),
                publish_date=article.get("date", ""),
                content=content,
                analysis_html=analysis_html,
                analysis_json=json.dumps(analysis_data, ensure_ascii=False),
                quality_score=quality_score,
                quality_reason=analysis_data.get("quality_reason", ""),
                word_count=len(content),
                status="new",
            )
            session.add(item)
            session.commit()
            logger.debug(
                f"    📖 Deep reading analysis saved "
                f"(quality: {quality_score}/10)"
            )

    def _fallback_card_generation(
        self, title: str, content: str, source: dict
    ) -> list[dict]:
        """Generate basic cards without AI when AI is unavailable."""
        cards = []
        # Extract key sentences (first 3 substantial paragraphs)
        paragraphs = [
            p.strip()
            for p in content.split("\n")
            if len(p.strip()) > 30
        ]

        for i, para in enumerate(paragraphs[:3]):
            cards.append({
                "front": f"阅读以下时政评论内容，概述其核心观点：\n{para[:200]}",
                "back": f"来自「{title}」的核心观点",
                "explanation": para[:500],
                "distractors": [],
                "tags": f"时政热点,{source.get('name', '')}",
                "source_date": datetime.now().strftime("%Y-%m-%d"),
            })

        return cards

    # ── Dedup & Import ──

    def _dedup_and_import(
        self,
        session: Session,
        cards: list[dict],
        article: dict,
        source: dict,
    ) -> int:
        """Deduplicate and import cards into the database."""
        if self.dry_run:
            for card_data in cards:
                # front = card_data.get("front", "")[:60]
                logger.debug(f"    📝 [DRY RUN] Would import: {card_data}...")
            return 0

        # Find user (first admin or any user)
        user = session.exec(
            select(User).where(User.is_admin == True)
        ).first()
        if not user:
            user = session.exec(select(User)).first()
        if not user:
            logger.error("    ❌ No user found in database")
            return 0

        # Find or create deck
        source_category_name = source.get("category", "时政热点")
        deck_name = f"AI-{source_category_name}"
        deck = session.exec(
            select(Deck).where(
                Deck.name == deck_name,
            )
        ).first()
        if not deck:
            deck = Deck(
                name=deck_name,
                description=f"AI自动生成的{source_category_name}卡片",
            )
            session.add(deck)
            session.commit()
            session.refresh(deck)

        # Find source category (fallback)
        source_category = session.exec(
            select(Category).where(Category.name == source_category_name)
        ).first()

        # Preload all categories for per-card lookup
        all_categories = session.exec(select(Category)).all()
        cat_name_map = {c.name: c for c in all_categories}

        # Dedup service
        dedup = DedupService(session, user.id)

        imported = 0
        deck_counts: dict[int, int] = {}  # deck_id → count of imported cards

        for card_data in cards:
            front = card_data.get("front", "")
            if not front:
                continue

            # Check for duplicates
            existing = dedup.find_duplicate(front)
            if existing:
                self.stats["cards_duplicated"] += 1
                continue

            # Resolve category: use AI-assigned category first, fall back to source
            card_cat_name = card_data.get("category", "")
            card_category = cat_name_map.get(card_cat_name) if card_cat_name else None
            if not card_category:
                card_category = source_category

            # Find or create deck for this card's category (if different from source)
            card_deck = deck
            if card_category and card_category.name != source_category_name:
                card_deck_name = f"AI-{card_category.name}"
                card_deck = session.exec(
                    select(Deck).where(Deck.name == card_deck_name)
                ).first()
                if not card_deck:
                    card_deck = Deck(
                        name=card_deck_name,
                        description=f"AI自动生成的{card_category.name}卡片",
                    )
                    session.add(card_deck)
                    session.commit()
                    session.refresh(card_deck)

            # Process meta_info
            meta_info = card_data.get("meta_info", "")
            if isinstance(meta_info, dict):
                meta_info = json.dumps(meta_info, ensure_ascii=False)

            # Process distractors
            distractors = card_data.get("distractors", "")
            if isinstance(distractors, list):
                distractors = json.dumps(distractors, ensure_ascii=False)

            card = Card(
                deck_id=card_deck.id,
                category_id=card_category.id if card_category else None,
                front=front,
                back=card_data.get("back", ""),
                explanation=card_data.get("explanation", ""),
                distractors=distractors,
                tags=card_data.get("tags", ""),
                meta_info=meta_info,
                source=article.get("url", ""),
                source_date=card_data.get("source_date", article.get("date", "")),
                is_ai_generated=True,
                ai_review_status="approved",
            )
            session.add(card)
            imported += 1
            deck_counts[card_deck.id] = deck_counts.get(card_deck.id, 0) + 1

        if imported > 0:
            # Update card counts for all affected decks
            for d_id, count in deck_counts.items():
                d = session.get(Deck, d_id)
                if d:
                    d.card_count = (d.card_count or 0) + count
                    session.add(d)
            session.add(deck)
            session.commit()

        return imported


# ── Ingestion endpoint (for cron or manual trigger) ──

async def run_pipeline(
    source_keys: list[str] | None = None,
    max_articles: int = 5,
    db_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Entry point for the pipeline, callable from API or CLI."""
    pipeline = ArticlePipeline(db_path=db_path, dry_run=dry_run)
    return await pipeline.run(source_keys=source_keys, max_articles=max_articles)


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(
        description="AI Article Analysis Pipeline - Fetch, analyze, and generate flashcards",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without saving to database",
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help=f"Source key: {', '.join(SOURCES.keys())}",
    )
    parser.add_argument(
        "--max-articles", type=int, default=5,
        help="Maximum articles per source (default: 5)",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Database path (default: backend/data/anki.db)",
    )

    args = parser.parse_args()

    sources = [args.source] if args.source else None

    logger.info("🚀 Starting AI Article Analysis Pipeline")
    logger.info(f"   Sources: {sources or 'all'}")
    logger.info(f"   Max articles: {args.max_articles}")
    logger.info(f"   Dry run: {args.dry_run}")

    stats = asyncio.run(
        run_pipeline(
            source_keys=sources,
            max_articles=args.max_articles,
            db_path=args.db,
            dry_run=args.dry_run,
        )
    )

    logger.info("\n📊 Pipeline Results:")
    logger.info(f"   Articles fetched: {stats['articles_fetched']}")
    logger.info(f"   Articles skipped (already processed): {stats['articles_skipped']}")
    logger.info(f"   Cards generated: {stats['cards_generated']}")
    logger.info(f"   Cards imported: {stats['cards_imported']}")
    logger.info(f"   Duplicates skipped: {stats['cards_duplicated']}")
    if stats["errors"]:
        logger.info(f"   Errors: {len(stats['errors'])}")
        for e in stats["errors"]:
            logger.error(f"     - {e}")


if __name__ == "__main__":
    main()
