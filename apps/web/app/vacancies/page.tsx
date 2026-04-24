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
    <div className="min-h-screen bg-gradient-to-b from-[#FFFDE7] via-[#FFF9C4] to-[#FFECB3] dark:from-neutral-950 dark:via-[#291c0e] dark:to-neutral-950">
      <div className="mx-auto max-w-3xl px-4 py-10">
        <nav className="mb-8 flex flex-wrap gap-4 text-sm font-medium text-neutral-800 dark:text-amber-100/90">
          <Link
            className="rounded-full border-2 border-neutral-900 bg-yellow-300 px-3 py-1 shadow-[2px_2px_0_0_#171717] transition hover:translate-x-px hover:translate-y-px hover:shadow-none dark:border-amber-200 dark:bg-yellow-500/20 dark:shadow-[2px_2px_0_0_#fcd34d]"
            href="/"
          >
            Главная
          </Link>
          <span className="rounded-full border-2 border-neutral-900 bg-rose-400 px-3 py-1 text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-rose-300 dark:bg-rose-500/40 dark:text-amber-50 dark:shadow-[2px_2px_0_0_#fda4af]">
            ⚡ Вакансии
          </span>
          <Link
            className="rounded-full border-2 border-neutral-900 bg-yellow-300 px-3 py-1 shadow-[2px_2px_0_0_#171717] transition hover:translate-x-px hover:translate-y-px hover:shadow-none dark:border-amber-200 dark:bg-yellow-500/20 dark:shadow-[2px_2px_0_0_#fcd34d]"
            href="/jobs"
          >
            Прогоны
          </Link>
        </nav>

        <h1 className="mb-2 text-2xl font-black tracking-tight text-neutral-900 dark:text-amber-50">
          Вакансии (балл ≥ {MIN_SCORE})
        </h1>
        <p className="mb-2 text-sm font-medium text-neutral-800/90 dark:text-amber-100/80">
          Загружено до {FETCH_CAP} строк из{" "}
          <code className="rounded-md border border-neutral-800 bg-yellow-200/80 px-1.5 py-0.5 font-mono text-neutral-900 dark:border-amber-300/50 dark:bg-yellow-500/20 dark:text-amber-50">
            vacancies
          </code>
          ; сортировка по дате (новые сверху), затем по баллу; метка «Новое» — попадание в базу за
          последние 72 ч (и без отметки «Откликнулся»). Письма в списке не показываются — только
          копирование. Ручной статус отклика пишется в{" "}
          <code className="rounded-md border border-neutral-800 bg-yellow-200/80 px-1.5 py-0.5 font-mono text-neutral-900 dark:border-amber-300/50 dark:bg-yellow-500/20 dark:text-amber-50">
            user_status
          </code>{" "}
          (нужна миграция{" "}
          <code className="rounded-md border border-neutral-800 bg-yellow-200/80 px-1.5 py-0.5 font-mono text-neutral-900 dark:border-amber-300/50 dark:bg-yellow-500/20 dark:text-amber-50">
            002_vacancies_user_status.sql
          </code>
          ).
        </p>
        {!loadError && raw.length > 0 && (
          <p className="mb-6 text-xs font-semibold text-neutral-700 dark:text-amber-200/70">
            В выборке: всего {raw.length}, с баллом ≥ {MIN_SCORE}:{" "}
            <span className="text-neutral-900 dark:text-amber-50">{scored.length}</span>
            {below > 0 ? `, остальные ниже порога или без балла: ${below}` : null}
          </p>
        )}

        {loadError ? (
          <p className="rounded-2xl border-4 border-neutral-900 bg-rose-100 p-4 text-sm font-medium text-neutral-900 shadow-[4px_4px_0_0_#171717] dark:border-rose-300 dark:bg-rose-950/50 dark:text-rose-100 dark:shadow-[4px_4px_0_0_#881337]">
            {loadError}
          </p>
        ) : raw.length === 0 ? (
          <p className="text-sm font-medium text-neutral-700 dark:text-amber-200/80">
            Таблица пуста или нет доступа. Проверь{" "}
            <code className="rounded border border-neutral-800 bg-yellow-200/70 px-1 font-mono dark:bg-yellow-500/15">
              NEXT_PUBLIC_SUPABASE_URL
            </code>{" "}
            и{" "}
            <code className="rounded border border-neutral-800 bg-yellow-200/70 px-1 font-mono dark:bg-yellow-500/15">
              SUPABASE_SERVICE_ROLE_KEY
            </code>{" "}
            на Vercel.
          </p>
        ) : scored.length === 0 ? (
          <p className="text-sm font-medium text-neutral-700 dark:text-amber-200/80">
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
    </div>
  );
}
