#!/usr/bin/env python3
"""
vacancy_llm_score:
  - picks vacancy_candidates where pipeline_status = pending_score
  - calls LLM to produce score 0..100 + score_breakdown compatible with existing schema
  - sets pipeline_status = scored and scored_at

Requires OPENAI_API_KEY (OpenAI-compatible).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from supabase import Client, create_client

try:
    from prometheus_agent.llm_client import call_openai_json, openai_cfg
except ModuleNotFoundError:
    # Allows running as a script: `python3 prometheus_agent/vacancy_llm_score.py`
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from prometheus_agent.llm_client import call_openai_json, openai_cfg

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
    raw = (os.environ.get("VACANCY_LLM_SCORE_BATCH") or "120").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 120
    return max(1, min(n, 400))


def _as_text(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


def _system_contract() -> str:
    return "\n".join(
        [
            "Return strictly valid JSON. No markdown, no comments, no trailing text.",
            "You are scoring a vacancy for a specific candidate profile.",
            "",
            "Output JSON keys:",
            "  score: integer (0..100)",
            "  score_breakdown: object with keys:",
            "    final: integer (0..100, same as score)",
            "    critical_failed: array[string] (0..N)",
            "    groups: object (keys B,C,D,E with integer points)",
            "    rules: array[object] each: {rule: string, points: integer, why: string}",
            "",
            "Scoring framework (mirror legacy rules):",
            "- Group A (critical, gate): role in target PM family; location remote/hybrid; full-time; not junior.",
            "  If any A fails -> cap final score at 49 and list failed keys in critical_failed.",
            "- Group B domain fit (0..40): FinTech/payments, B2B SaaS, growth/pricing/monetization, AI, platform/API, compliance.",
            "- Group C scope (0..30): ownership/roadmap, discovery/research, metrics/experimentation, cross-functional leadership.",
            "- Group D team (0..15): English, distributed/remote-first, product culture.",
            "- Group E bonus (0..10): remote + salary present + urgent; small penalty for director-only mismatch.",
            "",
            "Rules:",
            "- Be conservative: if evidence is weak, award fewer points.",
            "- Use extracted fields as primary signals; details text only to justify evidence.",
            "- Do not invent facts. If uncertain, reflect in rules/why.",
        ],
    )


def _prompt(row: dict) -> str:
    extracted = {
        "work_format": row.get("work_format"),
        "seniority": row.get("seniority"),
        "function_norm": row.get("function_norm"),
        "salary_min": row.get("salary_min"),
        "salary_max": row.get("salary_max"),
        "salary_currency": row.get("salary_currency"),
        "is_visa_sponsored": row.get("is_visa_sponsored"),
        "is_relocation": row.get("is_relocation"),
        "location_norm": row.get("location_norm"),
    }
    return "\n".join(
        [
            "Score this vacancy for the candidate profile used in Prometheus.",
            "",
            f"Company: {_as_text(row.get('company'))}",
            f"Role: {_as_text(row.get('role_title'))}",
            f"URL: {_as_text(row.get('url'))}",
            "",
            "Extracted fields JSON:",
            json.dumps(extracted, ensure_ascii=False),
            "",
            "Details:",
            _as_text(row.get("details")),
        ],
    )


def _pick_int(v: object) -> int | None:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


def _clamp_score(n: int) -> int:
    return 0 if n < 0 else (100 if n > 100 else n)


def main() -> None:
    cfg = openai_cfg(default_model="gpt-4o-mini")
    if not cfg:
        summary = {
            "job_type": "vacancy_llm_score",
            "stub": True,
            "reason": "missing OPENAI_API_KEY",
            "finished_at": _utc_iso(),
        }
        print(_SUMMARY_MARKER, flush=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return

    key, base, model = cfg
    sb = _client()
    n = _batch_size()
    sid = (os.environ.get("SEARCH_ID") or "").strip()

    q = (
        sb.table("vacancy_candidates")
        .select(
            "id, company, role_title, external_url, raw, pipeline_status, "
            "work_format, location_norm, seniority, function_norm, salary_min, salary_max, salary_currency, "
            "is_visa_sponsored, is_relocation",
            count="exact",
        )
        .eq("pipeline_status", "pending_score")
        .order("created_at", desc=False)
    )
    if sid:
        q = q.eq("search_id", sid)
    res = q.limit(n).execute()
    rows = getattr(res, "data", None) or []
    total_pending = int(getattr(res, "count", None) or 0)

    scored = 0
    skipped = 0
    errors = 0
    last_error: str | None = None

    for r in rows:
        vid = r.get("id")
        if vid is None:
            skipped += 1
            continue
        try:
            out = call_openai_json(
                key=key,
                base=base,
                model=model,
                system=_system_contract(),
                prompt=_prompt(
                    {
                        "company": r.get("company"),
                        "role_title": r.get("role_title"),
                        "url": r.get("external_url"),
                        "details": r.get("raw"),
                        "work_format": r.get("work_format"),
                        "location_norm": r.get("location_norm"),
                        "seniority": r.get("seniority"),
                        "function_norm": r.get("function_norm"),
                        "salary_min": r.get("salary_min"),
                        "salary_max": r.get("salary_max"),
                        "salary_currency": r.get("salary_currency"),
                        "is_visa_sponsored": r.get("is_visa_sponsored"),
                        "is_relocation": r.get("is_relocation"),
                    },
                ),
                temperature=0.2,
                timeout_sec=75.0,
            )

            score_raw = _pick_int(out.get("score"))
            breakdown = out.get("score_breakdown")
            if score_raw is None or not isinstance(breakdown, dict):
                raise ValueError("invalid score output")
            score = _clamp_score(score_raw)

            patch: dict = {
                "score": score,
                "score_breakdown": breakdown,
                "scored_at": _utc_iso(),
                "pipeline_status": "scored",
            }
            sb.table("vacancy_candidates").update(patch).eq("id", vid).eq("pipeline_status", "pending_score").execute()
            scored += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            last_error = str(e)
            sb.table("vacancy_candidates").update({"notes": f"score_warn: {str(e)[:200]}"}).eq("id", vid).eq(
                "pipeline_status",
                "pending_score",
            ).execute()

    summary = {
        "job_type": "vacancy_llm_score",
        "model": model,
        "base_url": base,
        "pending_score_total": total_pending,
        "batch_size": n,
        "rows_loaded": len(rows),
        "scored": scored,
        "skipped": skipped,
        "errors": errors,
        "last_error": (last_error[:400] if last_error else None),
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

