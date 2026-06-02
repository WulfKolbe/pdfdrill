"""extract_address — ADDRESS features via `usaddress` (US-centric; graceful).

usaddress tags a single address string. We run it per line and emit an ADDRESS
feature when the line parses with real street components (AddressNumber +
StreetName). US-centric — kept as a starting point / idea source for a future
locale-aware address extractor.
"""
from __future__ import annotations

from .features import Feature


def _usaddress():
    try:
        import usaddress
        return usaddress
    except Exception:
        return None


def available() -> bool:
    return _usaddress() is not None


def extract(text: str, page_id: str = "") -> list[Feature]:
    ua = _usaddress()
    if not ua or not (text or "").strip():
        return []
    out: list[Feature] = []
    cursor = 0
    for line in text.splitlines():
        s = line.strip()
        idx = text.find(line, cursor)
        if idx >= 0:
            cursor = idx + len(line)
        if len(s) < 6:
            continue
        try:
            tagged, kind = ua.tag(s)
        except Exception:               # RepeatedLabelError etc.
            continue
        labels = set(tagged.keys())
        if {"AddressNumber", "StreetName"} <= labels:
            start = idx + (len(line) - len(line.lstrip())) if idx >= 0 else None
            end = (start + len(s)) if start is not None else None
            out.append(Feature.create(page_id, "ADDRESS", s, 0.7, start, end))
    return out
