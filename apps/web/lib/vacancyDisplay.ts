export type VacancyRow = Record<string, unknown>;

export function str(row: VacancyRow, ...keys: string[]): string {
  for (const k of keys) {
    const v = row[k];
    if (v != null && String(v).trim() !== "") return String(v);
  }
  return "—";
}

export function numScore(row: VacancyRow): number | null {
  const s = row.score ?? row.total_score;
  if (typeof s === "number" && !Number.isNaN(s)) return s;
  if (typeof s === "string") {
    const n = parseFloat(s);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

/** Для сортировки «сначала новые»: первое валидное поле даты из типичных колонок. */
export function createdAtMs(row: VacancyRow): number {
  for (const k of ["created_at", "inserted_at", "updated_at"]) {
    const v = row[k];
    if (v == null || String(v).trim() === "") continue;
    const t = new Date(String(v)).getTime();
    if (!Number.isNaN(t)) return t;
  }
  return 0;
}

export function preview(text: string, max = 220): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}
