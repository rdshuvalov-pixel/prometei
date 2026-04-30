import { NextResponse } from "next/server";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";
import { toErrorMessage } from "@/lib/errorMessage";

function unauthorized() {
  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

function bearerToken(authHeader: string | null): string | null {
  if (!authHeader) return null;
  const m = authHeader.match(/^\s*Bearer\s+(.+)$/i);
  return m?.[1]?.trim() ?? null;
}

export async function GET() {
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
    return NextResponse.json({ jobs: data ?? [] });
  } catch (e) {
    const message = toErrorMessage(e);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const secret = process.env.ENQUEUE_SECRET?.trim();
  if (secret) {
    const token = bearerToken(request.headers.get("authorization"));
    if (token !== secret) return unauthorized();
  }

  let body: { job_type?: string; parent_search_id?: string } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  try {
    const sb = getSupabaseAdmin();
    const jobType = body.job_type ?? "script_crawl";
    const parentSearchId = String(body.parent_search_id ?? "").trim() || null;
    const { data, error } = await sb
      .from("job_runs")
      .insert({
        status: "queued",
        job_type: jobType,
        counters: {},
        payload: {
          job_type: jobType,
          source: "api",
          ...(parentSearchId ? { parent_search_id: parentSearchId } : {}),
        },
      })
      .select("id, status")
      .single();
    if (error) throw error;
    return NextResponse.json({ job: data }, { status: 201 });
  } catch (e) {
    const message = toErrorMessage(e);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
