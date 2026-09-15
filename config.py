"""
MileMoa Pipeline Configuration
"""
import os

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(PROJECT_ROOT, ".state")
CHECKPOINT_FILE = os.path.join(STATE_DIR, "checkpoint.json")
STATUS_FILE = os.path.join(PROJECT_ROOT, "STATUS.md")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "milemoa.db")

# ─── Scraper ──────────────────────────────────────────────────────────────────
BASE_URL = "https://www.milemoa.com/bbs/board"
BOARD_QUERY_PARAMS = "sort_index=regdate&order_type=desc"  # Chronological order by regdate
MAX_DEAL_AGE_DAYS = 90           # 3 months: filter out deals older than 90 days
MAX_PAGES_FIRST_RUN = 5          # Pages to scrape on first (cold) run
SCRAPE_DELAY_MIN = 1.0           # Min seconds between detail-page fetches
SCRAPE_DELAY_MAX = 2.0           # Max seconds between detail-page fetches
BACKOFF_BASE = 2.0               # Exponential backoff base for 429/503
BACKOFF_MAX_RETRIES = 5          # Max retries per request

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

# ─── Summarizer: Importance Scoring ──────────────────────────────────────────
HIGH_VALUE_KEYWORDS = [
    # Credit cards
    "사인업 보너스", "사인업보너스", "sign-up bonus", "signup bonus",
    "타겟오퍼", "타겟 오퍼", "target offer",
    "체이스", "아멕스", "amex", "chase", "시티", "citi",
    "연회비", "annual fee", "AF 면제",
    # Airline / Miles
    "역대급", "마일리지 개악", "마일리지 개편", "개악", "개편",
    "발권 후기", "발권후기", "비즈니스 클래스", "퍼스트 클래스",
    "럭셔리", "대한항공", "아시아나", "유나이티드", "델타",
    # Hotels
    "IHG", "힐튼", "하얏트", "매리어트", "리츠칼튼",
    "호텔 프로모션", "무료 숙박",
    # Deals
    "핫딜", "hot deal", "루머", "rumor",
    "한정", "마감임박", "긴급",
    # General high-value
    "꿀팁", "필독", "총정리", "비교분석",
]

# Category keywords → target_category mapping
CATEGORY_KEYWORDS = {
    "Credit Card": ["카드", "체이스", "아멕스", "시티", "사인업", "연회비", "credit card"],
    "Airline Miles": ["마일", "항공", "발권", "좌석", "비즈니스", "퍼스트", "airline", "miles"],
    "Hotel Points": ["호텔", "힐튼", "하얏트", "매리어트", "IHG", "리츠", "숙박", "hotel"],
    "Deal": ["핫딜", "딜", "할인", "프로모션", "쿠폰", "deal", "hot deal"],
    "General Travel": ["여행", "후기", "공항", "라운지", "travel"],
}

# Scoring thresholds
URGENCY_HIGH_THRESHOLD = 70
URGENCY_MEDIUM_THRESHOLD = 40

# Board categories that get a scoring boost
HIGH_VALUE_CATEGORIES = ["정보-카드", "정보-항공", "정보-호텔", "핫딜", "뉴스"]
