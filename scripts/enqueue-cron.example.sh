#!/usr/bin/env sh
# Пример для cron на VPS: ставит задачу в очередь через Vercel API.
# Задай VERCEL_URL и ENQUEUE_SECRET (тот же, что в Vercel env).

set -eu

VERCEL_URL="${VERCEL_URL:-https://YOUR-APP.vercel.app}"
ENQUEUE_SECRET="${ENQUEUE_SECRET:?export ENQUEUE_SECRET}"

curl -sS -X POST "${VERCEL_URL}/api/jobs" \
  -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"script_crawl"}'
