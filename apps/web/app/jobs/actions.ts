"use server";

import { revalidatePath } from "next/cache";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

export async function enqueueJob(formData: FormData) {
  const jobType = String(formData.get("job_type") ?? "script_crawl");
  const sb = getSupabaseAdmin();
  const { error } = await sb.from("job_runs").insert({
    status: "queued",
    payload: { job_type: jobType },
  });
  if (error) throw new Error(error.message);
  revalidatePath("/jobs");
}
