# План crawl / Tier 4 — статус (синхронизируй с `~/.cursor/plans/план_прометей_crawl_*.plan.md` при желании)

Последнее обновление: 2026-04-24.

## Перед эксплуатацией (прод)

Полный пошаговый чеклист секретов, Supabase, Vercel, VPS, cron, smoke-тестов и эксплуатации: **[`docs/PREPROD_CHECKLIST.md`](../docs/PREPROD_CHECKLIST.md)**. Закрывай пункты там перед выводом пайплайна в бой.

---

## Шаг 1 — Прогон и лимиты на VPS

~~Код: `MAX_CRAWL_URLS=0` без лимита, `CRAWL_DELAY_SEC`, Docker §5.1, том `out/` на хост.~~

**Ещё:** операторски подтвердить на своём VPS после `git pull` / `docker compose up --build`: реальный полный прогон, разбор `fetch_errors_urls` в отчёте.

---

## Шаг 2 — Документация окружения

~~`.env.worker.example`, `docs/ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md` (в т.ч. §5.1–5.2), README, §08, `CRAWL_SKIP_DOMAINS`, dispatch, Ashby/GH/Lever env.~~

---

## Шаг 3 — Tier 4

~~Ashby: `ashby_crawler.py` + `tier4_ashby`.~~  
~~Greenhouse + Lever: `board_feeds_tier4.py` + `tier4_board_feeds`.~~  
~~`worker_dispatch.py` по `JOB_TYPE`.~~

**Ещё:** LinkedIn / Indeed и т.п. из `search_targets.md` — отдельно (антибот); ~~Workable, Remotive, RemoteOK~~ в `board_feeds_tier4.py`; ~~чтение `_TIER4_QUERY` / env `TIER4_QUERY`~~ — [`tier4_query.py`](tier4_query.py) + поле в `details` / сводке.

---

## Шаг 4 — Даты и «≤ 5 дней»

~~JSON-LD `JobPosting` в `script_crawl.py` + `LISTING_MAX_AGE_DAYS`.~~  
~~Даты в Ashby / GH / Lever фидах.~~

**Ещё:** парсинг листингов там, где нет JSON-LD и нет публичного JSON (кастомные career, часть ATS).

---

## Шаг 5 — Шапка отчёта

~~`prometheus_agent/out/crawl_report_latest.md`, `ashby_report_latest.md`, `board_feeds_report_latest.md` + счётчики в JSON сводке (`tier_stats`, ошибки URL).~~

**Ещё (опционально):** ~~парсить stdout → `job_runs.counters`~~ — в [`worker/poll_jobs.py`](../worker/poll_jobs.py) после `--- сводка ---` (выкл.: `WORKER_PARSE_CHILD_COUNTERS=0`).

---

## Шаг 6 — Cron и нагрузка

~~В доке и примерах: разные `job_type`, комментарии в `enqueue-cron.example.sh`.~~

**Ещё:** на VPS завести **разные** cron-строки (например crawl ежедневно, `tier4_ashby` + `tier4_board_feeds` реже), поднять `JOB_TIMEOUT_SEC` при полном crawl.

---

## Зависимости (актуально)

| Блок        | Статус |
|------------|--------|
| Инфра MVP  | готово в репо |
| Tier 4 «топ» ATS | Ashby + GH + Lever готово |
| Tier 4 остальное | не сделано |
| Глубокий парсинг career | частично (JSON-LD) |
| Операции VPS/cron | на стороне пользователя |
