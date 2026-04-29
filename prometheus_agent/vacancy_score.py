#!/usr/bin/env python3
"""
vacancy_score:
  - picks vacancy_candidates where pipeline_status = pending_score
  - computes deterministic 0..100 score + score_breakdown (jsonb)
  - sets pipeline_status = scored, scored_at
  - promotes pipeline_status only; promotion into vacancies is a separate step
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

def _force() -> bool:
    return (os.environ.get("VACANCY_SCORE_FORCE") or "").strip().lower() in ("1", "true", "yes", "on")


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


_re_employment_fulltime = re.compile(r"\b(full[-\s]?time|permanent)\b", re.I)
_re_employment_not_fulltime = re.compile(r"\b(part[-\s]?time|contract|freelance)\b", re.I)

_re_role_ok = re.compile(
    r"\b(product manager|senior product manager|product lead|head of product|growth product|monetization)\b",
    re.I,
)
_re_role_junior = re.compile(r"\b(junior|intern)\b", re.I)
_re_role_director_only = re.compile(r"\b(director|vp|vice president|cpo|chief product)\b", re.I)

_re_domain_fintech = re.compile(r"\b(fintech|payments|banking|money flows|card|acquiring|kyc|aml)\b", re.I)
_re_domain_b2bsaas = re.compile(r"\b(b2b|saas)\b", re.I)
_re_domain_growth = re.compile(r"\b(moneti[sz]ation|pricing|growth|funnel|arpu|ltv|conversion)\b", re.I)
_re_domain_ai = re.compile(r"\b(ai|llm|machine learning)\b", re.I)
_re_domain_platform = re.compile(r"\b(platform|api|integration|integrations|sdk|developer)\b", re.I)
_re_domain_compliance = re.compile(r"\b(compliance|regulated|audit|soc2|iso27001|gdpr)\b", re.I)

_re_scope_ownership = re.compile(r"\b(strategy|vision|roadmap|ownership)\b", re.I)
_re_scope_discovery = re.compile(r"\b(discovery|research|user interviews|experiments?)\b", re.I)
_re_scope_metrics = re.compile(r"\b(kpi|metrics?|instrumentation|analytics|a/b|experimentation)\b", re.I)
_re_scope_leadership = re.compile(r"\b(cross[-\s]?functional|stakeholder|leadership|influence)\b", re.I)

_re_team_english = re.compile(r"\b(english)\b", re.I)
_re_team_distributed = re.compile(r"\b(remote[-\s]?first|distributed|international)\b", re.I)
_re_team_culture = re.compile(r"\b(product culture|strong product)\b", re.I)


def _score_row(row: dict) -> tuple[int, dict]:
    title = _s(row.get("role_title"))
    company = _s(row.get("company"))
    details = _s(row.get("details"))
    work_format = _s(row.get("work_format")).lower()
    seniority = _s(row.get("seniority")).lower()
    salary_min = _i(row.get("salary_min"))
    salary_max = _i(row.get("salary_max"))

    text = " \n".join([title, company, details]).strip()

    rules: list[dict] = []
    critical_failed: list[str] = []

    def rule(key: str, points: int, why: str) -> None:
        rules.append({"rule": key, "points": points, "why": why})

    # --- Group A (critical). If any fails -> cap at 49.
    role_ok = bool(_re_role_ok.search(title) or _re_role_ok.search(text))
    if role_ok:
        rule("A_role", 1, "Role matches PM/Lead/Head/Growth/Monetization")
    else:
        critical_failed.append("role")
        rule("A_role", 0, "Role does not match target PM family")

    # Location: Remote EU ✅ or Hybrid Lisbon ⚠️; onsite/hybrid outside Lisbon is ❌.
    # We only have coarse signals, so treat onsite as fail; hybrid is ok-ish; remote ok.
    if work_format == "remote":
        rule("A_location", 1, "Remote (assume EU-compatible)")
    elif work_format == "hybrid":
        # cannot verify Lisbon reliably from current extraction; keep as pass but flag later via LLM/notes
        rule("A_location", 1, "Hybrid (needs Lisbon verification)")
    else:
        critical_failed.append("location")
        rule("A_location", 0, "Onsite/unknown location format")

    # Employment: require full-time (if explicitly not full-time -> fail)
    if _re_employment_not_fulltime.search(text):
        critical_failed.append("employment")
        rule("A_fulltime", 0, "Not full-time (contract/part-time)")
    else:
        # pass if full-time mentioned OR unknown
        rule("A_fulltime", 1, "Full-time ok/unknown")

    # Seniority: middle/senior (junior -> fail); director-only roles are risky but not automatic fail
    if seniority == "junior" or _re_role_junior.search(title):
        critical_failed.append("seniority")
        rule("A_seniority", 0, "Junior role")
    else:
        rule("A_seniority", 1, "Middle/Senior ok/unknown")

    # --- Group B (domain & relevance) 0..40
    b = 0
    if _re_domain_fintech.search(text):
        b += 10
    if _re_domain_b2bsaas.search(text):
        b += 8
    if _re_domain_growth.search(text):
        b += 8
    if _re_domain_ai.search(text):
        b += 6
    if _re_domain_platform.search(text):
        b += 5
    if _re_domain_compliance.search(text):
        b += 3
    b = min(b, 40)
    rule("B_domain", b, "Domain signals (FinTech/B2B SaaS/Growth/AI/Platform/Compliance)")

    # --- Group C (scope & expectations) 0..30
    c = 0
    if _re_scope_ownership.search(text):
        c += 10
    if _re_scope_discovery.search(text):
        c += 8
    if _re_scope_metrics.search(text):
        c += 7
    if _re_scope_leadership.search(text):
        c += 5
    c = min(c, 30)
    rule("C_scope", c, "Ownership/discovery/metrics/leadership")

    # --- Group D (language & team) 0..15
    d = 0
    if _re_team_english.search(text):
        d += 6
    if _re_team_distributed.search(text):
        d += 5
    if _re_team_culture.search(text):
        d += 4
    d = min(d, 15)
    rule("D_team", d, "English + distributed + product culture")

    # --- Group E (bonuses) 0..10
    e = 0
    if work_format == "remote":
        e += 5
    if salary_min or salary_max:
        e += 2
    if "asap" in text.lower() or "urgent" in text.lower():
        e += 2
    if _re_role_director_only.search(title) and not _re_role_ok.search(title):
        e -= 2
    e = max(0, min(e, 10))
    rule("E_bonus", e, "Remote-friendly / salary / urgent")

    raw = b + c + d + e
    final = _clamp(raw)
    if critical_failed:
        final = min(final, 49)
    breakdown = {
        "final": final,
        "critical_failed": critical_failed,
        "groups": {"B": b, "C": c, "D": d, "E": e},
        "rules": rules,
    }
    return final, breakdown


def main() -> None:
    sb = _client()
    n = _batch_size()
    min_score = _promote_min()
    force = _force()
    sid = (os.environ.get("SEARCH_ID") or "").strip()

    q = sb.table("vacancy_candidates").select(
        "id, role_title, company, external_url, raw, pipeline_status, work_format, seniority, salary_min, salary_max",
        count="exact",
    )
    if sid:
        q = q.eq("search_id", sid)
    if force:
        # Rescore highest-score first (we'll overwrite score + breakdown deterministically).
        q = q.order("score", desc=True)
    else:
        q = q.eq("pipeline_status", "pending_score").order("created_at", desc=False)
    res = q.limit(n).execute()
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
            score, breakdown = _score_row(
                {
                    "role_title": r.get("role_title"),
                    "company": r.get("company"),
                    "url": r.get("external_url"),
                    "details": _s(r.get("raw")),
                    "work_format": r.get("work_format"),
                    "seniority": r.get("seniority"),
                    "salary_min": r.get("salary_min"),
                    "salary_max": r.get("salary_max"),
                },
            )
            patch: dict = {
                "score": score,
                "score_breakdown": breakdown,
                "scored_at": _utc_iso(),
                "pipeline_status": "scored",
            }
            up = sb.table("vacancy_candidates").update(patch).eq("id", vid)
            if not force:
                up = up.eq("pipeline_status", "pending_score")
            up.execute()
            scored += 1
            if score >= min_score:
                promoted += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            msg = str(e)
            sb.table("vacancy_candidates").update({"notes": f"score_warn: {msg[:200]}"}).eq("id", vid).eq(
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

