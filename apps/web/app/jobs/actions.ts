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

/** Hidden full run: three jobs (crawl + tier4 boards + ashby). Rate-limited by UTC day (cookie). */
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
    const types = ["script_crawl", "tier4_board_feeds", "tier4_ashby"] as const;
    for (const job_type of types) {
      const { error } = await sb.from("job_runs").insert({
        status: "queued",
        job_type,
        counters: {},
        payload: { job_type, source: "jobs_secret_ui" },
      });
      if (error) {
        return { ok: false, message: error.message };
      }
    }

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
      message: `Queued: ${types.join(", ")}.`,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, message: msg };
  }
}
