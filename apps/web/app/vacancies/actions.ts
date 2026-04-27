"use server";

import { revalidatePath } from "next/cache";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

export type VacancyStatusState = { ok: boolean; message: string };

export async function setVacancyUserStatusAction(
  vacancyId: string,
  userStatus: "applied" | null,
): Promise<VacancyStatusState> {
  const id = vacancyId.trim();
  if (!id) {
    return { ok: false, message: "Vacancy id is empty." };
  }
  if (id.startsWith("row-")) {
    return {
      ok: false,
      message:
        "This row has no stable id from the database — check that the vacancies table exposes an id column.",
    };
  }
  try {
    const sb = getSupabaseAdmin();
    const patch =
      userStatus === "applied"
        ? { user_status: "applied", user_status_at: new Date().toISOString() }
        : { user_status: null, user_status_at: null };
    const { data, error } = await sb
      .from("vacancies")
      .update(patch)
      .eq("id", id)
      .select("id");
    if (error) throw error;
    if (!data?.length) {
      return {
        ok: false,
        message:
          "No row updated. Often: missing user_status column or id mismatch — apply the user_status migration in Supabase.",
      };
    }
    revalidatePath("/vacancies");
    return { ok: true, message: "Saved." };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/user_status|column|schema/i.test(msg)) {
      return {
        ok: false,
        message:
          "The user_status column is missing in the database. Add it via your Supabase migration for vacancies.",
      };
    }
    return { ok: false, message: msg };
  }
}
