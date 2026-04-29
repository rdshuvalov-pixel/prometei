#!/usr/bin/env python3
"""
vacancy_llm (optional):
  - selects strong vacancies (status=Scored, score>=LLM_MIN_SCORE)
  - generates fit_reasoning + cover letters
  - writes fit_reasoning, cover_formal, cover_informal

Disabled by default: requires OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import httpx
from supabase import Client, create_client

_SUMMARY_MARKER = "--- сводка ---"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        raise SystemExit(2)
    return create_client(url, key)


def _batch_size() -> int:
    raw = (os.environ.get("VACANCY_LLM_BATCH") or "30").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 30
    return max(1, min(n, 120))


def _min_score() -> int:
    raw = (os.environ.get("LLM_MIN_SCORE") or "70").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 70
    return max(1, min(n, 100))


def _openai_cfg() -> tuple[str, str, str] | None:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().rstrip("/")
    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    return key, base, model


def _as_text(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


def _prompt(row: dict) -> str:
    return "\n".join(
        [
            "Ты помощник для подготовки отклика на вакансию.",
            "Сгенерируй краткое объяснение соответствия и 2 варианта cover letter.",
            "",
            "Верни СТРОГО JSON объект с ключами:",
            '  fit_reasoning: string (2-4 предложения, по делу, без воды)',
            '  cover_formal: string (до ~1200 символов)',
            '  cover_informal: string (до ~900 символов)',
            "",
            f"Компания: {_as_text(row.get('company'))}",
            f"Роль: {_as_text(row.get('role_title'))}",
            f"URL: {_as_text(row.get('url'))}",
            "Details:",
            _as_text(row.get("details")),
        ],
    )


def _call_openai(*, key: str, base: str, model: str, prompt: str, timeout_sec: float = 60.0) -> dict:
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return strictly valid JSON. No markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    with httpx.Client(timeout=timeout_sec) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    content = (((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty LLM response")
    # tolerate leading/trailing text by extracting JSON block
    s = content.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("LLM did not return JSON object")
    obj = json.loads(s[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("LLM JSON is not an object")
    return obj


def _pick_str(out: dict, *keys: str) -> str | None:
    for k in keys:
        v = out.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _derive_fit_reasoning_from_cover(cover: str) -> str | None:
    s = (cover or "").strip()
    if not s:
        return None
    # Cheap fallback: take first 2 sentences (or first 240 chars).
    parts: list[str] = []
    buf = ""
    for ch in s:
        buf += ch
        if ch in ".!?":
            p = buf.strip()
            if p:
                parts.append(p)
            buf = ""
        if len(parts) >= 2:
            break
        if len("".join(parts)) >= 260:
            break
    out = " ".join(parts).strip()
    if out:
        return out[:600]
    return s[:240]


def main() -> None:
    cfg = _openai_cfg()
    if not cfg:
        summary = {"job_type": "vacancy_llm", "stub": True, "reason": "missing OPENAI_API_KEY", "finished_at": _utc_iso()}
        print(_SUMMARY_MARKER, flush=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return

    key, base, model = cfg
    sb = _client()
    n = _batch_size()
    min_score = _min_score()

    res = (
        sb.table("vacancies")
        .select("id, company, role_title, url, details, score, status, fit_reasoning, cover_formal, cover_informal")
        .eq("status", "Scored")
        .gte("score", min_score)
        .order("score", desc=True)
        .limit(n)
        .execute()
    )
    rows = getattr(res, "data", None) or []

    updated = 0
    skipped = 0
    errors = 0

    for r in rows:
        vid = r.get("id")
        if vid is None:
            skipped += 1
            continue
        if _as_text(r.get("fit_reasoning")).strip() and _as_text(r.get("cover_formal")).strip() and _as_text(r.get("cover_informal")).strip():
            skipped += 1
            continue
        try:
            out = _call_openai(key=key, base=base, model=model, prompt=_prompt(r))
            patch: dict = {}
            cf = _pick_str(out, "cover_formal", "formal", "coverLetterFormal")
            ci = _pick_str(out, "cover_informal", "informal", "coverLetterInformal")
            fr = _pick_str(out, "fit_reasoning", "reasoning", "fit", "rationale", "match_reasoning")

            if cf:
                patch["cover_formal"] = cf
            if ci:
                patch["cover_informal"] = ci
            if fr:
                patch["fit_reasoning"] = fr
            elif cf:
                derived = _derive_fit_reasoning_from_cover(cf)
                if derived:
                    patch["fit_reasoning"] = derived
            if not patch:
                skipped += 1
                continue
            sb.table("vacancies").update(patch).eq("id", vid).execute()
            updated += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            sb.table("vacancies").update({"notes": f"llm_warn: {str(e)[:200]}"}).eq("id", vid).execute()

    summary = {
        "job_type": "vacancy_llm",
        "model": model,
        "min_score": min_score,
        "batch_size": n,
        "rows_loaded": len(rows),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

