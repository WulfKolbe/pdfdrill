"""extract_iban — IBAN features with self-contained mod-97 checksum validation.

No schwifty/stdnum: ISO 13616 (move the first 4 chars to the end, map A-Z→10-35,
mod 97 == 1). For a German IBAN the BLZ (Bankleitzahl) and account number are
derivable from fixed positions — see `german_parts`.
"""
from __future__ import annotations

import re

from .features import Feature

# IBAN: 2 country letters, 2 check digits, then up to 30 alnum (spaces allowed
# in the printed form, grouped in 4s).
_IBAN = re.compile(r"\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,34})\b")

# Per-country IBAN length (used to cut a candidate that ran into the next token,
# e.g. "DE…72 BIC COLSDE33" → the 22-char DE IBAN).
_IBAN_LEN = {"DE": 22, "AT": 20, "CH": 21, "NL": 18, "FR": 27, "BE": 16,
             "GB": 22, "IT": 27, "ES": 24, "LU": 20}


def is_valid(iban: str) -> bool:
    s = re.sub(r"\s+", "", iban or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{1,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(digits) % 97 == 1
    except ValueError:
        return False


def german_parts(iban: str) -> dict:
    """For a DEkk IBAN return {blz, konto}; {} otherwise. DE = DEkk BBBBBBBB KKKKKKKKKK."""
    s = re.sub(r"\s+", "", iban or "").upper()
    if not s.startswith("DE") or len(s) != 22:
        return {}
    return {"blz": s[4:12], "konto": s[12:22].lstrip("0") or "0"}


def extract(text: str, page_id: str = "") -> list[Feature]:
    out: list[Feature] = []
    seen: set = set()
    for m in _IBAN.finditer(text or ""):
        norm = re.sub(r"\s+", "", m.group(1)).upper()
        # Cut a candidate that ran into the following token to the country length.
        n = _IBAN_LEN.get(norm[:2])
        if n and len(norm) > n:
            norm = norm[:n]
        if norm in seen:
            continue
        seen.add(norm)
        valid = is_valid(norm)
        out.append(Feature.create(page_id, "IBAN", norm,
                                   1.0 if valid else 0.3, m.start(1), m.end(1)))
    return out


def available() -> bool:
    return True
