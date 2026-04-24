#!/usr/bin/env python3
"""
MVP-прогон под воркер: читает Supabase, печатает сводку в stdout (попадает в log job_runs).

Полная цепочка Tier/LLM из skill — отдельное расширение; здесь — стабильный шаг,
который можно вызывать из WORKER_CMD на VPS.

Окружение (наследует от воркера):
  SUPABASE_URL или NEXT_PUBLIC_SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  JOB_ID / WORKER_JOB_ID — uuid строки job_runs (опционально)
  JOB_TYPE — script_crawl | watchlist
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from supabase import Client, create_client


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


def _count_head(sb: Client, table: str) -> int | None:
    try:
        res = sb.table(table).select("id", count="exact", head=True).execute()
    except Exception as e:  # noqa: BLE001
        print(f"WARN: count {table}: {e}", file=sys.stderr)
        return None
    c = getattr(res, "count", None)
    return int(c) if c is not None else None


def main() -> None:
    job_type = os.environ.get("JOB_TYPE") or "script_crawl"
    job_id = os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or ""

    print(f"[{datetime.now(UTC).isoformat()}] script_crawl MVP start job_type={job_type!r} job_id={job_id!r}")

    if job_type == "watchlist":
        print("watchlist: в MVP только заглушка — расширь под watchlist_crawl.py при необходимости.")
        return

    sb = _client()
    n_vac = _count_head(sb, "vacancies")
    n_src = _count_head(sb, "vacancy_sources")
    n_jobs = _count_head(sb, "job_runs")

    print("--- сводка Supabase ---")
    print(f"vacancies:        {n_vac if n_vac is not None else 'n/a'}")
    print(f"vacancy_sources:  {n_src if n_src is not None else 'n/a'}")
    print(f"job_runs:         {n_jobs if n_jobs is not None else 'n/a'}")
    print("--- конец ---")
    print(f"[{datetime.now(UTC).isoformat()}] script_crawl MVP done")


if __name__ == "__main__":
    main()
