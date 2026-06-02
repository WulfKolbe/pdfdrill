"""extract_url — URL features via regex. (DOIs are handled by extract_doi.)"""
from __future__ import annotations

import re

from .features import Feature

# http(s)/ftp/www URLs; stops at whitespace and trailing sentence punctuation.
_URL = re.compile(r"(?:https?://|ftp://|www\.)[^\s<>\")\]]+", re.I)


def extract(text: str, page_id: str = "") -> list[Feature]:
    out: list[Feature] = []
    for m in _URL.finditer(text or ""):
        url = m.group(0).rstrip(".,;:)]}\"'")
        out.append(Feature.create(page_id, "URL", url, 0.93,
                                   m.start(), m.start() + len(url)))
    return out
