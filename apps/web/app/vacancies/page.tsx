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
import { VacanciesStatusFilter } from "./VacanciesStatusFilter";

export const dynamic = "force-dynamic";

const FETCH_CAP = 400;
const LIST_CAP = 100;

type PageProps = {
  searchParams: Promise<{ filter?: string }>;
};

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

export default async function VacanciesPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const onlyScored = sp.filter === "scored";

  let raw: VacancyRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    let q = sb
      .from("vacancies")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(FETCH_CAP);
    if (onlyScored) {
      q = q.eq("status", "scored");
    }
    let res = await q;
    if (
      res.error &&
      /created_at|column/i.test(String(res.error.message ?? ""))
    ) {
      let q2 = sb.from("vacancies").select("*").limit(FETCH_CAP);
      if (onlyScored) {
        q2 = q2.eq("status", "scored");
      }
      res = await q2;
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
        Вакансии
      </h1>
      <p className="mb-2 text-sm font-medium text-neutral-800/90 dark:text-amber-100/80">
        {onlyScored
          ? "Показаны позиции с Status = Scored (после оценки в пайплайне). Переключатель ниже — вернуться ко всем записям."
          : `Полный список в базе (до ${FETCH_CAP} строк в выборке, в карточках до ${LIST_CAP}). Отметка «откликнулся» хранится в карточке.`}
      </p>

      <VacanciesStatusFilter onlyScored={onlyScored} />

      {!loadError && raw.length > 0 && (
        <p className="mb-6 text-xs font-semibold text-neutral-700 dark:text-amber-200/70">
          В выборке: {raw.length}, показано: {items.length}
          {onlyScored ? " (Status = Scored)" : ""}
        </p>
      )}

      {loadError ? (
        <p className="rounded-2xl border-4 border-neutral-900 bg-rose-100 p-4 text-sm font-medium text-neutral-900 shadow-[4px_4px_0_0_#171717] dark:border-rose-300 dark:bg-rose-950/50 dark:text-rose-100 dark:shadow-[4px_4px_0_0_#881337]">
          {loadError}
        </p>
      ) : raw.length === 0 ? (
        <p className="text-sm font-medium text-neutral-700 dark:text-amber-200/80">
          {onlyScored
            ? "Пока нет вакансий со Status = Scored. Выбери «Все вакансии» или дождись, пока пайплайн отметит подходящие строки."
            : "Список пуст или нет доступа к данным. Проверь настройки подключения к базе в окружении деплоя."}
        </p>
      ) : (
        <VacanciesList items={items} />
      )}
    </PrometeiShell>
  );
}
