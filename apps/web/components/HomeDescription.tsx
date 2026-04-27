"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";

function parseInline(text: string): ReactNode[] {
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  const parts = text.split(re);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

function renderMarkdown(md: string): ReactNode {
  const lines = md.replace(/\r\n/g, "\n").trim().split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith("# ")) {
      out.push(
        <h1
          key={key++}
          className="mt-2 text-2xl font-black tracking-tight text-neutral-900 dark:text-amber-50"
        >
          {parseInline(line.slice(2))}
        </h1>,
      );
      i += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      out.push(
        <h2
          key={key++}
          className="mt-6 text-sm font-black uppercase tracking-wide text-neutral-900 dark:text-amber-50"
        >
          {parseInline(line.slice(3))}
        </h2>,
      );
      i += 1;
      continue;
    }
    if (/^\d+\.\s/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        const m = lines[i].match(/^\d+\.\s+(.*)$/);
        items.push(
          <li key={key++} className="leading-relaxed">
            {parseInline(m?.[1] ?? lines[i])}
          </li>,
        );
        i += 1;
      }
      out.push(
        <ol
          key={key++}
          className="mt-2 list-decimal space-y-1 pl-5 text-sm font-medium text-neutral-800 dark:text-amber-100/85"
        >
          {items}
        </ol>,
      );
      continue;
    }
    if (line.startsWith("- ")) {
      const items: ReactNode[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(
          <li key={key++} className="leading-relaxed">
            {parseInline(lines[i].slice(2))}
          </li>,
        );
        i += 1;
      }
      out.push(
        <ul
          key={key++}
          className="mt-2 list-disc space-y-1 pl-5 text-sm font-medium text-neutral-800 dark:text-amber-100/85"
        >
          {items}
        </ul>,
      );
      continue;
    }
    out.push(
      <p
        key={key++}
        className="mt-2 text-sm font-medium leading-relaxed text-neutral-800 dark:text-amber-100/85"
      >
        {parseInline(line)}
      </p>,
    );
    i += 1;
  }
  return <div className="space-y-1">{out}</div>;
}

export function HomeDescription({ en, ru }: { en: string; ru: string }) {
  const [lang, setLang] = useState<"en" | "ru">("en");
  const body = lang === "en" ? en : ru;
  const rendered = useMemo(() => renderMarkdown(body), [body]);

  return (
    <section
      className="mt-6 rounded-2xl border-4 border-neutral-900 bg-white/90 p-4 shadow-[4px_4px_0_0_#171717] dark:bg-neutral-900/80 dark:shadow-[4px_4px_0_0_#fbbf24]"
      aria-label="Product description"
    >
      <div className="mb-4 flex flex-wrap items-center gap-2 border-b-2 border-dashed border-neutral-900/20 pb-3 dark:border-amber-200/25">
        <span className="text-xs font-black uppercase tracking-wide text-neutral-600 dark:text-amber-200/70">
          Description
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setLang("en")}
            className={
              lang === "en"
                ? "rounded-full border-2 border-neutral-900 bg-rose-400 px-3 py-1 text-xs font-black text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-rose-300 dark:bg-rose-500/40 dark:text-amber-50"
                : "rounded-full border-2 border-neutral-900 bg-yellow-200 px-3 py-1 text-xs font-bold text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-amber-200 dark:bg-yellow-500/20 dark:text-amber-50"
            }
          >
            EN
          </button>
          <button
            type="button"
            onClick={() => setLang("ru")}
            className={
              lang === "ru"
                ? "rounded-full border-2 border-neutral-900 bg-rose-400 px-3 py-1 text-xs font-black text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-rose-300 dark:bg-rose-500/40 dark:text-amber-50"
                : "rounded-full border-2 border-neutral-900 bg-yellow-200 px-3 py-1 text-xs font-bold text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-amber-200 dark:bg-yellow-500/20 dark:text-amber-50"
            }
          >
            RU
          </button>
        </div>
      </div>
      {rendered}
    </section>
  );
}
