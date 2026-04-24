"use client";

import Link from "next/link";
import { useActionState, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  enqueueJobFromUi,
  setVacancyUserStatusAction,
  type EnqueueState,
} from "./actions";

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
  showNewBadge: boolean;
};

const initialEnqueue: EnqueueState = {
  ok: false,
  message: "",
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
      className="rounded border border-zinc-300 bg-white px-2 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
    >
      {done ? "Скопировано" : label}
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
  const applied = row.userStatus === "applied";

  function setApplied() {
    startTransition(async () => {
      await setVacancyUserStatusAction(row.id, "applied");
      onStatusChange();
    });
  }

  function clearApplied() {
    startTransition(async () => {
      await setVacancyUserStatusAction(row.id, null);
      onStatusChange();
    });
  }

  const formalOk = row.formal.trim() !== "" && row.formal !== "—";
  const informalOk = row.informal.trim() !== "" && row.informal !== "—";

  return (
    <li
      className={`rounded-lg border p-4 transition-colors dark:border-zinc-800 ${
        applied
          ? "border-zinc-300 bg-zinc-50/80 opacity-90 dark:border-zinc-700 dark:bg-zinc-900/40"
          : "border-zinc-200 dark:border-zinc-800"
      } ${row.showNewBadge && !applied ? "ring-1 ring-amber-400/60 dark:ring-amber-500/40" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{row.company}</p>
            {row.showNewBadge && !applied && (
              <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                Новое
              </span>
            )}
            {applied && (
              <span className="shrink-0 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-900 dark:bg-blue-950 dark:text-blue-200">
                Отклик отправлен
              </span>
            )}
          </div>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">{row.title}</p>
          <dl className="mt-2 grid gap-1 text-xs text-zinc-600 dark:text-zinc-400">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="text-zinc-500">Статус вакансии</dt>
              <dd>{row.pipelineStatus}</dd>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="text-zinc-500">Скоринг</dt>
              <dd>{row.matchStatus}</dd>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="text-zinc-500">Локация</dt>
              <dd className="min-w-0 break-words">{row.location}</dd>
            </div>
            {row.createdLabel !== "—" && (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                <dt className="text-zinc-500">В базе</dt>
                <dd>{row.createdLabel}</dd>
              </div>
            )}
          </dl>
        </div>
        {row.score != null && (
          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">
            {row.score}
          </span>
        )}
      </div>
      {row.url !== "—" && row.url.trim() !== "" && (
        <a
          href={row.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          Открыть источник
        </a>
      )}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
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
            className="rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Откликнулся
          </button>
        ) : (
          <button
            type="button"
            disabled={pending}
            onClick={clearApplied}
            className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-100 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Снять метку отклика
          </button>
        )}
      </div>
    </li>
  );
}

export function VacanciesList({
  items,
  enqueueSecretRequired,
}: {
  items: VacancyListItem[];
  enqueueSecretRequired: boolean;
}) {
  const router = useRouter();
  const [state, formAction, isEnqueuePending] = useActionState(
    enqueueJobFromUi,
    initialEnqueue,
  );
  const [hideApplied, setHideApplied] = useState(false);

  const visible = hideApplied
    ? items.filter((r) => r.userStatus !== "applied")
    : items;

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-zinc-200 bg-zinc-50/50 p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900/30">
        <h2 className="font-medium text-zinc-900 dark:text-zinc-100">
          Постановка в очередь (воркер на VPS)
        </h2>
        <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
          Тип{" "}
          <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">score_vacancies</code>{" "}
          сейчас запускает заглушку-счётчик; полный скоринг подключается отдельно. Остальные
          типы — как в cron.
        </p>
        <form action={formAction} className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="flex min-w-[12rem] flex-col gap-1 text-xs">
            <span className="text-zinc-500">Тип задачи</span>
            <select
              name="job_type"
              className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
              defaultValue="score_vacancies"
            >
              <option value="score_vacancies">score_vacancies (оценка / заглушка)</option>
              <option value="script_crawl">script_crawl</option>
              <option value="tier4_ashby">tier4_ashby</option>
              <option value="tier4_board_feeds">tier4_board_feeds</option>
            </select>
          </label>
          {enqueueSecretRequired ? (
            <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-xs">
              <span className="text-zinc-500">Секрет (ENQUEUE_SECRET)</span>
              <input
                type="password"
                name="enqueue_secret"
                autoComplete="off"
                className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-950"
                placeholder="Как в Vercel"
              />
            </label>
          ) : (
            <input type="hidden" name="enqueue_secret" value="" />
          )}
          <button
            type="submit"
            disabled={isEnqueuePending}
            className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {isEnqueuePending ? "Отправка…" : "В очередь"}
          </button>
        </form>
        {state.message ? (
          <p
            className={`mt-2 text-xs ${state.ok ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
          >
            {state.message}
          </p>
        ) : null}
        <p className="mt-2 text-xs">
          <Link href="/jobs" className="text-blue-600 hover:underline dark:text-blue-400">
            Открыть «Прогоны»
          </Link>
        </p>
      </section>

      <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
        <input
          type="checkbox"
          checked={hideApplied}
          onChange={(e) => setHideApplied(e.target.checked)}
          className="rounded border-zinc-400"
        />
        Скрыть отмеченные «Откликнулся»
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
        <p className="text-sm text-zinc-500">Все отфильтрованы. Сними галку «Скрыть».</p>
      ) : null}
    </div>
  );
}
