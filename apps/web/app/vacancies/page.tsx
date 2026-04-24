import Link from "next/link";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import {
  createdAtMs,
  numScore,
  str,
  type VacancyRow,
} from "@/lib/vacancyDisplay";
import { VacanciesList, type VacancyListItem } from "./VacanciesList";

export const dynamic = "force-dynamic";

const FETCH_CAP = 400;
const MIN_SCORE = 50;
const LIST_CAP = 100;
/** Бейдж «Новое»: вакансия попала в базу не раньше этого окна от момента открытия страницы. */
const NEW_BADGE_MS = 72 * 60 * 60 * 1000;

function formatCreatedLabel(createdRaw: string): string {
  if (createdRaw === "—") return "—";
  const d = new Date(createdRaw);
  return Number.isNaN(d.getTime())
    ? createdRaw
    : d.toLocaleString("ru-RU");
}

function toListItem(row: VacancyRow, index: number, nowMs: number): VacancyListItem {
  const id = String(row.id ?? row.uuid ?? `row-${index}`);
  const userStatus =
    typeof row.user_status === "string" && row.user_status.trim() !== ""
      ? row.user_status.trim()
      : null;
  const createdRaw = str(row, "created_at", "inserted_at");
  const t = createdAtMs(row);
  const applied = userStatus === "applied";
  const showNewBadge = t > 0 && nowMs - t <= NEW_BADGE_MS && !applied;

  return {
    id,
    company: str(row, "company", "employer"),
    title: str(row, "role_title", "title", "position"),
    score: numScore(row),
    url: str(row, "url", "apply_url", "link"),
    pipelineStatus: str(row, "status", "state"),
    matchStatus: str(row, "match_status", "match"),
    location: str(row, "location", "region", "geo", "office_location"),
    createdLabel: formatCreatedLabel(createdRaw),
    formal: str(row, "cover_formal", "cover_letter_formal"),
    informal: str(row, "cover_informal", "cover_letter_informal"),
    userStatus,
    showNewBadge,
  };
}

export default async function VacanciesPage() {
  let raw: VacancyRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    let res = await sb
      .from("vacancies")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(FETCH_CAP);
    if (
      res.error &&
      /created_at|column/i.test(String(res.error.message ?? ""))
    ) {
      res = await sb.from("vacancies").select("*").limit(FETCH_CAP);
    }
    const { data, error } = res;
    if (error) throw error;
    raw = (data ?? []) as VacancyRow[];
  } catch (e) {
    loadError = toErrorMessage(e);
  }

  const nowMs = Date.now();

  const scored = raw
    .filter((r) => {
      const s = numScore(r);
      return s != null && s >= MIN_SCORE;
    })
    .sort((a, b) => {
      const byTime = createdAtMs(b) - createdAtMs(a);
      if (byTime !== 0) return byTime;
      return (numScore(b) ?? 0) - (numScore(a) ?? 0);
    })
    .slice(0, LIST_CAP)
    .map((r, i) => toListItem(r, i, nowMs));

  const below = raw.filter((r) => {
    const s = numScore(r);
    return s == null || s < MIN_SCORE;
  }).length;

  const enqueueSecretRequired = Boolean(process.env.ENQUEUE_SECRET?.trim());

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
        ; сортировка по дате (новые сверху), затем по баллу; метка «Новое» — попадание в базу за
        последние 72 ч (и без отметки «Откликнулся»). Письма в списке не показываются — только
        копирование. Ручной статус отклика пишется в{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">user_status</code> (нужна
        миграция{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
          002_vacancies_user_status.sql
        </code>
        ).
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
        <VacanciesList
          items={scored}
          enqueueSecretRequired={enqueueSecretRequired}
        />
      )}
    </div>
  );
}
