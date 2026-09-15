"""
Scoring & Summarization Pipeline — Ranks posts by importance and
generates extractive summaries.

Uses rule-based keyword scoring + first-N-sentence extraction.
Architecture supports pluggable LLM backend via summarize_post_llm().
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import config
from core.checkpoint import CheckpointState, save_checkpoint
from pipeline.scraper import get_db_connection, init_db


# ─── Importance Scoring ─────────────────────────────────────────────────────

def compute_importance_score(post: dict) -> float:
    """
    Score a post's importance on a 0–100 scale based on:
    - Community engagement (comment count, view count)
    - High-value keyword presence in title + body
    - Category bonus
    """
    score = 0.0
    title = (post.get("title") or "").lower()
    body = (post.get("body_text") or "").lower()
    combined = title + " " + body

    # ── Comment engagement (max 30 pts) ──
    comments = post.get("comment_count", 0) or 0
    if comments >= 50:
        score += 30
    elif comments >= 20:
        score += 25
    elif comments >= 10:
        score += 20
    elif comments >= 5:
        score += 12
    elif comments >= 1:
        score += 5

    # ── View count (max 20 pts) ──
    views = post.get("view_count", 0) or 0
    if views >= 5000:
        score += 20
    elif views >= 2000:
        score += 15
    elif views >= 1000:
        score += 10
    elif views >= 500:
        score += 5

    # ── Keyword bonus (max 30 pts) ──
    keyword_hits = 0
    for kw in config.HIGH_VALUE_KEYWORDS:
        if kw.lower() in combined:
            keyword_hits += 1

    keyword_score = min(keyword_hits * 5, 30)
    score += keyword_score

    # ── Category bonus (max 15 pts) ──
    category = (post.get("category") or "").strip()
    for high_cat in config.HIGH_VALUE_CATEGORIES:
        if high_cat in category:
            score += 15
            break

    # ── Title length / quality heuristic (max 5 pts) ──
    if len(title) > 10:
        score += 3
    if any(c in title for c in ["!", "?", "역대", "긴급", "필독"]):
        score += 2

    return min(score, 100.0)


# ─── Category Classification ────────────────────────────────────────────────

def classify_category(post: dict) -> str:
    """Classify a post into a target category based on keyword matching."""
    title = (post.get("title") or "").lower()
    body = (post.get("body_text") or "")[:500].lower()
    combined = title + " " + body
    category = (post.get("category") or "").lower()

    scores = {}
    for cat, keywords in config.CATEGORY_KEYWORDS.items():
        cat_score = 0
        for kw in keywords:
            if kw.lower() in combined or kw.lower() in category:
                cat_score += 1
        scores[cat] = cat_score

    if not scores or max(scores.values()) == 0:
        return "General Travel"

    return max(scores, key=scores.get)


# ─── Extractive Summarization ───────────────────────────────────────────────

def extract_key_sentences(text: str, n: int = 3) -> list[str]:
    """
    Extract the first N meaningful sentences from the text.
    Filters out very short or boilerplate lines.
    """
    if not text:
        return ["(본문 없음)"]

    # Split by common sentence boundaries
    lines = re.split(r'[\n。.!?]+', text)

    # Filter meaningful lines
    meaningful = []
    for line in lines:
        line = line.strip()
        # Skip too short, pure whitespace, or boilerplate
        if len(line) < 8:
            continue
        if line.startswith(("http", "www.", "img", "출처:", "사진:")):
            continue
        meaningful.append(line)
        if len(meaningful) >= n:
            break

    if not meaningful:
        # Fallback: just take first chunk of text
        return [text[:200].strip() + "..."] if text else ["(본문 없음)"]

    return meaningful


def is_actionable_deal(post: dict) -> bool:
    """Determine if a post contains an actionable deal/offer."""
    combined = ((post.get("title") or "") + " " + (post.get("body_text") or "")[:300]).lower()
    deal_keywords = [
        "핫딜", "hot deal", "보너스", "bonus", "오퍼", "offer",
        "프로모션", "promotion", "할인", "discount", "한정",
        "마감", "무료", "free", "쿠폰", "coupon",
    ]
    return any(kw in combined for kw in deal_keywords)


def determine_urgency(score: float) -> str:
    """Map importance score to urgency level."""
    if score >= config.URGENCY_HIGH_THRESHOLD:
        return "High"
    elif score >= config.URGENCY_MEDIUM_THRESHOLD:
        return "Medium"
    else:
        return "Low"


def summarize_post(post: dict) -> dict:
    """
    Generate a structured summary for a single post using
    rule-based extractive summarization.
    """
    score = compute_importance_score(post)
    takeaways = extract_key_sentences(post.get("body_text", ""), n=3)
    category = classify_category(post)
    actionable = is_actionable_deal(post)
    urgency = determine_urgency(score)

    return {
        "post_id": post["post_id"],
        "title_ko": post.get("title", ""),
        "key_takeaways": json.dumps(takeaways, ensure_ascii=False),
        "target_category": category,
        "actionable_deal": 1 if actionable else 0,
        "urgency_level": urgency,
        "importance_score": round(score, 1),
        "summarized_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── LLM Summarization Hook (Future) ────────────────────────────────────────

def summarize_post_llm(post: dict, api_key: str, provider: str = "openai") -> Optional[dict]:
    """
    Placeholder for LLM-powered summarization.
    Swap in your preferred provider by implementing this function.

    Expected to return the same schema as summarize_post().
    """
    raise NotImplementedError(
        "LLM summarization not configured. "
        "Set your API key in config.py and implement this function."
    )


# ─── Batch Pipeline ─────────────────────────────────────────────────────────

def score_and_summarize(
    checkpoint: CheckpointState,
    progress_callback=None,
) -> CheckpointState:
    """
    Process all unsummarized posts: score and generate summaries.
    Updates checkpoint with processed IDs.
    """
    init_db()
    conn = get_db_connection()

    def _log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    # Find posts that haven't been summarized yet
    processed_set = set(checkpoint.processed_post_ids)

    rows = conn.execute("""
        SELECT p.*
        FROM posts p
        LEFT JOIN summaries s ON p.post_id = s.post_id
        WHERE s.post_id IS NULL
        ORDER BY p.post_id DESC
    """).fetchall()

    _log(f"   📝 {len(rows)} posts to summarize")

    count = 0
    for row in rows:
        post = dict(row)

        if post["post_id"] in processed_set:
            continue

        summary = summarize_post(post)

        # Insert summary into DB
        conn.execute("""
            INSERT OR REPLACE INTO summaries
                (post_id, title_ko, key_takeaways, target_category,
                 actionable_deal, urgency_level, importance_score, summarized_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            summary["post_id"],
            summary["title_ko"],
            summary["key_takeaways"],
            summary["target_category"],
            summary["actionable_deal"],
            summary["urgency_level"],
            summary["importance_score"],
            summary["summarized_at"],
        ))
        conn.commit()

        # Update checkpoint
        checkpoint.processed_post_ids.append(post["post_id"])
        count += 1

        if count % 10 == 0:
            save_checkpoint(checkpoint)
            _log(f"   📊 Summarized {count}/{len(rows)} posts...")

    # Final stats
    total_summarized = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
    checkpoint.total_posts_summarized = total_summarized

    conn.close()
    _log(f"   ✓ Summarized {count} new posts. Total: {total_summarized}")
    return checkpoint
