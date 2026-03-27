"""Special source crawlers for 人民日报 and 求是杂志.

These crawlers handle the unique page structures of these two key sources.
They are NOT affected by ingestion config settings (except schedule timing).
"""

import asyncio
import logging
import random
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("anki.crawlers")


def _bs4(html: str, parser: str = "html.parser"):
    """Lazy-import BeautifulSoup to avoid loading bs4/lxml at module level."""
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, parser)

# ── Anti-crawl: UA rotation ──
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _random_headers() -> dict[str, str]:
    """Return HTTP headers with a randomly chosen User-Agent."""
    return {"User-Agent": random.choice(_USER_AGENTS)}


HEADERS = _random_headers()  # backward compat


async def _polite_delay(min_s: float = 0.5, max_s: float = 2.0):
    """Random delay between requests to be polite to target servers."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int = 2,
    headers: dict | None = None,
) -> httpx.Response | None:
    """Fetch a URL with retry and exponential backoff.

    Returns the Response on success, or None after all retries fail.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = await client.get(url, headers=headers or _random_headers())
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None  # Don't retry 404s
            if attempt < max_retries:
                wait = (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning("HTTP %s for %s, retry %d/%d in %.1fs",
                               e.response.status_code, url[:80], attempt + 1, max_retries, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("HTTP %s for %s after %d retries", e.response.status_code, url[:80], max_retries)
                return None
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            if attempt < max_retries:
                wait = (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning("Connection error for %s: %s, retry %d/%d",
                               url[:80], str(e)[:60], attempt + 1, max_retries)
                await asyncio.sleep(wait)
            else:
                logger.error("Failed to fetch %s after %d retries: %s", url[:80], max_retries, str(e)[:80])
                return None
    return None

# ══════════════════════════════════════════════════════════════════════
# 人民日报 — Special crawler
# ══════════════════════════════════════════════════════════════════════

# Sections worth scraping for 公务员考试 (行测+申论)
# Key: section name keyword → priority (higher = more important)
RMRB_IMPORTANT_SECTIONS = {
    "评论": 10,   # 申论核心素材
    "理论": 9,    # 政治理论，习近平重要论述
    "经济": 8,    # 经济常识
    "记者调查": 7, # 深度调查，申论案例
    "新农村": 6,  # 三农/乡村振兴
    "民主政治": 6, # 政治制度
    "国际": 5,    # 国际常识
    #"文件": 4,    # 法律法规文本
    "特别报道": 4, # 看具体内容
}

# Sections to skip entirely
RMRB_SKIP_SECTIONS = {"副刊", "体育", "健康", "视觉", "广告", "假日生活", "人文"}

# 要闻 sections — only scrape first 4 pages of 要闻 to avoid too many
RMRB_MAX_YAOWEN_PAGES = 4


async def crawl_rmrb(date: datetime | None = None) -> list[dict]:
    """Crawl 人民日报 for a given date (defaults to today).

    Returns list of articles: [{"title": str, "url": str, "section": str, "date": str}]
    """
    if date is None:
        # Use China time (UTC+8)
        date = datetime.now(timezone(timedelta(hours=8)))

    date_str = date.strftime("%Y%m/%d")
    date_display = date.strftime("%Y-%m-%d")
    base_url = f"https://paper.people.com.cn/rmrb/pc/layout/{date_str}"

    articles: list[dict] = []

    try:
        # Step 1: Fetch node_01 to discover all sections for this date
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(f"{base_url}/node_01.html", headers=HEADERS)
            resp.raise_for_status()
            soup = _bs4(resp.text)

        # Parse all section links: node_XX.html
        section_links = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"node_(\d+)\.html", a["href"])
            if m:
                node_num = int(m.group(1))
                section_name = a.get_text(strip=True)
                # Extract just the name part: "05版：评论" → "评论"
                name_match = re.search(r"[：:](.+)", section_name)
                clean_name = name_match.group(1) if name_match else section_name
                section_links.append({
                    "node": node_num,
                    "name": clean_name,
                    "url": f"{base_url}/node_{m.group(1)}.html",
                })

        # Deduplicate by node number
        seen_nodes = set()
        unique_sections = []
        for s in section_links:
            if s["node"] not in seen_nodes:
                seen_nodes.add(s["node"])
                unique_sections.append(s)

        logger.debug(f"人民日报 {date_display}: found {len(unique_sections)} sections")

        # Step 2: Filter to important sections
        yaowen_count = 0
        sections_to_scrape = []
        for sec in unique_sections:
            name = sec["name"]

            # Skip explicitly excluded sections
            if any(skip in name for skip in RMRB_SKIP_SECTIONS):
                continue

            # 要闻 — limit to first N pages
            if name == "要闻":
                yaowen_count += 1
                if yaowen_count <= RMRB_MAX_YAOWEN_PAGES:
                    sections_to_scrape.append(sec)
                continue

            # Check if this is an important section
            for keyword in RMRB_IMPORTANT_SECTIONS:
                if keyword in name:
                    sections_to_scrape.append(sec)
                    break

        logger.debug(f"人民日报: scraping {len(sections_to_scrape)} sections: {[s['name'] for s in sections_to_scrape]}")

        # Step 3: Fetch articles from each section
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for sec in sections_to_scrape:
                try:
                    await _polite_delay(0.3, 1.0)
                    resp = await client.get(sec["url"], headers=_random_headers())
                    resp.raise_for_status()
                    sec_soup = _bs4(resp.text)

                    for a in sec_soup.find_all("a", href=True):
                        if "content_" in a["href"] and a.get_text(strip=True):
                            title = a.get_text(strip=True)
                            # Skip trivial entries
                            if len(title) < 5 or title in ("导读", "图片报道", "PDF下载"):
                                continue
                            url = a["href"]
                            if not url.startswith("http"):
                                url = urljoin(sec["url"], url)
                            articles.append({
                                "title": title,
                                "url": url,
                                "section": f"人民日报-{sec['name']}",
                                "date": date_display,
                            })
                except Exception as e:
                    logger.warning(f"人民日报: failed to fetch section {sec['name']}: {e}")

        # Deduplicate by URL
        seen = set()
        unique_articles = []
        for art in articles:
            if art["url"] not in seen:
                seen.add(art["url"])
                unique_articles.append(art)

        logger.debug(f"人民日报 {date_display}: total {len(unique_articles)} unique articles")
        return unique_articles

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info(f"人民日报 {date_display}: no edition (404) — likely a holiday")
            return []
        raise
    except Exception as e:
        logger.error(f"人民日报 crawl failed: {e}")
        return []


async def crawl_rmrb_range(
    start_date: datetime,
    end_date: datetime,
    *,
    progress_callback: Callable | None = None,
) -> list[dict]:
    """Crawl 人民日报 for a date range (inclusive).

    Args:
        start_date: First date to crawl.
        end_date: Last date to crawl (inclusive).
        progress_callback: Optional async callback(date_str, articles_count) for progress.

    Returns list of all articles across all dates, deduplicated by URL.
    """
    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    # Normalize to date only (strip time)
    current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if current > end:
        current, end = end, current

    # Safety: max 60 days to avoid abuse
    day_count = (end - current).days + 1
    if day_count > 60:
        logger.warning("RMRB backfill requested %d days, capping at 60", day_count)
        end = current + timedelta(days=59)
        day_count = 60

    logger.info("RMRB backfill: %s → %s (%d days)",
                current.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'), day_count)

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        try:
            day_articles = await crawl_rmrb(current)
            new_count = 0
            for art in day_articles:
                if art["url"] not in seen_urls:
                    seen_urls.add(art["url"])
                    all_articles.append(art)
                    new_count += 1
            logger.debug("RMRB %s: %d articles (%d new)", date_str, len(day_articles), new_count)
            if progress_callback:
                await progress_callback(date_str, new_count)
        except Exception as e:
            logger.warning("RMRB %s failed: %s", date_str, str(e)[:100])
            if progress_callback:
                await progress_callback(date_str, -1)  # -1 signals error

        # Check cancellation between days
        from app.routers.ingestion import _is_cancel_requested
        if _is_cancel_requested():
            logger.info("RMRB backfill cancelled after %s", date_str)
            break

        # Polite delay between days
        await _polite_delay(1.0, 2.5)
        current += timedelta(days=1)

    logger.info("RMRB backfill complete: %d total unique articles", len(all_articles))
    return all_articles


# ══════════════════════════════════════════════════════════════════════
# 求是杂志 — Special crawler
# ══════════════════════════════════════════════════════════════════════

async def crawl_qiushi() -> list[dict]:
    """Crawl 求是杂志 for the latest issue's articles.

    Returns list of articles: [{"title": str, "url": str, "section": str, "date": str}]
    """
    articles: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Step 1: Fetch directory page to find latest year
            resp = await client.get("https://www.qstheory.cn/qs/mulu.htm", headers=_random_headers())
            resp.raise_for_status()
            soup = _bs4(resp.text)

            # Find all year links
            year_links = []
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if re.match(r"\d{4}年", text):
                    url = a["href"]
                    if not url.startswith("http"):
                        url = urljoin("https://www.qstheory.cn/qs/mulu.htm", url)
                    year_links.append({"year": text, "url": url})

            if not year_links:
                logger.warning("求是: no year links found on directory page")
                return []

            # Use the first (latest) year
            latest_year = year_links[0]
            logger.debug(f"求是: latest year = {latest_year['year']}")

            # Step 2: Fetch year page to find latest issue
            await _polite_delay(0.5, 1.5)
            resp = await client.get(latest_year["url"], headers=_random_headers())
            resp.raise_for_status()
            year_soup = _bs4(resp.text)

            issue_links = []
            for a in year_soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                m = re.search(r"第(\d+)期", text)
                if m:
                    url = a["href"]
                    if not url.startswith("http"):
                        url = urljoin(latest_year["url"], url)
                    issue_links.append({"issue": int(m.group(1)), "text": text, "url": url})

            if not issue_links:
                logger.warning("求是: no issue links found on year page")
                return []

            # Get the latest issue (highest issue number)
            latest_issue = max(issue_links, key=lambda x: x["issue"])
            logger.debug(f"求是: latest issue = {latest_issue['text']}")

            # Step 3: Fetch issue page to get all article links
            await _polite_delay(0.5, 1.5)
            resp = await client.get(latest_issue["url"], headers=_random_headers())
            resp.raise_for_status()
            issue_soup = _bs4(resp.text)

            for a in issue_soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                href = a["href"]

                # Filter to real article links only
                if not title or len(title) < 5:
                    continue
                # Skip navigation and non-article links
                if any(skip in title for skip in (
                    "首页", "返回", "目录", "上一", "下一", "导航",
                    "理论资源", "sitemap", "投稿", "订阅", "关于我们",
                    "网站声明", "版权声明", "联系我们",
                )):
                    continue
                if "mulu" in href or href.startswith("#") or href.startswith("javascript"):
                    continue
                # Skip non-article paths (sitemap, index, etc.)
                if any(skip in href for skip in (
                    "sitemap", "mulu", "index.htm", "about.", "contact",
                )):
                    continue

                if not href.startswith("http"):
                    href = urljoin(latest_issue["url"], href)

                # Only include qstheory.cn article links (must have a date-like path)
                if "qstheory.cn" not in href or href == latest_issue["url"]:
                    continue
                # Articles have paths like /dukan/qs/2026-02/14/... or /20260214/<uuid>/c.html
                if not re.search(r'/\d{4}[-/]?\d{2}[-/]?\d{2}', href):
                    continue
                # Skip links from very old years (website boilerplate like 网站声明 from 2021)
                old_year_match = re.search(r'/(\d{4})[-/]?\d{2}', href)
                if old_year_match:
                    link_year = int(old_year_match.group(1))
                    from datetime import datetime
                    current_year = datetime.now().year
                    if link_year < current_year - 1:
                        continue

                articles.append({
                    "title": title,
                    "url": href,
                    "section": f"求是-{latest_issue['text']}",
                    "date": "",
                })

            # Deduplicate
            seen = set()
            unique = []
            for art in articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)

            logger.debug(f"求是: found {len(unique)} articles in {latest_issue['text']}")
            return unique

    except Exception as e:
        logger.error(f"求是 crawl failed: {e}")
        return []


async def crawl_qiushi_issues(year: int) -> list[dict]:
    """List all issues of 求是杂志 for a given year.

    Returns list: [{"issue": int, "text": str, "url": str}]
    sorted by issue number ascending.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Step 1: Fetch directory to find the year
            resp = await client.get(
                "https://www.qstheory.cn/qs/mulu.htm", headers=_random_headers(),
            )
            resp.raise_for_status()
            soup = _bs4(resp.text)

            year_url = None
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if text == f"{year}年":
                    url = a["href"]
                    if not url.startswith("http"):
                        url = urljoin("https://www.qstheory.cn/qs/mulu.htm", url)
                    year_url = url
                    break

            if not year_url:
                logger.warning("求是: year %d not found on directory page", year)
                return []

            # Step 2: Fetch year page to list issues
            await _polite_delay(0.5, 1.5)
            resp = await client.get(year_url, headers=_random_headers())
            resp.raise_for_status()
            year_soup = _bs4(resp.text)

            issues = []
            for a in year_soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                m = re.search(r"第(\d+)期", text)
                if m:
                    url = a["href"]
                    if not url.startswith("http"):
                        url = urljoin(year_url, url)
                    issues.append({
                        "issue": int(m.group(1)),
                        "text": text.strip(),
                        "url": url,
                    })

            # Deduplicate by issue number
            seen = set()
            unique = []
            for iss in issues:
                if iss["issue"] not in seen:
                    seen.add(iss["issue"])
                    unique.append(iss)

            unique.sort(key=lambda x: x["issue"])
            logger.debug("求是 %d年: found %d issues", year, len(unique))
            return unique

    except Exception as e:
        logger.error("求是 list issues for %d failed: %s", year, e)
        return []


async def crawl_qiushi_issue(issue_url: str, issue_name: str = "") -> list[dict]:
    """Crawl a specific issue of 求是杂志 by its URL.

    Args:
        issue_url: The URL of the issue page.
        issue_name: Display name like "第5期" for labeling.

    Returns list of articles: [{"title": str, "url": str, "section": str, "date": str}]
    """
    articles: list[dict] = []
    label = f"求是-{issue_name}" if issue_name else "求是杂志"

    # Extract expected year from issue_name (e.g. "2024年 《求是》2024年第1期")
    # or from the issue URL, so we can filter boilerplate links while allowing
    # old-year backfill.
    _name_year = re.search(r'(\d{4})', issue_name) if issue_name else None
    if _name_year:
        expected_year = int(_name_year.group(1))
    else:
        # Try new URL format: /YYYYMMDD/uuid/c.html
        _iy_match = re.search(r'/(\d{4})\d{4}/', issue_url)
        if not _iy_match:
            # Try old URL format: /YYYY-MM/DD/...
            _iy_match = re.search(r'/(\d{4})-\d{2}/', issue_url)
        expected_year = int(_iy_match.group(1)) if _iy_match else datetime.now().year

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(issue_url, headers=_random_headers())
            resp.raise_for_status()
            html_text = resp.text
            issue_soup = _bs4(html_text)

            all_links = issue_soup.find_all("a", href=True)
            logger.info("求是 %s: fetched issue page (%d bytes, %d links), expected_year=%d",
                        label, len(html_text), len(all_links), expected_year)

            for a in all_links:
                title = a.get_text(strip=True)
                href = a["href"]

                if not title or len(title) < 5:
                    continue
                if any(skip in title for skip in (
                    "首页", "返回", "目录", "上一", "下一", "导航",
                    "理论资源", "sitemap", "投稿", "订阅", "关于我们",
                    "网站声明", "版权声明", "联系我们",
                )):
                    continue
                if "mulu" in href or href.startswith("#") or href.startswith("javascript"):
                    continue
                if any(skip in href for skip in (
                    "sitemap", "mulu", "index.htm", "about.", "contact",
                )):
                    continue

                if not href.startswith("http"):
                    href = urljoin(issue_url, href)

                if "qstheory.cn" not in href or href == issue_url:
                    continue
                if not re.search(r'/\d{4}[-/]?\d{2}[-/]?\d{2}', href):
                    continue
                # Filter boilerplate links (e.g. 网站声明 from 2021) using
                # the issue's own year as reference, NOT the current year.
                old_year_match = re.search(r'/(\d{4})[-/]?\d{2}', href)
                if old_year_match:
                    link_year = int(old_year_match.group(1))
                    if link_year < expected_year - 1:
                        continue

                articles.append({
                    "title": title,
                    "url": href,
                    "section": label,
                    "date": "",
                })

            # Deduplicate
            seen = set()
            unique = []
            for art in articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)

            logger.info("求是 %s: found %d articles (after dedup)", label, len(unique))
            return unique

    except Exception as e:
        logger.error("求是 crawl issue %s failed: %s", issue_url[:80], e)
        return []


# ══════════════════════════════════════════════════════════════════════
# Generic content extraction using readability-lxml
# ══════════════════════════════════════════════════════════════════════

def extract_article_content(html: str, url: str = "") -> tuple[str, str]:
    """Extract article title and clean text from HTML using readability-lxml.

    Returns (title, body_text).
    """
    from readability import Document

    doc = Document(html)
    title = doc.short_title() or ""

    # Get the cleaned HTML content
    summary_html = doc.summary()

    # Parse the cleaned HTML to get plain text
    soup = _bs4(summary_html)

    # Remove remaining unwanted elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "iframe", "noscript"]):
        tag.decompose()

    # Convert <br> to newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Get text with paragraph separation
    body_text = soup.get_text(separator="\n", strip=True)

    # Clean up: remove excessive blank lines
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)

    # Remove known UI noise patterns (common across Chinese news sites)
    _noise_strings = [
        "放大", "缩小", "全文复制", "打印本页", "字体", "纠错",
        "分享到微信", "分享到微博", "分享到QQ", "分享到",
        "下载客户端", "扫一扫", "用微信扫", "二维码",
        "字号变大", "字号变小", "默认字号",
        "正在加载", "加载中",
    ]

    lines = body_text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            if clean_lines and clean_lines[-1] != "":
                clean_lines.append("")
            continue

        # Skip lines that are JUST a noise string (exact match or very short with noise)
        if line in _noise_strings:
            continue
        # Skip lines that are only a combo of noise strings (e.g. "放大 缩小 全文复制")
        stripped = line
        for ns in _noise_strings:
            stripped = stripped.replace(ns, "")
        if len(stripped.strip()) == 0:
            continue

        # Skip obvious boilerplate
        if re.match(
            r"^(首页|返回|分享到|来源[:：]|编辑[:：]|责编[:：]|责任编辑[:：]|作者[:：]|记者[:：]).{0,30}$",
            line,
        ):
            continue
        if re.match(
            r"^(上一篇|下一篇|相关文章|推荐阅读|热门推荐|点击进入|更多内容|原标题[:：]).{0,20}$",
            line,
        ):
            continue
        # Skip copyright / source lines
        if re.match(r"^[\(（].{2,30}[\)）]$", line):  # e.g. (责任编辑：xxx)
            continue
        # Skip pure tracking IDs
        if re.match(r"^[0-9a-f]{20,}$", line):
            continue

        clean_lines.append(line)

    body_text = "\n".join(clean_lines).strip()
    return title, body_text


def extract_article_date(html: str, url: str = "") -> str:
    """Extract publish date from an article page.

    Strategy:
    0. Domain-specific selectors (paper.people.com.cn etc.)
    1. <meta name="publishdate"> or similar meta tags (most reliable)
    2. Common date CSS classes (.pubtime, .h-time, .m-con-time, .time, etc.)
    3. Date pattern in URL
    Returns date string like '2026-02-27' or '' if not found.
    """
    soup = _bs4(html)

    # Method 0: Domain-specific selectors (meta tags are unreliable on some sites)
    is_paper_people = "paper.people.com.cn" in url
    if is_paper_people:
        # paper.people.com.cn has wrong meta publishdate (CMS template date)
        # Use <span class="newstime"> which has the real publish date
        el = soup.find("span", class_="newstime") or soup.find(class_="newstime")
        if el:
            text = el.get_text(strip=True)
            m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
            if m:
                result = _validate_date(m.group(1), m.group(2), m.group(3))
                if result:
                    return result
        # Also try <p class="sec"> which often contains date like "（2026年02月24日第 05 版）"
        sec_el = soup.find("p", class_="sec")
        if sec_el:
            text = sec_el.get_text(strip=True)
            m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
            if m:
                result = _validate_date(m.group(1), m.group(2), m.group(3))
                if result:
                    return result

    # Method 1: Meta tags (most reliable across Chinese news sites)
    # Skip for paper.people.com.cn — its meta publishdate is a wrong CMS template date
    if not is_paper_people:
        for meta in soup.find_all("meta"):
            name_attr = (meta.get("name") or meta.get("property") or "").lower()
            if any(kw in name_attr for kw in ("publishdate", "publish_date", "pubdate", "article:published_time")):
                content = meta.get("content", "").strip()
                if content:
                    m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", content)
                    if m:
                        return m.group(1).replace("/", "-")

    # Method 2: Common CSS selectors
    for cls in ("pubtime", "h-time", "m-con-time", "time", "date", "pub_time",
                "article-time", "publish-time", "post-date"):
        el = soup.find(class_=cls)
        if el:
            text = el.get_text(strip=True)
            m = re.search(r"(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})", text)
            if m:
                return m.group(1).replace("年", "-").replace("月", "-").replace("/", "-").rstrip("日")

    # Method 3: <time> element
    time_el = soup.find("time")
    if time_el:
        dt = time_el.get("datetime", "") or time_el.get_text(strip=True)
        m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", dt)
        if m:
            return m.group(1).replace("/", "-")

    # Method 4: Date from URL
    # Pattern: /YYYY-MM/DD/ or /YYYYMMDD/ or /YYYY/MMDD/ or /YYYYMM/DD/
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
    if m:
        result = _validate_date(m.group(1), m.group(2), m.group(3))
        if result:
            return result
    m = re.search(r"/(\d{4})[-/](\d{2})[-/](\d{2})", url)
    if m:
        result = _validate_date(m.group(1), m.group(2), m.group(3))
        if result:
            return result
    # Pattern: /YYYYMM/DD/ (e.g. paper.people.com.cn /202602/24/)
    m = re.search(r"/(\d{4})(\d{2})/(\d{2})/", url)
    if m:
        result = _validate_date(m.group(1), m.group(2), m.group(3))
        if result:
            return result

    # Method 5: Text patterns like "2026年02月24日" or "（2026年02月24日 ..."
    for el in soup.find_all(["span", "p", "div", "h4", "h3"], limit=40):
        text = el.get_text(strip=True)
        if len(text) > 200:
            continue
        m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
        if m:
            result = _validate_date(m.group(1), m.group(2), m.group(3))
            if result:
                return result

    return ""


def extract_article_author(html: str, url: str = "") -> str:
    """Extract author name from an article page.

    Strategy:
    0. Domain-specific selectors (paper.people.com.cn etc.)
    1. <meta name="author"> or similar meta tags
    2. Common CSS classes (.author, .writer, .editor, .source)
    3. Inline text patterns like '作者：xxx' or '来源：xxx  作者：xxx'
    Returns author string or '' if not found.
    """
    soup = _bs4(html)

    # Method 0: Domain-specific selectors
    is_paper_people = "paper.people.com.cn" in url
    if is_paper_people:
        # paper.people.com.cn meta author tag returns "第005版" (wrong)
        # Real author is in <p class="sec">: "孟繁哲《人民日报》（2026年02月24日..."
        sec_el = soup.find("p", class_="sec")
        if sec_el:
            text = sec_el.get_text(strip=True)
            m = re.search(r"^(.{2,6})[\s　]*《", text)
            if m:
                author = m.group(1).strip()
                if author and not re.search(r"[（(：:·•第]", author):
                    return author
        # Also try author info in spans within the article
        for el in soup.find_all(["span", "p"], limit=30):
            text = el.get_text(strip=True)
            if len(text) > 100:
                continue
            m = re.search(r"(?:记者|通讯员)\s+([^\s]{2,8})", text)
            if m:
                return m.group(1).strip()

    # Method 1: Meta tags
    # Skip for paper.people.com.cn — its meta author returns page number "第005版"
    if not is_paper_people:
        for meta in soup.find_all("meta"):
            name_attr = (meta.get("name") or meta.get("property") or "").lower()
            if name_attr in ("author", "article:author", "byl"):
                content = meta.get("content", "").strip()
                if content and len(content) <= 50:
                    return content

    # Method 2: Common CSS selectors for author
    for cls in ("author", "writer", "editor-name", "art_author", "author_name",
                "p-jc", "arti_editor", "article-source"):
        el = soup.find(class_=cls)
        if el:
            text = el.get_text(strip=True)
            # Clean common prefixes
            for prefix in ("作者：", "作者:", "编辑：", "编辑:", "责编：", "责编:",
                           "来源：", "来源:", "记者 ", "记者：", "记者:"):
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
                    break
            if text and 1 < len(text) <= 30:
                return text

    # Method 3: Look for text patterns in common containers
    for el in soup.find_all(["span", "p", "div"], limit=60):
        text = el.get_text(strip=True)
        if len(text) > 200:
            continue
        # Match patterns: 作者：张三  or  作者:李四
        m = re.search(r"作者[：:]\s*(.{2,20}?)(?:\s|$|/|｜|\|)", text)
        if m:
            return m.group(1).strip()
        # Match: 记者 张三 xxx
        m = re.search(r"(?:记者|通讯员)\s+([^\s]{2,8})", text)
        if m:
            return m.group(1).strip()
        # Match people.com.cn pattern: 孟繁哲《人民日报》（2026年... or 张三  《人民日报》
        m = re.search(r"^(.{2,6})[\s　]*《", text)
        if m:
            author = m.group(1).strip()
            # Filter out false positives like section headings
            if author and not re.search(r"[（(：:·•第]", author):
                return author

    return ""


# ══════════════════════════════════════════════════════════════════════
# Shared URL fetch + extract (used by fetch-url, ingestion, source test)
# ══════════════════════════════════════════════════════════════════════

# Domain → Chinese source name mapping
_DOMAIN_SOURCE_MAP = {
    "people.com.cn": "人民日报",
    "xinhuanet.com": "新华网",
    "news.cn": "新华网",
    "gmw.cn": "光明网",
    "qstheory.cn": "求是网",
    "gov.cn": "中国政府网",
    "cctv.com": "央视网",
    "chinanews.com": "中国新闻网",
    "cnr.cn": "央广网",
    "youth.cn": "中国青年网",
    "ce.cn": "中国经济网",
    "12371.cn": "共产党员网",
    "banyuetan.org": "半月谈",
}


def domain_to_source_name(url: str) -> str:
    """Map a URL's domain to a friendly Chinese source name."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    for d, name in _DOMAIN_SOURCE_MAP.items():
        if d in domain:
            return name
    return domain.replace("www.", "")


async def fetch_and_extract_url(
    url: str,
    *,
    timeout: float = 30.0,
    ssrf_check: bool = False,
) -> dict:
    """Fetch a URL, extract article content/title/date/source_name.

    Args:
        url: The URL to fetch.
        timeout: HTTP timeout in seconds.
        ssrf_check: If True, block private/loopback IPs (for user-facing endpoints).

    Returns:
        dict with keys: title, content, html, source_url, source_name,
                        publish_date.

    Raises:
        ValueError: If URL is invalid or SSRF check fails.
        httpx.HTTPStatusError: If HTTP request fails.
    """
    from urllib.parse import urlparse

    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    # ── SSRF protection ──
    if ssrf_check:
        import ipaddress
        import socket
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        if not hostname:
            raise ValueError("无效的URL")
        try:
            resolved_ips = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in resolved_ips:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    raise ValueError("不允许访问内网地址")
        except socket.gaierror:
            raise ValueError(f"无法解析域名: {hostname}")

    headers = _random_headers()
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=headers,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    title, content = extract_article_content(html, url)
    publish_date = extract_article_date(html, url)
    source_name = domain_to_source_name(url)

    return {
        "title": title,
        "content": content,
        "html": html,
        "source_url": url,
        "source_name": source_name,
        "publish_date": publish_date,
    }


# ══════════════════════════════════════════════════════════════════════
# Normal source crawler — generic article list → article fetch
# ══════════════════════════════════════════════════════════════════════

# Patterns indicating a link is an index/section page rather than an article
_NON_ARTICLE_PATH_PATTERNS = (
    r"index\.", r"list\.", r"sitemap", r"about\.", r"contact",
    r"/main/[a-z]+/$", r"/wenhui\.php$",
)
_NON_ARTICLE_URL_RE = re.compile("|".join(_NON_ARTICLE_PATH_PATTERNS), re.I)


def _validate_date(year: str, month: str, day: str) -> str:
    """Validate a date and return 'YYYY-MM-DD' or '' if invalid."""
    try:
        y, m, d = int(year), int(month), int(day)
        if 2000 <= y <= 2099 and 1 <= m <= 12 and 1 <= d <= 31:
            # Quick sanity check via datetime
            datetime(y, m, d)
            return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, TypeError):
        pass
    return ""


def _extract_date_from_url(url: str) -> str:
    """Try to extract a date from a URL path."""
    # /YYYYMMDD/  (e.g. banyuetan.org/jczl/detail/20260226/...)
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
    if m:
        result = _validate_date(m.group(1), m.group(2), m.group(3))
        if result:
            return result
    # /YYYY-MM/DD/  or /YYYY/MM/DD
    m = re.search(r"/(\d{4})[-/](\d{2})[-/](\d{2})", url)
    if m:
        result = _validate_date(m.group(1), m.group(2), m.group(3))
        if result:
            return result
    return ""


def _clean_title_and_extract_date(raw_title: str, url: str = "") -> tuple[str, str]:
    """Clean a title and extract any embedded date.

    Handles patterns like:
    - '把稳舵 扎深根2026-2-27 15:13' (date at end of title)
    - '把稳舵 扎深根 2026年2月27日' (Chinese date format)

    Returns (clean_title, date_str).
    """
    title = raw_title.strip()
    date = ""

    # Pattern 1: 'YYYY-M-D HH:MM' at end (共产党员网 format)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+\d{1,2}:\d{2}\s*$", title)
    if m:
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        title = title[:m.start()].strip()
        return title, date

    # Pattern 2: 'YYYY-MM-DD' at end
    m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})\s*$", title)
    if m:
        raw_date = m.group(1)
        parts = raw_date.split("-")
        date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        title = title[:m.start()].strip()
        return title, date

    # Pattern 3: 'YYYY年M月D日' at end
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*$", title)
    if m:
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        title = title[:m.start()].strip()
        return title, date

    # Fallback: extract date from URL
    if not date:
        date = _extract_date_from_url(url)

    return title, date


async def crawl_normal_source(
    source_name: str,
    source_url: str,
    source_type: str,
    max_articles: int = 20,
) -> list[dict]:
    """Crawl a normal source: fetch article list page, extract article links.

    Returns list of articles: [{"title": str, "url": str, "section": str, "date": str}]
    """
    articles: list[dict] = []

    try:
        await _polite_delay(0.5, 1.5)
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(source_url, headers=_random_headers())
            resp.raise_for_status()
            page_content = resp.text

        # Determine the source domain for filtering
        from urllib.parse import urlparse
        source_domain = urlparse(source_url).netloc

        if source_type == "rss":
            import feedparser
            feed = feedparser.parse(page_content)
            for entry in feed.entries[:max_articles]:
                url = entry.get("link", "")
                title = entry.get("title", "")
                if url and title:
                    articles.append({
                        "title": title,
                        "url": url,
                        "section": source_name,
                        "date": entry.get("published", ""),
                    })
        else:
            soup = _bs4(page_content)
            seen_urls = set()
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                href = a["href"]

                if len(title) < 10 or href.startswith("#") or href.startswith("javascript:"):
                    continue
                if not href.startswith("http"):
                    href = urljoin(source_url, href)

                # Skip links to other domains (cross-site sidebar links)
                link_domain = urlparse(href).netloc
                if link_domain != source_domain:
                    # Allow sub-domains of the same root
                    src_root = ".".join(source_domain.split(".")[-2:])
                    lnk_root = ".".join(link_domain.split(".")[-2:])
                    if src_root != lnk_root:
                        continue

                # Skip non-article pages (index pages, section pages, etc.)
                if _NON_ARTICLE_URL_RE.search(href):
                    continue
                # Skip links that look like section headers (very short paths)
                parsed_link = urlparse(href)
                path = parsed_link.path
                if path.count("/") <= 1 and not re.search(r"\d", path) and not parsed_link.query:
                    continue

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Clean title and extract date
                clean_title, date = _clean_title_and_extract_date(title, href)

                articles.append({
                    "title": clean_title,
                    "url": href,
                    "section": source_name,
                    "date": date,
                })
                if len(articles) >= max_articles:
                    break

        return articles

    except Exception as e:
        logger.error(f"Normal source '{source_name}' crawl failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════
# Default normal sources list
# ══════════════════════════════════════════════════════════════════════

NORMAL_SOURCES = [
    # 光明网
    {"name": "光明网-时评", "url": "https://guancha.gmw.cn/", "category": "申论素材", "type": "html"},
    {"name": "光明网-理论", "url": "https://theory.gmw.cn/", "category": "申论素材", "type": "html"},
    # 中国经济网
    {"name": "中国经济网-评新而论", "url": "http://views.ce.cn/main/yc/", "category": "常识判断", "type": "html"},
    # 瞭望 (verified sources — 重磅推介 & 治国理政纪事 removed: articles link to xinhua app)
    {"name": "瞭望-特别报道", "url": "https://lw.xinhuanet.com/tbbd.htm", "category": "时政热点", "type": "html"},
    {"name": "瞭望-深观察", "url": "https://lw.xinhuanet.com/rgc.htm", "category": "申论素材", "type": "html"},
    {"name": "瞭望-新格局", "url": "https://lw.xinhuanet.com/cj.htm", "category": "常识判断", "type": "html"},
    {"name": "瞭望-时评", "url": "https://lw.xinhuanet.com/sp2.htm", "category": "申论素材", "type": "html"},
    {"name": "瞭望-热点解析", "url": "https://lw.xinhuanet.com/rdjx.htm", "category": "时政热点", "type": "html"},
    {"name": "瞭望-政策解码", "url": "https://lw.xinhuanet.com/zcjm.htm", "category": "时政热点", "type": "html"},
    # 共产党员网
    {"name": "共产党员网-先锋文汇", "url": "https://tougao.12371.cn/wenhui.php", "category": "申论素材", "type": "html"},
    # 半月谈
    {"name": "半月谈-评论", "url": "http://www.banyuetan.org/byt/banyuetanpinglun/index.html", "category": "申论素材", "type": "html"},
    {"name": "半月谈-基层治理", "url": "http://www.banyuetan.org/byt/jicengzhili/index.html", "category": "申论素材", "type": "html"},
    # 求是网 (非杂志)
    {"name": "求是-求是网评", "url": "https://www.qstheory.cn/qswp.htm", "category": "申论素材", "type": "html"},
    {"name": "求是-理论精选", "url": "https://www.qstheory.cn/mlljx.htm", "category": "政治理论", "type": "html"},
    {"name": "求是-锐评观察", "url": "https://www.qstheory.cn/mrpgc.htm", "category": "申论素材", "type": "html"},
]

# System (special rule) sources — these are fixed and cannot be deleted
SYSTEM_SOURCES = [
    {
        "name": "人民日报",
        "url": "https://paper.people.com.cn/rmrb/pc/layout/{date}/node_01.html",
        "category": "时政热点",
        "type": "special",
        "description": "人民日报电子版，自动抓取每日重要版面（评论、理论、经济等）",
    },
    {
        "name": "求是杂志",
        "url": "https://www.qstheory.cn/qs/mulu.htm",
        "category": "政治理论",
        "type": "special",
        "description": "求是杂志，自动抓取最新一期的全部文章",
    },
]
