#!/usr/bin/env python3
"""
Пуллит public.job_runs: берёт одну строку status=queued, переводит в running,
опционально выполняет WORKER_CMD (shell), пишет done/failed.
Запуск: долгий цикл или один проход: python worker/poll_jobs.py --once
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

from supabase import Client, create_client


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "Нужны SUPABASE_URL (или NEXT_PUBLIC_SUPABASE_URL) и SUPABASE_SERVICE_ROLE_KEY",
        )
    return create_client(url, key)


def _pick_queued(sb: Client) -> dict | None:
    res = (
        sb.table("job_runs")
        .select("*")
        .eq("status", "queued")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return rows[0] if rows else None


def _claim(sb: Client, job_id: str) -> bool:
    res = (
        sb.table("job_runs")
        .update({"status": "running", "started_at": _utc_iso()})
        .eq("id", job_id)
        .eq("status", "queued")
        .execute()
    )
    rows = getattr(res, "data", None) or []
    return len(rows) > 0


def _finish_ok(sb: Client, job_id: str, counters: dict, log_extra: str) -> None:
    prev = _read_row(sb, job_id)
    log = (prev.get("log") or "") + log_extra
    sb.table("job_runs").update(
        {
            "status": "done",
            "finished_at": _utc_iso(),
            "counters": counters,
            "log": log[-120_000:],
        },
    ).eq("id", job_id).execute()


def _finish_fail(sb: Client, job_id: str, err: str) -> None:
    sb.table("job_runs").update(
        {
            "status": "failed",
            "finished_at": _utc_iso(),
            "error": err[:8000],
        },
    ).eq("id", job_id).execute()


def _read_row(sb: Client, job_id: str) -> dict:
    res = sb.table("job_runs").select("*").eq("id", job_id).limit(1).execute()
    rows = getattr(res, "data", None) or []
    return rows[0] if rows else {}


_SUMMARY_MARKER = "--- сводка ---"


def _parse_child_summary_json(stdout: str, stderr: str) -> dict | None:
    """Ищет JSON-объект после маркера сводки (script_crawl / ashby / board_feeds)."""
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


def _trim_counter_lists(d: dict, max_list: int = 120) -> dict:
    out = dict(d)
    for key in ("fetch_errors_urls", "skipped_blocked_urls"):
        v = out.get(key)
        if isinstance(v, list) and len(v) > max_list:
            out[key] = v[:max_list]
            out[f"{key}_truncated_len"] = len(v)
    return out


def run_once(sb: Client) -> None:
    job = _pick_queued(sb)
    if not job:
        return
    job_id = str(job["id"])
    job_type = str(job.get("job_type") or "script_crawl")

    if not _claim(sb, job_id):
        return

    cmd = (os.environ.get("WORKER_CMD") or "").strip()
    timeout = int(os.environ.get("JOB_TIMEOUT_SEC", "3600"))

    if not cmd:
        _finish_ok(
            sb,
            job_id,
            counters={"stub": True, "job_type": job_type},
            log_extra=f"\n[{_utc_iso()}] stub: WORKER_CMD пуст — задача закрыта как done.\n",
        )
        return

    child_env = {
        **os.environ,
        "WORKER_JOB_ID": job_id,
        "JOB_ID": job_id,
        "JOB_TYPE": job_type,
    }

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            check=False,
            timeout=timeout,
            capture_output=True,
            text=True,
            env=child_env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        tail = out[-8000:]
        if proc.returncode == 0:
            counters: dict = {
                "exit_code": 0,
                "job_type": job_type,
                "stdout_chars": len(out),
            }
            if os.environ.get("WORKER_PARSE_CHILD_COUNTERS", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            ):
                child = _parse_child_summary_json(proc.stdout or "", proc.stderr or "")
                if child:
                    merged = {**child, **counters}
                    counters = _trim_counter_lists(merged)
            _finish_ok(
                sb,
                job_id,
                counters=counters,
                log_extra=f"\n[{_utc_iso()}] WORKER_CMD exit=0\n{tail}\n",
            )
        else:
            msg = f"exit={proc.returncode}\n{tail}"
            _finish_fail(sb, job_id, msg)
    except subprocess.TimeoutExpired:
        _finish_fail(sb, job_id, f"timeout after {timeout}s")
    except Exception as e:  # noqa: BLE001
        _finish_fail(sb, job_id, f"{e}\n{traceback.format_exc()}"[-8000:])


def loop_forever(sb: Client) -> None:
    poll = float(os.environ.get("POLL_INTERVAL_SEC", "20"))
    while True:
        try:
            run_once(sb)
        except Exception:  # noqa: BLE001
            print(traceback.format_exc(), flush=True)
        time.sleep(poll)


def main() -> None:
    sb = _client()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once(sb)
        return
    loop_forever(sb)


if __name__ == "__main__":
    main()
