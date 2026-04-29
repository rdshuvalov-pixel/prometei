#!/usr/bin/env sh
# Пример для cron на VPS: POST /api/jobs на Vercel.
#
# Обязательно:
#   VERCEL_URL              — https://ТВОЙ-ПРОЕКТ.vercel.app (без слэша в конце)
#   ENQUEUE_SECRET          — тот же, что в Vercel ENQUEUE_SECRET
#
# Если на проекте включена защита деплоев (SSO), добавь секрет обхода:
#   VERCEL_PROTECTION_BYPASS — из Vercel → Deployment Protection → Protection Bypass for Automation
#   (это НЕ ENQUEUE_SECRET; см. docs/ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md §8.0)
#
# Другие job_type (нужен WORKER_CMD=python3 /app/prometheus_agent/worker_dispatch.py):
#   {"job_type":"tier4_ashby"}        — Ashby (ASHBY_SLUGS в .env.worker)
#   {"job_type":"tier4_board_feeds"} — GH/Lever/Workable + по умолчанию Remotive+RemoteOK (см. .env.worker)
#   {"job_type":"vacancy_enrich"}    — обогащение полей в vacancies (pending_enrich → pending_score)
#   {"job_type":"vacancy_score"}     — rule-based скоринг (pending_score → scored + status=Scored)
#   {"job_type":"vacancy_llm"}       — LLM-материалы (fit_reasoning + notes + cover letters)
#   {"job_type":"keyword_search"}    — поиск по ключевому слову по источникам (board_feeds/ashby/playwright)
#
# Для последовательного пайплайна (рекомендуется для одного воркера):
#   scripts/enqueue-pipeline.example.sh

set -eu

VERCEL_URL="${VERCEL_URL:-https://YOUR-APP.vercel.app}"
ENQUEUE_SECRET="${ENQUEUE_SECRET:?export ENQUEUE_SECRET}"

if [ -n "${VERCEL_PROTECTION_BYPASS:-}" ]; then
  curl -sS -X POST "${VERCEL_URL}/api/jobs" \
    -H "x-vercel-protection-bypass: ${VERCEL_PROTECTION_BYPASS}" \
    -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
    -H "Content-Type: application/json" \
    -d '{"job_type":"script_crawl"}'
  # Для Ashby Tier4 (нужен WORKER_CMD=worker_dispatch.py на воркере):
  # -d '{"job_type":"tier4_ashby"}'
else
  curl -sS -X POST "${VERCEL_URL}/api/jobs" \
    -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
    -H "Content-Type: application/json" \
    -d '{"job_type":"script_crawl"}'
fi
