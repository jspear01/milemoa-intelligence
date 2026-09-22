"""
MileMoa Dashboard — Streamlit-based interactive UI for browsing
scraped and summarized MileMoa posts.

Run: streamlit run ui/app.py
"""
from __future__ import annotations

import json
import os
import sys
import sqlite3
import subprocess
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
import config
importlib.reload(config)
from core.checkpoint import load_checkpoint, PipelinePhase

# ─── Page Config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="마일모아 인사이트",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* ── Global Theme ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* ── Header ── */
    .dashboard-header {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .dashboard-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .dashboard-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.8;
        font-size: 0.95rem;
    }

    /* ── Stat Cards ── */
    .stat-card {
        background: linear-gradient(145deg, #1e1e2e, #2a2a3e);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        text-align: center;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .stat-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stat-label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        opacity: 0.6;
        margin-top: 0.3rem;
    }

    /* ── Post Cards ── */
    .post-card {
        background: linear-gradient(145deg, #1a1a2e, #22223a);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        transition: transform 0.2s ease, border-color 0.3s ease;
    }
    .post-card:hover {
        transform: translateY(-1px);
        border-color: rgba(102, 126, 234, 0.3);
    }
    .post-title {
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 0.7rem;
        line-height: 1.4;
    }
    .post-title a {
        color: #e0e0ff;
        text-decoration: none;
    }
    .post-title a:hover {
        color: #667eea;
    }
    .post-meta {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
        margin-bottom: 0.8rem;
        font-size: 0.85rem;
        color: #94a3b8;
    }
    .post-takeaways {
        font-size: 0.92rem;
        line-height: 1.6;
        margin: 0.8rem 0;
        padding-left: 1rem;
        border-left: 3px solid rgba(102, 126, 234, 0.7);
        color: #e2e8f0;
    }

    /* ── Badges ── */
    .badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .badge-high {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .badge-medium {
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .badge-low {
        background: rgba(34, 197, 94, 0.2);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .badge-category {
        background: rgba(102, 126, 234, 0.15);
        color: #93a5f6;
        border: 1px solid rgba(102, 126, 234, 0.25);
    }
    .badge-deal {
        background: rgba(236, 72, 153, 0.2);
        color: #f472b6;
        border: 1px solid rgba(236, 72, 153, 0.3);
        animation: pulse 2s infinite;
    }
    .badge-fresh {
        background: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    /* ── Engagement Stats ── */
    .engagement {
        display: flex;
        gap: 1.2rem;
        font-size: 0.85rem;
        color: #94a3b8;
    }

    /* ── Sidebar Styling ── */
    .sidebar-section {
        margin-bottom: 1.5rem;
    }

    /* ── Status Indicator ── */
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .status-idle { background: #6b7280; }
    .status-scraping { background: #3b82f6; animation: pulse 1s infinite; }
    .status-summarizing { background: #8b5cf6; animation: pulse 1s infinite; }
    .status-ready { background: #22c55e; }
    .status-error { background: #ef4444; }
</style>
""", unsafe_allow_html=True)


# ─── Data Loading ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_data():
    """Load posts + summaries from SQLite."""
    if not os.path.exists(config.DB_PATH):
        return pd.DataFrame()

    conn = sqlite3.connect(config.DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT
                p.post_id, p.title, p.author, p.category, p.date_posted,
                p.url, p.view_count, p.comment_count, p.scraped_at,
                s.title_ko, s.key_takeaways, s.target_category,
                s.actionable_deal, s.urgency_level, s.importance_score
            FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            ORDER BY s.importance_score DESC NULLS LAST, p.post_id DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()

    return df


def format_relative_date(date_str: str) -> str:
    """Return a user-friendly relative time string (e.g., '오늘', '3일 전', '2달 전')."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip()[:10], "%Y.%m.%d")
        diff = (datetime.now() - dt).days
        if diff <= 0:
            return "오늘"
        elif diff == 1:
            return "어제"
        elif diff < 7:
            return f"{diff}일 전"
        elif diff < 30:
            return f"{diff // 7}주 전"
        elif diff < 365:
            return f"{diff // 30}달 전"
        else:
            return f"{diff // 365}년 전"
    except Exception:
        return ""


# ─── Header ──────────────────────────────────────────────────────────────────

st.markdown("""
<div class="dashboard-header">
    <h1>✈️ 마일모아 인사이트</h1>
    <p>MileMoa Community Intelligence — 핵심 정보를 빠르게 파악하세요</p>
</div>
""", unsafe_allow_html=True)


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ Controls")

    # Sync button
    if st.button("🔄 Sync / Resume", use_container_width=True, type="primary"):
        with st.spinner("파이프라인 실행 중..."):
            try:
                result = subprocess.run(
                    [sys.executable, "run.py", "sync"],
                    capture_output=True, text=True, timeout=600,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                if result.returncode == 0:
                    st.success("✅ 동기화 완료!")
                    st.cache_data.clear()
                else:
                    st.error(f"❌ Error:\n{result.stderr[:500]}")
            except subprocess.TimeoutExpired:
                st.warning("⏳ 시간 초과 — 백그라운드에서 계속 실행 중일 수 있습니다.")
            except Exception as e:
                st.error(f"❌ {e}")

    st.divider()

    # Pipeline status
    checkpoint = load_checkpoint()
    phase = checkpoint.pipeline_phase
    status_class = {
        "IDLE": "idle", "SCRAPING": "scraping",
        "SUMMARIZING": "summarizing", "DASHBOARD_READY": "ready",
        "ERROR": "error",
    }.get(phase, "idle")
    st.markdown(
        f'<span class="status-dot status-{status_class}"></span> **상태**: `{phase}`',
        unsafe_allow_html=True,
    )
    if checkpoint.last_run_timestamp:
        st.caption(f"마지막 동기화: {checkpoint.last_run_timestamp[:19]}")

    st.divider()
    st.markdown("### 📅 Deal Freshness (유효기간)")

    # Date filter: default to 3 months as old deals are no longer valid
    date_preset = st.radio(
        "등록일 기준 필터",
        ["최근 3개월 (권장 - 유효 딜)", "최근 1개월", "최근 2주", "전체 기간"],
        index=0,
        help="마일모아 등록일(sort_index=regdate&order_type=desc) 기준 최신 딜을 필터링합니다. 3개월이 지난 딜은 만료된 것으로 간주합니다."
    )

    st.divider()
    st.markdown("### 🔍 Filters")

    # Category filter
    target_categories = ["All", "Credit Card", "Airline Miles", "Hotel Points", "Deal", "General Travel"]
    selected_categories = st.multiselect(
        "카테고리",
        target_categories[1:],
        default=[],
        placeholder="모든 카테고리",
    )

    # Urgency filter
    urgency_options = ["High", "Medium", "Low"]
    selected_urgency = st.multiselect(
        "긴급도",
        urgency_options,
        default=[],
        placeholder="모든 레벨",
    )

    # Min comments
    min_comments = st.slider("최소 댓글 수", 0, 100, 0)

    # Actionable deals only
    deals_only = st.checkbox("🏷️ 핫딜만 보기")

    # Search
    search_query = st.text_input("🔎 검색", placeholder="키워드 입력...")


# ─── Load & Filter Data ─────────────────────────────────────────────────────

df = load_data()

if df.empty:
    st.info("📭 데이터가 없습니다. 사이드바의 **Sync / Resume** 버튼을 눌러 데이터를 가져오세요.")
    st.stop()

# Apply filters
filtered = df.copy()

# Date freshness filter (strictly by post registration date)
now = datetime.now()
max_age = getattr(config, "MAX_DEAL_AGE_DAYS", 90)
if date_preset == "최근 3개월 (권장 - 유효 딜)":
    cutoff = (now - timedelta(days=max_age)).strftime("%Y.%m.%d")
    filtered = filtered[filtered["date_posted"] >= cutoff]
elif date_preset == "최근 1개월":
    cutoff = (now - timedelta(days=30)).strftime("%Y.%m.%d")
    filtered = filtered[filtered["date_posted"] >= cutoff]
elif date_preset == "최근 2주":
    cutoff = (now - timedelta(days=14)).strftime("%Y.%m.%d")
    filtered = filtered[filtered["date_posted"] >= cutoff]

if selected_categories:
    filtered = filtered[filtered["target_category"].isin(selected_categories)]

if selected_urgency:
    filtered = filtered[filtered["urgency_level"].isin(selected_urgency)]

if min_comments > 0:
    filtered = filtered[filtered["comment_count"] >= min_comments]

if deals_only:
    filtered = filtered[filtered["actionable_deal"] == 1]

if search_query:
    mask = (
        filtered["title"].str.contains(search_query, case=False, na=False)
        | filtered["title_ko"].str.contains(search_query, case=False, na=False)
    )
    filtered = filtered[mask]


# ─── Quick Stats ─────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

total_posts = len(filtered)
hot_deals = len(filtered[filtered["actionable_deal"] == 1])
high_urgency = len(filtered[filtered["urgency_level"] == "High"])
last_sync = checkpoint.last_run_timestamp[:10] if checkpoint.last_run_timestamp else "—"

with col1:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{total_posts}</div>
        <div class="stat-label">유효 포스트</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{hot_deals}</div>
        <div class="stat-label">현재 진행중인 핫딜</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{high_urgency}</div>
        <div class="stat-label">High 긴급도</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{last_sync}</div>
        <div class="stat-label">마지막 동기화</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("")  # spacer

if date_preset == "최근 3개월 (권장 - 유효 딜)":
    st.caption("✨ **정렬 및 필터 안내**: 등록일 최신순(`sort_index=regdate&order_type=desc`) 기준 최근 3개월 이내 유효한 딜만 표시 중입니다.")


# ─── View Toggle ─────────────────────────────────────────────────────────────

view_mode = st.radio(
    "보기 모드",
    ["📋 Card View", "📊 Table View"],
    horizontal=True,
    label_visibility="collapsed",
)


# ─── Card View ───────────────────────────────────────────────────────────────

if view_mode == "📋 Card View":
    if filtered.empty:
        st.info("🔍 필터 조건에 맞는 포스트가 없습니다.")
    else:
        # ── Sort control ──
        sort_col, count_col = st.columns([2, 3])
        with sort_col:
            sort_by = st.selectbox(
                "정렬 기준",
                ["최신순 📅", "오래된순 📅", "중요도순 ⭐"],
                index=0,
                label_visibility="collapsed",
            )
        with count_col:
            st.caption(f"총 {len(filtered)}개 포스트")

        # Apply sort
        if sort_by == "최신순 📅":
            sorted_filtered = filtered.sort_values("date_posted", ascending=False)
        elif sort_by == "오래된순 📅":
            sorted_filtered = filtered.sort_values("date_posted", ascending=True)
        else:  # 중요도순
            sorted_filtered = filtered.sort_values("importance_score", ascending=False)

        for _, row in sorted_filtered.head(50).iterrows():
            urgency = row.get("urgency_level", "Low") or "Low"
            badge_class = f"badge-{urgency.lower()}"
            urgency_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(urgency, "⚪")

            # Parse takeaways
            takeaways = []
            try:
                takeaways = json.loads(row.get("key_takeaways", "[]") or "[]")
            except (json.JSONDecodeError, TypeError):
                pass
            takeaways_html = "<br>".join(f"• {t}" for t in takeaways) if takeaways else ""

            target_cat = row.get("target_category", "") or ""
            is_deal = row.get("actionable_deal", 0) == 1
            score = row.get("importance_score", 0) or 0
            url = row.get("url", "#") or "#"
            title = row.get("title", "") or row.get("title_ko", "")

            # Relative date calculation
            date_posted = row.get("date_posted", "") or ""
            relative_time = format_relative_date(date_posted)
            time_display = f"{date_posted} ({relative_time})" if relative_time else (date_posted or "—")
            is_new = relative_time in ["오늘", "어제", "1일 전", "2일 전", "3일 전"]
            fresh_badge = '<span class="badge badge-fresh">✨ NEW</span>' if is_new else ""

            deal_badge = '<span class="badge badge-deal">🏷️ CURRENT DEAL</span>' if is_deal else ""

            card_html = f"""<div class="post-card">
<div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap;">
<span class="badge {badge_class}">{urgency_emoji} {urgency}</span>
<span class="badge badge-category">{target_cat}</span>
{deal_badge}
{fresh_badge}
<span style="margin-left: auto; font-size: 0.75rem; opacity: 0.5;">Score: {score:.0f}</span>
</div>
<div class="post-title"><a href="{url}" target="_blank">{title}</a></div>
<div class="post-meta">
<span>✍️ {row.get('author', '') or '—'}</span>
<span>📂 {row.get('category', '') or '—'}</span>
<span>📅 {time_display}</span>
</div>
<div class="post-takeaways">{takeaways_html}</div>
<div class="engagement">
<span>👀 {row.get('view_count', 0):,} views</span>
<span>💬 {row.get('comment_count', 0):,} comments</span>
</div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)


# ─── Table View ──────────────────────────────────────────────────────────────

elif view_mode == "📊 Table View":
    if filtered.empty:
        st.info("🔍 필터 조건에 맞는 포스트가 없습니다.")
    else:
        # Build display DataFrame — include url alongside title for link column
        display_cols = [
            "urgency_level", "title", "url", "target_category", "author",
            "comment_count", "view_count", "importance_score",
            "actionable_deal", "date_posted",
        ]
        available_cols = [c for c in display_cols if c in filtered.columns]
        display_df = filtered[available_cols].copy()

        # Rename for display
        rename_map = {
            "urgency_level": "긴급도",
            "title": "제목",
            "url": "링크",
            "target_category": "카테고리",
            "author": "작성자",
            "comment_count": "댓글",
            "view_count": "조회",
            "importance_score": "점수",
            "actionable_deal": "핫딜",
            "date_posted": "등록일",
        }
        display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})

        st.dataframe(
            display_df,
            use_container_width=True,
            height=600,
            hide_index=True,
            column_config={
                "제목": st.column_config.TextColumn("제목", width="large"),
                "링크": st.column_config.LinkColumn(
                    "🔗 원문 링크",
                    display_text="열기 ↗",
                    width="small",
                ),
                "점수": st.column_config.NumberColumn("점수", format="%.1f"),
                "핫딜": st.column_config.CheckboxColumn("핫딜"),
                "댓글": st.column_config.NumberColumn("댓글"),
                "조회": st.column_config.NumberColumn("조회"),
            },
        )


# ─── Footer ──────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption("마일모아 인사이트 • Built with Streamlit • Data refreshes every 30s")
