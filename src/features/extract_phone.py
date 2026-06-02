"""extract_phone — PHONE features via `phonenumbers` (graceful if absent).

`region` is the default country for numbers written without a `+` prefix
(e.g. "US", "DE"); international `+…` numbers are found regardless.
"""
from __future__ import annotations

from .features import Feature


def _phonenumbers():
    try:
        import phonenumbers
        return phonenumbers
    except Exception:
        return None


def available() -> bool:
    return _phonenumbers() is not None


def extract(text: str, page_id: str = "", region: str = "US") -> list[Feature]:
    pn = _phonenumbers()
    if not pn or not (text or "").strip():
        return []
    out: list[Feature] = []
    try:
        for m in pn.PhoneNumberMatcher(text, region):
            e164 = pn.format_number(m.number, pn.PhoneNumberFormat.E164)
            out.append(Feature.create(page_id, "PHONE", e164, 0.9,
                                       m.start, m.end))
    except Exception:
        return out
    return out
