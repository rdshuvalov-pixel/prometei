"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { setVacancyUserStatusAction } from "./actions";

export type VacancyListItem = {
  id: string;
  company: string;
  title: string;
  score: number | null;
  url: string;
  pipelineStatus: string;
  matchStatus: string;
  location: string;
  createdLabel: string;
  formal: string;
  informal: string;
  userStatus: string | null;
};

function CopyBtn({
  label,
  text,
  disabled,
}: {
  label: string;
  text: string;
  disabled: boolean;
}) {
  const [done, setDone] = useState(false);
  async function onCopy() {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 2000);
    } catch {
      setDone(false);
    }
  }
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onCopy}
      className="rounded-lg border-2 border-neutral-900 bg-yellow-200 px-2.5 py-1.5 text-xs font-bold text-neutral-900 shadow-[2px_2px_0_0_#171717] transition hover:bg-yellow-300 hover:shadow-[1px_1px_0_0_#171717] disabled:translate-y-px disabled:opacity-40 disabled:shadow-none dark:border-amber-200 dark:bg-yellow-500/25 dark:text-amber-50 dark:shadow-[2px_2px_0_0_#fcd34d] dark:hover:bg-yellow-500/35"
    >
      {done ? "⚡ Скопировано!" : label}
    </button>
  );
}

function VacancyCard({
  row,
  onStatusChange,
}: {
  row: VacancyListItem;
  onStatusChange: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const applied = row.userStatus === "applied";

  function setApplied() {
    setStatusErr(null);
    startTransition(async () => {
      const res = await setVacancyUserStatusAction(row.id, "applied");
      if (!res.ok) {
        setStatusErr(res.message);
        return;
      }
      onStatusChange();
    });
  }

  function clearApplied() {
    setStatusErr(null);
    startTransition(async () => {
      const res = await setVacancyUserStatusAction(row.id, null);
      if (!res.ok) {
        setStatusErr(res.message);
        return;
      }
      onStatusChange();
    });
  }

  const formalOk = row.formal.trim() !== "" && row.formal !== "—";
  const informalOk = row.informal.trim() !== "" && row.informal !== "—";

  return (
    <li
      className={`rounded-2xl border-4 border-neutral-900 p-4 shadow-[4px_4px_0_0_#171717] transition-colors dark:shadow-[4px_4px_0_0_#fbbf24] ${
        applied
          ? "bg-neutral-200/90 dark:bg-neutral-800/80"
          : "bg-white/95 dark:bg-neutral-900/90"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-black text-neutral-900 dark:text-amber-50">{row.company}</p>
            {applied && (
              <span className="shrink-0 rounded-full border-2 border-neutral-900 bg-yellow-400 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-amber-200 dark:bg-amber-600/50 dark:text-amber-50">
                Пика-пика ✓
              </span>
            )}
          </div>
          <p className="text-sm font-semibold text-neutral-800 dark:text-amber-100/85">
            {row.title}
          </p>
          <dl className="mt-2 grid gap-1 text-xs font-medium text-neutral-800 dark:text-amber-100/75">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="text-neutral-600 dark:text-amber-200/60">Статус вакансии</dt>
              <dd>{row.pipelineStatus}</dd>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="text-neutral-600 dark:text-amber-200/60">Скоринг</dt>
              <dd>{row.matchStatus}</dd>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="text-neutral-600 dark:text-amber-200/60">Локация</dt>
              <dd className="min-w-0 break-words">{row.location}</dd>
            </div>
            {row.createdLabel !== "—" && (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                <dt className="text-neutral-600 dark:text-amber-200/60">В базе</dt>
                <dd>{row.createdLabel}</dd>
              </div>
            )}
          </dl>
        </div>
        {row.score != null && (
          <span className="shrink-0 rounded-full border-2 border-neutral-900 bg-yellow-300 px-2.5 py-0.5 text-xs font-black text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-amber-200 dark:bg-yellow-500/40 dark:text-amber-50 dark:shadow-[2px_2px_0_0_#ca8a04]">
            {row.score}
          </span>
        )}
      </div>
      {row.url !== "—" && row.url.trim() !== "" && (
        <a
          href={row.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-sm font-bold text-neutral-900 underline decoration-2 decoration-rose-400 underline-offset-2 hover:text-rose-700 dark:text-amber-200 dark:decoration-amber-400 dark:hover:text-amber-50"
        >
          Открыть источник →
        </a>
      )}
      {statusErr ? (
        <p className="mt-2 rounded-lg border-2 border-rose-600 bg-rose-100 px-2 py-1.5 text-xs font-bold text-rose-950 dark:border-rose-400 dark:bg-rose-950/60 dark:text-rose-100">
          {statusErr}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2 border-t-2 border-dashed border-neutral-900/20 pt-3 dark:border-amber-200/25">
        <CopyBtn
          label="Скопировать формальное"
          text={formalOk ? row.formal : ""}
          disabled={!formalOk}
        />
        <CopyBtn
          label="Скопировать неформальное"
          text={informalOk ? row.informal : ""}
          disabled={!informalOk}
        />
        {!applied ? (
          <button
            type="button"
            disabled={pending}
            onClick={setApplied}
            className="rounded-lg border-2 border-neutral-900 bg-rose-400 px-2.5 py-1.5 text-xs font-black text-neutral-900 shadow-[2px_2px_0_0_#171717] transition hover:translate-x-px hover:translate-y-px hover:shadow-none disabled:opacity-50 dark:border-rose-200 dark:bg-rose-500 dark:text-white"
          >
            Откликнулся!
          </button>
        ) : (
          <button
            type="button"
            disabled={pending}
            onClick={clearApplied}
            className="rounded-lg border-2 border-neutral-900 bg-white px-2.5 py-1.5 text-xs font-bold text-neutral-900 shadow-[2px_2px_0_0_#171717] hover:bg-yellow-100 dark:border-amber-200 dark:bg-neutral-800 dark:text-amber-100 dark:hover:bg-neutral-700"
          >
            Снять метку
          </button>
        )}
      </div>
    </li>
  );
}

export function VacanciesList({ items }: { items: VacancyListItem[] }) {
  const router = useRouter();
  const [hideApplied, setHideApplied] = useState(false);

  const visible = hideApplied
    ? items.filter((r) => r.userStatus !== "applied")
    : items;

  return (
    <div className="space-y-6">
      <label className="flex cursor-pointer items-center gap-2 rounded-full border-2 border-neutral-900 bg-yellow-100 px-3 py-2 text-sm font-bold text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-amber-200 dark:bg-yellow-600/20 dark:text-amber-50 dark:shadow-[2px_2px_0_0_#ca8a04]">
        <input
          type="checkbox"
          checked={hideApplied}
          onChange={(e) => setHideApplied(e.target.checked)}
          className="size-4 rounded border-2 border-neutral-900 text-neutral-900 accent-rose-500 dark:border-amber-200 dark:accent-rose-400"
        />
        Скрыть уже «пика-пика» отмеченные
      </label>

      <ul className="space-y-4">
        {visible.map((row) => (
          <VacancyCard
            key={row.id}
            row={row}
            onStatusChange={() => router.refresh()}
          />
        ))}
      </ul>
      {visible.length === 0 && items.length > 0 ? (
        <p className="rounded-xl border-2 border-neutral-900 bg-yellow-100 px-3 py-2 text-sm font-bold text-neutral-900 dark:border-amber-200 dark:bg-neutral-800 dark:text-amber-100">
          Все спрятались — сними галку «Скрыть».
        </p>
      ) : null}
    </div>
  );
}
