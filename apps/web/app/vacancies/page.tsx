import Link from "next/link";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import {
  numScore,
  preview,
  str,
  type VacancyRow,
} from "@/lib/vacancyDisplay";

export const dynamic = "force-dynamic";

const FETCH_CAP = 400;
const MIN_SCORE = 50;
const LIST_CAP = 100;

export default async function VacanciesPage() {
  let raw: VacancyRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    const { data, error } = await sb
      .from("vacancies")
      .select("*")
      .limit(FETCH_CAP);
    if (error) throw error;
    raw = (data ?? []) as VacancyRow[];
  } catch (e) {
    loadError = toErrorMessage(e);
  }

  const scored = raw
    .filter((r) => {
      const s = numScore(r);
      return s != null && s >= MIN_SCORE;
    })
    .sort((a, b) => (numScore(b) ?? 0) - (numScore(a) ?? 0))
    .slice(0, LIST_CAP);

  const below = raw.filter((r) => {
    const s = numScore(r);
    return s == null || s < MIN_SCORE;
  }).length;

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
        Вакансии (балл ≥ {MIN_SCORE})
      </h1>
      <p className="mb-2 text-sm text-zinc-600 dark:text-zinc-400">
        Загружено до {FETCH_CAP} строк из{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
          vacancies
        </code>
        ; фильтр по баллу на сервере страницы (без жёсткого{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">.gte</code>{" "}
        в PostgREST).
      </p>
      {!loadError && raw.length > 0 && (
        <p className="mb-6 text-xs text-zinc-500">
          В выборке: всего {raw.length}, с баллом ≥ {MIN_SCORE}:{" "}
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {scored.length}
          </span>
          {below > 0 ? `, остальные ниже порога или без балла: ${below}` : null}
        </p>
      )}

      {loadError ? (
        <p className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {loadError}
        </p>
      ) : raw.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Таблица пуста или нет доступа. Проверь{" "}
          <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
            NEXT_PUBLIC_SUPABASE_URL
          </code>{" "}
          и{" "}
          <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
            SUPABASE_SERVICE_ROLE_KEY
          </code>{" "}
          на Vercel.
        </p>
      ) : scored.length === 0 ? (
        <p className="text-sm text-zinc-500">
          В последних {raw.length} строках нет вакансий с баллом ≥ {MIN_SCORE}.
          Обнови скоринг в пайплайне или временно снизь порог в коде.
        </p>
      ) : (
        <ul className="space-y-4">
          {scored.map((row, index) => {
            const id = String(row.id ?? row.uuid ?? `row-${index}`);
            const company = str(row, "company", "employer");
            const title = str(row, "role_title", "title", "position");
            const score = numScore(row);
            const url = str(row, "url", "apply_url", "link");
            const status = str(row, "status", "state");
            const location = str(
              row,
              "location",
              "region",
              "geo",
              "office_location",
            );
            const created = str(row, "created_at", "inserted_at");
            const formal = str(row, "cover_formal", "cover_letter_formal");
            const informal = str(row, "cover_informal", "cover_letter_informal");

            return (
              <li
                key={id}
                className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{company}</p>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {title}
                    </p>
                    <dl className="mt-2 grid gap-1 text-xs text-zinc-600 dark:text-zinc-400">
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                        <dt className="text-zinc-500">Статус</dt>
                        <dd>{status}</dd>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                        <dt className="text-zinc-500">Локация</dt>
                        <dd className="min-w-0 break-words">{location}</dd>
                      </div>
                      {created !== "—" && (
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                          <dt className="text-zinc-500">В базе</dt>
                          <dd>
                            {(() => {
                              const d = new Date(created);
                              return Number.isNaN(d.getTime())
                                ? created
                                : d.toLocaleString("ru-RU");
                            })()}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>
                  {score != null && (
                    <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">
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
                    Открыть источник
                  </a>
                )}
                {(formal !== "—" || informal !== "—") && (
                  <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3 text-xs dark:border-zinc-800">
                    {formal !== "—" && (
                      <div>
                        <p className="mb-0.5 font-medium text-zinc-700 dark:text-zinc-300">
                          Письмо (форм.)
                        </p>
                        <p className="whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                          {preview(formal)}
                        </p>
                      </div>
                    )}
                    {informal !== "—" && (
                      <div>
                        <p className="mb-0.5 font-medium text-zinc-700 dark:text-zinc-300">
                          Письмо (неформ.)
                        </p>
                        <p className="whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                          {preview(informal, 400)}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
