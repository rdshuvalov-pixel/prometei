# Prod Runbook — Prometei

Этот документ — краткий регламент эксплуатации: где смотреть состояние, что делать при сбоях, и какие лимиты держать.

## 1) Где смотреть
- **Supabase → public.job_runs**
  - `status`: queued / running / done / failed
  - `error`: причина падения (если failed)
  - `log`: хвост stdout/stderr `WORKER_CMD` (если done)
  - `counters`: JSON сводка из `--- сводка ---`
- **Web UI**: `/jobs` и `/vacancies`
- **VPS (Docker)**:
  - `docker compose -f docker-compose.worker.yml ps`
  - `docker compose -f docker-compose.worker.yml logs --tail=300 worker`

## 2) Норма (SLO)
- `keyword_search`: до ~30 минут (зависит от Playwright)
- `vacancy_enrich`: секунды–минуты
- `vacancy_score`: секунды–минуты
- `vacancy_llm`: зависит от `VACANCY_LLM_BATCH` (обычно 1–10 минут)

## 3) Если задача зависла в running
Признак: `job_runs.status=running` и `now()-started_at` больше допустимого по типу задачи.

Алгоритм:
1) На VPS: посмотреть логи воркера:
   - `docker compose -f docker-compose.worker.yml logs --tail=300 worker`
2) Перезапустить воркер:
   - `docker compose -f docker-compose.worker.yml restart worker`
3) Если задача точно “умерла” (процесс не продолжится после restart):
   - пометить строку `job_runs` как `failed` и поставить задачу заново (enqueue).

Важно: воркер берёт **только queued**. Если контейнер перезапустили, а job остался running — его надо вручную завершить (failed), иначе он останется “вечным”.

## 4) Если LLM (OpenRouter) падает
Типовые причины:
- `401 Unauthorized` → ключ невалиден/не подтянулся в контейнер.
- non-json response → неправильный base URL (должен вести на OpenAI-compatible `/v1/...`), либо редирект.
- rate limit → уменьшить `VACANCY_LLM_BATCH`, поднять `LLM_MIN_SCORE`, реже запускать.

Проверка env внутри контейнера:
```bash
docker exec -it prometei-worker-1 sh -lc 'echo "KEY=${OPENAI_API_KEY:+set} BASE=$OPENAI_BASE_URL MODEL=$OPENAI_MODEL"'
```

## 5) Рекомендуемые “боевые” лимиты LLM (старт)
- `LLM_MIN_SCORE=80`
- `VACANCY_LLM_BATCH=10`
- 1–2 запуска в день

## 6) Пайплайн enqueue
Для одного воркера — использовать последовательный скрипт:
- `scripts/enqueue-pipeline.example.sh`

## 7) Быстрый ручной прогон очереди (без ожидания POLL_INTERVAL_SEC)
```bash
docker compose -f docker-compose.worker.yml run --rm worker python poll_jobs.py --once
```

