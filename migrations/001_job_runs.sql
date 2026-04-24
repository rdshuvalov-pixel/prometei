-- Очередь прогонов для воркера и веба (Supabase SQL Editor → вставить и выполнить).
-- Идемпотентно: если таблица уже есть с другой схемой — не выполняй слепо, сверь колонки.

create table if not exists public.job_runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  user_id uuid null references auth.users (id) on delete set null,
  job_type text not null,
  status text not null,
  started_at timestamptz null,
  finished_at timestamptz null,
  counters jsonb not null default '{}'::jsonb,
  log text null,
  error text null,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists job_runs_status_created_idx
  on public.job_runs (status, created_at desc);

comment on table public.job_runs is
  'Очередь прогонов: API пишет queued, воркер — running/done/failed.';
