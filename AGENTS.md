# MileMoa Community Intelligence Pipeline — Agent Contract

> **MANDATORY**: Before executing ANY task in this project, read `.state/checkpoint.json`
> and `STATUS.md` to understand the current pipeline state.

## Project Overview

This project scrapes posts from [MileMoa](https://www.milemoa.com/bbs/board),
scores them by community importance, generates extractive summaries, and displays
results on an interactive Streamlit dashboard. A checkpoint/harness system enables
pause-and-resume across sessions.

## Architecture

```
┌──────────────┐     ┌────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Checkpoint  │────▶│    Scraper      │────▶│   Summarizer     │────▶│  Dashboard   │
│   Engine     │     │  (incremental)  │     │ (score + extract)│     │  (Streamlit) │
└──────────────┘     └────────────────┘     └──────────────────┘     └─────────────┘
       │                     │                       │
       ▼                     ▼                       ▼
 .state/checkpoint.json   data/milemoa.db       data/milemoa.db
```

## File Layout

| Path | Purpose |
|------|---------|
| `config.py` | All configuration: URLs, headers, keywords, thresholds |
| `core/checkpoint.py` | Atomic checkpoint read/write + STATUS.md generation |
| `core/harness.py` | Pipeline orchestrator (scrape → score → summarize) |
| `pipeline/scraper.py` | HTML scraper with pagination, backoff, SQLite writes |
| `pipeline/summarizer.py` | Importance scoring + extractive summarization |
| `ui/app.py` | Streamlit dashboard with filters, stats, sync button |
| `run.py` | CLI entry point |
| `.state/checkpoint.json` | Pipeline state persistence (atomic writes) |
| `STATUS.md` | Human-readable pipeline status |
| `data/milemoa.db` | SQLite database with `posts` and `summaries` tables |

## Database Schema

### `posts` table
| Column | Type | Description |
|--------|------|-------------|
| `post_id` | TEXT PK | MileMoa document ID |
| `title` | TEXT | Post title |
| `author` | TEXT | Author username |
| `category` | TEXT | Board category tag |
| `date_posted` | TEXT | ISO 8601 or YYYY.MM.DD |
| `url` | TEXT | Full URL to the post |
| `view_count` | INTEGER | Number of views |
| `comment_count` | INTEGER | Number of comments |
| `body_text` | TEXT | Full post body text |
| `scraped_at` | TEXT | When this post was scraped |

### `summaries` table
| Column | Type | Description |
|--------|------|-------------|
| `post_id` | TEXT PK/FK | References posts(post_id) |
| `title_ko` | TEXT | Korean title |
| `key_takeaways` | TEXT | JSON array of 3 bullet points |
| `target_category` | TEXT | Credit Card / Airline Miles / Hotel Points / Deal / General Travel |
| `actionable_deal` | INTEGER | 1 if contains an actionable deal |
| `urgency_level` | TEXT | High / Medium / Low |
| `importance_score` | REAL | 0–100 importance score |
| `summarized_at` | TEXT | When summary was generated |

## Checkpoint Contract

The `.state/checkpoint.json` file contains:
```json
{
  "last_scraped_post_id": "12492904",
  "last_scraped_page": 5,
  "last_run_timestamp": "2026-09-14T01:00:00+00:00",
  "processed_post_ids": ["12492904", "12492890", ...],
  "pipeline_phase": "DASHBOARD_READY",
  "total_posts_scraped": 147,
  "total_posts_summarized": 147
}
```

**Pipeline Phases**: `IDLE` → `SCRAPING` → `SUMMARIZING` → `DASHBOARD_READY` | `ERROR`

### Resumption Rules
1. On `IDLE` or `DASHBOARD_READY`: Start fresh incremental scrape
2. On `SCRAPING`: Resume from `last_scraped_page`, skip `processed_post_ids`
3. On `SUMMARIZING`: Resume summarization of unsummarized posts
4. On `ERROR`: Log warning, attempt retry from last good state

## Agent Workflows

### `/sync` — Resume Ingestion
```bash
python run.py sync
```
Runs the full pipeline: load checkpoint → incremental scrape → score → summarize → update checkpoint.

### `/dashboard` — Launch UI
```bash
python run.py dashboard
# or: streamlit run ui/app.py
```

### `/reset-checkpoint` — Clean Slate
```bash
python run.py reset
```
Resets `.state/checkpoint.json` to default values. Does NOT delete the database.

### `/status` — Check Pipeline State
```bash
python run.py status
```

## Development Notes

- **Rate Limiting**: 1.0–2.0s random delay between detail page fetches, exponential backoff on 429/503
- **Atomic Writes**: Checkpoint uses `tempfile` + `os.replace` to prevent corruption
- **LLM Hook**: `pipeline/summarizer.py` has `summarize_post_llm()` placeholder for future LLM integration
- **Anti-Bot**: Uses `https://www.milemoa.com/bbs/board?page=N` URL pattern with realistic browser headers
