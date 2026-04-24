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
    return { ok: false, message: "Пустой id вакансии." };
  }
  try {
    const sb = getSupabaseAdmin();
    const patch =
      userStatus === "applied"
        ? { user_status: "applied", user_status_at: new Date().toISOString() }
        : { user_status: null, user_status_at: null };
    const { error } = await sb.from("vacancies").update(patch).eq("id", id);
    if (error) throw error;
    revalidatePath("/vacancies");
    return { ok: true, message: "Сохранено." };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/user_status|column|schema/i.test(msg)) {
      return {
        ok: false,
        message:
          "Колонки user_status нет в БД. Выполни migrations/002_vacancies_user_status.sql в Supabase.",
      };
    }
    return { ok: false, message: msg };
  }
}
