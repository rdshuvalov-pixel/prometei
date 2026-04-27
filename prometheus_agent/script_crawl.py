#!/usr/bin/env python3
"""
Прогон «сырьё → Supabase»: читает URL из markdown, качает HTML, вытаскивает <title>,
дедуп по (company, role_title), вставляет vacancies (New) + vacancy_sources.

Скоринг 28 параметров и письма — следующий слой (или Cursor skill); здесь только crawl+insert.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY; опционально JOB_ID, JOB_TYPE, MAX_CRAWL_URLS,
CRAWL_DELAY_SEC, CRAWL_SKIP_DOMAINS (через запятую; по умолчанию weworkremotely.com).
CRAWL_ROTATE_URLS (по умолчанию 1): при лимите MAX_CRAWL_URLS очередной прогон берёт следующее
окно URL по кругу; смещение в prometheus_agent/out/crawl_url_cursor.json (том на VPS).
CRAWL_ROTATE_URLS=0 — старое поведение (всегда первые N URL).

Шаг 4 (листинг): script type application/ld+json с @type JobPosting и datePosted; старше
LISTING_MAX_AGE_DAYS (по умолчанию 5) не вставляем; без datePosted — вставка с date_unknown.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import tier4_query
from supabase import Client, create_client

URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+")
TIER_RE = re.compile(r"^\s*Tier:\s*(.+)\s*$", re.I)
LD_JSON_SCRIPT_RE = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.DOTALL,
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


def _blocked_domains() -> set[str]:
    raw = os.environ.get("CRAWL_SKIP_DOMAINS", "weworkremotely.com")
    parts = [p.strip().lower() for p in raw.split(",")]
    return {p for p in parts if p}


def _url_blocked(url: str, blocked: set[str]) -> bool:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == d or host.endswith(f".{d}") for d in blocked)


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


def _filter_blocked_urls(
    urls: list[tuple[str, str]],
    blocked: set[str],
) -> tuple[list[tuple[str, str]], list[str]]:
    kept: list[tuple[str, str]] = []
    skipped: list[str] = []
    for url, tier in urls:
        if _url_blocked(url, blocked):
            skipped.append(url)
            print(f"SKIP domain {url!r} tier={tier!r}", file=sys.stderr)
            continue
        kept.append((url, tier))
    return kept, skipped


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


def _listing_max_age_days() -> int:
    raw = (os.environ.get("LISTING_MAX_AGE_DAYS") or "5").strip()
    try:
        n = int(raw)
    except ValueError:
        return 5
    return max(1, min(n, 365))


def _is_jobposting(obj: dict) -> bool:
    t = obj.get("@type") or obj.get("type")
    if isinstance(t, list):
        return any(str(x).lower() == "jobposting" for x in t)
    return str(t or "").lower() == "jobposting"


def _iter_ld_json_objects(obj: object) -> list[dict]:
    """Обходит JSON-LD дерево, возвращает только узлы JobPosting."""
    found: list[dict] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if _is_jobposting(o):
                found.append(o)
            for k, v in o.items():
                if k == "@context":
                    continue
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return found


def _parse_dateposted(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _jobposting_rows_from_html(
    html: str,
    page_url: str,
    netloc: str,
    cutoff: datetime,
) -> tuple[list[dict], int]:
    """
    Возвращает (список payload для вставки, число пропущенных как устаревшие по datePosted).
    Каждый payload: company, role_title, job_url, details_dict.
    """
    skipped_stale = 0
    rows: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    for m in LD_JSON_SCRIPT_RE.finditer(html):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for jp in _iter_ld_json_objects(data):
            title = (jp.get("title") or jp.get("name") or "").strip()
            if not title:
                continue
            job_url_key = str(jp.get("url") or jp.get("sameAs") or page_url).strip()[:500]
            ukey = (_norm_key(title), _norm_key(job_url_key))
            if ukey in seen_keys:
                continue
            seen_keys.add(ukey)

            org = jp.get("hiringOrganization")
            company = netloc
            if isinstance(org, dict):
                company = str(org.get("name") or org.get("legalName") or company).strip() or company

            job_url = str(jp.get("url") or jp.get("sameAs") or page_url).strip()[:2000]
            if not job_url.startswith("http"):
                job_url = page_url[:2000]

            dp = _parse_dateposted(jp.get("datePosted"))
            if dp is not None and dp < cutoff:
                skipped_stale += 1
                continue

            date_unknown = dp is None
            details = {
                "mvp_crawl": True,
                "listing_source": "json_ld_jobposting",
                "datePosted_raw": jp.get("datePosted"),
                "date_unknown": date_unknown,
                "valid_through": jp.get("validThrough"),
                "employment_type": jp.get("employmentType"),
            }
            if date_unknown:
                details["listing_date_note"] = (
                    "⚠️ Дата публикации неизвестна (в JobPosting нет datePosted)"
                )
            else:
                details["datePosted_iso"] = dp.isoformat()

            rows.append(
                {
                    "company": company[:500],
                    "role_title": title[:500],
                    "job_url": job_url,
                    "details": details,
                },
            )

    return rows, skipped_stale


def _max_crawl_urls() -> int | None:
    """None = без лимита (MAX_CRAWL_URLS=0 или отрицательное)."""
    raw = (os.environ.get("MAX_CRAWL_URLS") or "30").strip()
    try:
        n = int(raw)
    except ValueError:
        return 30
    if n <= 0:
        return None
    return n


def _crawl_rotate_enabled() -> bool:
    raw = (os.environ.get("CRAWL_ROTATE_URLS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _crawl_cursor_path(out_dir: Path) -> Path:
    return out_dir / "crawl_url_cursor.json"


def _load_crawl_cursor(out_dir: Path, url_count: int, targets_key: str) -> int:
    if url_count <= 0:
        return 0
    p = _crawl_cursor_path(out_dir)
    if not p.is_file():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if str(data.get("targets_key", "")) != targets_key:
        return 0
    try:
        stored_n = int(data.get("url_count", -1))
    except (TypeError, ValueError):
        stored_n = -1
    if stored_n != url_count:
        return 0
    try:
        start = int(data.get("start", 0))
    except (TypeError, ValueError):
        return 0
    return start % url_count


def _save_crawl_cursor(
    out_dir: Path,
    next_start: int,
    url_count: int,
    targets_key: str,
) -> None:
    if url_count <= 0:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"WARN: не удалось сохранить crawl cursor: {e}", file=sys.stderr)
        return
    payload = {
        "start": next_start % url_count,
        "url_count": url_count,
        "targets_key": targets_key,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    p = _crawl_cursor_path(out_dir)
    tmp = p.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError as e:
        print(f"WARN: crawl cursor write failed: {e}", file=sys.stderr)


def _take_crawl_batch(
    urls: list[tuple[str, str]],
    base: Path,
    targets_path: Path,
) -> tuple[list[tuple[str, str]], dict[str, object], tuple[Path, int, int, str] | None]:
    """
    При лимите MAX_CRAWL_URLS и включённой ротации — окно из len(urls) по кругу.
    Возвращает (batch, meta для counters, аргументы для _save_crawl_cursor после успешного прогона).
    """
    max_n = _max_crawl_urls()
    L = len(urls)
    meta: dict[str, object] = {
        "crawl_url_total": L,
        "crawl_batch_size": L,
        "crawl_rotate_active": False,
        "crawl_cursor_before": 0,
        "crawl_cursor_after": 0,
    }
    if L == 0:
        return [], meta, None
    if max_n is None or L <= max_n:
        return list(urls), meta, None
    if not _crawl_rotate_enabled():
        meta["crawl_batch_size"] = max_n
        return urls[:max_n], meta, None
    out_dir = base / "out"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"WARN: {out_dir} недоступен, ротация отключена: {e}", file=sys.stderr)
        meta["crawl_batch_size"] = max_n
        return urls[:max_n], meta, None
    key = targets_path.name
    start = _load_crawl_cursor(out_dir, L, key)
    batch = [urls[(start + i) % L] for i in range(max_n)]
    after = (start + max_n) % L
    meta["crawl_rotate_active"] = True
    meta["crawl_cursor_before"] = start
    meta["crawl_cursor_after"] = after
    meta["crawl_batch_size"] = len(batch)
    meta["crawl_cursor_file"] = str(_crawl_cursor_path(out_dir))
    return batch, meta, (out_dir, after, L, key)


def _write_crawl_report(base: Path, counters: dict, job_id: str) -> Path | None:
    """Markdown-отчёт: шапка с ошибками и счётчиками по tier."""
    out_dir = base / "out"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"WARN: не удалось создать {out_dir}: {e}", file=sys.stderr)
        return None
    tag = (job_id or "local")[:36].replace("/", "-")
    path = out_dir / f"crawl_report_{tag}.md"
    fe = counters.get("fetch_errors_urls") or []
    sk = counters.get("skipped_blocked_urls") or []
    tier_s = counters.get("tier_stats") or {}
    lines = [
        "# Отчёт crawl (MVP)\n",
        f"Сгенерировано: `{datetime.now(timezone.utc).isoformat()}`\n",
        f"job_id: `{job_id or '—'}`\n\n",
        "## Недоступные URL\n\n",
    ]
    if fe:
        lines.extend(f"- {u}\n" for u in fe)
    else:
        lines.append("_нет_\n")
    lines.append("\n## Отфильтрованные доменом (CRAWL_SKIP_DOMAINS)\n\n")
    if sk:
        lines.extend(f"- {u}\n" for u in sk)
    else:
        lines.append("_нет_\n")
    lines.append("\n## Сводка по tier (попытки / вставки / дубликаты / ошибки)\n\n")
    if tier_s:
        for tier, st in sorted(tier_s.items(), key=lambda x: str(x[0])):
            lines.append(
                f"- **{tier}**: attempted={st.get('attempted', 0)} "
                f"inserted={st.get('inserted', 0)} dup={st.get('duplicates', 0)} "
                f"err={st.get('errors', 0)}\n",
            )
    else:
        lines.append("_нет данных_\n")
    lines.append("\n## Полные counters (JSON)\n\n```json\n")
    lines.append(json.dumps(counters, ensure_ascii=False, indent=2))
    lines.append("\n```\n")
    text = "".join(lines)
    path.write_text(text, encoding="utf-8")
    latest = out_dir / "crawl_report_latest.md"
    latest.write_text(text, encoding="utf-8")
    print(f"report written: {path}", flush=True)
    return path


def _run_crawl(sb: Client, urls: list[tuple[str, str]], dedup: set[tuple[str, str]], t4q: str) -> dict:
    inserted = 0
    duplicates = 0
    errors = 0
    fetch_errors_urls: list[str] = []
    ldjson_skipped_stale_total = 0
    ldjson_listings_seen = 0
    delay = float(os.environ.get("CRAWL_DELAY_SEC", "1.0"))
    tier_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attempted": 0, "inserted": 0, "duplicates": 0, "errors": 0},
    )
    max_age = _listing_max_age_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    headers = {
        "User-Agent": "PrometeiWorker/1.0 (+script_crawl)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }

    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        for url, tier in urls:
            tier_stats[tier]["attempted"] += 1
            netloc = urlparse(url).netloc or "unknown"
            try:
                r = client.get(url)
                r.raise_for_status()
                fetched_at = datetime.now(timezone.utc).isoformat()
                listing_rows, skipped_stale = _jobposting_rows_from_html(
                    r.text,
                    url,
                    netloc,
                    cutoff,
                )
                ldjson_skipped_stale_total += skipped_stale

                if listing_rows:
                    ldjson_listings_seen += len(listing_rows)
                    base_meta = {
                        "fetched_at": fetched_at,
                        "http_status": r.status_code,
                        "page_url": url,
                    }
                    for item in listing_rows:
                        company = item["company"]
                        role_title = item["role_title"]
                        job_url = item["job_url"]
                        details = {**base_meta, **item["details"], "tier4_query": t4q}
                        key = (_norm_key(company), _norm_key(role_title))
                        if key in dedup:
                            duplicates += 1
                            tier_stats[tier]["duplicates"] += 1
                            print(f"DUP  {job_url} -> {company!r} / {role_title!r}")
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
                            "details": json.dumps(details, ensure_ascii=False),
                            "url": job_url[:2000],
                        }
                        ins = sb.table("vacancies").insert(row).execute()
                        ins_rows = getattr(ins, "data", None) or []
                        if not ins_rows:
                            errors += 1
                            tier_stats[tier]["errors"] += 1
                            print(f"ERR insert empty {job_url}", file=sys.stderr)
                            continue
                        vid = ins_rows[0]["id"]
                        sb.table("vacancy_sources").insert(
                            {
                                "vacancy_id": vid,
                                "platform": netloc[:255],
                                "url": job_url[:2000],
                            },
                        ).execute()
                        dedup.add(key)
                        inserted += 1
                        tier_stats[tier]["inserted"] += 1
                        print(f"OK   {job_url} -> id={vid} {company!r} / {role_title!r}")
                    time.sleep(delay)
                    continue

                title = _extract_title(r.text)
                if not title:
                    title = f"fetch:{netloc}"
                company, role_title = _guess_company_role(title, netloc)
                key = (_norm_key(company), _norm_key(role_title))
                if key in dedup:
                    duplicates += 1
                    tier_stats[tier]["duplicates"] += 1
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
                            "listing_source": "page_title_fallback",
                            "fetched_at": fetched_at,
                            "http_status": r.status_code,
                            "date_unknown": True,
                            "tier4_query": t4q,
                            "listing_date_note": (
                                "⚠️ Дата публикации неизвестна (нет JobPosting в ld+json)"
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    "url": url[:2000],
                }
                ins = sb.table("vacancies").insert(row).execute()
                ins_rows = getattr(ins, "data", None) or []
                if not ins_rows:
                    errors += 1
                    tier_stats[tier]["errors"] += 1
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
                tier_stats[tier]["inserted"] += 1
                print(f"OK   {url} -> id={vid} {company!r} / {role_title!r}")
            except Exception as e:  # noqa: BLE001
                errors += 1
                tier_stats[tier]["errors"] += 1
                fetch_errors_urls.append(url)
                print(f"ERR  {url} :: {e}", file=sys.stderr)
            time.sleep(delay)

    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "errors": errors,
        "urls_attempted": len(urls),
        "fetch_errors_urls": fetch_errors_urls[:200],
        "tier_stats": dict(tier_stats),
        "listing_max_age_days": max_age,
        "ldjson_listings_seen": ldjson_listings_seen,
        "ldjson_skipped_stale_date": ldjson_skipped_stale_total,
    }


def main() -> None:
    job_type = os.environ.get("JOB_TYPE") or "script_crawl"
    job_id = os.environ.get("WORKER_JOB_ID") or os.environ.get("JOB_ID") or ""
    base = _base_dir()

    print(f"[{datetime.now(timezone.utc).isoformat()}] script_crawl start job_type={job_type!r} job_id={job_id!r}")

    if job_type == "watchlist":
        path = base / "watchlist_targets.md"
    else:
        path = base / "search_targets.md"

    urls = _parse_targets_file(path)
    blocked = _blocked_domains()
    urls, skipped_blocked = _filter_blocked_urls(urls, blocked)
    print(
        f"targets file: {path} urls_found={len(urls) + len(skipped_blocked)} "
        f"after_domain_filter={len(urls)} blocked_domains={sorted(blocked)!r}",
    )
    if skipped_blocked:
        print(f"skipped_blocked_count={len(skipped_blocked)}", file=sys.stderr)

    sb = _client()
    before_v = _count_head(sb, "vacancies")
    before_s = _count_head(sb, "vacancy_sources")

    counters: dict = {
        "before_vacancies": before_v,
        "before_sources": before_s,
        "skipped_blocked_urls": skipped_blocked[:200],
        "max_crawl_urls_env": os.environ.get("MAX_CRAWL_URLS", "30"),
        "max_crawl_urls_resolved": _max_crawl_urls(),
    }

    if not urls:
        print("Нет URL (добавь незакомментированные https:// строки в markdown). Сводка:")
        counters["skipped"] = "no_urls"
    else:
        batch, batch_meta, cursor_save = _take_crawl_batch(urls, base, path)
        counters.update(batch_meta)
        if batch_meta.get("crawl_rotate_active"):
            print(
                f"crawl rotate: total={batch_meta.get('crawl_url_total')} "
                f"cursor {batch_meta.get('crawl_cursor_before')}→{batch_meta.get('crawl_cursor_after')} "
                f"batch={batch_meta.get('crawl_batch_size')}",
                flush=True,
            )
        dedup = _load_dedup_pairs(sb)
        print(f"dedup_pairs_loaded={len(dedup)}")
        t4q = tier4_query.load_tier4_query(base)
        crawl_stats = _run_crawl(sb, batch, dedup, t4q)
        counters["tier4_query_resolved"] = t4q
        counters.update(crawl_stats)
        if cursor_save is not None:
            od, after, n_urls, tkey = cursor_save
            _save_crawl_cursor(od, after, n_urls, tkey)

    after_v = _count_head(sb, "vacancies")
    after_s = _count_head(sb, "vacancy_sources")
    counters["after_vacancies"] = after_v
    counters["after_sources"] = after_s

    _write_crawl_report(base, counters, job_id)

    print("--- сводка ---")
    print(json.dumps(counters, ensure_ascii=False, indent=2))
    print(f"[{datetime.now(timezone.utc).isoformat()}] script_crawl done")


if __name__ == "__main__":
    main()
