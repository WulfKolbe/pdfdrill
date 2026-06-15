"""
identifiers — front-matter scan for known numbers + named-entity candidates.

A book's identifiers (ISBN, ISSN, DOI) and its publisher/author live on the
FRONT MATTER (title + copyright/imprint page). `booktoc` already tells us where
the front matter ends (the printed→PDF page offset), so we scan only those
early pages — cheap, precise, and on the lazy DocGraph read path.

Pure helpers here (`frontmatter_limit`, `collect_frontmatter_text`,
`caps_entities`); `commands.cmd_identifiers` wires them over DocGraph and the
`features` extractors (ISBN/ISSN via extract_isbn, DOI, German admin ids) plus
the arXiv id from the sidecar.

`caps_entities` is the "uppercase sequences are named-entity candidates" idea:
a run of ALL-CAPS words on the title page is almost always a publisher, author,
or institution — surfaced as NE candidates (complementing extract_names and the
acronym concepts), never asserted as resolved entities.
"""
from __future__ import annotations

import re

DEFAULT_FRONT = 5          # pages to scan when no front-matter offset is known
_FRONT_CAP = 20            # never scan more than this many "front" pages


def frontmatter_limit(offset: int, default: int = DEFAULT_FRONT,
                      cap: int = _FRONT_CAP) -> int:
    """The last PDF page to treat as front matter: the booktoc offset when it's
    a meaningful boundary, else a small default; always capped."""
    n = offset if (offset and offset >= 3) else default
    return min(n, cap)


def collect_frontmatter_text(nodes, limit: int) -> str:
    """Join the prose text of objects on pages 1..limit (front matter)."""
    parts = []
    for o in nodes:
        if o.type not in ("Paragraph", "Section", "Abstract", "ListItem", "Toc"):
            continue
        pg = o.props.get("page")
        if pg is None or pg > limit:
            continue
        t = o.props.get("text") or o.props.get("caption") or o.props.get("content") or ""
        if t:
            parts.append(t)
    return "\n".join(parts)


# ALL-CAPS run: words of 2+ uppercase letters (with internal & . - ' allowed),
# separated by single spaces. Roman numerals and id labels are excluded.
_CAPS_RUN = re.compile(r"\b[A-Z][A-Z&.'\-]*(?:\s+[A-Z][A-Z&.'\-]*)*\b")
_ROMAN = re.compile(r"^[IVXLCDM]+$")
_STOP = {"ISBN", "ISSN", "DOI", "ISMN", "LCCN", "EAN", "PDF", "TM", "AND", "OR",
         "OF", "THE", "A", "AN", "IN", "BY", "FOR", "ALL", "RIGHTS", "RESERVED",
         "USA", "UK", "EU"}


def caps_entities(text: str) -> list[str]:
    """ALL-CAPS sequences as named-entity candidates (publisher/author/org).

    A candidate is a run of caps words with >=2 words, OR a single word of >=4
    letters — minus roman numerals and id labels/stopwords. Deduped, in order."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _CAPS_RUN.finditer(text or ""):
        run = m.group(0).strip()
        words = [w for w in run.split() if w]
        # drop leading/trailing pure-stopword/roman words
        while words and (words[0] in _STOP or _ROMAN.match(words[0])):
            words.pop(0)
        while words and (words[-1] in _STOP or _ROMAN.match(words[-1])):
            words.pop()
        if not words:
            continue
        content = [w for w in words if w not in _STOP and not _ROMAN.match(w)
                   and len(re.sub(r"[^A-Z]", "", w)) >= 2]
        if not content:
            continue
        cand = " ".join(words)
        # keep multi-word runs, or a single word with >=4 caps letters
        if len(words) == 1 and len(re.sub(r"[^A-Z]", "", words[0])) < 4:
            continue
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out
