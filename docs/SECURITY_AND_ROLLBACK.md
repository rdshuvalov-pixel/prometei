# Security & Rollback — Prometei

## 1) Секреты (где хранятся)
- **Vercel (Production env):**
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `ENQUEUE_SECRET`
- **VPS `/opt/prometei/.env.worker`:**
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `OPENAI_API_KEY` (OpenRouter)
  - любые лимиты LLM (`LLM_MIN_SCORE`, `VACANCY_LLM_BATCH`)

Запрет: не хранить секреты в git, в issue/PR, в логах.

## 2) Ротация (минимальный регламент)
Рекомендуемая периодичность:
- `ENQUEUE_SECRET`: раз в 30–90 дней или при утечке
- `SUPABASE_SERVICE_ROLE_KEY`: раз в 30–90 дней или при утечке
- `OPENAI_API_KEY`: при подозрении на утечку или аномальном расходе

Шаги:
1) Создать новый секрет (OpenRouter key / случайная строка / service_role key).
2) Обновить в Vercel/VPS.
3) Перезапустить сервисы:
   - Vercel: redeploy
   - VPS: `docker compose ... up -d`
4) Проверить smoke: POST `/api/jobs` → job_runs queued → worker done.

## 3) Откат (VPS worker)
Хранить на VPS “последний хороший” SHA:
- в файле `/opt/prometei/LAST_GOOD_SHA` (вне git)

Откат:
```bash
cd /opt/prometei
git fetch origin main
git checkout <sha>
docker compose -f docker-compose.worker.yml up -d --build
```

После отката: проверить `/jobs` и свежий `job_runs` прогон.

## 4) Откат (Vercel web)
- Откатить через Vercel Deployments (Promote previous deployment) или через git revert и redeploy.

