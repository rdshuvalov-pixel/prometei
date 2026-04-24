import Link from "next/link";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import { numScore, type VacancyRow } from "@/lib/vacancyDisplay";

export const dynamic = "force-dynamic";

const MIN_SCORE = 50;
const SAMPLE = 500;

export default async function Home() {
  let vacancyTotal: number | null = null;
  let vacancyScored: number | null = null;
  let jobsTotal: number | null = null;
  let statsError: string | null = null;

  try {
    const sb = getSupabaseAdmin();

    const { count: vCount, error: vErr } = await sb
      .from("vacancies")
      .select("*", { count: "exact", head: true });
    if (vErr) throw vErr;
    vacancyTotal = vCount ?? 0;

    const { data: sample, error: sErr } = await sb
      .from("vacancies")
      .select("*")
      .limit(SAMPLE);
    if (sErr) throw sErr;
    const rows = (sample ?? []) as VacancyRow[];
    vacancyScored = rows.filter((r) => {
      const s = numScore(r);
      return s != null && s >= MIN_SCORE;
    }).length;

    const { count: jCount, error: jErr } = await sb
      .from("job_runs")
      .select("*", { count: "exact", head: true });
    if (jErr) throw jErr;
    jobsTotal = jCount ?? 0;
  } catch (e) {
    statsError = toErrorMessage(e);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
        Прометей
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        Веб-оболочка над Supabase: список вакансий, мониторинг прогонов; постановка в
        очередь — только <code className="rounded bg-zinc-100 px-1 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">POST /api/jobs</code>.
      </p>

      {statsError ? (
        <p className="mt-6 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Сводка из базы недоступна: {statsError}
        </p>
      ) : (
        <dl className="mt-6 grid gap-2 rounded-lg border border-zinc-200 bg-zinc-50/80 p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900/40">
          <div className="flex justify-between gap-4">
            <dt className="text-zinc-500">Вакансий в таблице</dt>
            <dd className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
              {vacancyTotal ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-zinc-500">
              С баллом ≥ {MIN_SCORE} (в первых {SAMPLE} строках)
            </dt>
            <dd className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
              {vacancyScored ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-zinc-500">Строк в job_runs</dt>
            <dd className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
              {jobsTotal ?? "—"}
            </dd>
          </div>
        </dl>
      )}

      <ul className="mt-10 flex flex-col gap-3 text-base">
        <li>
          <Link
            href="/vacancies"
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            Вакансии (карточки, письма, статус)
          </Link>
        </li>
        <li>
          <Link
            href="/jobs"
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            Прогоны: история, payload, логи
          </Link>
        </li>
        <li>
          <span className="text-sm text-zinc-500">
            API:{" "}
            <code className="rounded bg-zinc-100 px-1 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
              POST /api/jobs
            </code>
          </span>
        </li>
      </ul>
    </div>
  );
}
