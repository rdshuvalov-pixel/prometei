import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import {
  createdAtMs,
  numScore,
  str,
  type VacancyRow,
} from "@/lib/vacancyDisplay";
import { PrometeiShell } from "@/components/PrometeiShell";
import { VacanciesList, type VacancyListItem } from "./VacanciesList";

export const dynamic = "force-dynamic";

const FETCH_CAP = 400;
const LIST_CAP = 100;

function formatCreatedLabel(createdRaw: string): string {
  if (createdRaw === "—") return "—";
  const d = new Date(createdRaw);
  return Number.isNaN(d.getTime())
    ? createdRaw
    : d.toLocaleString("ru-RU");
}

function toListItem(row: VacancyRow, index: number): VacancyListItem {
  const id = String(row.id ?? row.uuid ?? `row-${index}`);
  const userStatus =
    typeof row.user_status === "string" && row.user_status.trim() !== ""
      ? row.user_status.trim()
      : null;
  const createdRaw = str(row, "created_at", "inserted_at");

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
      .eq("status", "scored")
      .order("created_at", { ascending: false })
      .limit(FETCH_CAP);
    if (
      res.error &&
      /created_at|column/i.test(String(res.error.message ?? ""))
    ) {
      res = await sb
        .from("vacancies")
        .select("*")
        .eq("status", "scored")
        .limit(FETCH_CAP);
    }
    const { data, error } = res;
    if (error) throw error;
    raw = (data ?? []) as VacancyRow[];
  } catch (e) {
    loadError = toErrorMessage(e);
  }

  const items = raw
    .sort((a, b) => {
      const byTime = createdAtMs(b) - createdAtMs(a);
      if (byTime !== 0) return byTime;
      return (numScore(b) ?? 0) - (numScore(a) ?? 0);
    })
    .slice(0, LIST_CAP)
    .map((r, i) => toListItem(r, i));

  return (
    <PrometeiShell active="vacancies">
      <h1 className="mb-2 text-2xl font-black tracking-tight text-neutral-900 dark:text-amber-50">
        Вакансии (status = scored)
      </h1>
      <p className="mb-2 text-sm font-medium text-neutral-800/90 dark:text-amber-100/80">
        Список только строк с{" "}
        <code className="rounded-md border border-neutral-800 bg-yellow-200/80 px-1.5 py-0.5 font-mono text-neutral-900 dark:border-amber-300/50 dark:bg-yellow-500/20 dark:text-amber-50">
          status = scored
        </code>{" "}
        (проставляет пайплайн после скоринга). До {FETCH_CAP} записей, в карточках — до{" "}
        {LIST_CAP}. Ручной статус отклика —{" "}
        <code className="rounded-md border border-neutral-800 bg-yellow-200/80 px-1.5 py-0.5 font-mono text-neutral-900 dark:border-amber-300/50 dark:bg-yellow-500/20 dark:text-amber-50">
          user_status
        </code>{" "}
        (миграция{" "}
        <code className="rounded-md border border-neutral-800 bg-yellow-200/80 px-1.5 py-0.5 font-mono text-neutral-900 dark:border-amber-300/50 dark:bg-yellow-500/20 dark:text-amber-50">
          002_vacancies_user_status.sql
        </code>
        ).
      </p>
      {!loadError && raw.length > 0 && (
        <p className="mb-6 text-xs font-semibold text-neutral-700 dark:text-amber-200/70">
          В выборке: {raw.length}, показано в списке: {items.length}
        </p>
      )}

      {loadError ? (
        <p className="rounded-2xl border-4 border-neutral-900 bg-rose-100 p-4 text-sm font-medium text-neutral-900 shadow-[4px_4px_0_0_#171717] dark:border-rose-300 dark:bg-rose-950/50 dark:text-rose-100 dark:shadow-[4px_4px_0_0_#881337]">
          {loadError}
        </p>
      ) : raw.length === 0 ? (
        <p className="text-sm font-medium text-neutral-700 dark:text-amber-200/80">
          Нет строк со статусом scored (или нет доступа). Проверь env на Vercel и что воркер /
          <code className="mx-0.5 rounded border border-neutral-800 bg-yellow-200/70 px-1 font-mono dark:bg-yellow-500/15">
            script_score_stub.py
          </code>{" "}
          переводит подходящие строки в scored.
        </p>
      ) : (
        <VacanciesList items={items} />
      )}
    </PrometeiShell>
  );
}
