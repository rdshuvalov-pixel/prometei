"use server";

import { revalidatePath } from "next/cache";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

export async function enqueueJob(formData: FormData) {
  const jobType = String(formData.get("job_type") ?? "script_crawl");
  const sb = getSupabaseAdmin();
  const { error } = await sb.from("job_runs").insert({
    status: "queued",
    job_type: jobType,
    counters: {},
    payload: { job_type: jobType, source: "web_action" },
  });
  if (error) throw new Error(error.message);
  revalidatePath("/jobs");
}
