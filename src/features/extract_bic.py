"""extract_bic — BIC/SWIFT features (ISO 9362: 8 or 11 chars).

Bare BIC patterns over-match ordinary uppercase words, so a hit is accepted only
when it is labelled (BIC/SWIFT nearby) or 11 chars long with a valid country
code in positions 5-6.
"""
from __future__ import annotations

import re

from .features import Feature

# bank(4 letters) + country(2 letters) + location(2 alnum) + optional branch(3).
_BIC = re.compile(r"\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b")
_LABEL = re.compile(r"\b(?:BIC|SWIFT)\b", re.I)
_COUNTRIES = {"DE", "AT", "CH", "FR", "NL", "BE", "GB", "IT", "ES", "LU", "US"}


def extract(text: str, page_id: str = "") -> list[Feature]:
    text = text or ""
    out: list[Feature] = []
    seen: set = set()
    for m in _BIC.finditer(text):
        bic = m.group(1)
        if bic in seen:
            continue
        window = text[max(0, m.start() - 25):m.start()]
        labelled = bool(_LABEL.search(window))
        plausible = bic[4:6] in _COUNTRIES
        if not (labelled or (len(bic) == 11 and plausible)):
            continue
        seen.add(bic)
        out.append(Feature.create(page_id, "BIC", bic,
                                   0.9 if labelled else 0.6, m.start(1), m.end(1)))
    return out


def available() -> bool:
    return True
