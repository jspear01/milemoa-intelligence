"""
Pipeline Harness — Orchestrates scrape → score → summarize flow
with checkpoint persistence at each step boundary.
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone

from core.checkpoint import (
    CheckpointState,
    PipelinePhase,
    load_checkpoint,
    save_checkpoint,
    update_status_md,
)
from pipeline import scraper, summarizer


def run_pipeline(mode: str = "full", progress_callback=None):
    """
    Execute the pipeline with checkpoint-based resumption.

    Args:
        mode: "full" | "scrape" | "summarize"
        progress_callback: Optional callable(message: str) for UI updates
    """
    def _log(msg: str):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    checkpoint = load_checkpoint()

    # If we're resuming from an ERROR state, log it and allow retry
    if checkpoint.pipeline_phase == PipelinePhase.ERROR.value:
        _log(f"⚠️  Resuming from ERROR state. Last error: {checkpoint.error_message}")
        _log("   Attempting to continue pipeline...")

    try:
        # ── Phase 1: Scraping ────────────────────────────────────────────
        if mode in ("full", "scrape"):
            _log("🔄 Phase 1: Scraping MileMoa posts...")
            checkpoint.pipeline_phase = PipelinePhase.SCRAPING.value
            checkpoint.last_run_timestamp = datetime.now(timezone.utc).isoformat()
            save_checkpoint(checkpoint)
            update_status_md(checkpoint)

            checkpoint = scraper.scrape_incremental(
                checkpoint, progress_callback=_log
            )

            _log(f"   ✓ Scraping complete. {checkpoint.total_posts_scraped} total posts in DB.")
            save_checkpoint(checkpoint)
            update_status_md(checkpoint)

        # ── Phase 2: Scoring & Summarization ─────────────────────────────
        if mode in ("full", "summarize"):
            _log("🧠 Phase 2: Scoring and summarizing posts...")
            checkpoint.pipeline_phase = PipelinePhase.SUMMARIZING.value
            save_checkpoint(checkpoint)
            update_status_md(checkpoint)

            checkpoint = summarizer.score_and_summarize(
                checkpoint, progress_callback=_log
            )

            _log(f"   ✓ Summarization complete. {checkpoint.total_posts_summarized} posts summarized.")
            save_checkpoint(checkpoint)
            update_status_md(checkpoint)

        # ── Done ─────────────────────────────────────────────────────────
        checkpoint.pipeline_phase = PipelinePhase.DASHBOARD_READY.value
        checkpoint.error_message = None
        save_checkpoint(checkpoint)
        update_status_md(checkpoint)
        _log("✅ Pipeline complete! Dashboard data is ready.")

    except KeyboardInterrupt:
        _log("⏹️  Pipeline interrupted by user. Checkpoint saved.")
        checkpoint.pipeline_phase = PipelinePhase.IDLE.value
        save_checkpoint(checkpoint)
        update_status_md(checkpoint)
        raise

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _log(f"❌ Pipeline error: {e}")
        checkpoint.pipeline_phase = PipelinePhase.ERROR.value
        checkpoint.error_message = error_msg
        save_checkpoint(checkpoint)
        update_status_md(checkpoint)
        raise

    return checkpoint


def reset_checkpoint():
    """Reset checkpoint to a clean state."""
    state = CheckpointState()
    save_checkpoint(state)
    update_status_md(state)
    print("🗑️  Checkpoint reset to clean state.")
    return state
