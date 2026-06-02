"""extract_ids — German administrative identifiers (labelled).

Emits one Feature per labelled id, the label becoming the type:
Steuernummer→STEUERNUMMER, Kassenzeichen→KASSENZEICHEN, Aktenzeichen→AKTENZEICHEN,
Rechnungsnummer→INVOICE_NO, Kundennummer→CUSTOMER_NO. Value is the id token.
"""
from __future__ import annotations

import re

from .features import Feature

_LABELS = [
    ("STEUERNUMMER", r"Steuernummer|Steuer-?Nr\.?|St\.?-?Nr\.?"),
    ("KASSENZEICHEN", r"Kassenzeichen"),
    ("AKTENZEICHEN", r"Aktenzeichen|Az\.?"),
    ("INVOICE_NO", r"Rechnungs(?:nummer|-?Nr\.?)"),
    ("CUSTOMER_NO", r"Kunden(?:nummer|-?Nr\.?)"),
]
# value: a digit-led id with German separators ( . / - space ), e.g.
# "725.356.194.433", "17-70", "204/5012/3456".
_VALUE = re.compile(r"\s*[:#]?\s*(\d[\d./\- ]{3,40}\d)")
_RULES = [(typ, re.compile(lbl, re.I)) for typ, lbl in _LABELS]


def extract(text: str, page_id: str = "") -> list[Feature]:
    text = text or ""
    out: list[Feature] = []
    seen: set = set()
    for typ, label_re in _RULES:
        for lm in label_re.finditer(text):
            vm = _VALUE.match(text, lm.end())
            if not vm:
                continue
            value = vm.group(1).strip(" .-")
            key = (typ, value)
            if key in seen:
                continue
            seen.add(key)
            out.append(Feature.create(page_id, typ, value, 0.85,
                                       vm.start(1), vm.end(1)))
    return out


def available() -> bool:
    return True
