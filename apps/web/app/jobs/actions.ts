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
    const { data: searchRow, error: searchErr } = await sb
      .from("search_runs")
      .insert({
        status: "queued",
        source: "jobs_secret_ui",
        params: { rate_limited_cookie: RUN_COOKIE },
      })
      .select("id")
      .single();
    if (searchErr) return { ok: false, message: searchErr.message };
    const search_id = String(searchRow?.id ?? "").trim();
    if (!search_id) return { ok: false, message: "Failed to create search run." };

    const { error } = await sb.from("job_runs").insert({
      status: "queued",
      job_type: "full_search",
      counters: {},
      payload: { job_type: "full_search", source: "jobs_secret_ui", search_id },
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
      message: `Queued: full_search (search_id=${search_id}).`,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, message: msg };
  }
}
