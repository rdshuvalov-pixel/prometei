#!/usr/bin/env python3
"""
Публичные фиды Tier 4 без браузера:
  - Greenhouse: GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs
  - Lever:      GET https://api.lever.co/v0/postings/{company}?mode=json
  - Workable:   POST https://apply.workable.com/api/v3/accounts/{slug}/jobs (пагинация nextPage)
  - Remotive:   GET https://remotive.com/api/remote-jobs?category=product (и fallback без category)
  - RemoteOK:   GET https://remoteok.com/api

Фильтр по заголовку (Product Manager / Lead / …) и возрасту ≤ TIER4_MAX_JOB_AGE_DAYS
по first_published (GH) / createdAt (Lever) / published (Workable).

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY;
GREENHOUSE_BOARD_TOKENS, LEVER_COMPANIES, WORKABLE_ACCOUNT_SLUGS (через запятую);
WORKABLE_MAX_PAGES (по умолчанию 20);
REMOTIVE_TIER4 / REMOTEOK_TIER4 — по умолчанию **1** (включено); задай **0** чтобы отключить;
TIER4_MAX_JOB_AGE_DAYS (по умолчанию 5); BOARD_FEED_DELAY_SEC (по умолчанию 0.55).
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

TITLE_RE = re.compile(
    r"(product\s+manager|product\s+lead|head\s+of\s+product|group\s+product|"
    r"director,?\s*product|vp\s*,?\s*product|chief\s+product\s+officer|\bcpo\b)",
    re.I,
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


def _candidate_url_exists(sb: Client, platform: str, url: str) -> bool:
    try:
        res = (
            sb.table("vacancy_candidates")
            .select("id")
            .eq("platform", platform[:255])
            .eq("external_url", url[:2000])
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
    company: str | None,
    role_title: str | None,
    platform: str,
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
                "source": "tier4_board_feeds",
                "tier": "4",
                "platform": platform[:255] if platform else None,
                "external_url": external_url[:2000],
                "company": company[:500] if company else None,
                "role_title": role_title[:500] if role_title else None,
                "published_at": None,
                "fingerprint": _fingerprint(company or "", role_title or "", external_url),
                "raw": raw or {},
                "pipeline_status": "pending_enrich",
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


def _max_age_days() -> int:
    raw = (os.environ.get("TIER4_MAX_JOB_AGE_DAYS") or "5").strip()
    try:
        n = int(raw)
    except ValueError:
        return 5
    return max(1, min(n, 365))


def _delay() -> float:
    try:
        return float(os.environ.get("BOARD_FEED_DELAY_SEC", "0.55"))
    except ValueError:
        return 0.55


def _workable_max_pages() -> int:
    raw = (os.environ.get("WORKABLE_MAX_PAGES") or "20").strip()
    try:
        n = int(raw)
    except ValueError:
        return 20
    return max(1, min(n, 100))


def _fetch_workable_jobs(client: httpx.Client, slug: str, delay: float) -> list[dict]:
    """Все страницы v3 /jobs для аккаунта (публичный API)."""
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    wh = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://apply.workable.com",
        "Referer": f"https://apply.workable.com/{slug}/",
    }
    out: list[dict] = []
    token: str | None = None
    for _ in range(_workable_max_pages()):
        body: dict = {
            "query": "",
            "token": token,
            "department": [],
            "location": [],
            "workplace": [],
            "worktype": [],
        }
        r = client.post(url, json=body, headers=wh, timeout=40.0)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            break
        batch = data.get("results") or []
        if not isinstance(batch, list):
            break
        out.extend(batch)
        token = data.get("nextPage")
        if not token or not batch:
            break
        time.sleep(delay)
    return out


def _load_dedup_pairs(sb: Client, limit_rows: int = 15000) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    step = 1000
    for offset in range(0, limit_rows, step):
        try:
            res = (
                sb.table("vacancy_candidates")
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
            pairs.add(
                (_norm_key(str(r.get("company") or "")), _norm_key(str(r.get("role_title") or ""))),
            )
        if len(rows) < step:
            break
    return pairs


def _parse_iso_any(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip()
    if not t:
        return None
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_lever_ms(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    try:
        sec = float(ms) / 1000.0
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _parse_epoch_s(ep: int | float | None) -> datetime | None:
    if ep is None:
        return None
    try:
        return datetime.fromtimestamp(float(ep), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _source_on(var: str, *, default: str = "1") -> bool:
    """По умолчанию включено; 0/false/no/off — выключить."""
    return (os.environ.get(var) or default).strip().lower() not in ("0", "false", "no", "off")


def _write_report(base: Path, counters: dict, job_id: str) -> None:
    out_dir = base / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = (job_id or "boards")[:36].replace("/", "-")
    path = out_dir / f"board_feeds_report_{tag}.md"
    text = (
        f"# Отчёт GH + Lever + Workable + Remotive + RemoteOK\n\n`{datetime.now(timezone.utc).isoformat()}` "
        f"job_id=`{job_id or '—'}`\n\n```json\n"
        f"{json.dumps(counters, ensure_ascii=False, indent=2)}\n```\n"
    )
    path.write_text(text, encoding="utf-8")
    (out_dir / "board_feeds_report_latest.md").write_text(text, encoding="utf-8")
    print(f"report written: {path}", flush=True)


def _split_env_list(name: str) -> list[str]:
    raw = os.environ.get(name) or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _try_insert(
    sb: Client,
    dedup: set[tuple[str, str]],
    *,
    company: str,
    role_title: str,
    job_url: str,
    platform: str,
    tier: str,
    details: dict,
    search_id: str | None,
) -> str:
    key = (_norm_key(company), _norm_key(role_title))
    if key in dedup:
        return "dup"
    if _vacancy_source_exists(sb, platform, job_url):
        return "dup_url"
    if _candidate_url_exists(sb, platform, job_url):
        return "dup_url"
    try:
        ins = sb.table("vacancy_candidates").insert(
            {
                "search_id": (search_id or None),
                "source": "tier4_board_feeds",
                "tier": tier[:64],
                "platform": platform[:255],
                "external_url": job_url[:2000],
                "company": company[:500],
                "role_title": role_title[:500],
                "published_at": None,
                "fingerprint": _fingerprint(company, role_title, job_url),
                "raw": {"details": details},
                "pipeline_status": "pending_enrich",
            },
        ).execute()
        ins_rows = getattr(ins, "data", None) or []
        if not ins_rows:
            return "err"
        dedup.add(key)
        return "ok"
    except Exception as e:  # noqa: BLE001
        print(f"ERR insert {job_url} :: {e}", file=sys.stderr)
        return "err"


def main() -> None:
    job_id = os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or ""
    base = _base_dir()
    t4q = tier4_query.load_tier4_query(base)
    cutoff = datetime.now(timezone.utc) - timedelta(days=_max_age_days())
    delay = _delay()
    sid = _search_id()
    search_source = (os.environ.get("SEARCH_SOURCE") or "").strip() or "full_search"

    gh_tokens = _split_env_list("GREENHOUSE_BOARD_TOKENS")
    lever_slugs = _split_env_list("LEVER_COMPANIES")
    workable_slugs = _split_env_list("WORKABLE_ACCOUNT_SLUGS")
    use_remotive = _source_on("REMOTIVE_TIER4")
    use_remoteok = _source_on("REMOTEOK_TIER4")

    if (
        not gh_tokens
        and not lever_slugs
        and not workable_slugs
        and not use_remotive
        and not use_remoteok
    ):
        print(
            "WARN: нет источников: задай GREENHOUSE_BOARD_TOKENS / LEVER_COMPANIES / "
            "WORKABLE_ACCOUNT_SLUGS или включи REMOTIVE_TIER4 / REMOTEOK_TIER4 (по умолчанию 1). Выход.",
            file=sys.stderr,
        )
        sys.exit(0)

    sb = _client()
    dedup = _load_dedup_pairs(sb)

    inserted = 0
    duplicates = 0
    errors = 0
    skipped_title = 0
    skipped_age = 0
    skipped_no_date = 0
    preview: list[str] = []

    headers = {
        "User-Agent": "PrometeiWorker/1.0 (+board_feeds_tier4)",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=55.0, headers=headers) as client:
        for token in gh_tokens:
            api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            try:
                t0 = time.time()
                r = client.get(api)
                latency_ms = int((time.time() - t0) * 1000)
                r.raise_for_status()
                data = r.json()
                if sid:
                    _log_target(
                        sb,
                        search_id=sid,
                        source=search_source,
                        platform="greenhouse",
                        url=api,
                        http_status=int(r.status_code),
                        latency_ms=latency_ms,
                        outcome="fetched_ok",
                        meta={"board_token": token},
                    )
            except Exception as e:  # noqa: BLE001
                errors += 1
                if sid:
                    _log_target(
                        sb,
                        search_id=sid,
                        source=search_source,
                        platform="greenhouse",
                        url=api,
                        http_status=None,
                        latency_ms=None,
                        outcome="http_error",
                        error=str(e),
                        meta={"board_token": token},
                    )
                print(f"ERR greenhouse {token!r} :: {e}", file=sys.stderr)
                time.sleep(delay)
                continue

            jobs = data.get("jobs") if isinstance(data, dict) else None
            if not isinstance(jobs, list):
                errors += 1
                print(f"ERR greenhouse {token!r} unexpected JSON", file=sys.stderr)
                time.sleep(delay)
                continue

            for job in jobs:
                title = str(job.get("title") or "").strip()
                if not TITLE_RE.search(title):
                    skipped_title += 1
                    continue
                pub = _parse_iso_any(str(job.get("first_published") or "")) or _parse_iso_any(
                    str(job.get("updated_at") or ""),
                )
                if pub is None:
                    skipped_no_date += 1
                    continue
                if pub < cutoff:
                    skipped_age += 1
                    continue

                company = str(job.get("company_name") or token).strip() or token
                company = f"{company} (Greenhouse)"
                url = str(job.get("absolute_url") or api)[:2000]
                loc = job.get("location") or {}
                loc_name = loc.get("name") if isinstance(loc, dict) else None
                details = {
                    "source": "greenhouse_board_api",
                    "board_token": token,
                    "first_published": job.get("first_published"),
                    "updated_at": job.get("updated_at"),
                    "location": loc_name,
                    "date_unknown": False,
                    "tier4_query": t4q,
                }
                st = _try_insert(
                    sb,
                    dedup,
                    company=company,
                    role_title=title[:500],
                    job_url=url,
                    platform="greenhouse.io",
                    tier="4_greenhouse",
                    details=details,
                    search_id=(sid or None),
                )
                if st == "ok":
                    inserted += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=url,
                            company=company,
                            role_title=title,
                            platform="greenhouse.io",
                            raw={"details": details},
                            decision="insert",
                        )
                    if len(preview) < 25:
                        preview.append(f"[GH {token}] {title}")
                elif st in ("dup", "dup_url"):
                    duplicates += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=url,
                            company=company,
                            role_title=title,
                            platform="greenhouse.io",
                            raw={"details": details},
                            decision="skip_duplicate",
                            reason=st,
                        )
                else:
                    errors += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=url,
                            company=company,
                            role_title=title,
                            platform="greenhouse.io",
                            raw={"details": details},
                            decision="skip_error",
                            reason="insert_error",
                        )
            time.sleep(delay)

        for slug in lever_slugs:
            api = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            try:
                t0 = time.time()
                r = client.get(api)
                latency_ms = int((time.time() - t0) * 1000)
                r.raise_for_status()
                data = r.json()
                if sid:
                    _log_target(
                        sb,
                        search_id=sid,
                        source=search_source,
                        platform="lever",
                        url=api,
                        http_status=int(r.status_code),
                        latency_ms=latency_ms,
                        outcome="fetched_ok",
                        meta={"company": slug},
                    )
            except Exception as e:  # noqa: BLE001
                errors += 1
                if sid:
                    _log_target(
                        sb,
                        search_id=sid,
                        source=search_source,
                        platform="lever",
                        url=api,
                        http_status=None,
                        latency_ms=None,
                        outcome="http_error",
                        error=str(e),
                        meta={"company": slug},
                    )
                print(f"ERR lever {slug!r} :: {e}", file=sys.stderr)
                time.sleep(delay)
                continue

            if not isinstance(data, list):
                errors += 1
                print(f"ERR lever {slug!r} unexpected JSON", file=sys.stderr)
                time.sleep(delay)
                continue

            display = slug.replace("-", " ").strip().title() or slug
            for job in data:
                title = str(job.get("text") or "").strip()
                if not TITLE_RE.search(title):
                    skipped_title += 1
                    continue
                pub = _parse_lever_ms(job.get("createdAt"))
                if pub is None:
                    skipped_no_date += 1
                    continue
                if pub < cutoff:
                    skipped_age += 1
                    continue

                company = f"{display} (Lever)"
                url = str(job.get("hostedUrl") or job.get("applyUrl") or api)[:2000]
                cats = job.get("categories") if isinstance(job.get("categories"), dict) else {}
                details = {
                    "source": "lever_public_api",
                    "company_slug": slug,
                    "createdAt": job.get("createdAt"),
                    "workplaceType": job.get("workplaceType"),
                    "location": cats.get("location") if isinstance(cats, dict) else None,
                    "date_unknown": False,
                    "tier4_query": t4q,
                }
                st = _try_insert(
                    sb,
                    dedup,
                    company=company,
                    role_title=title[:500],
                    job_url=url,
                    platform="jobs.lever.co",
                    tier="4_lever",
                    details=details,
                    search_id=(sid or None),
                )
                if st == "ok":
                    inserted += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=url,
                            company=company,
                            role_title=title,
                            platform="jobs.lever.co",
                            raw={"details": details},
                            decision="insert",
                        )
                    if len(preview) < 25:
                        preview.append(f"[LV {slug}] {title}")
                elif st in ("dup", "dup_url"):
                    duplicates += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=url,
                            company=company,
                            role_title=title,
                            platform="jobs.lever.co",
                            raw={"details": details},
                            decision="skip_duplicate",
                            reason=st,
                        )
                else:
                    errors += 1
                    if sid:
                        _log_candidate_and_decision(
                            sb,
                            search_id=sid,
                            external_url=url,
                            company=company,
                            role_title=title,
                            platform="jobs.lever.co",
                            raw={"details": details},
                            decision="skip_error",
                            reason="insert_error",
                        )
            time.sleep(delay)

        for slug in workable_slugs:
            try:
                jobs = _fetch_workable_jobs(client, slug, delay)
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"ERR workable {slug!r} :: {e}", file=sys.stderr)
                time.sleep(delay)
                continue

            display = slug.replace("-", " ").strip().title() or slug
            for job in jobs:
                jstate = str(job.get("state") or "").lower()
                if jstate and jstate != "published":
                    continue
                title = str(job.get("title") or "").strip()
                if not TITLE_RE.search(title):
                    skipped_title += 1
                    continue
                pub = _parse_iso_any(str(job.get("published") or ""))
                if pub is None:
                    skipped_no_date += 1
                    continue
                if pub < cutoff:
                    skipped_age += 1
                    continue

                shortcode = str(job.get("shortcode") or "").strip()
                job_url = (
                    f"https://apply.workable.com/{slug}/j/{shortcode}/"
                    if shortcode
                    else f"https://apply.workable.com/{slug}/"
                )[:2000]
                company = f"{display} (Workable)"
                loc = job.get("location")
                loc_s = None
                if isinstance(loc, dict):
                    loc_s = loc.get("city") or loc.get("country") or str(loc.get("name") or "")
                details = {
                    "source": "workable_public_api_v3",
                    "account_slug": slug,
                    "shortcode": shortcode or None,
                    "published": job.get("published"),
                    "remote": job.get("remote"),
                    "workplace": job.get("workplace"),
                    "location": loc_s,
                    "date_unknown": False,
                    "tier4_query": t4q,
                }
                st = _try_insert(
                    sb,
                    dedup,
                    company=company,
                    role_title=title[:500],
                    job_url=job_url,
                    platform="apply.workable.com",
                    tier="4_workable",
                    details=details,
                    search_id=(sid or None),
                )
                if st == "ok":
                    inserted += 1
                    if len(preview) < 25:
                        preview.append(f"[WK {slug}] {title}")
                elif st == "dup":
                    duplicates += 1
                else:
                    errors += 1
            time.sleep(delay)

        if use_remotive:
            rem_jobs: list[dict] = []
            for rem_url in (
                "https://remotive.com/api/remote-jobs?category=product",
                "https://remotive.com/api/remote-jobs",
            ):
                try:
                    r = client.get(rem_url)
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:  # noqa: BLE001
                    errors += 1
                    print(f"ERR remotive {rem_url!r} :: {e}", file=sys.stderr)
                    continue
                batch = data.get("jobs") if isinstance(data, dict) else None
                if isinstance(batch, list):
                    rem_jobs.extend(batch)
                time.sleep(delay)
            seen_r: set[str] = set()
            for job in rem_jobs:
                jid = str(job.get("id") or job.get("url") or "")
                if jid in seen_r:
                    continue
                seen_r.add(jid)
                title = str(job.get("title") or "").strip()
                if not TITLE_RE.search(title):
                    skipped_title += 1
                    continue
                pub = _parse_iso_any(str(job.get("publication_date") or ""))
                if pub is None:
                    skipped_no_date += 1
                    continue
                if pub < cutoff:
                    skipped_age += 1
                    continue
                company = str(job.get("company_name") or "Remotive").strip()
                company = f"{company} (Remotive)"
                url = str(job.get("url") or "https://remotive.com/remote-jobs")[:2000]
                details = {
                    "source": "remotive_public_api",
                    "category": job.get("category"),
                    "candidate_required_location": job.get("candidate_required_location"),
                    "publication_date": job.get("publication_date"),
                    "job_type": job.get("job_type"),
                    "date_unknown": False,
                    "tier4_query": t4q,
                    "aggregator_note": "Глобальный агрегатор; EU не фильтруется на уровне API",
                }
                st = _try_insert(
                    sb,
                    dedup,
                    company=company,
                    role_title=title[:500],
                    job_url=url,
                    platform="remotive.com",
                    tier="4_remotive",
                    details=details,
                    search_id=(sid or None),
                )
                if st == "ok":
                    inserted += 1
                    if len(preview) < 25:
                        preview.append(f"[RM] {title}")
                elif st == "dup":
                    duplicates += 1
                else:
                    errors += 1

        if use_remoteok:
            try:
                r = client.get("https://remoteok.com/api")
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"ERR remoteok :: {e}", file=sys.stderr)
                data = []

            if not isinstance(data, list):
                errors += 1
            else:
                seen_ok: set[str] = set()
                for job in data[1:]:
                    if not isinstance(job, dict) or "position" not in job:
                        continue
                    jid = str(job.get("id") or job.get("url") or "")
                    if jid in seen_ok:
                        continue
                    seen_ok.add(jid)
                    title = str(job.get("position") or "").strip()
                    if not TITLE_RE.search(title):
                        skipped_title += 1
                        continue
                    pub = _parse_iso_any(str(job.get("date") or "")) or _parse_epoch_s(
                        job.get("epoch"),
                    )
                    if pub is None:
                        skipped_no_date += 1
                        continue
                    if pub < cutoff:
                        skipped_age += 1
                        continue
                    company = str(job.get("company") or "RemoteOK").strip()
                    company = f"{company} (RemoteOK)"
                    url = str(job.get("url") or job.get("apply_url") or "https://remoteok.com")[
                        :2000
                    ]
                    details = {
                        "source": "remoteok_public_api",
                        "location": job.get("location"),
                        "date": job.get("date"),
                        "epoch": job.get("epoch"),
                        "tags": job.get("tags"),
                        "date_unknown": False,
                        "tier4_query": t4q,
                        "aggregator_note": "Глобальный агрегатор; EU не фильтруется на уровне API",
                    }
                    st = _try_insert(
                        sb,
                        dedup,
                        company=company,
                        role_title=title[:500],
                        job_url=url,
                        platform="remoteok.com",
                        tier="4_remoteok",
                        details=details,
                        search_id=(sid or None),
                    )
                    if st == "ok":
                        inserted += 1
                        if len(preview) < 25:
                            preview.append(f"[ROK] {title}")
                    elif st == "dup":
                        duplicates += 1
                    else:
                        errors += 1
            time.sleep(delay)

    counters = {
        "inserted": inserted,
        "duplicates": duplicates,
        "errors": errors,
        "skipped_title": skipped_title,
        "skipped_age": skipped_age,
        "skipped_no_date": skipped_no_date,
        "greenhouse_tokens": gh_tokens,
        "lever_slugs": lever_slugs,
        "workable_slugs": workable_slugs,
        "workable_max_pages": _workable_max_pages(),
        "remotive_tier4": use_remotive,
        "remoteok_tier4": use_remoteok,
        "tier4_query_resolved": t4q,
        "max_age_days": _max_age_days(),
        "preview": preview,
    }
    _write_report(base, counters, job_id)
    print("--- сводка ---")
    print(json.dumps(counters, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
