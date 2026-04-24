import Link from "next/link";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import { enqueueJob } from "./actions";

export const dynamic = "force-dynamic";

type JobRow = Record<string, unknown>;

function formatJson(value: unknown, max = 600): string {
  try {
    const s = JSON.stringify(value, null, 2) ?? "";
    if (s.length <= max) return s;
    return `${s.slice(0, max)}…`;
  } catch {
    return String(value);
  }
}

function formatTs(value: unknown): string {
  if (value == null || value === "") return "—";
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString("ru-RU");
}

export default async function JobsPage() {
  let jobs: JobRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    let res = await sb
      .from("job_runs")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(50);
    if (
      res.error &&
      /created_at|column/i.test(String(res.error.message ?? ""))
    ) {
      res = await sb.from("job_runs").select("*").limit(50);
    }
    const { data, error } = res;
    if (error) throw error;
    jobs = (data ?? []) as JobRow[];
  } catch (e) {
    loadError = toErrorMessage(e);
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
        Таблица{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
          job_runs
        </code>
        : статус <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">queued</code>{" "}
        забирает воркер. Ниже — <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">payload</code>{" "}
        и <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">counters</code>, если есть в
        строке.
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
        <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <p className="font-medium">Ошибка загрузки</p>
          <p className="mt-1 whitespace-pre-wrap">{loadError}</p>
          <p className="mt-2 text-xs opacity-90">
            Если таблицы ещё нет — создай миграцию{" "}
            <code className="rounded bg-amber-100/80 px-1 dark:bg-amber-900/50">
              job_runs
            </code>{" "}
            в Supabase и redeploy.
          </p>
        </div>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Пока нет строк. Нажми «В очередь» или дерни{" "}
          <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">POST /api/jobs</code>.
        </p>
      ) : (
        <ul className="space-y-4">
          {jobs.map((j, index) => {
            const id = String(j.id ?? `job-${index}`);
            const jobType =
              j.job_type != null && String(j.job_type).trim() !== ""
                ? String(j.job_type)
                : null;
            const status = j.status != null ? String(j.status) : "—";
            const created = formatTs(j.created_at);
            const started = formatTs(j.started_at);
            const finished = formatTs(j.finished_at);
            const payload = "payload" in j ? j.payload : undefined;
            const counters = "counters" in j ? j.counters : undefined;
            const log = "log" in j ? j.log : undefined;

            return (
              <li
                key={id}
                className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-zinc-500">{id}</span>
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium dark:bg-zinc-800">
                    {status}
                  </span>
                  {jobType && (
                    <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-900 dark:bg-sky-900 dark:text-sky-100">
                      {jobType}
                    </span>
                  )}
                </div>
                <dl className="mt-2 grid gap-1 text-xs text-zinc-600 dark:text-zinc-400">
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-zinc-500">Создан</dt>
                    <dd>{created}</dd>
                  </div>
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-zinc-500">Старт / финиш</dt>
                    <dd>
                      {started} → {finished}
                    </dd>
                  </div>
                </dl>
                {payload !== undefined && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      payload
                    </summary>
                    <pre className="mt-2 max-h-48 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] leading-snug text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
                      {formatJson(payload, 800)}
                    </pre>
                  </details>
                )}
                {counters !== undefined && counters !== null && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      counters
                    </summary>
                    <pre className="mt-2 max-h-48 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] leading-snug text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
                      {formatJson(counters, 800)}
                    </pre>
                  </details>
                )}
                {log != null && String(log).trim() !== "" && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      log (фрагмент)
                    </summary>
                    <pre className="mt-2 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
                      {String(log).slice(0, 1200)}
                      {String(log).length > 1200 ? "…" : ""}
                    </pre>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
