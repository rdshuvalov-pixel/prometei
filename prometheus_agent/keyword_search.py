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
import subprocess
import sys
import time
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
    # Backward compat: treat the current job_run_id as search/run id.
    return (os.environ.get("SEARCH_ID") or os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or "").strip()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _step_timeout_sec() -> int:
    raw = (os.environ.get("SEARCH_STEP_TIMEOUT_SEC") or "").strip()
    try:
        n = int(raw) if raw else 0
    except ValueError:
        n = 0
    return max(0, min(n, 6 * 3600))


def _append_job_log(sb: Client, job_id: str, text: str) -> None:
    if not job_id:
        return
    try:
        res = sb.table("job_runs").select("log").eq("id", job_id).limit(1).execute()
        rows = getattr(res, "data", None) or []
        prev = (rows[0].get("log") if rows else "") or ""
        blob = (prev + text)[-120_000:]
        sb.table("job_runs").update({"log": blob}).eq("id", job_id).execute()
    except Exception:
        return


def _set_job_counters(sb: Client, job_id: str, counters: dict) -> None:
    if not job_id:
        return
    try:
        sb.table("job_runs").update({"counters": counters}).eq("id", job_id).execute()
    except Exception:
        return


def main() -> None:
    job_id = (os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or "").strip()
    sid = _search_id()
    if sid and not os.environ.get("SEARCH_ID"):
        os.environ["SEARCH_ID"] = sid

    keyword = (os.environ.get("KEYWORD") or "Product Manager").strip()
    counters: dict = {
        "job_type": "keyword_search",
        "keyword": keyword,
        "job_id": job_id,
        "run_id": sid or None,
        "started_at": _utc_iso(),
    }
    timeout_sec = _step_timeout_sec()
    sb = _client()
    _set_job_counters(sb, job_id, counters)
    _append_job_log(sb, job_id, f"[{_utc_iso()}] keyword_search start run_id={sid or '—'} keyword={keyword!r}\n")

    if not sid:
        # Still allow running lanes; they'll just skip DB logging where search_id is required.
        counters["warn"] = "missing run id (SEARCH_ID/JOB_ID)"

    from pathlib import Path
    base = Path(__file__).resolve().parent
    steps = [
        ("search", "tier4_board_feeds", base / "board_feeds_tier4.py"),
        ("search", "tier4_ashby", base / "ashby_crawler.py"),
        ("search", "playwright_search", base / "playwright_search.py"),
    ]

    for step, substep, script in steps:
        _append_job_log(sb, job_id, f"[{_utc_iso()}] step={step} substep={substep} start\n")
        counters["current_substep"] = substep
        counters["current_substep_started_at"] = _utc_iso()
        _set_job_counters(sb, job_id, counters)
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                check=False,
                capture_output=True,
                text=True,
                timeout=(timeout_sec or None),
                env={
                    **os.environ,
                    "JOB_TYPE": substep,
                    "WORKER_JOB_ID": job_id,
                    "JOB_ID": job_id,
                    "SEARCH_ID": sid,
                },
            )
        except subprocess.TimeoutExpired:
            _append_job_log(sb, job_id, f"[{_utc_iso()}] substep={substep} TIMEOUT after {timeout_sec}s\n")
            raise SystemExit(124)
        elapsed_ms = int((time.time() - t0) * 1000)
        child_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        ok = proc.returncode == 0
        step_counters = {"exit_code": proc.returncode, "elapsed_ms": elapsed_ms, "stdout_chars": len(child_out)}
        counters.setdefault("steps", []).append({**step_counters, "substep": substep})
        counters["current_substep_finished_at"] = _utc_iso()
        _set_job_counters(sb, job_id, counters)
        _append_job_log(
            sb,
            job_id,
            f"[{_utc_iso()}] substep={substep} done exit={proc.returncode} elapsed_ms={elapsed_ms} out_tail={child_out[-600:].replace(chr(0), '')}\n",
        )
        if not ok:
            raise SystemExit(proc.returncode)

    counters["finished_at"] = _utc_iso()
    counters.pop("current_substep", None)
    counters.pop("current_substep_started_at", None)
    counters.pop("current_substep_finished_at", None)
    _set_job_counters(sb, job_id, counters)
    _append_job_log(sb, job_id, f"[{_utc_iso()}] keyword_search done\n")
    print(_SUMMARY_MARKER)
    print(json.dumps(counters, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

