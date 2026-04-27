"use client";

import { useState, useTransition } from "react";
import { enqueueFullSearchFromSecret } from "./actions";

/** Невидимая зона: правый верх страницы «Прогоны». */
export function JobsSecretTrigger() {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);

  function onActivate() {
    setMsg(null);
    start(async () => {
      const r = await enqueueFullSearchFromSecret();
      setMsg(r.ok ? r.message : r.message);
    });
  }

  return (
    <div className="relative h-8 w-8 shrink-0">
      <button
        type="button"
        title=""
        aria-label=" "
        disabled={pending}
        onClick={onActivate}
        className="absolute inset-0 cursor-default opacity-0 focus:opacity-5"
      />
      {msg ? (
        <span className="sr-only" role="status">
          {msg}
        </span>
      ) : null}
    </div>
  );
}
