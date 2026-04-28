#!/usr/bin/env python3
"""
Единый «поиск в целом» (single job):
  - создаёт/использует search_runs.id (search_id)
  - пишет шаги в search_steps + агрегаты в counters job_runs (через stdout summary)
  - последовательно запускает: script_crawl → tier4_board_feeds → tier4_ashby

Воркера запускают через worker/poll_jobs.py, который выставляет env:
  WORKER_JOB_ID / JOB_ID / JOB_TYPE

Опционально принимает search_id из:
  - env SEARCH_ID
  - job_runs.payload.search_id (если payload есть)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
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


def _read_job_payload(sb: Client, job_run_id: str) -> dict:
    try:
        res = sb.table("job_runs").select("payload").eq("id", job_run_id).limit(1).execute()
    except Exception:
        return {}
    rows = getattr(res, "data", None) or []
    payload = rows[0].get("payload") if rows else None
    return payload if isinstance(payload, dict) else {}


def _ensure_search_run(sb: Client, *, job_run_id: str, source: str | None) -> str:
    # 1) env override
    env_id = (os.environ.get("SEARCH_ID") or "").strip()
    if env_id:
        return env_id
    # 2) payload.search_id
    payload = _read_job_payload(sb, job_run_id)
    pid = str(payload.get("search_id") or "").strip()
    if pid:
        return pid
    # 3) create new row
    ins = sb.table("search_runs").insert(
        {
            "status": "running",
            "source": source,
            "job_run_id": job_run_id,
            "params": {"created_by": "full_search"},
        },
    ).execute()
    data = getattr(ins, "data", None)
    row = data[0] if isinstance(data, list) and data else (data or {})
    sid = str((row or {}).get("id") or "").strip()
    if not sid:
        raise RuntimeError("failed to create search_runs row")
    return sid


def _search_status(sb: Client, search_id: str, status: str, error: str | None = None) -> None:
    patch: dict = {"status": status}
    if error:
        patch["params"] = {"error": error[:4000]}
    sb.table("search_runs").update(patch).eq("id", search_id).execute()


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


def _step_finish(
    sb: Client,
    *,
    step_id: str,
    status: str,
    counters: dict | None = None,
    error: str | None = None,
) -> None:
    patch: dict = {"status": status, "finished_at": _utc_iso()}
    if counters is not None:
        patch["counters"] = counters
    if error:
        patch["error"] = error[:8000]
    sb.table("search_steps").update(patch).eq("id", step_id).execute()


def _run_child(script: Path, *, env: dict[str, str], timeout_sec: int) -> tuple[int, str, str, dict]:
    proc = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        timeout=timeout_sec,
        capture_output=True,
        text=True,
        env=env,
    )
    child = _parse_child_summary_json(proc.stdout or "", proc.stderr or "") or {}
    return proc.returncode, proc.stdout or "", proc.stderr or "", child


def main() -> None:
    job_run_id = (os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or "").strip()
    if not job_run_id:
        print("ERROR: missing WORKER_JOB_ID/JOB_ID", file=sys.stderr)
        raise SystemExit(2)

    sb = _client()

    payload = _read_job_payload(sb, job_run_id)
    source = str(payload.get("source") or os.environ.get("SEARCH_SOURCE") or "").strip() or None

    search_id = _ensure_search_run(sb, job_run_id=job_run_id, source=source)
    os.environ["SEARCH_ID"] = search_id

    timeout = int(os.environ.get("JOB_TIMEOUT_SEC", "3600"))

    scripts = [
        ("extract", "script_crawl", _base_dir() / "script_crawl.py"),
        ("extract", "tier4_board_feeds", _base_dir() / "board_feeds_tier4.py"),
        ("extract", "tier4_ashby", _base_dir() / "ashby_crawler.py"),
    ]

    overall: dict = {
        "job_type": "full_search",
        "search_id": search_id,
        "started_at": _utc_iso(),
        "steps": [],
    }

    _search_status(sb, search_id, "running")

    try:
        for step, substep, script in scripts:
            step_row_id = _step_start(sb, search_id=search_id, step=step, substep=substep)
            child_env = {
                **os.environ,
                "WORKER_JOB_ID": job_run_id,
                "JOB_ID": job_run_id,
                "JOB_TYPE": substep,
                "SEARCH_ID": search_id,
                "SEARCH_SOURCE": source or "",
            }
            t0 = time.time()
            rc, out, err, child_counters = _run_child(script, env=child_env, timeout_sec=timeout)
            elapsed_ms = int((time.time() - t0) * 1000)
            child_counters = {**child_counters, "exit_code": rc, "elapsed_ms": elapsed_ms}

            if rc == 0:
                _step_finish(sb, step_id=step_row_id, status="done", counters=child_counters)
            else:
                _step_finish(
                    sb,
                    step_id=step_row_id,
                    status="failed",
                    counters=child_counters,
                    error=(err or out)[-8000:],
                )
                raise RuntimeError(f"{substep} failed exit={rc}")

            overall["steps"].append(
                {
                    "step": step,
                    "substep": substep,
                    "elapsed_ms": elapsed_ms,
                    "counters": child_counters,
                },
            )

        overall["finished_at"] = _utc_iso()
        _search_status(sb, search_id, "done")
    except Exception as e:  # noqa: BLE001
        overall["finished_at"] = _utc_iso()
        overall["error"] = str(e)
        try:
            _search_status(sb, search_id, "failed", error=str(e))
        except Exception:
            pass
        raise
    finally:
        print(_SUMMARY_MARKER)
        print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

