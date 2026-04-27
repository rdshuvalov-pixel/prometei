import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";
import { PrometeiShell } from "@/components/PrometeiShell";
import { JobsSecretTrigger } from "./JobsSecretTrigger";

export const dynamic = "force-dynamic";

type JobRow = Record<string, unknown>;

function formatJson(value: unknown, max = 600): string {
  try {
    const s = JSON.stringify(value, null, 2) ?? "";
    if (s.length <= max) return s;
    return `${s.slice(0, max)}…`;
  } catch {
    return String(value);
  }
}

function formatTs(value: unknown): string {
  if (value == null || value === "") return "—";
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString("en-US");
}

export default async function JobsPage() {
  let jobs: JobRow[] = [];
  let loadError: string | null = null;
  try {
    const sb = getSupabaseAdmin();
    let res = await sb
      .from("job_runs")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(50);
    if (
      res.error &&
      /created_at|column/i.test(String(res.error.message ?? ""))
    ) {
      res = await sb.from("job_runs").select("*").limit(50);
    }
    const { data, error } = res;
    if (error) throw error;
    jobs = (data ?? []) as JobRow[];
  } catch (e) {
    loadError = toErrorMessage(e);
  }

  return (
    <PrometeiShell active="jobs" headerRight={<JobsSecretTrigger />}>
      <h1 className="mb-2 text-2xl font-black tracking-tight text-neutral-900 dark:text-amber-50">
        Run history
      </h1>
      <p className="mb-4 text-sm font-medium text-neutral-800 dark:text-amber-100/80">
        The worker picks up jobs in <strong>queued</strong> state. On <strong>failed</strong>, open
        the <strong>Error</strong> block and the <strong>log</strong> details. For the Docker worker,
        check container logs on your server (e.g. <code className="font-mono">docker compose logs</code>{" "}
        for the worker service).
      </p>

      <section className="mb-8 rounded-2xl border-4 border-neutral-900 bg-white/90 p-4 text-sm font-medium text-neutral-800 shadow-[4px_4px_0_0_#171717] dark:bg-neutral-900/80 dark:text-amber-100/85 dark:shadow-[4px_4px_0_0_#fbbf24]">
        <p className="font-black text-neutral-900 dark:text-amber-50">Enqueue jobs</p>
        <p className="mt-2">
          <code className="rounded bg-yellow-200/90 px-1 font-mono dark:bg-yellow-500/25">
            POST /api/jobs
          </code>{" "}
          with JSON body such as{" "}
          <code className="rounded bg-yellow-200/90 px-1 font-mono dark:bg-yellow-500/25">
            {`{"job_type":"script_crawl"}`}
          </code>{" "}
          or another <code className="rounded bg-yellow-200/90 px-1 font-mono dark:bg-yellow-500/25">job_type</code>.
          If <code className="rounded bg-yellow-200/90 px-1 font-mono dark:bg-yellow-500/25">ENQUEUE_SECRET</code>{" "}
          is set on Vercel, send header{" "}
          <code className="rounded bg-yellow-200/90 px-1 font-mono dark:bg-yellow-500/25">
            Authorization: Bearer …
          </code>
          .
        </p>
      </section>

      {loadError ? (
        <div className="rounded-2xl border-4 border-amber-600 bg-amber-100 p-4 text-sm font-bold text-amber-950 dark:border-amber-400 dark:bg-amber-950/50 dark:text-amber-100">
          <p>Load error</p>
          <p className="mt-1 whitespace-pre-wrap">{loadError}</p>
          <p className="mt-2 text-xs font-medium opacity-90">
            If the table is missing, create it in Supabase and redeploy the app.
          </p>
        </div>
      ) : jobs.length === 0 ? (
        <p className="text-sm font-medium text-neutral-700 dark:text-amber-200/80">
          No rows yet. Enqueue via{" "}
          <code className="rounded border border-neutral-800 bg-yellow-200/70 px-1 font-mono dark:bg-yellow-500/15">
            POST /api/jobs
          </code>{" "}
          (cron or manual).
        </p>
      ) : (
        <ul className="space-y-4">
          {jobs.map((j, index) => {
            const id = String(j.id ?? `job-${index}`);
            const jobType =
              j.job_type != null && String(j.job_type).trim() !== ""
                ? String(j.job_type)
                : null;
            const status = j.status != null ? String(j.status) : "—";
            const created = formatTs(j.created_at);
            const started = formatTs(j.started_at);
            const finished = formatTs(j.finished_at);
            const payload = "payload" in j ? j.payload : undefined;
            const counters = "counters" in j ? j.counters : undefined;
            const log = "log" in j ? j.log : undefined;
            const errRaw = "error" in j ? j.error : undefined;
            const err =
              errRaw != null && String(errRaw).trim() !== ""
                ? String(errRaw)
                : null;
            const failed = status.toLowerCase() === "failed";

            return (
              <li
                key={id}
                className={`rounded-2xl border-4 border-neutral-900 p-4 shadow-[4px_4px_0_0_#171717] dark:shadow-[4px_4px_0_0_#fbbf24] ${
                  failed
                    ? "border-rose-700 bg-rose-100/90 dark:border-rose-400 dark:bg-rose-950/50"
                    : "bg-white/95 dark:bg-neutral-900/90"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-neutral-600 dark:text-amber-200/70">
                    {id}
                  </span>
                  <span
                    className={`rounded-full border-2 border-neutral-900 px-2 py-0.5 text-xs font-black shadow-[2px_2px_0_0_#171717] dark:shadow-[2px_2px_0_0_#fcd34d] ${
                      failed
                        ? "bg-rose-400 text-neutral-900 dark:border-rose-200 dark:bg-rose-600 dark:text-white"
                        : "bg-yellow-200 text-neutral-900 dark:border-amber-200 dark:bg-yellow-500/30 dark:text-amber-50"
                    }`}
                  >
                    {status}
                  </span>
                  {jobType && (
                    <span className="rounded-full border-2 border-neutral-900 bg-sky-200 px-2 py-0.5 text-xs font-bold text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-sky-300 dark:bg-sky-900/60 dark:text-sky-100">
                      {jobType}
                    </span>
                  )}
                </div>
                <dl className="mt-2 grid gap-1 text-xs font-medium text-neutral-800 dark:text-amber-100/75">
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-neutral-600 dark:text-amber-200/60">Created</dt>
                    <dd>{created}</dd>
                  </div>
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-neutral-600 dark:text-amber-200/60">Start → finish</dt>
                    <dd>
                      {started} → {finished}
                    </dd>
                  </div>
                </dl>
                {err && (
                  <div className="mt-3 rounded-xl border-2 border-rose-700 bg-white p-3 dark:border-rose-400 dark:bg-rose-950/40">
                    <p className="text-xs font-black text-rose-900 dark:text-rose-100">Error field</p>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-snug text-rose-950 dark:text-rose-100">
                      {err.length > 12000 ? `${err.slice(0, 12000)}…` : err}
                    </pre>
                  </div>
                )}
                {payload !== undefined && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-bold text-neutral-800 dark:text-amber-100">
                      payload
                    </summary>
                    <pre className="mt-2 max-h-48 overflow-auto rounded-lg border-2 border-neutral-900/20 bg-yellow-50/80 p-2 font-mono text-[11px] leading-snug text-neutral-900 dark:border-amber-200/30 dark:bg-neutral-950 dark:text-amber-100">
                      {formatJson(payload, 800)}
                    </pre>
                  </details>
                )}
                {counters !== undefined && counters !== null && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-bold text-neutral-800 dark:text-amber-100">
                      counters
                    </summary>
                    <pre className="mt-2 max-h-48 overflow-auto rounded-lg border-2 border-neutral-900/20 bg-yellow-50/80 p-2 font-mono text-[11px] leading-snug text-neutral-900 dark:border-amber-200/30 dark:bg-neutral-950 dark:text-amber-100">
                      {formatJson(counters, 800)}
                    </pre>
                  </details>
                )}
                {log != null && String(log).trim() !== "" && (
                  <details className="mt-2" open={failed}>
                    <summary className="cursor-pointer text-xs font-bold text-neutral-800 dark:text-amber-100">
                      log (excerpt){failed ? " — expanded on failed" : ""}
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto rounded-lg border-2 border-neutral-900/20 bg-yellow-50/80 p-2 font-mono text-[11px] text-neutral-900 dark:border-amber-200/30 dark:bg-neutral-950 dark:text-amber-100">
                      {String(log).slice(0, failed ? 4000 : 1200)}
                      {String(log).length > (failed ? 4000 : 1200) ? "…" : ""}
                    </pre>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </PrometeiShell>
  );
}
