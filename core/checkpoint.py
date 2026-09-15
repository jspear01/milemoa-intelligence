"""
Checkpoint Engine — Atomic state persistence for the MileMoa pipeline.

State is stored in `.state/checkpoint.json` and a human-readable summary
is written to `STATUS.md` at the project root.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import config


class PipelinePhase(str, Enum):
    IDLE = "IDLE"
    SCRAPING = "SCRAPING"
    SUMMARIZING = "SUMMARIZING"
    DASHBOARD_READY = "DASHBOARD_READY"
    ERROR = "ERROR"


@dataclass
class CheckpointState:
    last_scraped_post_id: Optional[str] = None
    last_scraped_page: int = 0
    last_run_timestamp: Optional[str] = None
    processed_post_ids: list = field(default_factory=list)
    pipeline_phase: str = PipelinePhase.IDLE.value
    error_message: Optional[str] = None
    total_posts_scraped: int = 0
    total_posts_summarized: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointState":
        # Handle enum conversion
        phase = data.get("pipeline_phase", PipelinePhase.IDLE.value)
        if isinstance(phase, PipelinePhase):
            phase = phase.value
        data["pipeline_phase"] = phase
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def _ensure_state_dir():
    """Create the .state directory if it doesn't exist."""
    os.makedirs(config.STATE_DIR, exist_ok=True)


def load_checkpoint() -> CheckpointState:
    """
    Load checkpoint from disk. Returns a default state if the file
    doesn't exist or is corrupt.
    """
    _ensure_state_dir()
    if not os.path.exists(config.CHECKPOINT_FILE):
        return CheckpointState()
    try:
        with open(config.CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CheckpointState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"⚠️  Checkpoint file corrupt, starting fresh: {e}")
        return CheckpointState()


def save_checkpoint(state: CheckpointState):
    """
    Atomically write checkpoint to disk using temp file + os.replace
    to prevent corruption if interrupted mid-write.
    """
    _ensure_state_dir()
    data = state.to_dict()
    data["_saved_at"] = datetime.now(timezone.utc).isoformat()

    # Write to temp file first, then atomic replace
    fd, tmp_path = tempfile.mkstemp(
        dir=config.STATE_DIR, suffix=".tmp", prefix="ckpt_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, config.CHECKPOINT_FILE)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def update_status_md(state: CheckpointState):
    """
    Write a human-/agent-readable STATUS.md summarizing the current
    pipeline state.
    """
    phase_emoji = {
        PipelinePhase.IDLE.value: "⏸️",
        PipelinePhase.SCRAPING.value: "🔄",
        PipelinePhase.SUMMARIZING.value: "🧠",
        PipelinePhase.DASHBOARD_READY.value: "✅",
        PipelinePhase.ERROR.value: "❌",
    }
    emoji = phase_emoji.get(state.pipeline_phase, "❓")

    content = f"""# MileMoa Pipeline Status

| Field | Value |
|-------|-------|
| **Status** | {emoji} `{state.pipeline_phase}` |
| **Last Run** | {state.last_run_timestamp or "Never"} |
| **Last Scraped Post ID** | {state.last_scraped_post_id or "None"} |
| **Last Scraped Page** | {state.last_scraped_page} |
| **Total Posts Scraped** | {state.total_posts_scraped} |
| **Total Posts Summarized** | {state.total_posts_summarized} |
| **Processed IDs Count** | {len(state.processed_post_ids)} |

"""
    if state.error_message:
        content += f"""## ❌ Last Error

```
{state.error_message}
```

"""

    content += f"""## Quick Reference

- **Checkpoint file**: `.state/checkpoint.json`
- **Database**: `data/milemoa.db`
- **Dashboard**: `streamlit run ui/app.py`
- **Sync**: `python run.py sync`

---
*Auto-generated at {datetime.now(timezone.utc).isoformat()}*
"""

    with open(config.STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(content)
