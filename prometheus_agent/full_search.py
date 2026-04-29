#!/usr/bin/env python3
"""
Единый «поиск в целом» (single job):
  - больше не использует funnel-таблицы search_runs/search_steps (они удалены)
  - последовательно запускает: keyword_search (который сам запускает board_feeds/ashby/playwright)

Run identity: используем JOB_ID/WORKER_JOB_ID (job_runs.id) как run id и прокидываем
в дочерние скрипты через SEARCH_ID для совместимости с логами/кандидатами.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from supabase import Client, create_client

_SUMMARY_MARKER = "--- сводка ---"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        raise SystemExit(2)
    return create_client(url, key)


def _parse_child_summary_json(stdout: str, stderr: str) -> dict | None:
    text = f"{stdout or ''}\n{stderr or ''}"
    if _SUMMARY_MARKER not in text:
        return None
    tail = text.rsplit(_SUMMARY_MARKER, 1)[-1].strip()
    start = tail.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    for i in range(start, len(tail)):
        c = tail[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    try:
        data = json.loads(tail[start:end])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _job_id() -> str:
    return (os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or "").strip()


def main() -> None:
    job_run_id = _job_id()
    if not job_run_id:
        print("ERROR: missing WORKER_JOB_ID/JOB_ID", file=sys.stderr)
        raise SystemExit(2)

    # Compatibility: downstream scripts still log candidates/targets under SEARCH_ID.
    os.environ["SEARCH_ID"] = job_run_id

    overall: dict = {
        "job_type": "full_search",
        "job_run_id": job_run_id,
        "started_at": _utc_iso(),
    }

    try:
        # Delegate to keyword_search as the orchestrator of lanes.
        script = _base_dir() / "keyword_search.py"
        if not script.is_file():
            raise RuntimeError("missing keyword_search.py")
        import subprocess  # local import to keep module lean

        proc = subprocess.run(
            [sys.executable, str(script)],
            check=False,
            timeout=int(os.environ.get("JOB_TIMEOUT_SEC", "3600")),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "WORKER_JOB_ID": job_run_id,
                "JOB_ID": job_run_id,
                "JOB_TYPE": "keyword_search",
                "SEARCH_ID": job_run_id,
            },
        )
        child = _parse_child_summary_json(proc.stdout or "", proc.stderr or "") or {}
        overall["child"] = {**child, "exit_code": proc.returncode}
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
        overall["finished_at"] = _utc_iso()
    except Exception as e:  # noqa: BLE001
        overall["finished_at"] = _utc_iso()
        overall["error"] = str(e)
        raise
    finally:
        print(_SUMMARY_MARKER)
        print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

