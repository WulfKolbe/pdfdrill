"""extract_doi — DOI features via regex (type DOI)."""
from __future__ import annotations

import re

from .features import Feature

_DOI = re.compile(r"10\.\d{4,}/[^\s\"<>)\]]+", re.I)


def extract(text: str, page_id: str = "") -> list[Feature]:
    out: list[Feature] = []
    for m in _DOI.finditer(text or ""):
        doi = m.group(0).rstrip(".,;:)]}\"'")
        out.append(Feature.create(page_id, "DOI", doi, 0.95,
                                   m.start(), m.start() + len(doi)))
    return out
