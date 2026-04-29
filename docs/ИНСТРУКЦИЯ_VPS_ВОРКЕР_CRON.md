# Терминал: VPS, воркер (Docker) и cron (enqueue)

Всё ниже выполняется **на твоём сервере** (SSH), не на Mac, если не указано иначе. Подставь свои значения вместо примеров в угловых скобках или `…`.

---

## 0. Что должно быть уже сделано

- Перед выводом в прод пройди чеклист: **[`PREPROD_CHECKLIST.md`](PREPROD_CHECKLIST.md)** (секреты, Supabase, образ, cron, smoke-тесты).
- Репозиторий с кодом есть на GitHub, на Vercel задеплоен **`apps/web`**, в Vercel заданы **`NEXT_PUBLIC_SUPABASE_URL`** и **`SUPABASE_SERVICE_ROLE_KEY`**.
- В Supabase есть таблица **`public.job_runs`** (см. [`migrations/001_job_runs.sql`](../migrations/001_job_runs.sql)).
- Для cron с секретом: в Vercel добавлен **`ENQUEUE_SECRET`** и сделан **Redeploy** (иначе `POST /api/jobs` без Bearer может ещё открываться — см. README).

---

## 1. Подключиться к VPS по SSH

На своём компьютере:

```bash
ssh <пользователь>@<IP_или_домен>
```

Пример: `ssh root@203.0.113.50`

Дальше все команды — **уже внутри сессии SSH** на сервере, если не сказано обратное.

---

## 2. Установить Docker и Compose (если ещё нет)

Debian / Ubuntu (типичный Contabo):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Дальше добавь репозиторий Docker под свою версию ОС — проще всего следовать официальной инструкции:  
https://docs.docker.com/engine/install/ubuntu/  
(или для Debian — раздел Debian на той же странице документации.)

После установки:

```bash
sudo systemctl enable --now docker
docker --version
docker compose version
```

Должны быть **`Docker version …`** и **`Docker Compose version v2…`**. Команда именно **`docker compose`** (два слова), не обязательно старый бинарь `docker-compose`.

Чтобы запускать Docker без `sudo` (по желанию):

```bash
sudo usermod -aG docker "$USER"
```

Выйди из SSH и зайди снова, чтобы группа применилась.

---

## 3. Склонировать репозиторий на сервер

Рабочая папка на твой вкус, например `/opt/prometei`:

```bash
sudo mkdir -p /opt/prometei
sudo chown "$USER":"$USER" /opt/prometei
cd /opt/prometei
git clone https://github.com/rdshuvalov-pixel/prometei.git .
```

Если репозиторий приватный — настрой **SSH-ключ** на сервере и клонируй по SSH-URL, или используй **Personal Access Token** с `git clone https://<token>@github.com/...` (токен не сохраняй в истории команд; лучше SSH).

Обновление кода позже:

```bash
cd /opt/prometei
git pull origin main
```

---

## 4. Воркер: файл окружения `.env.worker`

Из **корня репозитория** на сервере (там же, где лежат `docker-compose.worker.yml` и `Dockerfile.worker`):

```bash
cd /opt/prometei
cp .env.worker.example .env.worker
chmod 600 .env.worker
nano .env.worker
```

В редакторе заполни минимум:

- **`SUPABASE_URL`** — тот же URL, что **`NEXT_PUBLIC_SUPABASE_URL`** в Vercel (например `https://abcdefgh.supabase.co`).
- **`SUPABASE_SERVICE_ROLE_KEY`** — **service_role** из Supabase (Settings → API). Этот ключ **нельзя** светить в git и скриншотах.

Опционально:

- **`POLL_INTERVAL_SEC`** — как часто опрашивать очередь (по умолчанию 20).
- **`WORKER_CMD`** — пусто = stub **`done`**. Иначе одна из команд (путь **только** с префиксом **`/app/`** — так устроен [`Dockerfile.worker`](../Dockerfile.worker), `WORKDIR /app`):
  - **`python3 /app/prometheus_agent/script_crawl.py`** — обход URL из `search_targets.md` (или `watchlist_targets.md`, если в очереди **`job_type`:** `watchlist`). Отчёт: **`prometheus_agent/out/crawl_report_latest.md`** (в контейнере путь **`/app/prometheus_agent/out/`**).
  - **`python3 /app/prometheus_agent/worker_dispatch.py`** — по **`JOB_TYPE`** из задачи: обычный crawl или **`tier4_ashby`** → [`ashby_crawler.py`](../prometheus_agent/ashby_crawler.py) (Ashby public API, фильтр PM/Lead + EU/remote + возраст вакансии).
  - Неверно: **`/data/prometheus_agent/...`** — в этом образе каталога **`/data`** нет, будет **`[Errno 2] No such file or directory`** и **`exit=2`**. Замени на **`/app/prometheus_agent/...`**.
- **`MAX_CRAWL_URLS`** — лимит URL за прогон для `script_crawl`; **`0`** = без лимита (все ссылки из markdown).
- **`CRAWL_DELAY_SEC`** — пауза между HTTP-запросами (сек).
- **`CRAWL_SKIP_DOMAINS`** — через запятую; по умолчанию в коде отрезается **`weworkremotely.com`**.
- Для Ashby (при `tier4_ashby`): **`ASHBY_SLUGS`**, **`TIER4_MAX_JOB_AGE_DAYS`**, **`ASHBY_DELAY_SEC`**, опционально **`TIER4_RELAX_GEO=1`** (см. [`.env.worker.example`](../.env.worker.example)).

Сохрани файл: в `nano` — `Ctrl+O`, Enter, `Ctrl+X`.

---

## 5. Воркер: сборка и запуск Docker

Всё ещё из корня репо:

```bash
cd /opt/prometei
docker compose -f docker-compose.worker.yml build
docker compose -f docker-compose.worker.yml up -d
```

Проверка, что контейнер запущен:

```bash
docker compose -f docker-compose.worker.yml ps
```

Логи (живой поток, выход `Ctrl+C`):

```bash
docker compose -f docker-compose.worker.yml logs -f worker
```

Один проход вручную (без бесконечного цикла — для отладки):

```bash
cd /opt/prometei
docker compose -f docker-compose.worker.yml run --rm worker python poll_jobs.py --once
```

Остановить воркер:

```bash
cd /opt/prometei
docker compose -f docker-compose.worker.yml down
```

После **`git pull`** пересобери и перезапусти:

```bash
cd /opt/prometei
git pull origin main
docker compose -f docker-compose.worker.yml up -d --build
```

### 5.1 Разовый прогон `script_crawl` на VPS (без очереди `job_runs`)

Пакеты **`httpx`** и **`supabase`** ставятся **в Docker-образ воркера**, а не в системный Python. Запуск **`python3 prometheus_agent/script_crawl.py`** с хоста без venv даёт **`ModuleNotFoundError: No module named 'httpx'`**.

**Вариант A (рекомендуется):** тот же образ, путь внутри контейнера **`/app/prometheus_agent/script_crawl.py`**:

```bash
cd /opt/prometei
docker compose -f docker-compose.worker.yml run --rm \
  -e MAX_CRAWL_URLS=0 -e CRAWL_DELAY_SEC=1 \
  worker python3 /app/prometheus_agent/script_crawl.py
```

`SUPABASE_*` берутся из **`.env.worker`**. Лог — в stdout этой команды. Файлы **`out/crawl_report_*.md`** при таком запуске создаются **внутри ephemeral-контейнера** и с **`--rm`** на диск хоста не попадают; для постоянного **`out/`** на сервере добавь в **`docker-compose.worker.yml`** у сервиса **`worker`** том, например:

`./prometheus_agent/out:/app/prometheus_agent/out`

**Вариант B:** хостовый Python:

```bash
cd /opt/prometei
python3 -m venv .venv-worker
. .venv-worker/bin/activate
pip install -r requirements-worker.txt
set -a && source .env.worker && set +a
export MAX_CRAWL_URLS=0 CRAWL_DELAY_SEC=1
python3 prometheus_agent/script_crawl.py
```

Ошибка **`can't open file '/data/prometheus_agent/script_crawl.py'`** / **`[Errno 2]`**: в **`.env.worker`** на VPS в **`WORKER_CMD`** стоит путь с **`/data/`**. Для **`docker-compose.worker.yml`** из этого репо нужно **`/app/prometheus_agent/...`**. Исправь строку, затем **`docker compose -f docker-compose.worker.yml up -d --build`** (или хотя бы **`restart`**, если образ уже с кодом в **`/app`**).

### 5.2 Greenhouse + Lever (`tier4_board_feeds`)

При **`WORKER_CMD=python3 /app/prometheus_agent/worker_dispatch.py`** в **`.env.worker`** задай **`GREENHOUSE_BOARD_TOKENS`**, **`LEVER_COMPANIES`**, **`WORKABLE_ACCOUNT_SLUGS`** (по необходимости) и при желании отключи агрегаторы **`REMOTIVE_TIER4=0`**, **`REMOTEOK_TIER4=0`** (по умолчанию оба включены — тянут публичные API Remotive + RemoteOK). Очередь: **`POST /api/jobs`** с **`{"job_type":"tier4_board_feeds"}`**. Отчёт: **`prometheus_agent/out/board_feeds_report_latest.md`**.

---

## 6. Cron: постановка задачи в очередь через Vercel

Идея: по расписанию вызывать **`POST https://<твой-проект>.vercel.app/api/jobs`** с телом JSON и (если в Vercel задан **`ENQUEUE_SECRET`**) заголовком **`Authorization: Bearer <секрет>`**.

### 6.1. Скрипт на сервере

Репозиторий уже содержит [`scripts/enqueue-cron.example.sh`](../scripts/enqueue-cron.example.sh). На VPS:

```bash
cd /opt/prometei
chmod +x scripts/enqueue-cron.example.sh
```

Проверка **одним запуском** из терминала (подставь свой URL и секрет):

```bash
cd /opt/prometei
export VERCEL_URL="https://ТВОЙ-ПРОЕКТ.vercel.app"
export ENQUEUE_SECRET="тот_же_секрет_что_в_VERCEL_ENQUEUE_SECRET"
./scripts/enqueue-cron.example.sh
```

Если всё ок, в ответе будет JSON с созданной задачей; в Supabase в **`job_runs`** появится новая строка со статусом **`queued`**.

После успешного **`WORKER_CMD`** воркер пишет в **`job_runs.counters`** не только `exit_code` / `stdout_chars`, но и JSON из блока **`--- сводка ---`** в конце вывода `script_crawl` / `ashby_crawler` / `board_feeds_tier4` (если не отключено: **`WORKER_PARSE_CHILD_COUNTERS=0`** в `.env.worker`).

Если **`ENQUEUE_SECRET` в Vercel не задан**, Bearer не нужен — тогда для теста можно временно вызвать `curl` без заголовка (в проде лучше задать секрет).

### 6.2. Добавить в crontab

Открыть редактор расписания:

```bash
crontab -e
```

Пример: **каждый день в 06:30** по времени сервера (часовой пояс VPS смотри командой `timedatectl` или `date`):

```cron
30 6 * * * cd /opt/prometei && VERCEL_URL="https://ТВОЙ-ПРОЕКТ.vercel.app" ENQUEUE_SECRET="СЛУЧАЙНАЯ_СТРОКА_КАК_В_VERCEL" ./scripts/enqueue-cron.example.sh >> /var/log/prometei-enqueue.log 2>&1
```

**Важно:** в `ENQUEUE_SECRET` должен быть **тот же произвольный секрет**, что ты задал в Vercel (например вывод `openssl rand -hex 32`), **не** ключ Supabase и не JWT сервисной роли.

Создать лог-файл и права (если пишешь в `/var/log`):

```bash
sudo touch /var/log/prometei-enqueue.log
sudo chown "$USER":"$USER" /var/log/prometei-enqueue.log
```

Либо пиши лог в домашний каталог, например `>> "$HOME/prometei-enqueue.log" 2>&1` — тогда `sudo` не нужен.

Проверить, что строка попала в crontab:

```bash
crontab -l
```

---

## 7. Контрольный чеклист

1. Воркер: `docker compose … ps` — контейнер **Up**; в логах нет бесконечных ошибок подключения к Supabase.
2. В Supabase: после `curl`/cron в **`job_runs`** появляется **`queued`**, через время воркер переводит в **`running`** / **`done`** (или **`failed`** при ошибке **`WORKER_CMD`**).
3. Vercel: **`ENQUEUE_SECRET`** задан, если хочешь закрыть анонимный `POST`.

Заполненные URL и хост — в [`prometheus_agent/08_web_app_architecture.md`](../prometheus_agent/08_web_app_architecture.md), §12.

---

## 7.1. Задача в `job_runs` со статусом **failed** («упала»)

1. **Веб:** страница **Прогоны** (`/jobs`) — красная карточка, блок **«Ошибка (поле error)»**, раскрытый **log** (хвост stdout/stderr воркера).
2. **Supabase:** таблица `job_runs` → колонки **`error`**, **`log`**, **`counters`**.
3. **VPS:** логи контейнера (часто там полный traceback до обрезки в БД):
   ```bash
   cd /opt/prometei
   docker compose -f docker-compose.worker.yml logs --tail=300 worker
   ```
4. Частые причины: **`WORKER_CMD`** не тот или путь к скрипту неверный (**`/data/...`** вместо **`/app/...`** в Docker из этого репо → **`exit=2`**, файл не найден); **`JOB_TIMEOUT_SEC`**; **exit≠0** у Python (ошибка в `script_crawl` / tier4 / сети / ключ Supabase в `.env.worker`); для типов tier4 — не заданы **`ASHBY_SLUGS`** и т.д. в `.env.worker`.

---

## 8. Проверка сквозняка (API → `job_runs` → воркер)

Подставь **`VERCEL_URL`** — боевой `https://….vercel.app` **без слэша в конце** (иначе часто будет **308** и тело ответа не то, что ждёшь). Если в Vercel задан **`ENQUEUE_SECRET`**, подставь ту же строку в **`ENQUEUE_SECRET`** ниже.

### 8.0. HTML «Authentication Required» и HTTP 401 от Vercel (не `ENQUEUE_SECRET`)

Если **`curl`** возвращает длинный **HTML** со словами **Authentication Required** / **Vercel Authentication** — включена **защита деплоев** (Deployment Protection, SSO). До приложения Next запрос **не доходит**, это **не** проверка `ENQUEUE_SECRET` в коде.

**Вариант A.** Vercel → Project → Settings → **Deployment Protection** — для **Production** отключи защиту или оставь только для Preview.

**Вариант B.** **Protection Bypass for Automation** — в тех же настройках создай секрет обхода. В **`curl`** добавь заголовок (это **другой** секрет, не `ENQUEUE_SECRET`). Документация: [Protection Bypass for Automation](https://vercel.com/docs/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation).

```bash
export VERCEL_PROTECTION_BYPASS="секрет_из_vercel_bypass_automation"

curl -sS -w "\nHTTP:%{http_code}\n" -X POST "${VERCEL_URL}/api/jobs" \
  -H "x-vercel-protection-bypass: ${VERCEL_PROTECTION_BYPASS}" \
  -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"script_crawl"}'
```

**Вариант C.** Установлен **Vercel CLI** и ты залогинен: `vercel curl` — обход часто подставляется сам.

Скрипт [`scripts/enqueue-cron.example.sh`](../scripts/enqueue-cron.example.sh) поддерживает опциональный **`VERCEL_PROTECTION_BYPASS`** (тот же заголовок).

### 8.1. С Mac или с VPS: создать задачу в очереди

**С секретом в Vercel (`ENQUEUE_SECRET`) и без защиты деплоя (или с заголовком из §8.0):**

```bash
export VERCEL_URL="https://<твой-домен>/api/jobs"
export ENQUEUE_SECRET="ENQUEUE_SECRET"

curl -sS -w "\nHTTP:%{http_code}\n" -X POST "${VERCEL_URL}/api/jobs" \
  -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"script_crawl"}'
```

**Если видишь HTTP 308** — это редирект (частые причины: в **`VERCEL_URL`** был **`http://`**, или **слэш в конце** домена, или домен не тот). Сначала посмотри заголовок **`Location`**:

```bash
curl -sS -D - -o /dev/null -X POST "${VERCEL_URL}/api/jobs" \
  -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"script_crawl"}' | head -20
```

Исправь **`VERCEL_URL`** на тот адрес, который в **`Location`** (обычно тот же хост с **`https://`** и **без** завершающего **`/`** перед **`/api/jobs`**).

Если нужно явно следовать редиректу одной командой (редко нужно при правильном URL):

```bash
curl -sS -L -w "\nHTTP:%{http_code}\n" -X POST "${VERCEL_URL}/api/jobs" \
  -H "Authorization: Bearer ${ENQUEUE_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"script_crawl"}'
```

(`-L`: в современном **curl** для **308** метод **POST** к новому URL обычно сохраняется.)

**Без секрета в Vercel** (переменная `ENQUEUE_SECRET` в Vercel не создана):

```bash
export VERCEL_URL="https://ТВОЙ-ПРОЕКТ.vercel.app"

curl -sS -w "\nHTTP:%{http_code}\n" -X POST "${VERCEL_URL}/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"script_crawl"}'
```

Ожидание: **HTTP:201** и JSON с полем **`job`** (внутри **`id`**, **`status`**: обычно **`queued`**).

**Если HTTP 401 и тело — маленький JSON** `{"error":"Unauthorized"}` — это уже **наше** API: в Vercel задан **`ENQUEUE_SECRET`**, а **`Authorization: Bearer`** не совпал или отсутствует. См. пункты ниже.

**Если HTTP 401 и тело — большой HTML** — сначала пройди **§8.0** (защита деплоев Vercel).

Для **JSON** `Unauthorized`:

1. В **Vercel → Environment Variables** сравни **`ENQUEUE_SECRET`** с `export ENQUEUE_SECRET=...`.
2. Заголовок: **`Authorization: Bearer ОДИН_ПРОБЕЛ_секрет`**.
3. После смены секрета — **Redeploy**.
4. Временно без секрета: удали **`ENQUEUE_SECRET`**, **Redeploy** (в проде не оставляй).

### 8.2. Посмотреть последние задачи через API (без секрета)

```bash
curl -sS "${VERCEL_URL}/api/jobs" | head -c 4000
```

При установленном **`jq`**:

```bash
curl -sS "${VERCEL_URL}/api/jobs" | jq '.jobs[:5]'
```

### 8.3. На VPS: форсировать один цикл воркера

Из каталога репо (где `docker-compose.worker.yml`):

```bash
cd /opt/prometei
docker compose -f docker-compose.worker.yml run --rm worker python poll_jobs.py --once
```

Сразу после этого снова:

```bash
curl -sS "${VERCEL_URL}/api/jobs" | jq '.jobs[:3]'
```

Ожидание: свежая строка прошла **`queued` → `running` → `done`** (или **`failed`**, если **`WORKER_CMD`** падает). Если **`WORKER_CMD` пуст** — будет **`done`** со **`stub`** в **`counters`**.

### 8.4. Логи воркера (постоянный процесс)

```bash
cd /opt/prometei
docker compose -f docker-compose.worker.yml logs --tail 80 worker
```

Поток в реальном времени (выход `Ctrl+C`):

```bash
docker compose -f docker-compose.worker.yml logs -f worker
```

### 8.5. Supabase (Table Editor или SQL Editor)

В **SQL Editor**:

```sql
select id, status, job_type, created_at, started_at, finished_at
from public.job_runs
order by created_at desc
limit 10;
```

Сверь **`status`** и время с шагами выше.

### 8.6. Что дальше после успешной проверки

1. Убедиться, что в **crontab** в `ENQUEUE_SECRET` **не** лежит ключ Supabase — только **тот же** секрет, что в Vercel (если JWT попал в репозиторий или в лог — **сротировать**: новый service role в Supabase при утечке, новый `ENQUEUE_SECRET` в Vercel, обновить cron).
2. Задать реальный **`WORKER_CMD`** в **`.env.worker`**, пересобрать:  
   `docker compose -f docker-compose.worker.yml up -d --build`
3. Заполнить §12 в [`prometheus_agent/08_web_app_architecture.md`](../prometheus_agent/08_web_app_architecture.md) реальными URL (без секретов).
