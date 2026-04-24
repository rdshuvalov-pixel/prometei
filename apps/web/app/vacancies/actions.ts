"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

const SEEN_COOKIE = "prometei_vacancies_seen_until";

export type VacancyStatusState = { ok: boolean; message: string };

export async function markAllVacanciesSeenAction(): Promise<VacancyStatusState> {
  try {
    const jar = await cookies();
    jar.set(SEEN_COOKIE, new Date().toISOString(), {
      path: "/",
      maxAge: 60 * 60 * 24 * 400,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    revalidatePath("/vacancies");
    return { ok: true, message: "Метки «Новое» сброшены для текущего списка." };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, message: msg };
  }
}

export async function setVacancyUserStatusAction(
  vacancyId: string,
  userStatus: "applied" | null,
): Promise<VacancyStatusState> {
  const id = vacancyId.trim();
  if (!id) {
    return { ok: false, message: "Пустой id вакансии." };
  }
  if (id.startsWith("row-")) {
    return {
      ok: false,
      message:
        "У записи нет id в ответе Supabase — проверь таблицу vacancies (должна быть колонка id).",
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
          "Строка не обновлена (0 строк). Часто: нет колонок user_status / id не совпал. Выполни migrations/002_vacancies_user_status.sql и проверь id в Supabase.",
      };
    }
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
