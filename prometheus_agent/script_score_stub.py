#!/usr/bin/env python3
"""
Заглушка очереди «оценка»: считает вакансии без скоринга. Полноценный 28-параметровый
скоринг — отдельный слой; воркер уже может принять job_type score_vacancies.
"""
from __future__ import annotations

import json
import os
import sys

from supabase import create_client


def _client():
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


def main() -> None:
    sb = _client()
    pending = (
        sb.table("vacancies")
        .select("*", count="exact", head=True)
        .eq("match_status", "pending_score")
        .execute()
    )
    n_pending = int(getattr(pending, "count", None) or 0)

    scored = (
        sb.table("vacancies")
        .select("*", count="exact", head=True)
        .gt("score", 0)
        .execute()
    )
    n_scored = int(getattr(scored, "count", None) or 0)

    summary = {
        "pending_score_rows": n_pending,
        "rows_with_positive_score": n_scored,
        "stub": True,
        "hint": "Подключи полноценный скорер вместо script_score_stub.py",
    }
    print("--- сводка ---", flush=True)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
