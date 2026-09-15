# ✈️ 마일모아 인사이트 (MileMoa Community Intelligence)

마일모아(MileMoa) 커뮤니티의 최신 등록글을 자동으로 수집하여 중요도를 평가하고 핵심 요약과 핫딜 정보를 한눈에 제공하는 인터랙티브 대시보드입니다.

![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Status](https://img.shields.io/badge/Status-Active-success.svg)

---

## 주요 기능

- 📅 **등록일 최신순 정렬 (`sort_index=regdate&order_type=desc`)**: 오래된 끌올 글이 아닌 실제 최근 작성된 글을 우선 수집합니다.
- ⏱️ **3개월 유효기간 필터 (Deal Freshness)**: 만료된 옛날 프로모션을 걸러내고 최근 3개월 이내 유효한 딜만 표시합니다.
- 🎯 **커뮤니티 중요도 스코어링 (0~100점)**: 조회수, 댓글 수, 카드/마일/항공/호텔 핵심 키워드를 기반으로 중요도를 산출합니다.
- 🏷️ **핫딜 자동 감지 (CURRENT DEAL)**: 진행 중인 카드 사인업 보너스, 타겟 오퍼, 발권 꿀팁을 자동으로 분류합니다.
- 🔄 **체크포인트 & 자동 동기화**: 중단된 지점부터 이어서 수집하는 하네스 엔진 및 GitHub Actions를 통한 정기 자동 업데이트를 지원합니다.

---

## 프로젝트 구조

```
├── config.py                 # 전역 설정 (URL, 헤더, 키워드, 스코어링 기준)
├── run.py                    # CLI 실행 진입점 (sync, scrape, summarize, status, reset)
├── core/
│   ├── checkpoint.py         # 상태 저장/복구 (원자적 쓰기)
│   └── harness.py            # 파이프라인 오케스트레이터
├── pipeline/
│   ├── scraper.py            # HTML 스크래퍼 (페이지네이션, 백오프, 날짜 컷오프)
│   └── summarizer.py         # 중요도 평가 및 핵심 요약
├── ui/
│   └── app.py                # Streamlit 인터랙티브 대시보드
├── data/
│   └── milemoa.db            # SQLite 데이터베이스 (posts, summaries 테이블)
├── .state/
│   └── checkpoint.json       # 파이프라인 체크포인트 상태 파일
├── .streamlit/
│   └── config.toml           # Streamlit 테마 설정
└── .github/workflows/
    └── scrape.yml            # GitHub Actions 정기 스크래핑 워크플로우
```

---

## 로컬 실행 방법

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 대시보드 실행
```bash
streamlit run ui/app.py
```
브라우저에서 `http://localhost:8501`로 접속합니다.

### 3. CLI를 통한 수동 동기화
```bash
python run.py sync
```

---

## Streamlit Cloud 배포 안내

1. GitHub에 이 저장소를 Push합니다.
2. [share.streamlit.io](https://share.streamlit.io)에 접속하여 로그인합니다.
3. **New app** 버튼을 클릭하고 다음 정보를 입력합니다:
   - **Repository**: `<본인-깃허브-계정>/<저장소-이름>`
   - **Branch**: `main`
   - **Main file path**: `ui/app.py`
4. **Deploy!** 버튼을 누르면 무료 클라우드 배포가 완료됩니다.
