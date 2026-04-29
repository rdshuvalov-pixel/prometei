#!/usr/bin/env python3
"""
vacancy_enrich:
  - picks vacancy_candidates where pipeline_status = pending_enrich
  - parses role_title/details/url to fill normalized fields
  - sets pipeline_status = pending_score and enriched_at

This is deterministic (no LLM) and idempotent by status.
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
    raw = (os.environ.get("VACANCY_ENRICH_BATCH") or "120").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 120
    return max(1, min(n, 500))


def _as_text(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


def _details_text(row: dict) -> str:
    raw = row.get("details")
    if raw is None:
        return ""
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return ""
        # Often details is JSON encoded into text; try to parse and flatten.
        try:
            obj = json.loads(s)
            return _as_text(obj)
        except Exception:
            return s
    return _as_text(raw)


_re_remote = re.compile(r"\b(remote|fully remote|work from home|wfh)\b", re.I)
_re_hybrid = re.compile(r"\b(hybrid)\b", re.I)
_re_onsite = re.compile(r"\b(on[-\s]?site|onsite|in[-\s]?office)\b", re.I)

_re_seniority = [
    (re.compile(r"\b(junior|jr\.?)\b", re.I), "junior"),
    (re.compile(r"\b(mid|middle)\b", re.I), "mid"),
    (re.compile(r"\b(senior|sr\.?)\b", re.I), "senior"),
    (re.compile(r"\b(lead|principal|head)\b", re.I), "lead"),
]

_re_salary = re.compile(
    r"(?P<cur>\\$|€|£|usd|eur|gbp)\\s*(?P<min>\\d{2,3}(?:[\\.,]\\d{3})?)\\s*(?:[-–—]|to)\\s*(?P<max>\\d{2,3}(?:[\\.,]\\d{3})?)",
    re.I,
)


def _currency_norm(raw: str) -> str | None:
    r = (raw or "").strip().lower()
    if r in ("$", "usd"):
        return "USD"
    if r in ("€", "eur"):
        return "EUR"
    if r in ("£", "gbp"):
        return "GBP"
    return None


def _int_money(s: str) -> int | None:
    t = (s or "").replace(",", "").replace(".", "").strip()
    if not t.isdigit():
        return None
    try:
        n = int(t)
    except ValueError:
        return None
    return n if n > 0 else None


def _extract(row: dict) -> dict:
    title = _as_text(row.get("role_title")).strip()
    company = _as_text(row.get("company")).strip()
    url = _as_text(row.get("url")).strip()
    text = " \n".join([title, company, url, _details_text(row)]).strip()

    patch: dict = {}

    # work_format
    if _re_remote.search(text):
        patch["work_format"] = "remote"
    elif _re_hybrid.search(text):
        patch["work_format"] = "hybrid"
    elif _re_onsite.search(text):
        patch["work_format"] = "onsite"

    # seniority
    for rx, label in _re_seniority:
        if rx.search(title) or rx.search(text):
            patch["seniority"] = label
            break

    # function_norm (very coarse)
    t = title.lower()
    if "product" in t and "manager" in t:
        patch["function_norm"] = "product_management"
    elif "growth" in t:
        patch["function_norm"] = "growth"
    elif "project manager" in t:
        patch["function_norm"] = "project_management"

    # visa/relocation (best-effort)
    if re.search(r"\\b(visa sponsorship|sponsor visa|h1b)\\b", text, re.I):
        patch["is_visa_sponsored"] = True
    if re.search(r"\\b(relocation|relocate|relocation assistance)\\b", text, re.I):
        patch["is_relocation"] = True

    # salary range (best-effort)
    m = _re_salary.search(text)
    if m:
        cur = _currency_norm(m.group("cur"))
        mn = _int_money(m.group("min"))
        mx = _int_money(m.group("max"))
        if cur:
            patch["salary_currency"] = cur
        if mn:
            patch["salary_min"] = mn
        if mx:
            patch["salary_max"] = mx

    # location_norm: keep it empty for now (requires source-specific parsing)
    # (we still add a placeholder if details contains explicit location string)
    if not patch.get("location_norm"):
        mm = re.search(r"\\b(location|based in)\\s*[:\\-]\\s*([^\\n\\r\\|]{2,80})", text, re.I)
        if mm:
            patch["location_norm"] = mm.group(2).strip()[:120]

    return patch


def main() -> None:
    sb = _client()
    n = _batch_size()
    sid = (os.environ.get("SEARCH_ID") or "").strip()

    # Diagnostics: понять, что именно видит воркер в таблице на старте шага.
    try:
        all_pending = (
            sb.table("vacancy_candidates")
            .select("id", count="exact", head=True)
            .eq("pipeline_status", "pending_enrich")
            .execute()
        )
        pending_enrich_total_all = int(getattr(all_pending, "count", None) or 0)
    except Exception:
        pending_enrich_total_all = -1
    pending_enrich_total_sid = None
    if sid:
        try:
            sid_pending = (
                sb.table("vacancy_candidates")
                .select("id", count="exact", head=True)
                .eq("pipeline_status", "pending_enrich")
                .eq("search_id", sid)
                .execute()
            )
            pending_enrich_total_sid = int(getattr(sid_pending, "count", None) or 0)
        except Exception:
            pending_enrich_total_sid = -1

    q = (
        sb.table("vacancy_candidates")
        .select("id, role_title, company, external_url, raw, pipeline_status", count="exact")
        .eq("pipeline_status", "pending_enrich")
        .order("created_at", desc=False)
    )
    if sid:
        q = q.eq("search_id", sid)
    res = q.limit(n).execute()
    rows = getattr(res, "data", None) or []
    total_pending = int(getattr(res, "count", None) or 0)

    enriched = 0
    skipped = 0
    errors = 0

    for r in rows:
        vid = r.get("id")
        if vid is None:
            skipped += 1
            continue
        try:
            patch = _extract(
                {
                    "role_title": r.get("role_title"),
                    "company": r.get("company"),
                    "url": r.get("external_url"),
                    "details": _as_text(r.get("raw")),
                },
            )
            patch["enriched_at"] = _utc_iso()
            patch["pipeline_status"] = "pending_score"
            sb.table("vacancy_candidates").update(patch).eq("id", vid).eq("pipeline_status", "pending_enrich").execute()
            enriched += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            msg = str(e)
            sb.table("vacancy_candidates").update(
                {"pipeline_status": "pending_score", "notes": f"enrich_warn: {msg[:200]}"},
            ).eq("id", vid).eq("pipeline_status", "pending_enrich").execute()

    summary = {
        "job_type": "vacancy_enrich",
        "search_id": (sid or None),
        "pending_enrich_total_all": pending_enrich_total_all,
        "pending_enrich_total_sid": pending_enrich_total_sid,
        "pending_enrich_total": total_pending,
        "batch_size": n,
        "rows_loaded": len(rows),
        "enriched": enriched,
        "skipped": skipped,
        "errors": errors,
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

