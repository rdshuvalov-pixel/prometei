#!/usr/bin/env python3
"""
vacancy_score:
  - picks vacancies where pipeline_status = pending_score
  - computes deterministic 0..100 score + score_breakdown (jsonb)
  - sets pipeline_status = scored, scored_at
  - promotes status=Scored when score >= SCORE_PROMOTE_MIN
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

from supabase import Client, create_client

_SUMMARY_MARKER = "--- сводка ---"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        raise SystemExit(2)
    return create_client(url, key)


def _batch_size() -> int:
    raw = (os.environ.get("VACANCY_SCORE_BATCH") or "160").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 160
    return max(1, min(n, 700))


def _promote_min() -> int:
    raw = (os.environ.get("SCORE_PROMOTE_MIN") or "50").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 50
    return max(1, min(n, 100))


def _s(v: object) -> str:
    return (v if isinstance(v, str) else str(v or "")).strip()


def _i(v: object) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _clamp(n: int) -> int:
    return 0 if n < 0 else (100 if n > 100 else n)


_re_bad_contract = re.compile(r"\b(contract|freelance|part[-\s]?time)\b", re.I)
_re_good_fulltime = re.compile(r"\b(full[-\s]?time|permanent)\b", re.I)
_re_pm = re.compile(r"\b(product manager|pm)\b", re.I)
_re_ai = re.compile(r"\b(ai|ml|machine learning)\b", re.I)
_re_b2b = re.compile(r"\b(b2b)\b", re.I)


def _score_row(row: dict) -> tuple[int, dict]:
    title = _s(row.get("role_title"))
    company = _s(row.get("company"))
    details = _s(row.get("details"))
    work_format = _s(row.get("work_format")).lower()
    seniority = _s(row.get("seniority")).lower()
    salary_min = _i(row.get("salary_min"))
    salary_max = _i(row.get("salary_max"))

    text = " \n".join([title, company, details]).strip()

    score = 0
    rules: list[dict] = []

    def add(delta: int, key: str, why: str) -> None:
        nonlocal score, rules
        score += delta
        rules.append({"rule": key, "delta": delta, "why": why})

    # role relevance
    if _re_pm.search(title) or _re_pm.search(text):
        add(+25, "pm_keyword", "PM keyword in title/details")
    else:
        add(-20, "pm_missing", "No PM keyword")

    # format
    if work_format == "remote":
        add(+10, "remote", "Remote work format")
    elif work_format == "hybrid":
        add(+6, "hybrid", "Hybrid work format")
    elif work_format == "onsite":
        add(-4, "onsite", "Onsite only")

    # seniority
    if seniority == "lead":
        add(+8, "seniority_lead", "Lead/Principal role")
    elif seniority == "senior":
        add(+10, "seniority_senior", "Senior role")
    elif seniority == "mid":
        add(+4, "seniority_mid", "Mid role")
    elif seniority == "junior":
        add(-8, "seniority_junior", "Junior role")

    # contract flags
    if _re_bad_contract.search(text):
        add(-12, "contract", "Contract/freelance/part-time")
    if _re_good_fulltime.search(text):
        add(+6, "fulltime", "Full-time/permanent mentioned")

    # domain hints
    if _re_ai.search(text):
        add(+4, "ai_ml", "AI/ML mentioned")
    if _re_b2b.search(text):
        add(+3, "b2b", "B2B mentioned")

    # salary signal
    if salary_min or salary_max:
        add(+5, "salary_present", "Salary range present")

    # quality heuristics
    if len(title) >= 6:
        add(+2, "title_len_ok", "Non-empty title")
    if "http" in _s(row.get("url")):
        add(+2, "url_present", "URL present")

    final = _clamp(score + 50)  # shift to be mostly positive
    breakdown = {"base": 50, "raw": score, "final": final, "rules": rules}
    return final, breakdown


def main() -> None:
    sb = _client()
    n = _batch_size()
    min_score = _promote_min()

    res = (
        sb.table("vacancies")
        .select(
            "id, role_title, company, url, details, pipeline_status, work_format, seniority, salary_min, salary_max",
            count="exact",
        )
        .eq("pipeline_status", "pending_score")
        .order("created_at", desc=False)
        .limit(n)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    total_pending = int(getattr(res, "count", None) or 0)

    scored = 0
    promoted = 0
    skipped = 0
    errors = 0

    for r in rows:
        vid = r.get("id")
        if vid is None:
            skipped += 1
            continue
        try:
            score, breakdown = _score_row(r)
            patch: dict = {
                "score": score,
                "score_breakdown": breakdown,
                "scored_at": _utc_iso(),
                "pipeline_status": "scored",
            }
            if score >= min_score:
                patch["status"] = "Scored"
            sb.table("vacancies").update(patch).eq("id", vid).eq("pipeline_status", "pending_score").execute()
            scored += 1
            if score >= min_score:
                promoted += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            msg = str(e)
            sb.table("vacancies").update({"notes": f"score_warn: {msg[:200]}"}).eq("id", vid).eq(
                "pipeline_status",
                "pending_score",
            ).execute()

    summary = {
        "job_type": "vacancy_score",
        "pending_score_total": total_pending,
        "batch_size": n,
        "rows_loaded": len(rows),
        "scored": scored,
        "promoted_to_scored_status": promoted,
        "score_promote_min": min_score,
        "skipped": skipped,
        "errors": errors,
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

