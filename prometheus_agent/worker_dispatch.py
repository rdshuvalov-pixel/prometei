#!/usr/bin/env python3
"""
Точка входа для WORKER_CMD: по JOB_TYPE запускает нужный скрипт в том же Python.

- script_crawl, (пусто), unknown → script_crawl.py
- watchlist → script_crawl.py (читает watchlist_targets.md)
- tier4_ashby, ashby_tier4 → ashby_crawler.py
- tier4_board_feeds, tier4_greenhouse_lever, board_feeds → board_feeds_tier4.py
- score_vacancies, vacancy_score, evaluate, scoring → script_score_stub.py (заглушка счётчика)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    job_type = (os.environ.get("JOB_TYPE") or "script_crawl").strip().lower()
    base = Path(__file__).resolve().parent
    py = sys.executable
    if job_type in ("full_search", "fullrun", "search"):
        script = base / "full_search.py"
    elif job_type in ("keyword_search", "keyword", "pm_search"):
        script = base / "keyword_search.py"
    elif job_type in ("tier4_ashby", "ashby_tier4", "ashby"):
        script = base / "ashby_crawler.py"
    elif job_type in ("tier4_board_feeds", "tier4_greenhouse_lever", "board_feeds"):
        script = base / "board_feeds_tier4.py"
    elif job_type in (
        "score_vacancies",
        "vacancy_score",
        "evaluate",
        "scoring",
    ):
        script = base / "script_score_stub.py"
    else:
        script = base / "script_crawl.py"
    if not script.is_file():
        print(f"ERROR: нет файла {script}", file=sys.stderr)
        return 2
    return subprocess.call([py, str(script)])


if __name__ == "__main__":
    raise SystemExit(main())
