import Link from "next/link";

export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
        Прометей
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        Веб-оболочка над Supabase: список вакансий и очередь прогонов для воркера.
      </p>
      <ul className="mt-10 flex flex-col gap-3 text-base">
        <li>
          <Link
            href="/vacancies"
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            Вакансии (score ≥ 50)
          </Link>
        </li>
        <li>
          <Link
            href="/jobs"
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            Прогоны и «В очередь»
          </Link>
        </li>
        <li>
          <span className="text-sm text-zinc-500">
            API:{" "}
            <code className="rounded bg-zinc-100 px-1 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
              POST /api/jobs
            </code>
          </span>
        </li>
      </ul>
    </div>
  );
}
