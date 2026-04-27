import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import { PrometeiShell } from "@/components/PrometeiShell";
import { HomeDescription } from "@/components/HomeDescription";
import { loadHomeDescriptionSplit } from "@/lib/loadHomeDescription";
import { VACANCY_STATUS_SCORED } from "@/lib/vacancyStatus";

export const dynamic = "force-dynamic";

type JobRow = Record<string, unknown>;

function tsJob(j: JobRow): number {
  for (const k of ["finished_at", "started_at", "created_at"] as const) {
    const raw = j[k];
    const n = Date.parse(String(raw ?? ""));
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

function pickLastFinished(jobs: JobRow[]): JobRow | null {
  const done = jobs.filter((j) => {
    const s = String(j.status ?? "").toLowerCase();
    return s === "done" || s === "failed";
  });
  if (!done.length) return null;
  done.sort((a, b) => tsJob(b) - tsJob(a));
  return done[0] ?? null;
}

function counterNum(counters: unknown, key: string): number | null {
  if (!counters || typeof counters !== "object") return null;
  const v = (counters as Record<string, unknown>)[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export default async function Home() {
  const { en, ru } = await loadHomeDescriptionSplit();

  let vacancyTotal: number | null = null;
  let draftsCount: number | null = null;
  let jobsTotal: number | null = null;
  let lastJob: JobRow | null = null;
  let statsError: string | null = null;

  try {
    const sb = getSupabaseAdmin();

    const { count: vCount, error: vErr } = await sb
      .from("vacancies")
      .select("*", { count: "exact", head: true });
    if (vErr) throw vErr;
    vacancyTotal = vCount ?? 0;

    const { count: dCount, error: dErr } = await sb
      .from("vacancies")
      .select("*", { count: "exact", head: true })
      .eq("match_status", "pending_score")
      .neq("status", VACANCY_STATUS_SCORED);
    if (dErr) throw dErr;
    draftsCount = dCount ?? 0;

    const { count: jCount, error: jErr } = await sb
      .from("job_runs")
      .select("*", { count: "exact", head: true });
    if (jErr) throw jErr;
    jobsTotal = jCount ?? 0;

    let res = await sb
      .from("job_runs")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(80);
    if (
      res.error &&
      /created_at|column/i.test(String(res.error.message ?? ""))
    ) {
      res = await sb.from("job_runs").select("*").limit(80);
    }
    const { data: jr, error: jrErr } = res;
    if (jrErr) throw jrErr;
    lastJob = pickLastFinished((jr ?? []) as JobRow[]);
  } catch (e) {
    statsError = toErrorMessage(e);
  }

  const counters = lastJob?.counters;
  const inserted = counterNum(counters, "inserted");
  const urlsAttempted = counterNum(counters, "urls_attempted");
  const lastStatus = lastJob ? String(lastJob.status ?? "—") : "—";
  const lastType =
    lastJob && lastJob.job_type != null && String(lastJob.job_type).trim() !== ""
      ? String(lastJob.job_type)
      : "—";
  const lastFinishedLabel = lastJob
    ? (() => {
        const raw = lastJob.finished_at ?? lastJob.started_at ?? lastJob.created_at;
        const d = new Date(String(raw ?? ""));
        return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("en-US");
      })()
    : "—";

  return (
    <PrometeiShell active="home">
      <HomeDescription en={en} ru={ru} />

      <section
        className="mt-8 rounded-2xl border-4 border-neutral-900 bg-white/90 p-4 shadow-[4px_4px_0_0_#171717] dark:bg-neutral-900/80 dark:shadow-[4px_4px_0_0_#fbbf24]"
        aria-label="Stack"
      >
        <h2 className="text-xs font-black uppercase tracking-wide text-neutral-900 dark:text-amber-50">
          Stack
        </h2>
        <p className="mt-2 text-sm font-medium text-neutral-800 dark:text-amber-100/85">
          Next.js · Vercel · Supabase · Docker · VPS
        </p>
      </section>

      {statsError ? (
        <p className="mt-6 rounded-2xl border-4 border-amber-600 bg-amber-100 p-3 text-xs font-bold text-amber-950 dark:border-amber-400 dark:bg-amber-950/40 dark:text-amber-100">
          Live stats unavailable: {statsError}
        </p>
      ) : (
        <dl className="mt-8 grid gap-3 rounded-2xl border-4 border-neutral-900 bg-yellow-100/60 p-4 text-sm font-semibold text-neutral-900 shadow-[4px_4px_0_0_#171717] dark:border-amber-200 dark:bg-yellow-600/15 dark:text-amber-50 dark:shadow-[4px_4px_0_0_#ca8a04]">
          <div className="flex flex-wrap justify-between gap-2">
            <dt className="text-neutral-700 dark:text-amber-200/80">Vacancies in database</dt>
            <dd className="tabular-nums">{vacancyTotal ?? "—"}</dd>
          </div>
          <div className="flex flex-wrap justify-between gap-2">
            <dt className="text-neutral-700 dark:text-amber-200/80">
              Awaiting scoring (not yet {VACANCY_STATUS_SCORED})
            </dt>
            <dd className="tabular-nums">{draftsCount ?? "—"}</dd>
          </div>
          <div className="flex flex-wrap justify-between gap-2">
            <dt className="text-neutral-700 dark:text-amber-200/80">Run history rows</dt>
            <dd className="tabular-nums">{jobsTotal ?? "—"}</dd>
          </div>
          <div className="col-span-full border-t-2 border-dashed border-neutral-900/25 pt-3 dark:border-amber-200/30">
            <p className="text-xs font-black uppercase tracking-wide text-neutral-800 dark:text-amber-100">
              Last finished run
            </p>
            <div className="mt-2 grid gap-1 text-xs">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-neutral-600 dark:text-amber-200/70">Type & outcome</span>
                <span>
                  {lastType} · {lastStatus}
                </span>
              </div>
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-neutral-600 dark:text-amber-200/70">Time</span>
                <span>{lastFinishedLabel}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-neutral-600 dark:text-amber-200/70">New rows this run</span>
                <span className="tabular-nums">{inserted ?? "—"}</span>
              </div>
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-neutral-600 dark:text-amber-200/70">Pages fetched (crawl)</span>
                <span className="tabular-nums">{urlsAttempted ?? "—"}</span>
              </div>
            </div>
            {!lastJob ? (
              <p className="mt-2 text-[11px] font-medium text-neutral-600 dark:text-amber-200/60">
                No finished runs yet — numbers will appear after the worker completes a job.
              </p>
            ) : null}
          </div>
        </dl>
      )}
    </PrometeiShell>
  );
}
