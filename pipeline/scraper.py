"""
MileMoa Scraper — Incremental scraping with pagination, rate limiting,
exponential backoff, and checkpoint integration.

Target: https://www.milemoa.com/bbs/board
Uses XpressEngine (XE) board layout.
"""
from __future__ import annotations

import os
import random
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config
from core.checkpoint import CheckpointState, save_checkpoint, update_status_md


# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    """Initialize SQLite database and create tables if needed."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id       TEXT PRIMARY KEY,
            title         TEXT NOT NULL,
            author        TEXT,
            category      TEXT,
            date_posted   TEXT,
            url           TEXT,
            view_count    INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            body_text     TEXT,
            scraped_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS summaries (
            post_id          TEXT PRIMARY KEY,
            title_ko         TEXT,
            key_takeaways    TEXT,
            target_category  TEXT,
            actionable_deal  INTEGER DEFAULT 0,
            urgency_level    TEXT,
            importance_score REAL,
            summarized_at    TEXT,
            FOREIGN KEY (post_id) REFERENCES posts(post_id)
        );
    """)
    conn.commit()
    conn.close()


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── HTTP Client ─────────────────────────────────────────────────────────────

class MileMoaClient:
    """HTTP client with retry logic and rate limiting."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.REQUEST_HEADERS)

    def fetch(self, url: str, retries: int = 0) -> Optional[str]:
        """
        Fetch a URL with exponential backoff on 429/503.
        Returns HTML string or None on failure.
        """
        try:
            resp = self.session.get(url, timeout=15)

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in (429, 503) and retries < config.BACKOFF_MAX_RETRIES:
                wait = config.BACKOFF_BASE ** (retries + 1) + random.uniform(0, 1)
                print(f"   ⏳ Rate limited ({resp.status_code}), waiting {wait:.1f}s...")
                time.sleep(wait)
                return self.fetch(url, retries + 1)

            print(f"   ⚠️  HTTP {resp.status_code} for {url}")
            return None

        except requests.RequestException as e:
            if retries < config.BACKOFF_MAX_RETRIES:
                wait = config.BACKOFF_BASE ** (retries + 1)
                print(f"   ⏳ Request error: {e}, retrying in {wait:.1f}s...")
                time.sleep(wait)
                return self.fetch(url, retries + 1)
            print(f"   ❌ Failed to fetch {url}: {e}")
            return None


# ─── Parsers ─────────────────────────────────────────────────────────────────

def parse_board_page(html: str) -> list[dict]:
    """
    Parse a MileMoa board listing page and extract post metadata.
    Returns list of post dicts (without body_text — that requires detail fetch).

    MileMoa uses Rhymix/XE LicenseBoard skin with lb-* class naming:
      - Container: div.lb-board > table.lb-table > tbody > tr
      - Each row: tr (with optional class lb-item)
      - Notice rows: category link has class lb-notice, or td.lb-in-no text is "공지"
    """
    soup = BeautifulSoup(html, "lxml")
    posts = []

    # Primary selector: Rhymix LicenseBoard table rows
    rows = soup.select("table.lb-table tbody tr")

    # Fallback: try div-based lb-item layout
    if not rows:
        rows = soup.select("div.lb-board div.lb-item, div.lb-board li.lb-item")

    # Last fallback: any row containing a board post link
    if not rows:
        rows = soup.select("tr")
        rows = [r for r in rows if r.select_one("a[href*='/bbs/board/']")]

    for row in rows:
        try:
            post = _parse_row(row)
            if post:
                posts.append(post)
        except Exception as e:
            print(f"   ⚠️  Failed to parse row: {e}")
            continue

    return posts


def _parse_row(row) -> Optional[dict]:
    """Parse a single post row element into a dict."""

    # ── Skip notice/pinned posts ──
    # Method 1: title h3 has class "lb-notice"
    notice_h3 = row.select_one("h3.lb-notice")
    if notice_h3:
        return None

    # Method 2: parent tbody has class "lb-notice"
    parent_tbody = row.find_parent("tbody")
    if parent_tbody and "lb-notice" in (parent_tbody.get("class") or []):
        return None

    # Method 3: number cell (td.lb-no) contains "공지"
    no_cell = row.select_one("td.lb-no")
    if no_cell and "공지" in no_cell.get_text(strip=True):
        return None

    # ── Title & URL ──
    # The actual link is `a.lb-in-title.lb-link` (not the h3)
    title_link = row.select_one("a.lb-link[href*='/bbs/board/']")
    if not title_link:
        title_link = row.select_one("a.lb-in-title")
    if not title_link:
        title_link = row.select_one("a[href*='/bbs/board/']")
    if not title_link:
        return None

    title = title_link.get_text(strip=True)
    href = title_link.get("href", "")

    # Strip query parameters — the listing appends ?page=N which causes 403 on detail fetch
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(href)
    clean_href = urlunparse(parsed._replace(query="", fragment=""))
    url = urljoin(config.BASE_URL, clean_href) if not clean_href.startswith("http") else clean_href

    # Extract post_id from URL: /bbs/board/12345678
    post_id_match = re.search(r"/bbs/board/(\d+)", href)
    if not post_id_match:
        post_id_match = re.search(r"document_srl=(\d+)", href)
    if not post_id_match:
        return None
    post_id = post_id_match.group(1)

    # ── Category ──
    cat_el = row.select_one("a.lb-in-category")
    category = cat_el.get_text(strip=True) if cat_el else ""

    # ── Comment count ──
    comment_el = row.select_one("a.lb-in-comments")
    comment_text = comment_el.get_text(strip=True) if comment_el else "0"
    comment_count = _parse_int(comment_text)

    # ── Author ──
    # Actual class: td.lb-nick_name > span.lb-author
    author_cell = row.select_one("td.lb-nick_name")
    if author_cell:
        author_el = author_cell.select_one("span.lb-author") or author_cell.select_one("span")
        author = author_el.get_text(strip=True) if author_el else author_cell.get_text(strip=True)
    else:
        author = ""

    # ── Date ──
    # Actual class: td.lb-regdate
    date_cell = row.select_one("td.lb-regdate")
    date_text = date_cell.get_text(strip=True) if date_cell else ""

    # ── View count ──
    # Actual class: td.lb-readed_count
    view_cell = row.select_one("td.lb-readed_count")
    view_count = _parse_int(view_cell.get_text(strip=True)) if view_cell else 0

    return {
        "post_id": post_id,
        "title": title,
        "author": author,
        "category": category,
        "date_posted": date_text,
        "url": url,
        "view_count": view_count,
        "comment_count": comment_count,
    }


def parse_post_detail(html: str) -> str:
    """Extract the body text from a post detail page."""
    soup = BeautifulSoup(html, "lxml")

    # Rhymix/XE content selectors (in priority order)
    body_el = (
        soup.select_one("div.xe_content")
        or soup.select_one("div.rd_body div.xe_content")
        or soup.select_one("div.document_27_12492904")  # document_{mid}_{srl} pattern
        or soup.select_one("article.content")
        or soup.select_one("div.rd_body")
        or soup.select_one("div.board_read div.content")
    )

    # Broader fallback: find any div whose class starts with "document_"
    if not body_el:
        for div in soup.find_all("div"):
            classes = div.get("class", [])
            for cls in classes:
                if cls.startswith("document_"):
                    body_el = div
                    break
            if body_el:
                break

    if body_el:
        # Remove script/style/iframe tags
        for tag in body_el.find_all(["script", "style", "iframe"]):
            tag.decompose()
        return body_el.get_text(separator="\n", strip=True)

    return ""


def _parse_int(text: str) -> int:
    """Extract integer from text, handling Korean number suffixes."""
    text = text.strip().replace(",", "")
    nums = re.findall(r"\d+", text)
    return int(nums[0]) if nums else 0


# ─── Incremental Scraper ────────────────────────────────────────────────────

def scrape_incremental(
    checkpoint: CheckpointState,
    progress_callback=None,
) -> CheckpointState:
    """
    Scrape MileMoa board incrementally from where we last stopped.

    - First run (no checkpoint): scrapes MAX_PAGES_FIRST_RUN pages
    - Subsequent runs: scrapes until hitting last_scraped_post_id
    """
    init_db()
    client = MileMoaClient()
    conn = get_db_connection()

    is_first_run = checkpoint.last_scraped_post_id is None
    max_pages = config.MAX_PAGES_FIRST_RUN if is_first_run else 50  # safety cap
    stop_at_id = checkpoint.last_scraped_post_id

    # 3-month deal freshness cutoff
    cutoff_dt = datetime.now() - timedelta(days=config.MAX_DEAL_AGE_DAYS)
    cutoff_date = cutoff_dt.strftime("%Y.%m.%d")

    newest_id_this_run = None
    total_new = 0
    hit_boundary = False

    def _log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    _log(f"   📅 Current deals cutoff: {cutoff_date} (within {config.MAX_DEAL_AGE_DAYS} days)")

    for page_num in range(1, max_pages + 1):
        if hit_boundary:
            break

        query_params = getattr(config, "BOARD_QUERY_PARAMS", "sort_index=regdate&order_type=desc")
        page_url = f"{config.BASE_URL}?{query_params}&page={page_num}"
        _log(f"   📄 Fetching page {page_num}: {page_url}")

        html = client.fetch(page_url)
        if not html:
            _log(f"   ⚠️  Failed to fetch page {page_num}, stopping pagination.")
            break

        posts = parse_board_page(html)
        if not posts:
            _log(f"   ⚠️  No posts found on page {page_num}, stopping.")
            break

        _log(f"   📋 Found {len(posts)} posts on page {page_num}")

        for post in posts:
            # Check incremental boundary (already scraped post)
            if stop_at_id and post["post_id"] == stop_at_id:
                _log(f"   🛑 Hit boundary post {stop_at_id}, stopping.")
                hit_boundary = True
                break

            # Check 3-month date cutoff: since posts are ordered by regdate desc,
            # once we see a date older than cutoff_date, all following posts are older.
            post_date = post.get("date_posted", "")
            if post_date and post_date < cutoff_date:
                _log(f"   🛑 Hit 3-month cutoff ({post_date} < {cutoff_date}), stopping.")
                hit_boundary = True
                break

            # Skip if already in DB
            existing = conn.execute(
                "SELECT post_id FROM posts WHERE post_id = ?",
                (post["post_id"],)
            ).fetchone()
            if existing:
                continue

            # Track newest post ID
            if newest_id_this_run is None:
                newest_id_this_run = post["post_id"]

            # Fetch detail page for body text
            _log(f"   📖 Fetching detail: {post['title'][:40]}...")
            detail_html = client.fetch(post["url"])
            if detail_html:
                post["body_text"] = parse_post_detail(detail_html)

                # Also try to extract view count and date from detail page
                # if they were missing from the listing
                _extract_detail_metadata(detail_html, post)
            else:
                post["body_text"] = ""

            post["scraped_at"] = datetime.now(timezone.utc).isoformat()

            # Insert into DB
            _insert_post(conn, post)
            total_new += 1

            # Respectful delay between detail fetches
            delay = random.uniform(config.SCRAPE_DELAY_MIN, config.SCRAPE_DELAY_MAX)
            time.sleep(delay)

        # Update checkpoint after each page
        checkpoint.last_scraped_page = page_num
        if newest_id_this_run:
            checkpoint.last_scraped_post_id = newest_id_this_run
        save_checkpoint(checkpoint)

    # Update final stats
    total_in_db = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    checkpoint.total_posts_scraped = total_in_db
    if newest_id_this_run:
        checkpoint.last_scraped_post_id = newest_id_this_run

    conn.close()
    _log(f"   📊 Scraped {total_new} new posts. Total in DB: {total_in_db}")
    return checkpoint


def _extract_detail_metadata(html: str, post: dict):
    """Extract additional metadata from detail page if missing from listing."""
    soup = BeautifulSoup(html, "lxml")

    # Try to get view count from detail page
    if not post.get("view_count"):
        view_el = soup.select_one("span.view, span.count, .side.fr span")
        if view_el:
            post["view_count"] = _parse_int(view_el.get_text())

    # Try to get date from detail page
    if not post.get("date_posted"):
        date_el = soup.select_one("span.date, time, .side span.date")
        if date_el:
            post["date_posted"] = date_el.get("datetime", "") or date_el.get_text(strip=True)

    # Try to get author from detail page
    if not post.get("author"):
        author_el = soup.select_one("a.member_plate, span.author, .profile_info .nick")
        if author_el:
            post["author"] = author_el.get_text(strip=True)

    # Try to get category from detail page
    if not post.get("category"):
        cat_el = soup.select_one("a.cate, span.category, .board_read .cate")
        if cat_el:
            post["category"] = cat_el.get_text(strip=True)


def _insert_post(conn: sqlite3.Connection, post: dict):
    """Insert or update a post in the database."""
    conn.execute("""
        INSERT OR REPLACE INTO posts
            (post_id, title, author, category, date_posted, url,
             view_count, comment_count, body_text, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post["post_id"],
        post["title"],
        post.get("author", ""),
        post.get("category", ""),
        post.get("date_posted", ""),
        post.get("url", ""),
        post.get("view_count", 0),
        post.get("comment_count", 0),
        post.get("body_text", ""),
        post.get("scraped_at", ""),
    ))
    conn.commit()
