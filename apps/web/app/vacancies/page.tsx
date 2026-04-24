import Link from "next/link";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

export const dynamic = "force-dynamic";

type VacancyRow = Record<string, unknown>;

function str(row: VacancyRow, ...keys: string[]) {
  for (const k of keys) {
    const v = row[k];
    if (v != null && String(v).trim() !== "") return String(v);
  }
  return "—";
}

function numScore(row: VacancyRow): number | null {
  const s = row.score ?? row.total_score;
  if (typeof s === "number" && !Number.isNaN(s)) return s;
  if (typeof s === "string") {
    const n = parseFloat(s);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

export default async function VacanciesPage() {
  const minScore = 50;
  let rows: VacancyRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    const { data, error } = await sb
      .from("vacancies")
      .select("*")
      .gte("score", minScore)
      .order("score", { ascending: false })
      .limit(100);
    if (error) throw error;
    rows = (data ?? []) as VacancyRow[];
  } catch (e) {
    loadError =
      e instanceof Error ? e.message : "Не удалось загрузить vacancies";
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <nav className="mb-8 flex gap-4 text-sm text-zinc-600 dark:text-zinc-400">
        <Link className="hover:underline" href="/">
          Главная
        </Link>
        <span className="font-medium text-zinc-900 dark:text-zinc-100">
          Вакансии
        </span>
        <Link className="hover:underline" href="/jobs">
          Прогоны
        </Link>
      </nav>

      <h1 className="mb-2 text-2xl font-semibold tracking-tight">
        Вакансии (балл ≥ {minScore})
      </h1>
      <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
        Данные из Supabase, таблица{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
          vacancies
        </code>
        .
      </p>

      {loadError ? (
        <p className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {loadError}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Нет строк с нужным баллом или таблица пуста.
        </p>
      ) : (
        <ul className="space-y-4">
          {rows.map((row, index) => {
            const id = String(row.id ?? row.uuid ?? `row-${index}`);
            const company = str(row, "company", "employer");
            const title = str(row, "role_title", "title", "position");
            const score = numScore(row);
            const url = str(row, "url", "apply_url", "link");
            return (
              <li
                key={id}
                className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <p className="font-medium">{company}</p>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {title}
                    </p>
                  </div>
                  {score != null && (
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">
                      {score}
                    </span>
                  )}
                </div>
                {url !== "—" && (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-sm text-blue-600 hover:underline dark:text-blue-400"
                  >
                    Открыть
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
