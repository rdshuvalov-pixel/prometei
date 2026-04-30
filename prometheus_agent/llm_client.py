from __future__ import annotations

import json
import os

import httpx


def openai_cfg(*, default_model: str) -> tuple[str, str, str] | None:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().rstrip("/")
    model = (os.environ.get("OPENAI_MODEL") or default_model).strip()
    return key, base, model


def call_openai_json(
    *,
    key: str,
    base: str,
    model: str,
    system: str,
    prompt: str,
    temperature: float = 0.2,
    timeout_sec: float = 60.0,
) -> dict:
    norm_base = base.rstrip("/")
    if norm_base.endswith("/api"):
        norm_base = f"{norm_base}/v1"
    url = f"{norm_base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(temperature),
    }
    with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    content = (((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty LLM response")
    s = content.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("LLM did not return JSON object")
    obj = json.loads(s[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("LLM JSON is not an object")
    return obj

