import { NextResponse } from "next/server";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

function unauthorized() {
  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

export async function GET() {
  try {
    const sb = getSupabaseAdmin();
    const { data, error } = await sb
      .from("job_runs")
      .select(
        "id, status, payload, counters, created_at, started_at, finished_at",
      )
      .order("created_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    return NextResponse.json({ jobs: data ?? [] });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const secret = process.env.ENQUEUE_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    const token = auth?.startsWith("Bearer ") ? auth.slice(7) : null;
    if (token !== secret) return unauthorized();
  }

  let body: { job_type?: string } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  try {
    const sb = getSupabaseAdmin();
    const { data, error } = await sb
      .from("job_runs")
      .insert({
        status: "queued",
        payload: { job_type: body.job_type ?? "script_crawl" },
      })
      .select("id, status, created_at")
      .single();
    if (error) throw error;
    return NextResponse.json({ job: data }, { status: 201 });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
