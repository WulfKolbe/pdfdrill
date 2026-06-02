"""extract_dates — DATE features via `dateparser` (graceful if absent)."""
from __future__ import annotations

from .features import Feature


def _search_dates():
    try:
        from dateparser.search import search_dates
        return search_dates
    except Exception:
        return None


def available() -> bool:
    return _search_dates() is not None


def extract(text: str, page_id: str = "", languages: list[str] | None = None) -> list[Feature]:
    sd = _search_dates()
    if not sd or not (text or "").strip():
        return []
    try:
        found = sd(text, languages=languages,
                   settings={"STRICT_PARSING": True}) or []
    except Exception:
        return []
    out: list[Feature] = []
    cursor = 0
    for sub, dt in found:
        idx = text.find(sub, cursor)
        start = idx if idx >= 0 else None
        end = (idx + len(sub)) if idx >= 0 else None
        if idx >= 0:
            cursor = end
        out.append(Feature.create(page_id, "DATE", dt.date().isoformat(),
                                   0.8, start, end))
    return out
