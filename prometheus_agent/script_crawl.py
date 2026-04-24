#!/usr/bin/env python3
"""
Прогон «сырьё → Supabase»: читает URL из markdown, качает HTML, вытаскивает <title>,
дедуп по (company, role_title), вставляет vacancies (New) + vacancy_sources.

Скоринг 28 параметров и письма — следующий слой (или Cursor skill); здесь только crawl+insert.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY; опционально JOB_ID, JOB_TYPE, MAX_CRAWL_URLS, CRAWL_DELAY_SEC.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from supabase import Client, create_client

URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+")
TIER_RE = re.compile(r"^\s*Tier:\s*(.+)\s*$", re.I)


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


def _count_head(sb: Client, table: str) -> int | None:
    try:
        res = sb.table(table).select("id", count="exact", head=True).execute()
        c = getattr(res, "count", None)
        return int(c) if c is not None else None
    except Exception as e:  # noqa: BLE001
        print(f"WARN: count {table}: {e}", file=sys.stderr)
        return None


def _norm_key(s: str) -> str:
    return " ".join(s.lower().strip().split())


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


def _parse_targets_file(path: Path) -> list[tuple[str, str]]:
    """Список (url, tier_label)."""
    if not path.is_file():
        return []
    current_tier = "unknown"
    out: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m_t = TIER_RE.match(raw)
        if m_t:
            current_tier = m_t.group(1).strip()[:64]
            continue
        for m in URL_RE.finditer(line):
            url = m.group(0).rstrip(").,;]")
            if url.startswith("http"):
                out.append((url, current_tier))
    return out


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]{1,800})</title>", html, re.I | re.DOTALL)
    if not m:
        return ""
    return html_lib.unescape(re.sub(r"\s+", " ", m.group(1)).strip())


def _guess_company_role(title: str, netloc: str) -> tuple[str, str]:
    t = title.strip() or netloc or "unknown"
    for sep in (" | ", " - ", " – ", " — ", " · "):
        if sep in t:
            a, b = t.split(sep, 1)
            a, b = a.strip(), b.strip()
            if len(a) > 1 and len(b) > 1:
                return a[:500], b[:500]
    if len(t) > 120:
        return (netloc or "web")[:500], t[:500]
    return (netloc or "web")[:500], (t or "role")[:500]


def _today_str() -> str:
    return date.today().isoformat()


def _run_crawl(sb: Client, urls: list[tuple[str, str]], dedup: set[tuple[str, str]]) -> dict:
    inserted = 0
    duplicates = 0
    errors = 0
    max_n = int(os.environ.get("MAX_CRAWL_URLS", "30"))
    delay = float(os.environ.get("CRAWL_DELAY_SEC", "1.0"))
    urls = urls[:max_n]

    headers = {
        "User-Agent": "PrometeiWorker/1.0 (+script_crawl)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }

    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        for url, tier in urls:
            netloc = urlparse(url).netloc or "unknown"
            try:
                r = client.get(url)
                r.raise_for_status()
                title = _extract_title(r.text)
                if not title:
                    title = f"fetch:{netloc}"
                company, role_title = _guess_company_role(title, netloc)
                key = (_norm_key(company), _norm_key(role_title))
                if key in dedup:
                    duplicates += 1
                    print(f"DUP  {url} -> {company!r} / {role_title!r}")
                    time.sleep(delay)
                    continue

                row = {
                    "created_at": _today_str(),
                    "company": company,
                    "role_title": role_title,
                    "platform": netloc[:255],
                    "tier": tier[:64],
                    "status": "New",
                    "score": 0,
                    "match_status": "pending_score",
                    "details": json.dumps(
                        {
                            "mvp_crawl": True,
                            "fetched_at": datetime.now(UTC).isoformat(),
                            "http_status": r.status_code,
                        },
                        ensure_ascii=False,
                    ),
                    "url": url[:2000],
                }
                ins = sb.table("vacancies").insert(row).select("id").execute()
                ins_rows = getattr(ins, "data", None) or []
                if not ins_rows:
                    errors += 1
                    print(f"ERR insert empty {url}", file=sys.stderr)
                    time.sleep(delay)
                    continue
                vid = ins_rows[0]["id"]
                sb.table("vacancy_sources").insert(
                    {
                        "vacancy_id": vid,
                        "platform": netloc[:255],
                        "url": url[:2000],
                    },
                ).execute()
                dedup.add(key)
                inserted += 1
                print(f"OK   {url} -> id={vid} {company!r} / {role_title!r}")
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"ERR  {url} :: {e}", file=sys.stderr)
            time.sleep(delay)

    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "errors": errors,
        "urls_attempted": len(urls),
    }


def main() -> None:
    job_type = os.environ.get("JOB_TYPE") or "script_crawl"
    job_id = os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or ""
    base = _base_dir()

    print(f"[{datetime.now(UTC).isoformat()}] script_crawl start job_type={job_type!r} job_id={job_id!r}")

    if job_type == "watchlist":
        path = base / "watchlist_targets.md"
    else:
        path = base / "search_targets.md"

    urls = _parse_targets_file(path)
    print(f"targets file: {path} urls_found={len(urls)}")

    sb = _client()
    before_v = _count_head(sb, "vacancies")
    before_s = _count_head(sb, "vacancy_sources")

    counters: dict = {"before_vacancies": before_v, "before_sources": before_s}

    if not urls:
        print("Нет URL (добавь незакомментированные https:// строки в markdown). Сводка:")
        counters["skipped"] = "no_urls"
    else:
        dedup = _load_dedup_pairs(sb)
        print(f"dedup_pairs_loaded={len(dedup)}")
        crawl_stats = _run_crawl(sb, urls, dedup)
        counters.update(crawl_stats)

    after_v = _count_head(sb, "vacancies")
    after_s = _count_head(sb, "vacancy_sources")
    counters["after_vacancies"] = after_v
    counters["after_sources"] = after_s

    print("--- сводка ---")
    print(json.dumps(counters, ensure_ascii=False, indent=2))
    print(f"[{datetime.now(UTC).isoformat()}] script_crawl done")


if __name__ == "__main__":
    main()
