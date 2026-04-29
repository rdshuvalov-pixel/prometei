"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

const RUN_COOKIE = "prometei_fullrun_utc";
const MAX_RUNS_PER_UTC_DAY = 2;

function utcDay(): string {
  return new Date().toISOString().slice(0, 10);
}

export type SecretEnqueueState = { ok: boolean; message: string };

/** Hidden full run: one sequential funnel job. Rate-limited by UTC day (cookie). */
export async function enqueueFullSearchFromSecret(): Promise<SecretEnqueueState> {
  try {
    const jar = await cookies();
    const day = utcDay();
    const raw = jar.get(RUN_COOKIE)?.value ?? "";
    const parts = raw.split(",").filter(Boolean);
    const usedToday = parts.filter((p) => p === day).length;
    if (usedToday >= MAX_RUNS_PER_UTC_DAY) {
      return {
        ok: false,
        message: `Limit: at most ${MAX_RUNS_PER_UTC_DAY} full runs per UTC calendar day. Try again tomorrow.`,
      };
    }

    const sb = getSupabaseAdmin();
    const { error } = await sb.from("job_runs").insert({
      status: "queued",
      job_type: "keyword_search",
      counters: {},
      payload: { job_type: "keyword_search", source: "jobs_secret_ui" },
    });
    if (error) return { ok: false, message: error.message };

    const next = [...parts, day];
    const trimmed = next.slice(-200);
    jar.set(RUN_COOKIE, trimmed.join(","), {
      path: "/",
      maxAge: 60 * 60 * 24 * 120,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    revalidatePath("/jobs");
    revalidatePath("/");
    return {
      ok: true,
      message: "Queued: keyword_search.",
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, message: msg };
  }
}
