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


# region agent log
def _agent_log(*, run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        p = "/Users/luqy/Documents/Cursor/Агент Прометей/.cursor/debug-184508.log"
        payload = {
            "sessionId": "184508",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def _dbg_run_id(row: dict) -> str:
    return str(row.get("id") or "unknown")


def _dbg_parent(row: dict) -> str | None:
    return _parent_search_id(row)


# endregion agent log


_WORKER_BUILD_TAG = "2026-04-30.worker_chainfix_v2"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _jt(raw: object) -> str:
    return str(raw or "").strip().lower()


def _payload(row: dict) -> dict:
    p = row.get("payload")
    return p if isinstance(p, dict) else {}


def _parent_search_id(row: dict) -> str | None:
    p = _payload(row)
    v = p.get("parent_search_id")
    s = str(v or "").strip()
    return s or None


def _required_prev(job_type: str) -> list[str] | None:
    jt = _jt(job_type)
    return {
        # vacancy_enrich can start from either search root (keyword/full) or a manual script_crawl run.
        "vacancy_enrich": ["keyword_search", "full_search", "script_crawl"],
        "vacancy_score": ["vacancy_enrich"],
        "vacancy_llm": ["vacancy_score"],
        "vacancy_promote": ["vacancy_llm"],
    }.get(jt)


def _root_done(sb: Client, parent_search_id: str) -> bool:
    """
    Root gate: parent_search_id must exist as a done row in job_runs.

    We intentionally don't hardcode job_type here: any root-type producer (keyword_search/full_search/script_crawl)
    can be used as a pipeline root.
    """
    if not parent_search_id:
        return False
    try:
        res = sb.table("job_runs").select("id, job_type").eq("id", parent_search_id).eq("status", "done").limit(1).execute()
    except Exception:
        return False
    rows = getattr(res, "data", None) or []
    return bool(rows)


def _has_done(sb: Client, *, job_type: str, parent_search_id: str) -> bool:
    """
    Hard gate helper.

    For keyword_search/full_search the run id equals the job id (root row).
    For pipeline steps (enrich/score/llm/promote) we enqueue separate job_runs rows
    and link them via payload.parent_search_id to the root run id.
    """
    jt = _jt(job_type)
    q = sb.table("job_runs").select("id").eq("job_type", jt).eq("status", "done").limit(1)
    if jt in ("keyword_search", "full_search", "script_crawl"):
        q = q.eq("id", parent_search_id)
    else:
        q = q.eq("payload->>parent_search_id", parent_search_id)
    res = q.execute()
    rows = getattr(res, "data", None) or []
    return bool(rows)


def _gate_or_raise(sb: Client, row: dict) -> None:
    jt = _jt(row.get("job_type"))
    pid = _parent_search_id(row)
    if not pid:
        _agent_log(
            run_id=_dbg_run_id(row),
            hypothesis_id="H1",
            location="worker/poll_jobs.py:_gate_or_raise",
            message="gate skipped (no parent_search_id)",
            data={"job_type": jt},
        )
        return
    prev = _required_prev(jt)
    if not prev:
        _agent_log(
            run_id=_dbg_run_id(row),
            hypothesis_id="H1",
            location="worker/poll_jobs.py:_gate_or_raise",
            message="gate skipped (no required prev)",
            data={"job_type": jt, "parent_search_id": pid},
        )
        return
    # First-level gate: root must be done. This prevents "enrich for a run that never finished producing candidates".
    if jt == "vacancy_enrich" and not _root_done(sb, pid):
        _agent_log(
            run_id=_dbg_run_id(row),
            hypothesis_id="H1",
            location="worker/poll_jobs.py:_gate_or_raise",
            message="gate failed (root not done)",
            data={"job_type": jt, "parent_search_id": pid},
        )
        raise RuntimeError(f"gate: require root(id={pid})=done before {jt}")

    ok = any(_has_done(sb, job_type=p, parent_search_id=pid) for p in prev)
    if not ok:
        need = " or ".join(prev)
        _agent_log(
            run_id=_dbg_run_id(row),
            hypothesis_id="H1",
            location="worker/poll_jobs.py:_gate_or_raise",
            message="gate failed",
            data={"job_type": jt, "parent_search_id": pid, "need_done": prev},
        )
        raise RuntimeError(f"gate: require ({need})=done for parent_search_id={pid} before {jt}")
    _agent_log(
        run_id=_dbg_run_id(row),
        hypothesis_id="H1",
        location="worker/poll_jobs.py:_gate_or_raise",
        message="gate ok",
        data={"job_type": jt, "parent_search_id": pid, "prev": prev},
    )


def _enqueue_next(sb: Client, *, parent_search_id: str, next_job_type: str) -> None:
    sb.table("job_runs").insert(
        {
            "status": "queued",
            "job_type": next_job_type,
            "counters": {},
            "payload": {
                "source": "worker_autochain",
                "job_type": next_job_type,
                "parent_search_id": parent_search_id,
            },
        },
    ).execute()


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "Нужны SUPABASE_URL (или NEXT_PUBLIC_SUPABASE_URL) и SUPABASE_SERVICE_ROLE_KEY",
        )
    return create_client(url, key)


def _pick_queued(sb: Client) -> dict | None:
    """
    Picks next queued job.

    Important: multiple jobs can share the exact same created_at (single INSERT of several rows),
    and UUID ordering is effectively random. To keep pipeline order stable, we apply a lightweight
    priority within the earliest created_at batch.
    """

    priority: dict[str, int] = {
        "keyword_search": 5,
        "full_search": 5,
        "vacancy_enrich": 10,
        "vacancy_score": 20,
        "vacancy_llm": 30,
        "vacancy_promote": 40,
        "tier4_board_feeds": 60,
        "tier4_ashby": 60,
        "playwright_search": 60,
        "script_crawl": 70,
        "watchlist": 70,
    }

    res = (
        sb.table("job_runs")
        .select("*")
        .eq("status", "queued")
        .order("created_at", desc=False)
        .order("id", desc=False)
        .limit(20)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None

    earliest = min((r.get("created_at") for r in rows if r.get("created_at") is not None), default=None)
    if earliest is None:
        earliest_rows = rows
    else:
        earliest_rows = [r for r in rows if r.get("created_at") == earliest] or rows

    def _key(r: dict) -> tuple[int, str]:
        jt = _jt(r.get("job_type"))
        pr = priority.get(jt, 50)
        return (pr, str(r.get("id") or ""))

    earliest_rows.sort(key=_key)
    return earliest_rows[0]


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
    if isinstance(counters, dict):
        counters.setdefault("worker_build_tag", _WORKER_BUILD_TAG)
    sb.table("job_runs").update(
        {
            "status": "done",
            "finished_at": _utc_iso(),
            "counters": counters,
            "log": log[-120_000:],
        },
    ).eq("id", job_id).execute()

    # Autochain: ставим только следующий шаг, чтобы не было путаницы.
    jt = _jt(prev.get("job_type"))
    pid = str(prev.get("id") or "").strip()
    payload = _payload(prev)
    parent = _parent_search_id(prev) or pid
    if jt in ("keyword_search", "full_search"):
        _enqueue_next(sb, parent_search_id=pid, next_job_type="vacancy_enrich")
        return
    if jt == "script_crawl":
        _enqueue_next(sb, parent_search_id=pid, next_job_type="vacancy_enrich")
        return
    if payload.get("parent_search_id"):
        if jt == "vacancy_enrich":
            _enqueue_next(sb, parent_search_id=parent, next_job_type="vacancy_score")
        elif jt == "vacancy_score":
            _enqueue_next(sb, parent_search_id=parent, next_job_type="vacancy_llm")
        elif jt == "vacancy_llm":
            _enqueue_next(sb, parent_search_id=parent, next_job_type="vacancy_promote")


def _finish_fail(sb: Client, job_id: str, err: str) -> None:
    try:
        prev = _read_row(sb, job_id)
        counters = prev.get("counters")
        if isinstance(counters, dict):
            counters.setdefault("worker_build_tag", _WORKER_BUILD_TAG)
            sb.table("job_runs").update({"counters": counters}).eq("id", job_id).execute()
    except Exception:
        pass
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
    job_type = _jt(job.get("job_type") or "script_crawl")
    _agent_log(
        run_id=job_id,
        hypothesis_id="H2",
        location="worker/poll_jobs.py:run_once",
        message="picked queued job",
        data={
            "job_type": job_type,
            "created_at": job.get("created_at"),
            "payload_parent_search_id": _dbg_parent(job),
            "payload_keys": sorted(list(_payload(job).keys())),
        },
    )

    if not _claim(sb, job_id):
        return

    try:
        _gate_or_raise(sb, job)
    except Exception as e:  # noqa: BLE001
        _finish_fail(sb, job_id, str(e))
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
        "SEARCH_ID": _parent_search_id(job) or job_id,
    }
    _agent_log(
        run_id=job_id,
        hypothesis_id="H3",
        location="worker/poll_jobs.py:run_once",
        message="spawn worker cmd",
        data={
            "cmd": cmd,
            "timeout": timeout,
            "JOB_TYPE": job_type,
            "SEARCH_ID": child_env.get("SEARCH_ID"),
            "parent_search_id": _dbg_parent(job),
        },
    )

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
