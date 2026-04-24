# prometei

## Vercel (если видишь `404: NOT_FOUND` при успешном Deploy)

1. **Project → Settings → General → Root Directory:** `apps/web` (не `app`, не корень репо).
2. **Build & Development → Framework Preset:** **Next.js** (не «Other» / не Static).
3. **Output Directory:** оставь **пустым** (дефолт Next на Vercel). Любой кастомный `dist`/`out`/`public` ломает выдачу.
4. Открой **точный** Production URL из вкладки **Deployments → последний деплой → Visit** (не старый preview-URL).
5. Если включена **Deployment Protection** (SSO), без входа в Vercel может быть не тот ответ — для проверки временно ослабь защиту или залогинься.

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
| `ENQUEUE_SECRET` | опционально; если задан — `POST /api/jobs` только с `Authorization: Bearer …` |

Запиши сюда боевой адрес (из **Deployments → Production → Visit**), чтобы не искать потом:

**Production URL:** `https://________________.vercel.app`

После правок env — **Redeploy** production.
