#!/usr/bin/env python3
"""
vacancy_llm (optional):
  - selects strong vacancy_candidates (pipeline_status=scored, score>=LLM_MIN_SCORE)
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
    # Candidate facts (from prometei_job_search_skill/data_cv.md + Screening_Shuvalov.md).
    candidate = "\n".join(
        [
            "Кандидат: Ruslan Shuvalov",
            "Профиль: Senior Product Manager | FinTech | B2B SaaS | AI Products",
            "Локация: Portugal (near Lisbon) | EU citizen | Remote preferred",
            "",
            "Ключевые достижения (используй 1 сильную цифру):",
            "- ARPU +90% (монетизация, contextual upsell, UDP Auto)",
            "- Support 2.5 days → 6 hours; 46% requests automated by AI agent (Unlimit)",
            "- New product 0 → 2.4M RUB/month; +31% revenue contribution (InSales)",
        ],
    )

    # Output contract (from 02_output.md + 05_cover_letter.md + 03_communication.md).
    return "\n".join(
        [
            "Ты — карьерный агент «Прометей». Пиши коротко, по делу, без воды и без выдумок.",
            "Цель: подготовить материалы для отклика по вакансии.",
            "",
            "Верни СТРОГО JSON объект с ключами:",
            '  fit_reasoning: string (2-4 предложения: стоит ли откликаться и почему)',
            '  why_fit: array[string] (5-8 bullet points: JD -> релевантный опыт кандидата)',
            '  why_not: array[string] (0-5 bullet points: риски/несовпадения или пустой список)',
            '  cover_formal: string (EN, 150–220 words, 3–5 paragraphs, 1 strong metric)',
            '  cover_informal: string (EN, 5–8 lines, 1–2 facts/metrics, вопрос в конце)',
            '  notes: string (коротко: если данные неполные/remote неясно/ATS JS-heavy — что проверить)',
            "",
            "Правила:",
            "- Не пиши общие фразы типа “motivated / great fit” без доказательств.",
            "- Если в JD про payments/compliance — используй FinTech фрейм; если про growth/pricing — growth фрейм.",
            "- Если локация спорная (office/hybrid не Lisbon) — укажи риск в notes.",
            "",
            "Данные кандидата:",
            candidate,
            "",
            f"Компания: {_as_text(row.get('company'))}",
            f"Роль: {_as_text(row.get('role_title'))}",
            f"URL: {_as_text(row.get('url'))}",
            "Details:",
            _as_text(row.get("details")),
        ],
    )


def _call_openai(*, key: str, base: str, model: str, prompt: str, timeout_sec: float = 60.0) -> dict:
    # OpenRouter SDK uses base https://openrouter.ai/api and appends /v1 internally.
    # To support both styles, normalize /api -> /api/v1 for OpenAI-compatible endpoints.
    norm_base = base.rstrip("/")
    if norm_base.endswith("/api"):
        norm_base = f"{norm_base}/v1"
    url = f"{norm_base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return strictly valid JSON. No markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    # OpenRouter may redirect /api/chat/completions -> /api/v1/chat/completions; follow redirects.
    with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception as e:  # noqa: BLE001
            head = (r.text or "")[:280].replace("\n", "\\n")
            raise ValueError(f"non-json response status={r.status_code} head={head} err={e}") from e
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


def _pick_list_str(out: dict, *keys: str) -> list[str] | None:
    for k in keys:
        v = out.get(k)
        if isinstance(v, list):
            items: list[str] = []
            for it in v:
                if isinstance(it, str) and it.strip():
                    items.append(it.strip())
            if items:
                return items
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
    force = (os.environ.get("VACANCY_LLM_FORCE") or "").strip().lower() in ("1", "true", "yes", "on")
    sid = (os.environ.get("SEARCH_ID") or "").strip()

    q = (
        sb.table("vacancy_candidates")
        .select(
            "id, company, role_title, external_url, raw, score, pipeline_status, fit_reasoning, cover_formal, cover_informal, notes",
        )
        .eq("pipeline_status", "scored")
        .gte("score", min_score)
        .order("score", desc=True)
    )
    if sid:
        q = q.eq("search_id", sid)
    res = q.limit(n).execute()
    rows = getattr(res, "data", None) or []
    target_table = "vacancy_candidates"

    if not rows:
        # Legacy fallback: process vacancies directly if candidates pipeline is not producing scored rows yet.
        res2 = (
            sb.table("vacancies")
            .select("id, company, role_title, url, details, score, fit_reasoning, cover_formal, cover_informal, notes")
            .gte("score", min_score)
            .order("score", desc=True)
            .limit(n)
            .execute()
        )
        rows = getattr(res2, "data", None) or []
        target_table = "vacancies"

    updated = 0
    skipped = 0
    errors = 0
    last_error: str | None = None

    for r in rows:
        vid = r.get("id")
        if vid is None:
            skipped += 1
            continue
        already_has_letters = bool(_as_text(r.get("cover_formal")).strip() and _as_text(r.get("cover_informal")).strip())
        already_has_reason = bool(_as_text(r.get("fit_reasoning")).strip())
        already_has_why_blocks = "Почему подходит" in _as_text(r.get("notes")) or "Why fits" in _as_text(r.get("notes"))
        if (not force) and already_has_letters and already_has_reason and already_has_why_blocks:
            skipped += 1
            continue
        try:
            if target_table == "vacancies":
                prompt_row = {
                    "company": r.get("company"),
                    "role_title": r.get("role_title"),
                    "url": r.get("url"),
                    "details": r.get("details"),
                }
            else:
                prompt_row = {
                    "company": r.get("company"),
                    "role_title": r.get("role_title"),
                    "url": r.get("external_url"),
                    "details": r.get("raw"),
                }
            out = _call_openai(key=key, base=base, model=model, prompt=_prompt(prompt_row))
            patch: dict = {}
            cf = _pick_str(out, "cover_formal", "formal", "coverLetterFormal")
            ci = _pick_str(out, "cover_informal", "informal", "coverLetterInformal")
            fr = _pick_str(out, "fit_reasoning", "reasoning", "fit", "rationale", "match_reasoning")
            notes = _pick_str(out, "notes", "note")
            why_fit = _pick_list_str(out, "why_fit", "whyFit", "fit_points")
            why_not = _pick_list_str(out, "why_not", "whyNot", "risks")

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
            # Store structured bullets into notes (append) to keep UI compatibility.
            note_parts: list[str] = []
            if why_fit:
                note_parts.append("✅ Почему подходит:\n- " + "\n- ".join(why_fit[:10]))
            if why_not:
                note_parts.append("⚠️ Почему не подходит:\n- " + "\n- ".join(why_not[:10]))
            if notes:
                note_parts.append(f"📝 Notes:\n{notes}")
            if note_parts:
                prev = _as_text(r.get("notes")).strip()
                blob = "\n\n".join(note_parts).strip()
                patch["notes"] = (prev + "\n\n" + blob).strip() if prev else blob
            if not patch:
                skipped += 1
                continue
            if target_table == "vacancy_candidates":
                patch["llm_at"] = _utc_iso()
                patch["pipeline_status"] = "llm_done"
            sb.table(target_table).update(patch).eq("id", vid).execute()
            updated += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            last_error = str(e)
            sb.table(target_table).update({"notes": f"llm_warn: {str(e)[:200]}"}).eq("id", vid).execute()

    summary = {
        "job_type": "vacancy_llm",
        "model": model,
        "base_url": base,
        "min_score": min_score,
        "batch_size": n,
        "rows_loaded": len(rows),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "last_error": (last_error[:400] if last_error else None),
        "finished_at": _utc_iso(),
    }
    print(_SUMMARY_MARKER, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

