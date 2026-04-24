# prometei

## Vercel (если видишь `404: NOT_FOUND` при успешном Deploy)

1. **Project → Settings → General → Root Directory:** `apps/web` (не `app`, не корень репо).
2. **Build & Development → Framework Preset:** **Next.js** (не «Other» / не Static).
3. **Output Directory:** оставь **пустым** (дефолт Next на Vercel). Любой кастомный `dist`/`out`/`public` ломает выдачу.
4. Открой **точный** Production URL из вкладки **Deployments → последний деплой → Visit** (не старый preview-URL).
5. Если включена **Deployment Protection** (SSO), **`curl`** и **cron** получат HTML «Authentication Required», а не JSON приложения. Либо ослабь защиту для **Production**, либо включи **Protection Bypass for Automation** и передавай заголовок **`x-vercel-protection-bypass`** (см. [`docs/ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md`](docs/ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md) §8.0), либо используй **`vercel curl`** под залогиненным CLI.

После смены настроек — **Redeploy** без кэша (сними галку *Use existing Build Cache*).

---

## 1. Supabase — `job_runs`

1. В **SQL Editor** выполни скрипт из [`migrations/001_job_runs.sql`](migrations/001_job_runs.sql) (если таблицы ещё нет). Если таблица уже создана вручную — сверь колонки: нужны как минимум `job_type`, `status`, `counters`, `payload` (как в скрипте).
2. В **Table Editor** проверь `public.job_runs` и при необходимости одну тестовую строку со статусом `queued`.

Веб и API ожидают вставку с полями **`job_type`**, **`counters`** (можно `{}`), **`payload`**, **`status`**.

---

## 2. Vercel — Production env и URL

В **Project → Settings → Environment Variables** (Production) задай:

| Переменная | Назначение |
|------------|------------|
| `NEXT_PUBLIC_SUPABASE_URL` | URL проекта Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role (только сервер) |
| `ENQUEUE_SECRET` | **рекомендуется** в проде: без него `POST /api/jobs` доступен всем; с секретом нужен `Authorization: Bearer …` |

Постановка в очередь: **POST /api/jobs** (cron, curl, скрипт).

Запиши сюда боевой адрес (из **Deployments → Production → Visit**), чтобы не искать потом:

**Production URL:** `https://________________.vercel.app`

После правок env — **Redeploy** production.

---

## 3. Воркер на VPS (Contabo и т.п.)

**Пошаговые команды в терминале (SSH, Docker, cron):** [`docs/ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md`](docs/ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md).  
**Перед эксплуатацией:** чеклист [`docs/PREPROD_CHECKLIST.md`](docs/PREPROD_CHECKLIST.md).

1. Скопируй на сервер репозиторий (или только каталоги `worker/`, `Dockerfile.worker`, `docker-compose.worker.yml`, `requirements-worker.txt`).
2. `cp .env.worker.example .env.worker` и заполни **`SUPABASE_URL`**, **`SUPABASE_SERVICE_ROLE_KEY`**.
3. В **`.env.worker`** задай **`WORKER_CMD`**: либо **`python3 /app/prometheus_agent/script_crawl.py`** (career crawl + отчёт в `prometheus_agent/out/`), либо **`python3 /app/prometheus_agent/worker_dispatch.py`** — тогда по **`job_type`**: crawl, **`tier4_ashby`**, **`tier4_board_feeds`** (Greenhouse + Lever, см. [`board_feeds_tier4.py`](prometheus_agent/board_feeds_tier4.py)). Полный список URL: **`MAX_CRAWL_URLS=0`**. Пока **`WORKER_CMD` пуст** — stub **`done`**.
4. Запуск: `docker compose -f docker-compose.worker.yml up -d --build` (из корня репо). Логи: `docker compose -f docker-compose.worker.yml logs -f worker`.

Один проход без цикла (отладка):  
`docker compose -f docker-compose.worker.yml run --rm worker python poll_jobs.py --once`

---

## 4. Cron → постановка в очередь через Vercel

1. В Vercel добавь **`ENQUEUE_SECRET`** (Production) и **Redeploy**.
2. На VPS в cron вызывай скрипт по образцу [`scripts/enqueue-cron.example.sh`](scripts/enqueue-cron.example.sh): экспортируй **`VERCEL_URL`** (боевой `https://….vercel.app`) и **`ENQUEUE_SECRET`**.
3. Права: `chmod +x scripts/enqueue-cron.example.sh` (локально или на сервере).

---

## 5. Чеклист «что где лежит» (§12)

Заполняемый список URL, хостов и галочек — в [`prometheus_agent/08_web_app_architecture.md`](prometheus_agent/08_web_app_architecture.md), раздел **12**.
