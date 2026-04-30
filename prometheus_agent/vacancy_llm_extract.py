#!/usr/bin/env python3
"""
vacancy_llm_extract:
  - picks vacancy_candidates where pipeline_status = pending_enrich
  - calls LLM to extract normalized fields (work_format, seniority, salary, etc.)
  - sets pipeline_status = pending_score and enriched_at

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
    # Allows running as a script: `python3 prometheus_agent/vacancy_llm_extract.py`
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
    raw = (os.environ.get("VACANCY_LLM_EXTRACT_BATCH") or "80").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 80
    return max(1, min(n, 300))


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
            "You extract vacancy attributes from a job posting.",
            "",
            "Output JSON keys (omit unknown keys, do not invent):",
            '  work_format: one of ["remote","hybrid","onsite"]',
            '  seniority: one of ["junior","mid","senior","lead"]',
            '  function_norm: one of ["product_management","growth","project_management"]',
            "  salary_currency: one of [\"USD\",\"EUR\",\"GBP\"]",
            "  salary_min: integer",
            "  salary_max: integer",
            "  is_visa_sponsored: boolean",
            "  is_relocation: boolean",
            "  location_norm: short string (<=120 chars, e.g. city/country if explicit)",
            "",
            "Rules:",
            "- Prefer conservative extraction: if not explicit, omit the key.",
            "- salary_min/salary_max: only if a clear numeric range exists.",
            "- location_norm: only if explicit in the text (do not guess).",
        ],
    )


def _prompt(row: dict) -> str:
    return "\n".join(
        [
            "Extract normalized fields for this vacancy.",
            "",
            f"Company: {_as_text(row.get('company'))}",
            f"Role: {_as_text(row.get('role_title'))}",
            f"URL: {_as_text(row.get('url'))}",
            "Details:",
            _as_text(row.get("details")),
        ],
    )


def _pick_enum(v: object, allowed: set[str]) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    return s if s in allowed else None


def _pick_bool(v: object) -> bool | None:
    if isinstance(v, bool):
        return v
    return None


def _pick_int(v: object) -> int | None:
    if isinstance(v, int):
        return v if v > 0 else None
    if isinstance(v, str) and v.strip().isdigit():
        n = int(v.strip())
        return n if n > 0 else None
    return None


def _pick_str(v: object, max_len: int) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    return s[:max_len]


def main() -> None:
    cfg = openai_cfg(default_model="gpt-4o-mini")
    if not cfg:
        summary = {
            "job_type": "vacancy_llm_extract",
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
        .select("id, company, role_title, external_url, raw, pipeline_status", count="exact")
        .eq("pipeline_status", "pending_enrich")
        .order("created_at", desc=False)
    )
    if sid:
        q = q.eq("search_id", sid)
    res = q.limit(n).execute()
    rows = getattr(res, "data", None) or []
    total_pending = int(getattr(res, "count", None) or 0)

    extracted = 0
    skipped = 0
    errors = 0
    last_error: str | None = None

    allowed_work = {"remote", "hybrid", "onsite"}
    allowed_seniority = {"junior", "mid", "senior", "lead"}
    allowed_function = {"product_management", "growth", "project_management"}
    allowed_cur = {"USD", "EUR", "GBP"}

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
                    },
                ),
                temperature=0.1,
                timeout_sec=60.0,
            )

            patch: dict = {}
            wf = _pick_enum(out.get("work_format"), allowed_work)
            if wf:
                patch["work_format"] = wf
            sen = _pick_enum(out.get("seniority"), allowed_seniority)
            if sen:
                patch["seniority"] = sen
            fn = _pick_enum(out.get("function_norm"), allowed_function)
            if fn:
                patch["function_norm"] = fn
            cur = out.get("salary_currency")
            if isinstance(cur, str) and cur.strip().upper() in allowed_cur:
                patch["salary_currency"] = cur.strip().upper()
            mn = _pick_int(out.get("salary_min"))
            mx = _pick_int(out.get("salary_max"))
            if mn:
                patch["salary_min"] = mn
            if mx:
                patch["salary_max"] = mx
            iv = _pick_bool(out.get("is_visa_sponsored"))
            if iv is not None:
                patch["is_visa_sponsored"] = iv
            ir = _pick_bool(out.get("is_relocation"))
            if ir is not None:
                patch["is_relocation"] = ir
            loc = _pick_str(out.get("location_norm"), 120)
            if loc:
                patch["location_norm"] = loc

            if not patch:
                skipped += 1
                # Still advance status: we want scoring step to run even if extraction is empty.
                patch = {}

            patch["enriched_at"] = _utc_iso()
            patch["pipeline_status"] = "pending_score"
            sb.table("vacancy_candidates").update(patch).eq("id", vid).eq("pipeline_status", "pending_enrich").execute()
            extracted += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            last_error = str(e)
            sb.table("vacancy_candidates").update(
                {"pipeline_status": "pending_score", "notes": f"extract_warn: {str(e)[:200]}"},
            ).eq("id", vid).eq("pipeline_status", "pending_enrich").execute()

    summary = {
        "job_type": "vacancy_llm_extract",
        "model": model,
        "base_url": base,
        "pending_enrich_total": total_pending,
        "batch_size": n,
        "rows_loaded": len(rows),
        "extracted": extracted,
        "skipped": skipped,
        "errors": errors,
        "last_error": (last_error[:400] if last_error else None),
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

