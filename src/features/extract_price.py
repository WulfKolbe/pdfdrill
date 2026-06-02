"""extract_price — PRICE features via `price-parser` (graceful if absent).

price-parser parses ONE string into (amount, currency); it doesn't search. So
we regex candidate money tokens, then parse each. Value is `"<amount> <currency>"`.
"""
from __future__ import annotations

import re

from .features import Feature

# A currency symbol/code adjacent to a number, either order.
_MONEY = re.compile(
    r"(?:(?:[$€£¥]|USD|EUR|GBP|CHF|JPY)\s?\d[\d.,]*"
    r"|\d[\d.,]*\s?(?:[$€£¥]|USD|EUR|GBP|CHF|JPY|Euro|Dollar))",
    re.I)


def _price_cls():
    try:
        from price_parser import Price
        return Price
    except Exception:
        return None


def available() -> bool:
    return _price_cls() is not None


def extract(text: str, page_id: str = "") -> list[Feature]:
    Price = _price_cls()
    if not Price or not (text or "").strip():
        return []
    out: list[Feature] = []
    for m in _MONEY.finditer(text):
        token = m.group(0)
        try:
            p = Price.fromstring(token)
        except Exception:
            continue
        if p.amount is None:
            continue
        value = f"{p.amount}" + (f" {p.currency}" if p.currency else "")
        out.append(Feature.create(page_id, "PRICE", value, 0.85,
                                   m.start(), m.end()))
    return out
