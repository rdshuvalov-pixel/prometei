"""
Целевая строка поиска Tier 4: env TIER4_QUERY, иначе из search_targets.md
(строка _TIER4_QUERY: … или закомментированная # QUERY: …), иначе дефолт.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_TIER4_QUERY = '"Product Manager" OR "Product Lead" remote EU'

_TIER4_MD_RE = re.compile(r"^\s*_TIER4_QUERY:\s*(.+?)\s*$", re.M | re.I)
_QUERY_COMMENT_RE = re.compile(r"^\s*#\s*QUERY:\s*(.+?)\s*$", re.M | re.I)


def load_tier4_query(base_dir: Path | None = None) -> str:
    direct = (os.environ.get("TIER4_QUERY") or "").strip()
    if direct:
        return direct[:2000]

    root = base_dir or Path(__file__).resolve().parent
    path = root / "search_targets.md"
    if not path.is_file():
        return DEFAULT_TIER4_QUERY

    text = path.read_text(encoding="utf-8")
    m = _TIER4_MD_RE.search(text)
    if m:
        return m.group(1).strip()[:2000]
    m2 = _QUERY_COMMENT_RE.search(text)
    if m2:
        return m2.group(1).strip()[:2000]
    return DEFAULT_TIER4_QUERY
