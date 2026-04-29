#!/usr/bin/env python3
"""
Публичный Ashby Job Posting API: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
Фильтр: Product Manager / Product Lead (+ варианты), remote + EU/EEA/UK по location, ≤ TIER4_MAX_JOB_AGE_DAYS дней по publishedAt.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY; ASHBY_SLUGS (через запятую, по умолчанию kraken.com);
TIER4_MAX_JOB_AGE_DAYS (по умолчанию 5); ASHBY_DELAY_SEC (по умолчанию 0.65);
TIER4_RELAX_GEO=1 — не требовать EU-маркер в location (только remote).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import tier4_query
from supabase import Client, create_client

# PM / product lead (англ.)
TITLE_RE = re.compile(
    r"(product\s+manager|product\s+lead|head\s+of\s+product|group\s+product|"
    r"director,?\s*product|vp\s*,?\s*product|chief\s+product\s+officer|\bcpo\b)",
    re.I,
)

# Подстроки location (EU + EFTA + UK + обобщения)
EU_MARKERS = frozenset(
    (
        "austria",
        "belgium",
        "bulgaria",
        "croatia",
        "cyprus",
        "czech",
        "denmark",
        "estonia",
        "finland",
        "france",
        "germany",
        "greece",
        "hungary",
        "ireland",
        "italy",
        "latvia",
        "lithuania",
        "luxembourg",
        "malta",
        "netherlands",
        "poland",
        "portugal",
        "romania",
        "slovakia",
        "slovenia",
        "spain",
        "sweden",
        "norway",
        "switzerland",
        "iceland",
        "liechtenstein",
        "united kingdom",
        "u.k.",
        "uk,",
        " uk",
        "london",
        "europe",
        "european",
        " eu",
        "emea",
        "eea",
        "european union",
        "berlin",
        "amsterdam",
        "paris",
        "warsaw",
        "lisbon",
        "dublin",
        "barcelona",
        "madrid",
        "milan",
        "munich",
        "prague",
        "budapest",
        "bucharest",
        "helsinki",
        "stockholm",
        "oslo",
        "zurich",
        "vienna",
        "brussels",
        "athens",
    ),
)


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


def _norm_key(s: str) -> str:
    return " ".join(s.lower().strip().split())


def _search_id() -> str:
    return (os.environ.get("SEARCH_ID") or "").strip()


def _fingerprint(*parts: str) -> str:
    s = "|".join(p.strip().lower() for p in parts if p is not None)
    return hashlib.sha1(s.encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324


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
        rows = getattr(res, "data", None) or []
        return len(rows) > 0
    except Exception:
        return False


def _log_target(
    sb: Client,
    *,
    search_id: str,
    source: str,
    platform: str,
    url: str,
    http_status: int | None,
    latency_ms: int | None,
    outcome: str,
    error: str | None = None,
    meta: dict | None = None,
) -> None:
    try:
        sb.table("search_targets_log").insert(
            {
                "search_id": search_id,
                "source": source,
                "tier": "4",
                "platform": platform[:255] if platform else None,
                "url": url[:2000],
                "http_status": http_status,
                "latency_ms": latency_ms,
                "outcome": outcome[:64],
                "error": error,
                "meta": meta or {},
            },
        ).execute()
    except Exception:
        return


def _log_candidate_and_decision(
    sb: Client,
    *,
    search_id: str,
    external_url: str,
    company: str,
    role_title: str,
    raw: dict,
    decision: str,
    reason: str | None = None,
    inserted_vacancy_id: int | None = None,
) -> None:
    if not (company and str(company).strip()) or not (role_title and str(role_title).strip()):
        return
    if not (external_url and str(external_url).strip().startswith("http")):
        return
    try:
        ins = sb.table("vacancy_candidates").insert(
            {
                "search_id": search_id,
                "source": "tier4_ashby",
                "tier": "4",
                "platform": "jobs.ashbyhq.com",
                "external_url": external_url[:2000],
                "company": company[:500],
                "role_title": role_title[:500],
                "published_at": raw.get("published_at"),
                "fingerprint": _fingerprint(company, role_title, external_url),
                "raw": raw or {},
            },
        ).execute()
        data = getattr(ins, "data", None)
        row = data[0] if isinstance(data, list) and data else (data or {})
        cid = (row or {}).get("id")
        if not cid:
            return
        sb.table("vacancy_ingest_decisions").insert(
            {
                "search_id": search_id,
                "candidate_id": cid,
                "decision": decision,
                "reason": reason,
                "inserted_vacancy_id": inserted_vacancy_id,
                "meta": {},
            },
        ).execute()
    except Exception as e:  # noqa: BLE001
        print(f"WARN funnel log failed: {e}", file=sys.stderr)
        return

def _today_str() -> str:
    return date.today().isoformat()


def _load_dedup_pairs(sb: Client, limit_rows: int = 15000) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    step = 1000
    for offset in range(0, limit_rows, step):
        try:
            res = (
                sb.table("vacancies")
                .select("company, role_title")
                .range(offset, offset + step - 1)
                .execute()
            )
        except Exception as e:  # noqa: BLE001
            print(f"WARN: dedup fetch offset={offset}: {e}", file=sys.stderr)
            break
        rows = getattr(res, "data", None) or []
        if not rows:
            break
        for r in rows:
            c = str(r.get("company") or "")
            t = str(r.get("role_title") or "")
            pairs.add((_norm_key(c), _norm_key(t)))
        if len(rows) < step:
            break
    return pairs


def _slug_display(slug: str) -> str:
    s = slug.strip().lower().removesuffix(".com").replace(".", " ").strip()
    return (s[:1].upper() + s[1:]) if s else slug


def _job_locations_blob(job: dict) -> str:
    parts = [str(job.get("location") or "")]
    for sec in job.get("secondaryLocations") or []:
        if isinstance(sec, dict):
            parts.append(str(sec.get("location") or ""))
    return " ".join(parts).lower()


def _location_ok(job: dict) -> bool:
    if os.environ.get("TIER4_RELAX_GEO", "").strip() in ("1", "true", "yes"):
        return bool(job.get("isRemote") or str(job.get("workplaceType") or "") == "Remote")
    loc = _job_locations_blob(job)
    if not (job.get("isRemote") or str(job.get("workplaceType") or "") in ("Remote", "Hybrid")):
        return False
    if any(m in loc for m in EU_MARKERS):
        return True
    # «Remote» без страны — допускаем с пометкой в details при вставке
    if job.get("isRemote") and len(loc.strip()) < 4:
        return True
    return False


def _published_ok(published_at: str | None, cutoff: datetime) -> bool:
    if not published_at:
        return False
    try:
        # Ashby: 2026-04-24T15:52:09.627+00:00
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except (TypeError, ValueError):
        return False


def _write_report(base: Path, counters: dict, job_id: str) -> None:
    out_dir = base / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = (job_id or "ashby")[:36].replace("/", "-")
    path = out_dir / f"ashby_report_{tag}.md"
    lines = [
        "# Отчёт Ashby Tier4\n",
        f"`{datetime.now(timezone.utc).isoformat()}` job_id=`{job_id or '—'}`\n\n",
        "## Счётчики\n\n",
        "```json\n",
        json.dumps(counters, ensure_ascii=False, indent=2),
        "\n```\n",
    ]
    text = "".join(lines)
    path.write_text(text, encoding="utf-8")
    (out_dir / "ashby_report_latest.md").write_text(text, encoding="utf-8")
    print(f"report written: {path}", flush=True)


def _ashby_slugs() -> list[str]:
    raw = os.environ.get("ASHBY_SLUGS", "kraken.com")
    return [p.strip() for p in raw.split(",") if p.strip()]


def main() -> None:
    job_id = os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or ""
    base = _base_dir()
    t4q = tier4_query.load_tier4_query(base)
    max_age = int(os.environ.get("TIER4_MAX_JOB_AGE_DAYS", "5"))
    delay = float(os.environ.get("ASHBY_DELAY_SEC", "0.65"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    print(f"[{datetime.now(timezone.utc).isoformat()}] ashby_crawler start job_id={job_id!r}")

    sb = _client()
    sid = _search_id()
    search_source = (os.environ.get("SEARCH_SOURCE") or "").strip() or "full_search"
    dedup = _load_dedup_pairs(sb)
    inserted = 0
    duplicates = 0
    skipped_title = 0
    skipped_geo = 0
    skipped_age = 0
    skipped_unlisted = 0
    errors = 0
    matched_preview: list[str] = []

    headers = {
        "User-Agent": "PrometeiWorker/1.0 (+ashby_crawler)",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=40.0, headers=headers) as client:
        for slug in _ashby_slugs():
            url_api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            try:
                t0 = time.time()
                r = client.get(url_api, params={"includeCompensation": "false"})
                latency_ms = int((time.time() - t0) * 1000)
                r.raise_for_status()
                data = r.json()
                if sid:
                    _log_target(
                        sb,
                        search_id=sid,
                        source=search_source,
                        platform="ashby",
                        url=url_api,
                        http_status=int(r.status_code),
                        latency_ms=latency_ms,
                        outcome="fetched_ok",
                        meta={"slug": slug},
                    )
            except Exception as e:  # noqa: BLE001
                errors += 1
                if sid:
                    _log_target(
                        sb,
                        search_id=sid,
                        source=search_source,
                        platform="ashby",
                        url=url_api,
                        http_status=None,
                        latency_ms=None,
                        outcome="http_error",
                        error=str(e),
                        meta={"slug": slug},
                    )
                print(f"ERR slug={slug} :: {e}", file=sys.stderr)
                time.sleep(delay)
                continue

            jobs = data.get("jobs") or []
            company = f"{_slug_display(slug)} (Ashby)"
            for job in jobs:
                if not job.get("isListed", True):
                    skipped_unlisted += 1
                    continue
                title = str(job.get("title") or "")
                if not TITLE_RE.search(title):
                    skipped_title += 1
                    continue
                if not _location_ok(job):
                    skipped_geo += 1
                    continue
                pub = job.get("publishedAt")
                if not _published_ok(str(pub) if pub else None, cutoff):
                    skipped_age += 1
                    continue

                role_title = title[:500]
                key = (_norm_key(company), _norm_key(role_title))
                if key in dedup:
                    duplicates += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=str(job.get("jobUrl") or job.get("applyUrl") or url_api)[:2000],
                            company=company,
                            role_title=role_title,
                            raw={"details": {"source": "ashby_posting_api", "slug": slug, "published_at": job.get("publishedAt")}},
                            decision="skip_duplicate",
                            reason="dup_company_role",
                        )
                    continue

                job_url = str(job.get("jobUrl") or job.get("applyUrl") or url_api)[:2000]
                if _vacancy_source_exists(sb, "jobs.ashbyhq.com", job_url):
                    duplicates += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=job_url,
                            company=company,
                            role_title=role_title,
                            raw={"details": {"source": "ashby_posting_api", "slug": slug, "published_at": pub}},
                            decision="skip_duplicate",
                            reason="dup_platform_url",
                        )
                    continue
                ambiguous_geo = not any(m in _job_locations_blob(job) for m in EU_MARKERS)
                details = {
                    "source": "ashby_posting_api",
                    "slug": slug,
                    "published_at": pub,
                    "is_remote": job.get("isRemote"),
                    "workplace_type": job.get("workplaceType"),
                    "location": job.get("location"),
                    "tier4_query": t4q,
                    "tier4_channel": "ashby",
                    "ambiguous_geo": ambiguous_geo,
                    "date_unknown": False,
                }
                row = {
                    "created_at": _today_str(),
                    "company": company[:500],
                    "role_title": role_title,
                    "platform": "jobs.ashbyhq.com"[:255],
                    "tier": "4_ashby",
                    "status": "New",
                    "score": 0,
                    "pipeline_status": "pending_enrich",
                    "details": json.dumps(details, ensure_ascii=False),
                    "url": job_url,
                }
                try:
                    ins = sb.table("vacancies").insert(row).execute()
                    ins_rows = getattr(ins, "data", None) or []
                    if not ins_rows:
                        errors += 1
                        continue
                    vid = ins_rows[0]["id"]
                    try:
                        sb.table("vacancy_sources").insert(
                            {
                                "vacancy_id": vid,
                                "platform": "jobs.ashbyhq.com"[:255],
                                "url": job_url,
                            },
                        ).execute()
                    except Exception:
                        pass
                    dedup.add(key)
                    inserted += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=job_url,
                            company=company,
                            role_title=role_title,
                            raw={"details": details},
                            decision="insert",
                            inserted_vacancy_id=int(vid),
                        )
                    if len(matched_preview) < 30:
                        matched_preview.append(f"{title} | {job.get('location')} | {pub}")
                except Exception as e:  # noqa: BLE001
                    errors += 1
                    print(f"ERR insert {slug} {title!r} :: {e}", file=sys.stderr)
            time.sleep(delay)

    counters = {
        "tier4_query_resolved": t4q,
        "inserted": inserted,
        "duplicates": duplicates,
        "skipped_title": skipped_title,
        "skipped_geo": skipped_geo,
        "skipped_age": skipped_age,
        "skipped_unlisted": skipped_unlisted,
        "errors": errors,
        "slugs": _ashby_slugs(),
        "max_age_days": max_age,
        "matched_preview": matched_preview,
    }
    _write_report(base, counters, job_id)
    print("--- сводка ---")
    print(json.dumps(counters, ensure_ascii=False, indent=2))
    print(f"[{datetime.now(timezone.utc).isoformat()}] ashby_crawler done")


if __name__ == "__main__":
    main()
