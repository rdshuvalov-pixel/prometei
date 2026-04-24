# Терминал: VPS, воркер (Docker) и cron (enqueue)

Всё ниже выполняется **на твоём сервере** (SSH), не на Mac, если не указано иначе. Подставь свои значения вместо примеров в угловых скобках или `…`.

---

## 0. Что должно быть уже сделано

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
- **`WORKER_CMD`** — одна shell-команда внутри контейнера для реального прогона. **Пока строка закомментирована или пуста** — воркер только снимает `queued` и ставит **`done`** со stub в `counters` (чтобы очередь не зависала).

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
export ENQUEUE_SECRET="тот_же_секрет_что_в_Vercel"
./scripts/enqueue-cron.example.sh
```

Если всё ок, в ответе будет JSON с созданной задачей; в Supabase в **`job_runs`** появится новая строка со статусом **`queued`**.

Если **`ENQUEUE_SECRET` в Vercel не задан**, Bearer не нужен — тогда для теста можно временно вызвать `curl` без заголовка (в проде лучше задать секрет).

### 6.2. Добавить в crontab

Открыть редактор расписания:

```bash
crontab -e
```

Пример: **каждый день в 06:30** по времени сервера (часовой пояс VPS смотри командой `timedatectl` или `date`):

```cron
30 6 * * * cd /opt/prometei && VERCEL_URL="https://ТВОЙ-ПРОЕКТ.vercel.app" ENQUEUE_SECRET="ТВОЙ_СЕКРЕТ" ./scripts/enqueue-cron.example.sh >> /var/log/prometei-enqueue.log 2>&1
```

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
