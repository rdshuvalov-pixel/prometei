#!/usr/bin/env python3
"""
vacancy_promote:
  - selects vacancy_candidates that passed thresholds (score>=PROMOTE_MIN, pipeline_status=llm_done by default)
  - inserts into vacancies (+ vacancy_sources) with dedupe
  - marks candidate promoted_at + promoted_vacancy_id
"""

from __future__ import annotations

import json
import os
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
    raw = (os.environ.get("VACANCY_PROMOTE_BATCH") or "120").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 120
    return max(1, min(n, 600))


def _min_score() -> int:
    raw = (os.environ.get("PROMOTE_MIN_SCORE") or "50").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 50
    return max(1, min(n, 100))


def _require_llm() -> bool:
    raw = (os.environ.get("PROMOTE_REQUIRE_LLM") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _require_letters() -> bool:
    raw = (os.environ.get("PROMOTE_REQUIRE_LETTERS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _s(v: object) -> str:
    return (v if isinstance(v, str) else str(v or "")).strip()


def _details_to_text(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw, ensure_ascii=False)
    except Exception:
        return str(raw)


def _vacancy_source_exists(sb: Client, platform: str, url: str) -> bool:
    try:
        res = (
            sb.table("vacancy_sources")
            .select("id")
            .eq("platform", platform[:255])
            .eq("url", url[:2000])
            .limit(1)
            .execute()
        )
    except Exception:
        return False
    rows = getattr(res, "data", None) or []
    return bool(rows)


def main() -> None:
    sb = _client()
    n = _batch_size()
    min_score = _min_score()
    require_llm = _require_llm()
    require_letters = _require_letters()
    sid = (os.environ.get("SEARCH_ID") or "").strip()

    q = (
        sb.table("vacancy_candidates")
        .select(
            "id, created_at, company, role_title, platform, tier, external_url, raw, score, "
            "work_format, location_norm, seniority, function_norm, salary_min, salary_max, salary_currency, "
            "is_visa_sponsored, is_relocation, fit_reasoning, cover_formal, cover_informal, notes, "
            "pipeline_status, promoted_at, promoted_vacancy_id",
            count="exact",
        )
        .eq("pipeline_status", "llm_done" if require_llm else "scored")
        .gte("score", min_score)
        .is_("promoted_at", "null")
        .order("created_at", desc=False)
    )
    if sid:
        q = q.eq("search_id", sid)
    res = q.limit(n).execute()
    rows = getattr(res, "data", None) or []
    total = int(getattr(res, "count", None) or 0)

    inserted = 0
    skipped = 0
    dup_url = 0
    errors = 0

    for r in rows:
        cid = _s(r.get("id"))
        url = _s(r.get("external_url"))
        platform = _s(r.get("platform"))
        company = _s(r.get("company"))[:500]
        role_title = _s(r.get("role_title"))[:500]
        if not cid or not url or not platform or not company or not role_title:
            skipped += 1
            continue

        if require_letters:
            fr = _s(r.get("fit_reasoning"))
            cf = _s(r.get("cover_formal"))
            ci = _s(r.get("cover_informal"))
            if not (fr and cf and ci):
                skipped += 1
                sb.table("vacancy_candidates").update(
                    {"notes": "promote_skip: missing_llm_materials"},
                ).eq("id", cid).execute()
                continue

        if _vacancy_source_exists(sb, platform, url):
            dup_url += 1
            sb.table("vacancy_candidates").update({"promoted_at": _utc_iso(), "notes": "promote_skip: dup_url"}).eq(
                "id",
                cid,
            ).execute()
            continue

        try:
            row = {
                "created_at": str(r.get("created_at") or "")[:10] or datetime.now(timezone.utc).date().isoformat(),
                "company": company,
                "role_title": role_title,
                "platform": platform[:255],
                "tier": _s(r.get("tier"))[:64] or None,
                "status": "Scored",
                "score": int(r.get("score") or 0),
                "pipeline_status": "scored",
                "details": _details_to_text(r.get("raw")),
                "url": url[:2000],
                "work_format": r.get("work_format"),
                "location_norm": r.get("location_norm"),
                "seniority": r.get("seniority"),
                "function_norm": r.get("function_norm"),
                "salary_min": r.get("salary_min"),
                "salary_max": r.get("salary_max"),
                "salary_currency": r.get("salary_currency"),
                "is_visa_sponsored": r.get("is_visa_sponsored"),
                "is_relocation": r.get("is_relocation"),
                "fit_reasoning": r.get("fit_reasoning"),
                "cover_formal": r.get("cover_formal"),
                "cover_informal": r.get("cover_informal"),
                "notes": r.get("notes"),
                "enriched_at": r.get("enriched_at"),
                "scored_at": r.get("scored_at"),
            }
            ins = sb.table("vacancies").insert(row).execute()
            data = getattr(ins, "data", None) or []
            if not data:
                errors += 1
                continue
            vid = data[0]["id"]
            try:
                sb.table("vacancy_sources").insert(
                    {"vacancy_id": vid, "platform": platform[:255], "url": url[:2000]},
                ).execute()
            except Exception:
                pass
            sb.table("vacancy_candidates").update({"promoted_at": _utc_iso(), "promoted_vacancy_id": int(vid)}).eq(
                "id",
                cid,
            ).execute()
            inserted += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            sb.table("vacancy_candidates").update({"notes": f"promote_err: {str(e)[:180]}"}).eq("id", cid).execute()

    summary = {
        "job_type": "vacancy_promote",
        "promote_min_score": min_score,
        "promote_require_llm": require_llm,
        "promote_require_letters": require_letters,
        "candidates_total": total,
        "rows_loaded": len(rows),
        "inserted": inserted,
        "dup_url": dup_url,
        "skipped": skipped,
        "errors": errors,
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

