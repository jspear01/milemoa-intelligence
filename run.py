#!/usr/bin/env python3
"""
MileMoa Pipeline CLI — Entry point for scraping, summarizing, and dashboard.

Usage:
    python run.py sync            # Full pipeline: scrape + summarize
    python run.py scrape          # Scrape only
    python run.py summarize       # Summarize only (must have data)
    python run.py dashboard       # Launch Streamlit dashboard
    python run.py reset           # Reset checkpoint to clean state
    python run.py status          # Show current pipeline status
"""
from __future__ import annotations

import os
import subprocess
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command in ("sync", "full"):
        from core.harness import run_pipeline
        run_pipeline(mode="full")

    elif command == "scrape":
        from core.harness import run_pipeline
        run_pipeline(mode="scrape")

    elif command == "summarize":
        from core.harness import run_pipeline
        run_pipeline(mode="summarize")

    elif command == "dashboard":
        ui_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ui", "app.py"
        )
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", ui_path,
            "--server.headless", "true",
        ])

    elif command in ("reset", "reset-checkpoint"):
        from core.harness import reset_checkpoint
        reset_checkpoint()

    elif command == "status":
        from core.checkpoint import load_checkpoint
        ckpt = load_checkpoint()
        print(f"""
╔══════════════════════════════════════════╗
║     MileMoa Pipeline Status              ║
╠══════════════════════════════════════════╣
║  Phase:              {ckpt.pipeline_phase:<20s}║
║  Last Run:           {(ckpt.last_run_timestamp or 'Never')[:20]:<20s}║
║  Last Scraped ID:    {(ckpt.last_scraped_post_id or 'None'):<20s}║
║  Last Page:          {str(ckpt.last_scraped_page):<20s}║
║  Total Scraped:      {str(ckpt.total_posts_scraped):<20s}║
║  Total Summarized:   {str(ckpt.total_posts_summarized):<20s}║
║  Processed IDs:      {str(len(ckpt.processed_post_ids)):<20s}║
╚══════════════════════════════════════════╝
""")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
