#!/usr/bin/env python3
"""
Заглушка очереди «оценка»: считает вакансии без скоринга; переводит в status=Scored строки
с score >= SCORE_PROMOTE_MIN (по умолчанию 50) и match_status=pending_score. Полноценный
28-параметровый скоринг — отдельный слой.
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


def _promote_min() -> int:
    raw = (os.environ.get("SCORE_PROMOTE_MIN") or "50").strip()
    try:
        n = int(raw)
    except ValueError:
        return 50
    return max(1, min(n, 100))


def main() -> None:
    sb = _client()
    pending = (
        sb.table("vacancies")
        .select("id", count="exact", head=True)
        .eq("match_status", "pending_score")
        .execute()
    )
    n_pending = int(getattr(pending, "count", None) or 0)

    scored = (
        sb.table("vacancies")
        .select("id", count="exact", head=True)
        .gt("score", 0)
        .execute()
    )
    n_scored = int(getattr(scored, "count", None) or 0)

    min_score = _promote_min()
    promoted = 0
    try:
        up = (
            sb.table("vacancies")
            .update({"status": "Scored"})
            .eq("match_status", "pending_score")
            .gte("score", min_score)
            .or_("status.is.null,status.neq.Scored")
            .select("id")
            .execute()
        )
        rows = getattr(up, "data", None) or []
        promoted = len(rows) if isinstance(rows, list) else 0
    except Exception as e:  # noqa: BLE001
        print(f"WARN promote status=scored :: {e}", file=sys.stderr)

    summary = {
        "pending_score_rows": n_pending,
        "rows_with_positive_score": n_scored,
        "promoted_to_scored": promoted,
        "score_promote_min": min_score,
        "stub": True,
        "hint": "Подключи полноценный скорер вместо script_score_stub.py",
    }
    print("--- сводка ---", flush=True)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
