/** Pipeline status in DB: capital S (matches stored rows). */
export const VACANCY_STATUS_SCORED = "Scored" as const;

export function isScoredFilterParam(value: string | undefined): boolean {
  if (!value) return false;
  return value === VACANCY_STATUS_SCORED || value.toLowerCase() === "scored";
}
