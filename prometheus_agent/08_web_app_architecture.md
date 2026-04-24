# 08 — Веб и инфраструктура (Прометей)

Краткая карта: Next.js на Vercel (`apps/web`), очередь `job_runs` в Supabase, воркер на VPS (Docker), постановка задач только через **`POST /api/jobs`**.

Пошаговые команды сборки, env и cron — в корневом [`README.md`](../README.md).

---

## 12. Чеклист «что задеплоено — куда смотреть»

Заполни **реальными значениями** (не коммить секреты в git).

| Что | Где / значение |
|-----|----------------|
| **Прод UI (Vercel)** | `https://________________.vercel.app` |
| **API постановки в очередь** | `{Production URL}/api/jobs` — `POST`, JSON `{"job_type":"script_crawl"}` или `watchlist`; при наличии `ENQUEUE_SECRET` — заголовок `Authorization: Bearer …` |
| **Supabase (проект)** | URL: `https://______.supabase.co` — регион и ref зафиксировать здесь: `________________` |
| **Таблицы** | `public.vacancies`, `public.vacancy_sources`, `public.job_runs` — миграция [`migrations/001_job_runs.sql`](../migrations/001_job_runs.sql) при новой базе |
| **Цели crawl** | [`search_targets.md`](search_targets.md), [`watchlist_targets.md`](watchlist_targets.md) — URL для `script_crawl.py` |
| **VPS воркер** | Хост: `________________` — `docker compose -f docker-compose.worker.yml`; env из [`.env.worker.example`](../.env.worker.example) |
| **Cron enqueue** | Расписание: `________________` — скрипт [`scripts/enqueue-cron.example.sh`](../scripts/enqueue-cron.example.sh), переменные `VERCEL_URL`, `ENQUEUE_SECRET` на машине с cron |
| **Репозиторий** | `https://github.com/rdshuvalov-pixel/prometei` (или актуальный remote) |

**Статус внедрения** (галочки вручную):

- [ ] Vercel: Root `apps/web`, Framework Next.js, env заданы, Production URL проверен
- [ ] Supabase: `job_runs` доступна, тестовый `POST /api/jobs` создаёт строку `queued`
- [ ] VPS: воркер запущен, в логах видно забор `queued` (или stub `done`)
- [ ] Cron: по расписанию дергается `POST` с Bearer (если включён секрет)
