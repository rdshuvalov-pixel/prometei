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

set -eu

VERCEL_URL="${VERCEL_URL:-https://YOUR-APP.vercel.app}"
ENQUEUE_SECRET="${ENQUEUE_SECRET:?export ENQUEUE_SECRET}"

if [ -n "${VERCEL_PROTECTION_BYPASS:-}" ]; then
  curl -sS -X POST "${VERCEL_URL}/api/jobs" \
    -H "x-vercel-protection-bypass: ${VERCEL_PROTECTION_BYPASS}" \
    -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
    -H "Content-Type: application/json" \
    -d '{"job_type":"script_crawl"}'
else
  curl -sS -X POST "${VERCEL_URL}/api/jobs" \
    -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
    -H "Content-Type: application/json" \
    -d '{"job_type":"script_crawl"}'
fi
