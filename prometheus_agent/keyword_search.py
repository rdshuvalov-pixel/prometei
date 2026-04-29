#!/usr/bin/env python3
"""
keyword_search: выполняет поиск по ключевому слову (по умолчанию "Product Manager")
по всем доступным источникам, которые можно обойти без браузера:
  - Ashby (ASHBY_SLUGS через posting-api)
  - Board feeds (Greenhouse/Lever/Workable + RemoteOK/Remotive) — существующий скрипт

JS/SPA площадки будут добавлены отдельным lane через Playwright.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from supabase import Client, create_client

_SUMMARY_MARKER = "--- сводка ---"


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        raise SystemExit(2)
    return create_client(url, key)


def _search_id() -> str:
    return (os.environ.get("SEARCH_ID") or "").strip()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step_start(sb: Client, *, search_id: str, step: str, substep: str) -> str:
    res = sb.table("search_steps").insert(
        {"search_id": search_id, "step": step, "substep": substep, "status": "running"},
    ).execute()
    data = getattr(res, "data", None)
    row = data[0] if isinstance(data, list) and data else (data or {})
    sid = str((row or {}).get("id") or "").strip()
    if not sid:
        raise RuntimeError("failed to create search_steps row")
    return sid


def _step_finish(sb: Client, *, step_id: str, status: str, counters: dict, error: str | None = None) -> None:
    patch: dict = {"status": status, "finished_at": _utc_iso(), "counters": counters}
    if error:
        patch["error"] = error[:8000]
    sb.table("search_steps").update(patch).eq("id", step_id).execute()


def main() -> None:
    # MVP: reuse existing implementations; focus on correctly writing funnel artifacts.
    job_id = (os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or "").strip()
    sid = _search_id()
    sb = _client()

    keyword = (os.environ.get("KEYWORD") or "Product Manager").strip()
    counters: dict = {
        "job_type": "keyword_search",
        "keyword": keyword,
        "job_id": job_id,
        "search_id": sid or None,
        "started_at": _utc_iso(),
    }

    if not sid:
        # Without search_id we cannot write funnel tables; still exit cleanly with summary.
        print(_SUMMARY_MARKER)
        print(json.dumps({**counters, "warn": "missing SEARCH_ID"}, ensure_ascii=False, indent=2))
        return

    # For now: run board feeds and ashby as-is, but under explicit search_steps.
    import subprocess
    import time
    from pathlib import Path

    base = Path(__file__).resolve().parent
    steps = [
        ("search", "tier4_board_feeds", base / "board_feeds_tier4.py"),
        ("search", "tier4_ashby", base / "ashby_crawler.py"),
        ("search", "playwright_search", base / "playwright_search.py"),
    ]

    for step, substep, script in steps:
        step_row_id = _step_start(sb, search_id=sid, step=step, substep=substep)
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(script)],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "JOB_TYPE": substep,
                "WORKER_JOB_ID": job_id,
                "JOB_ID": job_id,
                "SEARCH_ID": sid,
            },
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        child_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        ok = proc.returncode == 0
        step_counters = {"exit_code": proc.returncode, "elapsed_ms": elapsed_ms, "stdout_chars": len(child_out)}
        _step_finish(
            sb,
            step_id=step_row_id,
            status="done" if ok else "failed",
            counters=step_counters,
            error=None if ok else child_out[-8000:],
        )
        if not ok:
            raise SystemExit(proc.returncode)

    counters["finished_at"] = _utc_iso()
    print(_SUMMARY_MARKER)
    print(json.dumps(counters, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

