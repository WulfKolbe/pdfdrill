"""
Citation tiddler titles — the single place a citekey becomes a title.

A citekey reaches a tiddler title from three directions: the marker baked into
paragraph text at build time (`latex_source._transclude_cites`), the Reference
tiddler the projector emits, and the PLACEHOLDER tiddler the projector emits for
a citekey with no Reference behind it. Each derived the name independently, and
the placeholder disagreed — so on a document with citations but no bibliography
(the normal state before `bibsource` runs) every citation link pointed at a
title nothing had created: 46 of 46 dangling on 2209.00445v3.

Underscores and hyphens are KEPT. Stripping every non-alphanumeric turned the
author's `knn_with_lime` into `knnwithlime`, which is both harder to read and
impossible to map back to the .bib entry by eye.
"""
from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^A-Za-z0-9_\-]+")


def safe_citekey(citekey: str) -> str:
    """A citekey reduced to what a tiddler title may hold, keeping `_` and `-`.

    Runs of unsafe characters collapse to ONE underscore, and leading/trailing
    ones are trimmed, so `van der Berg:2019` → `van_der_Berg_2019` rather than a
    name with doubled or dangling separators.
    """
    return _UNSAFE.sub("_", (citekey or "").strip()).strip("_")


def citation_title(bibkey: str, citekey: str, index: int | None = None) -> str:
    """The tiddler title for `citekey` in `bibkey`'s namespace.

    `index` (1-based) names an entry whose citekey is empty — a printed
    bibliography parsed from OCR often has no key at all.
    """
    key = safe_citekey(citekey)
    if not key:
        key = str(index if index is not None else 1)
    return f"{bibkey}_REF_{key}"
