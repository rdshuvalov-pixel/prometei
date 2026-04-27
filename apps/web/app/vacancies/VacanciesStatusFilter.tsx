import Link from "next/link";

const pillBase =
  "inline-flex items-center justify-center rounded-full border-2 border-neutral-900 px-4 py-2 text-sm font-bold shadow-[2px_2px_0_0_#171717] transition hover:translate-x-px hover:translate-y-px hover:shadow-none dark:shadow-[2px_2px_0_0_#fcd34d]";
const inactive = `${pillBase} bg-yellow-200 text-neutral-900 dark:border-amber-200 dark:bg-yellow-500/20 dark:text-amber-50`;
const active =
  `${pillBase} bg-rose-400 text-neutral-900 dark:border-rose-300 dark:bg-rose-500/40 dark:text-amber-50`;

export function VacanciesStatusFilter({ onlyScored }: { onlyScored: boolean }) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3">
      <span className="text-xs font-black uppercase tracking-wide text-neutral-600 dark:text-amber-200/70">
        Показать:
      </span>
      <Link className={onlyScored ? inactive : active} href="/vacancies">
        Все вакансии
      </Link>
      <Link
        className={onlyScored ? active : inactive}
        href="/vacancies?filter=scored"
      >
        Status = Scored
      </Link>
    </div>
  );
}
