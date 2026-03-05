"""
E2E tests for the ingestion service parser.

Tests RSS and HTML fetching from real news sources to verify
URLs are valid and parsers extract meaningful content.

Run:  python -m pytest tests/test_ingestion_parser.py -v -s
"""

import asyncio
import logging

import httpx
import pytest

from app.services.ingestion_service import RSS_SOURCES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_url(url: str, timeout: float = 30.0) -> httpx.Response:
    """Fetch a URL and return the response."""
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        },
    ) as client:
        return await client.get(url)


# ---------------------------------------------------------------------------
# Test: All configured sources are reachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source", RSS_SOURCES, ids=[s["name"] for s in RSS_SOURCES]
)
async def test_source_reachable(source):
    """Each configured news source URL should return HTTP 200."""
    resp = await _fetch_url(source["url"])
    assert resp.status_code == 200, (
        f"{source['name']} ({source['url']}) returned {resp.status_code}"
    )
    assert len(resp.text) > 100, (
        f"{source['name']} returned near-empty body ({len(resp.text)} bytes)"
    )


# ---------------------------------------------------------------------------
# Test: RSS parser extracts articles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [s for s in RSS_SOURCES if s["type"] == "rss"],
    ids=[s["name"] for s in RSS_SOURCES if s["type"] == "rss"],
)
async def test_rss_parser(source):
    """RSS sources should yield valid feed entries with titles."""
    import feedparser

    resp = await _fetch_url(source["url"])
    assert resp.status_code == 200

    feed = feedparser.parse(resp.text)
    entries = feed.entries
    logger.info(
        "%s: %d entries, feed version=%s",
        source["name"],
        len(entries),
        feed.version,
    )

    # Should have at least one entry
    assert len(entries) > 0, f"{source['name']} RSS feed has no entries"

    # Each entry should have a title
    for entry in entries[:5]:
        title = entry.get("title", "")
        assert title, f"{source['name']}: entry missing title"
        assert len(title) > 2, f"{source['name']}: title too short: {title!r}"
        logger.info("  [%s] %s", source["name"], title[:60])


# ---------------------------------------------------------------------------
# Test: HTML parser extracts links with meaningful text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [s for s in RSS_SOURCES if s["type"] == "html" and "banyuetan" not in s.get("url", "")],
    ids=[s["name"] for s in RSS_SOURCES if s["type"] == "html" and "banyuetan" not in s.get("url", "")],
)
async def test_html_parser(source):
    """HTML sources should yield links with >10-char titles."""
    from bs4 import BeautifulSoup

    resp = await _fetch_url(source["url"])
    assert resp.status_code == 200

    soup = BeautifulSoup(resp.text, "lxml")
    articles = []
    for item in soup.find_all("a", href=True)[:50]:
        title = item.get_text(strip=True)
        if len(title) > 10:
            articles.append({"title": title, "link": item["href"]})

    logger.info(
        "%s: found %d articles with >10-char titles",
        source["name"],
        len(articles),
    )

    assert len(articles) > 0, (
        f"{source['name']} ({source['url']}) yielded no articles with >10-char text"
    )

    for art in articles[:5]:
        logger.info("  [%s] %s → %s", source["name"], art["title"][:60], art["link"][:80])


# ---------------------------------------------------------------------------
# Test: Full pipeline for each source type (without DB/AI)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_fetch_pipeline():
    """Integration test: fetch all sources and verify we get content."""
    results = {"rss": 0, "html": 0, "errors": []}
    import feedparser
    from bs4 import BeautifulSoup

    for source in RSS_SOURCES:
        try:
            resp = await _fetch_url(source["url"])
            if resp.status_code != 200:
                results["errors"].append(
                    f"{source['name']}: HTTP {resp.status_code}"
                )
                continue

            if source["type"] == "rss":
                feed = feedparser.parse(resp.text)
                count = len(feed.entries)
                results["rss"] += count
                logger.info("RSS %s: %d entries", source["name"], count)
            elif source["type"] == "html":
                soup = BeautifulSoup(resp.text, "lxml")
                count = sum(
                    1
                    for a in soup.find_all("a", href=True)
                    if len(a.get_text(strip=True)) > 10
                )
                results["html"] += count
                logger.info("HTML %s: %d links", source["name"], count)
        except Exception as e:
            results["errors"].append(f"{source['name']}: {e}")

    total = results["rss"] + results["html"]
    logger.info(
        "Pipeline total: %d items (RSS: %d, HTML: %d), %d errors",
        total,
        results["rss"],
        results["html"],
        len(results["errors"]),
    )
    # At least some sources should work
    assert total > 0, f"No content fetched. Errors: {results['errors']}"
    # Print errors as warnings, don't hard-fail on individual source issues
    for err in results["errors"]:
        logger.warning("Source error: %s", err)
