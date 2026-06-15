"""extract_isbn — ISBN-10 / ISBN-13 / ISSN, with self-contained checksum
validation (no python-stdnum dep; mirrors extract_iban's keyless approach).

These live on a book's copyright / imprint page (front matter). Each is emitted
as a Feature whose type is ISBN or ISSN and whose value is the normalized form
(ISBN → digits only; ISSN → NNNN-NNNN). Only checksum-valid identifiers are
emitted, so a stray 13-digit order number is never mistaken for an ISBN.
"""
from __future__ import annotations

import re

from .features import Feature

# candidate token shapes (validated by checksum before emitting)
_ISBN13 = re.compile(r"\b97[89][\d\- ]{10,16}\d\b")
_ISBN10 = re.compile(r"\b\d[\d\- ]{8,12}[\dX]\b", re.I)
_ISSN = re.compile(r"\b\d{4}-\d{3}[\dX]\b", re.I)
# a preceding label raises confidence and disambiguates ISBN-10 from noise
_LABEL = re.compile(r"(?i)\b(e-?)?is[bs]n(?:[-\s]?1[03])?\b")


def _digits(s: str) -> str:
    return re.sub(r"[^0-9Xx]", "", s).upper()


def valid_isbn13(s: str) -> bool:
    d = _digits(s)
    if len(d) != 13 or not d.isdigit():
        return False
    chk = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(d))
    return chk % 10 == 0


def valid_isbn10(s: str) -> bool:
    d = _digits(s)
    if len(d) != 10 or not re.fullmatch(r"\d{9}[\dX]", d):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d))
    return total % 11 == 0


def valid_issn(s: str) -> bool:
    d = _digits(s)
    if len(d) != 8 or not re.fullmatch(r"\d{7}[\dX]", d):
        return False
    total = sum((8 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d))
    return total % 11 == 0


def extract(text: str, page_id: str = "") -> list[Feature]:
    text = text or ""
    out: list[Feature] = []
    seen: set[tuple[str, str]] = set()

    def add(typ: str, value: str, m, conf: float) -> None:
        key = (typ, value)
        if key in seen:
            return
        seen.add(key)
        out.append(Feature.create(page_id, typ, value, conf, m.start(), m.end()))

    for m in _ISBN13.finditer(text):
        if valid_isbn13(m.group(0)):
            add("ISBN", _digits(m.group(0)), m, 0.97)
    for m in _ISBN10.finditer(text):
        if valid_isbn10(m.group(0)):
            labelled = bool(_LABEL.search(text[max(0, m.start() - 12):m.start()]))
            add("ISBN", _digits(m.group(0)), m, 0.97 if labelled else 0.9)
    for m in _ISSN.finditer(text):
        if valid_issn(m.group(0)):
            add("ISSN", m.group(0).upper(), m, 0.95)
    return out


def available() -> bool:
    return True
