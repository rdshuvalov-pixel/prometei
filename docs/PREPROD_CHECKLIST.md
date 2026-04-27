# Чеклист перед эксплуатацией (Прометей)

Отмечай пункты по мере закрытия. Детали команд: [`ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md`](ИНСТРУКЦИЯ_VPS_ВОРКЕР_CRON.md), [`README.md`](../README.md), [`prometheus_agent/PLAN_CRAWL_STATUS.md`](../prometheus_agent/PLAN_CRAWL_STATUS.md).

---

## 1. Секреты и доступы

- [ ] В **Vercel Production** заданы `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, при необходимости **`ENQUEUE_SECRET`**; после правок env выполнен **Redeploy**.
- [ ] На **VPS** в `.env.worker` указан **`SUPABASE_SERVICE_ROLE_KEY` (роль service_role)**, не ключ anon; секреты **не** в git и не в публичных скриншотах.
- [ ] Значение **`ENQUEUE_SECRET`** в Vercel и в cron-скрипте на VPS **совпадает**; `curl` передаёт `Authorization: Bearer …` при включённом секрете.
- [ ] При **Deployment Protection** на Vercel настроен обход для автоматизации (**`x-vercel-protection-bypass`**) или защита ослаблена для Production — иначе enqueue получит HTML вместо JSON.

---

## 2. Supabase (схема и безопасность)

- [ ] Выполнена миграция для **`public.job_runs`** ([`migrations/001_job_runs.sql`](../migrations/001_job_runs.sql)); при необходимости согласованы таблицы **`vacancies`** / **`vacancy_sources`** с полями, которые пишут скрипты.
- [ ] Проверены **RLS** и политики: понятно, кто что читает/пишет; публичный доступ к API не даёт лишних прав.
- [ ] Задуман **бэкап** или политика хранения данных в Supabase (экспорт / настройки проекта).

---

## 3. Репозиторий и образ воркера

- [ ] На VPS выполнены **`git pull`** и **`docker compose -f docker-compose.worker.yml up -d --build`**.
- [ ] В **`.env.worker`** задан **`WORKER_CMD`**: прямой `script_crawl.py` или **`worker_dispatch.py`**, если нужны разные `job_type` (`tier4_ashby`, `tier4_board_feeds`).
- [ ] Для полного обхода career-URL: **`MAX_CRAWL_URLS=0`** (или осознанный лимит); заданы **`CRAWL_DELAY_SEC`**, при длинных прогонах — **`JOB_TIMEOUT_SEC`**.
- [ ] В **`docker-compose.worker.yml`** смонтирован каталог **`./prometheus_agent/out`** на хост (отчёты не теряются с `--rm`).
- [ ] Решение по **`WORKER_PARSE_CHILD_COUNTERS`**: `1` (парсинг JSON после `--- сводка ---` в `job_runs.counters`) или `0` при отказе от мержа.

---

## 4. Цели и Tier 4 (данные)

- [ ] Финализирован **[`prometheus_agent/search_targets.md`](../prometheus_agent/search_targets.md)** (порядок tier’ов, список URL).
- [ ] Строка **`_TIER4_QUERY`** в markdown или переопределение через **`TIER4_QUERY`** в env ([`tier4_query.py`](../prometheus_agent/tier4_query.py)).
- [ ] Заполнены списки под фиды (по необходимости): **`ASHBY_SLUGS`**, **`GREENHOUSE_BOARD_TOKENS`**, **`LEVER_COMPANIES`**, **`WORKABLE_ACCOUNT_SLUGS`**.
- [ ] Решение по агрегаторам: **`REMOTIVE_TIER4`** / **`REMOTEOK_TIER4`** (по умолчанию включены; при шуме — `0`).
- [ ] При необходимости расширен **`CRAWL_SKIP_DOMAINS`** (помимо дефолта weworkremotely).

---

## 5. Очередь и cron

- [ ] **`POST {Production URL}/api/jobs`** возвращает успех и в **`job_runs`** появляется строка со статусом **`queued`**.
- [ ] Воркер переводит задачу **`queued` → `running` → `done`** (или **`failed`** с текстом в **`error`**).
- [ ] На VPS в cron заданы **`VERCEL_URL`** (без лишнего слэша в конце), **`ENQUEUE_SECRET`**; лог пишется в файл с корректными правами.
- [ ] Расписание согласовано: отдельно тяжёлый **`script_crawl`**, отдельно **`tier4_*`**, чтобы не упираться в таймаут.

---

## 6. Smoke-тесты и приёмка

- [ ] Один прогон **`script_crawl`** через Docker (см. §5.1 в инструкции VPS): нет массовых ошибок, обновлён **`prometheus_agent/out/crawl_report_latest.md`**.
- [ ] При использовании: прогон **`tier4_ashby`** и/или **`tier4_board_feeds`** — строки в **`vacancies`**, отчёты в **`out/`**, в **`job_runs.counters`** видна сводка (если включён парсинг stdout).
- [ ] При необходимости проверен веб: **GET `/api/jobs`**, страницы вакансий — ожидаемое поведение.
- [ ] Список вакансий на Vercel показывает только **`status = scored`**; при пустом списке проверь, что воркер/скоринг переводит строки в **`scored`** (см. **`script_score_stub.py`** / полноценный скорер).

---

## 7. Эксплуатация после запуска

- [ ] Назначен ответственный за просмотр **`job_runs`**, логов Docker и **`prometheus_agent/out/`**.
- [ ] Есть план **ротации секретов** при утечке (`ENQUEUE_SECRET`, service_role).
- [ ] На VPS зафиксирован **commit или тег** образа для возможного отката.

---

## 8. Вне скоупа текущего продукта

- [ ] Осознанно: **LinkedIn / Indeed / Glassdoor** и аналогичные площадки из Tier 4 **не** считаются готовыми к прод без отдельного решения (браузер, прокси, платные API, юридические ограничения).
