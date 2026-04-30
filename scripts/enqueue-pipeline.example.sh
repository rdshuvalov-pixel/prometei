#!/usr/bin/env sh
# enqueue-pipeline.example.sh
#
# Назначение: поставить в очередь последовательный пайплайн задач через Vercel API:
#   keyword_search -> vacancy_enrich -> vacancy_score -> vacancy_llm
#
# Важно: если воркер один, порядок критичен. Поэтому ставим задачи с паузами между POST,
# чтобы created_at отличались и очередь была FIFO.
#
# Обязательно:
#   VERCEL_URL       — https://ТВОЙ-ПРОЕКТ.vercel.app (без слэша в конце)
#   ENQUEUE_SECRET   — тот же, что в Vercel ENQUEUE_SECRET
#
# Опционально (если включена Vercel Deployment Protection):
#   VERCEL_PROTECTION_BYPASS — из Vercel → Deployment Protection → Protection Bypass for Automation
#
# Настройка темпа:
#   PIPELINE_SLEEP_SEC=12
#
set -eu

VERCEL_URL="${VERCEL_URL:-https://YOUR-APP.vercel.app}"
ENQUEUE_SECRET="${ENQUEUE_SECRET:?export ENQUEUE_SECRET}"
PIPELINE_SLEEP_SEC="${PIPELINE_SLEEP_SEC:-12}"

post_job() {
  job_type="$1"
  parent_search_id="${2:-}"
  payload="{\"job_type\":\"${job_type}\""
  if [ -n "${parent_search_id}" ]; then
    payload="${payload},\"parent_search_id\":\"${parent_search_id}\""
  fi
  payload="${payload}}"
  if [ -n "${VERCEL_PROTECTION_BYPASS:-}" ]; then
    curl -sS -X POST "${VERCEL_URL}/api/jobs" \
      -H "x-vercel-protection-bypass: ${VERCEL_PROTECTION_BYPASS}" \
      -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
      -H "Content-Type: application/json" \
      -d "${payload}"
  else
    curl -sS -X POST "${VERCEL_URL}/api/jobs" \
      -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
      -H "Content-Type: application/json" \
      -d "${payload}"
  fi
}

ROOT_JSON="$(post_job "keyword_search")"
ROOT_ID="$(printf "%s" "${ROOT_JSON}" | python3 -c 'import json,sys; print((json.load(sys.stdin) or {}).get("job",{}).get("id",""))' 2>/dev/null || true)"
if [ -z "${ROOT_ID}" ]; then
  echo "ERROR: не удалось распарсить job id из ответа /api/jobs"
  echo "${ROOT_JSON}"
  exit 1
fi
echo "${ROOT_JSON}"
sleep "${PIPELINE_SLEEP_SEC}"
post_job "vacancy_enrich" "${ROOT_ID}"; echo ""
sleep "${PIPELINE_SLEEP_SEC}"
post_job "vacancy_score" "${ROOT_ID}"; echo ""
sleep "${PIPELINE_SLEEP_SEC}"
post_job "vacancy_llm" "${ROOT_ID}"; echo ""

