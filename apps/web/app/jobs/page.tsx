import Link from "next/link";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { enqueueJob } from "./actions";

export const dynamic = "force-dynamic";

type JobRow = {
  id: string;
  status: string | null;
  payload: unknown;
  counters: unknown;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export default async function JobsPage() {
  let jobs: JobRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    const { data, error } = await sb
      .from("job_runs")
      .select(
        "id, status, payload, counters, created_at, started_at, finished_at",
      )
      .order("created_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    jobs = (data ?? []) as JobRow[];
  } catch (e) {
    loadError =
      e instanceof Error ? e.message : "Не удалось загрузить job_runs";
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <nav className="mb-8 flex gap-4 text-sm text-zinc-600 dark:text-zinc-400">
        <Link className="hover:underline" href="/">
          Главная
        </Link>
        <Link className="hover:underline" href="/vacancies">
          Вакансии
        </Link>
        <span className="font-medium text-zinc-900 dark:text-zinc-100">
          Прогоны
        </span>
      </nav>

      <h1 className="mb-2 text-2xl font-semibold tracking-tight">
        История прогонов
      </h1>
      <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
        Строка в{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
          job_runs
        </code>{" "}
        со статусом{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
          queued
        </code>{" "}
        заберёт воркер.
      </p>

      <section className="mb-10 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <h2 className="mb-3 text-sm font-medium text-zinc-800 dark:text-zinc-200">
          Запустить прогон
        </h2>
        <form action={enqueueJob} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-600 dark:text-zinc-400">Тип</span>
            <select
              name="job_type"
              className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              defaultValue="script_crawl"
            >
              <option value="script_crawl">script_crawl</option>
              <option value="watchlist">watchlist</option>
            </select>
          </label>
          <button
            type="submit"
            className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
          >
            В очередь
          </button>
        </form>
      </section>

      {loadError ? (
        <p className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {loadError}
        </p>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-zinc-500">Пока нет записей.</p>
      ) : (
        <ul className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {jobs.map((j) => (
            <li key={j.id} className="flex flex-col gap-1 px-4 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-zinc-500">{j.id}</span>
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium dark:bg-zinc-800">
                  {j.status}
                </span>
              </div>
              <span className="text-xs text-zinc-500">
                {j.created_at
                  ? new Date(j.created_at).toLocaleString("ru-RU")
                  : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
