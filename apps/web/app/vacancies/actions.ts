"use server";

import { revalidatePath } from "next/cache";
import { getSupabaseAdmin } from "@/lib/supabaseAdmin";

export type EnqueueState = {
  ok: boolean;
  message: string;
  jobId?: string;
};

export async function enqueueJobFromUi(
  _prev: EnqueueState,
  formData: FormData,
): Promise<EnqueueState> {
  const jobType = String(formData.get("job_type") || "score_vacancies").trim();
  const secret = String(formData.get("enqueue_secret") || "").trim();
  const required = process.env.ENQUEUE_SECRET?.trim();
  if (required && secret !== required) {
    return { ok: false, message: "Неверный секрет постановки (как ENQUEUE_SECRET на Vercel)." };
  }

  try {
    const sb = getSupabaseAdmin();
    const { data, error } = await sb
      .from("job_runs")
      .insert({
        status: "queued",
        job_type: jobType,
        counters: {},
        payload: { job_type: jobType, source: "vacancies_ui" },
      })
      .select("id")
      .single();
    if (error) throw error;
    const id = data?.id != null ? String(data.id) : "";
    revalidatePath("/vacancies");
    revalidatePath("/jobs");
    return {
      ok: true,
      message: id
        ? `Задача в очереди, id: ${id}. Статус — на странице «Прогоны».`
        : "Задача в очереди.",
      jobId: id || undefined,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, message: msg };
  }
}

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
