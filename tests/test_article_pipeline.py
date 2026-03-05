"""Tests for source crawlers and ingestion pipeline."""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.source_crawlers import (
    NORMAL_SOURCES, SYSTEM_SOURCES,
    RMRB_IMPORTANT_SECTIONS, RMRB_SKIP_SECTIONS,
    extract_article_content,
)


class TestSourceCrawlers:
    def test_sources_defined(self):
        """Normal and system sources are properly defined."""
        assert len(NORMAL_SOURCES) >= 15
        for source in NORMAL_SOURCES:
            assert "name" in source
            assert "url" in source
            assert "category" in source
            assert "type" in source

        assert len(SYSTEM_SOURCES) == 2
        for source in SYSTEM_SOURCES:
            assert source["type"] == "special"

    def test_system_sources_names(self):
        names = [s["name"] for s in SYSTEM_SOURCES]
        assert "人民日报" in names
        assert "求是杂志" in names

    def test_rmrb_sections(self):
        """Important and skip section sets are disjoint."""
        important_keys = set(RMRB_IMPORTANT_SECTIONS.keys())
        assert len(important_keys & RMRB_SKIP_SECTIONS) == 0

    def test_extract_article_content(self):
        """extract_article_content returns title and cleaned text."""
        html = """
        <html>
        <head><title>测试标题 - 人民日报</title></head>
        <body>
        <nav>导航栏内容应该被移除</nav>
        <article>
            <h1>测试标题</h1>
            <p>这是第一段正文内容，包含了非常重要的信息。</p>
            <p>这是第二段正文内容，继续讨论重要话题。</p>
        </article>
        <footer>页脚内容应该被移除</footer>
        </body>
        </html>
        """
        title, body = extract_article_content(html, "http://example.com/article")
        assert "测试标题" in title
        assert "第一段正文" in body
        assert "第二段正文" in body

    def test_extract_article_content_empty(self):
        """extract_article_content handles minimal HTML."""
        title, body = extract_article_content("<html><body></body></html>", "http://x.com")
        assert isinstance(title, str)
        assert isinstance(body, str)

    def test_normal_source_urls_valid(self):
        """All normal source URLs look valid."""
        for source in NORMAL_SOURCES:
            assert source["url"].startswith("http"), f"{source['name']} has invalid URL"
