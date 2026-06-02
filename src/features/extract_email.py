"""extract_email — EMAIL features via regex (optionally validated)."""
from __future__ import annotations

import re

from .features import Feature

_EMAIL = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")


def _valid(addr: str) -> bool:
    try:                                    # optional hardening
        from email_validator import validate_email, EmailNotValidError
    except ImportError:
        return True
    try:
        validate_email(addr, check_deliverability=False)
        return True
    except Exception:
        return False


def extract(text: str, page_id: str = "") -> list[Feature]:
    out: list[Feature] = []
    for m in _EMAIL.finditer(text or ""):
        addr = m.group(0)
        out.append(Feature.create(page_id, "EMAIL", addr,
                                   0.95 if _valid(addr) else 0.7,
                                   m.start(), m.end()))
    return out
