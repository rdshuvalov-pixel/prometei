import type { ReactNode } from "react";
import Link from "next/link";
import { PikachuPeek } from "./PikachuPeek";

export type PrometeiNav = "home" | "vacancies" | "jobs";

const pill =
  "rounded-full border-2 border-neutral-900 px-3 py-1 text-sm font-medium shadow-[2px_2px_0_0_#171717] transition hover:translate-x-px hover:translate-y-px hover:shadow-none dark:shadow-[2px_2px_0_0_#fcd34d]";
const pillInactive = `${pill} bg-yellow-300 text-neutral-900 dark:border-amber-200 dark:bg-yellow-500/20 dark:text-amber-50`;
const pillActive =
  "rounded-full border-2 border-neutral-900 bg-rose-400 px-3 py-1 text-sm font-medium text-neutral-900 shadow-[2px_2px_0_0_#171717] dark:border-rose-300 dark:bg-rose-500/40 dark:text-amber-50 dark:shadow-[2px_2px_0_0_#fda4af]";

export function PrometeiShell({
  active,
  headerRight,
  children,
}: {
  active: PrometeiNav;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-gradient-to-b from-[#FFFDE7] via-[#FFF9C4] to-[#FFECB3] dark:from-neutral-950 dark:via-[#291c0e] dark:to-neutral-950">
      <PikachuPeek />
      <div className="relative z-10 mx-auto max-w-3xl px-4 py-10">
        <div className="relative mb-8 flex flex-wrap items-center justify-between gap-4">
          <nav className="flex flex-wrap gap-4 text-sm font-medium text-neutral-800 dark:text-amber-100/90">
            <Link className={active === "home" ? pillActive : pillInactive} href="/">
              Home
            </Link>
            <Link
              className={active === "vacancies" ? pillActive : pillInactive}
              href="/vacancies"
            >
              Vacancies
            </Link>
            <Link className={active === "jobs" ? pillActive : pillInactive} href="/jobs">
              Runs
            </Link>
          </nav>
          {headerRight ? (
            <div className="pointer-events-auto flex shrink-0 items-center">{headerRight}</div>
          ) : null}
        </div>
        {children}
      </div>
    </div>
  );
}
