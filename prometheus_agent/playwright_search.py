#!/usr/bin/env python3
"""
Playwright lane: JS/SPA career pages.

Goal: for each target URL, try to find vacancy links whose visible text contains KEYWORD
(default: "Product Manager"). Write them to vacancy_candidates (draft) and log outcomes.

This is intentionally conservative: if we can't reliably extract role URLs, we record
searched_no_results / skip_not_searchable rather than emitting null candidates.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright
from supabase import Client, create_client

# NOTE: this file is executed as a script in the worker container, not as a package module.
from platform_search import PlatformLane, detect_platform

_SUMMARY_MARKER = "--- сводка ---"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host(url: str) -> str:
    h = (urlparse(url).netloc or "").lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def _fingerprint(*parts: str) -> str:
    s = "|".join((p or "").strip().lower() for p in parts)
    return hashlib.sha1(s.encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        raise SystemExit(2)
    return create_client(url, key)


def _search_id() -> str:
    return (os.environ.get("SEARCH_ID") or "").strip()


def _log_target(
    sb: Client,
    *,
    search_id: str,
    source: str,
    tier: str | None,
    platform: str,
    url: str,
    outcome: str,
    http_status: int | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
    meta: dict | None = None,
) -> None:
    try:
        sb.table("search_targets_log").insert(
            {
                "search_id": search_id,
                "source": source,
                "tier": tier[:64] if tier else None,
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


def _insert_candidate(
    sb: Client,
    *,
    search_id: str,
    tier: str | None,
    platform: str,
    external_url: str,
    company: str,
    role_title: str,
    raw: dict,
) -> None:
    if not company.strip() or not role_title.strip():
        return
    if not external_url.startswith("http"):
        return
    try:
        sb.table("vacancy_candidates").insert(
            {
                "search_id": search_id,
                "source": "playwright",
                "tier": tier[:64] if tier else None,
                "platform": platform[:255] if platform else None,
                "external_url": external_url[:2000],
                "company": company[:500],
                "role_title": role_title[:500],
                "published_at": None,
                "fingerprint": _fingerprint(company, role_title, external_url),
                "raw": raw or {},
            },
        ).execute()
    except Exception:
        return


@dataclass
class Target:
    url: str
    tier: str


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_targets_from_search_md(path: Path) -> list[Target]:
    # Reuse the markdown convention: lines with URLs, tier blocks as "Tier: N".
    tier = "unknown"
    out: list[Target] = []
    url_re = re.compile(r"https?://[^\s\)\]<>\"']+")
    tier_re = re.compile(r"^\s*Tier:\s*(.+)\s*$", re.I)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = tier_re.match(raw)
        if m:
            tier = m.group(1).strip()[:64] or "unknown"
            continue
        for mm in url_re.finditer(line):
            url = mm.group(0).rstrip(").,;]")
            if url.startswith("http"):
                out.append(Target(url=url, tier=tier))
    return out


def _take_batch(urls: list[Target]) -> list[Target]:
    raw = (os.environ.get("PLAYWRIGHT_MAX_URLS") or os.environ.get("MAX_CRAWL_URLS") or "30").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 30
    if n <= 0:
        return urls
    return urls[:n]


def main() -> None:
    sid = _search_id()
    if not sid:
        print(_SUMMARY_MARKER)
        print(json.dumps({"job_type": "playwright_search", "warn": "missing SEARCH_ID"}, ensure_ascii=False))
        return

    keyword = (os.environ.get("KEYWORD") or "Product Manager").strip()
    kw_re = re.compile(re.escape(keyword), re.I)
    sb = _client()

    search_md = _base_dir() / "search_targets.md"
    targets = _load_targets_from_search_md(search_md)
    batch = _take_batch(targets)

    counters = {
        "job_type": "playwright_search",
        "keyword": keyword,
        "targets_total": len(targets),
        "targets_attempted": len(batch),
        "searched_ok": 0,
        "searched_no_results": 0,
        "skipped_not_searchable": 0,
        "errors": 0,
        "candidates_inserted": 0,
        "started_at": _utc_iso(),
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(int(os.environ.get("PLAYWRIGHT_TIMEOUT_MS", "30000")))

        for t in batch:
            d = detect_platform(t.url)
            platform = _host(t.url) or d.canonical

            if d.lane != PlatformLane.playwright:
                counters["skipped_not_searchable"] += 1
                _log_target(
                    sb,
                    search_id=sid,
                    source="playwright",
                    tier=t.tier,
                    platform=platform,
                    url=t.url,
                    outcome="skip_not_searchable",
                    meta={"kind": d.kind, "lane": d.lane},
                )
                continue

            t0 = time.time()
            try:
                page.goto(t.url, wait_until="domcontentloaded")
                latency_ms = int((time.time() - t0) * 1000)

                # Simple extraction: scan anchors with keyword in visible text.
                anchors = page.eval_on_selector_all(
                    "a",
                    """(els) => els
                      .map(a => ({text: (a.innerText||'').trim(), href: a.href||a.getAttribute('href')||''}))
                      .filter(x => x.text && x.href)""",
                )
                matches: list[dict] = []
                for a in anchors[:5000]:
                    text = str(a.get("text") or "").strip()
                    href = str(a.get("href") or "").strip()
                    if not text or not href:
                        continue
                    if not kw_re.search(text):
                        continue
                    abs_url = href if href.startswith("http") else urljoin(t.url, href)
                    matches.append({"title": text, "url": abs_url})
                    if len(matches) >= int(os.environ.get("PLAYWRIGHT_MAX_MATCHES", "40")):
                        break

                if matches:
                    counters["searched_ok"] += 1
                    _log_target(
                        sb,
                        search_id=sid,
                        source="playwright",
                        tier=t.tier,
                        platform=platform,
                        url=t.url,
                        outcome="searched_ok",
                        http_status=200,
                        latency_ms=latency_ms,
                        meta={"matches": len(matches), "kind": d.kind},
                    )
                    company = platform
                    for m in matches:
                        _insert_candidate(
                            sb,
                            search_id=sid,
                            tier=t.tier,
                            platform=platform,
                            external_url=str(m["url"]),
                            company=company,
                            role_title=str(m["title"]),
                            raw={"via": "playwright", "target_url": t.url, "kind": d.kind},
                        )
                        counters["candidates_inserted"] += 1
                else:
                    counters["searched_no_results"] += 1
                    _log_target(
                        sb,
                        search_id=sid,
                        source="playwright",
                        tier=t.tier,
                        platform=platform,
                        url=t.url,
                        outcome="searched_no_results",
                        http_status=200,
                        latency_ms=latency_ms,
                        meta={"kind": d.kind},
                    )
            except (PWTimeout, PWError, Exception) as e:  # noqa: BLE001
                counters["errors"] += 1
                _log_target(
                    sb,
                    search_id=sid,
                    source="playwright",
                    tier=t.tier,
                    platform=platform,
                    url=t.url,
                    outcome="http_error",
                    error=str(e),
                    meta={"kind": d.kind},
                )
                continue

        context.close()
        browser.close()

    counters["finished_at"] = _utc_iso()
    print(_SUMMARY_MARKER)
    print(json.dumps(counters, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

