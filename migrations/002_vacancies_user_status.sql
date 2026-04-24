-- Ручной статус из веб-интерфейса (отклик и т.д.). Выполни в Supabase SQL Editor, если таблица vacancies уже есть.

alter table public.vacancies
  add column if not exists user_status text null;

alter table public.vacancies
  add column if not exists user_status_at timestamptz null;

comment on column public.vacancies.user_status is
  'UI: applied — пользователь отметил отклик; null — без метки.';

comment on column public.vacancies.user_status_at is
  'Когда выставлен user_status (серверное время).';
