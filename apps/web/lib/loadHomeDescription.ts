import { readFile } from "node:fs/promises";
import { join } from "node:path";

/** Markdown source: keep in sync with repo `docs/Описание на главной.md` (copy ships with `apps/web` for Vercel). */
export async function loadHomeDescriptionSplit(): Promise<{ en: string; ru: string }> {
  const filePath = join(process.cwd(), "content", "home-description.md");
  const raw = await readFile(filePath, "utf-8");
  const parts = raw.split("----------------------------------------");
  let ru = (parts[0] ?? "").trim();
  ru = ru.replace(/^Русская версия\s*\n?/i, "").trim();
  let en = (parts[1] ?? "").trim();
  en = en.replace(/^[\n\r]*English version\s*\n?/i, "").trim();
  return { en, ru };
}
