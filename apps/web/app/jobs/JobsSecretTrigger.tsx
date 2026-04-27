"use client";

import { useState, useTransition } from "react";
import { enqueueFullSearchFromSecret } from "./actions";

/**
 * Invisible 8×8 launch hit area — parent should position (e.g. fixed bottom-right in shell).
 */
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
    <div className="relative h-full w-full">
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
