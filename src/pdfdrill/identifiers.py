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


# author-list separators on a title page / byline
_AUTHOR_SEP = re.compile(r"\s*(?:,|;|&|\band\b|\bund\b|\bet al\.?)\s*", re.I)
_NAME_TOKEN = re.compile(r"^[A-Za-z][A-Za-z.'\-]*$")


def split_author_names(text: str) -> list[str]:
    """Split a byline / author run into individual names. Splits on commas /
    'and' / '&' / ';', title-cases ALL-CAPS, and keeps only name-like chunks
    (1–4 alphabetic tokens, ≥2 chars total)."""
    out: list[str] = []
    seen: set[str] = set()
    for chunk in _AUTHOR_SEP.split(text or ""):
        chunk = re.sub(r"\s+", " ", chunk).strip(" .,")
        if not chunk:
            continue
        if chunk.isupper():
            chunk = chunk.title()
        toks = chunk.split()
        if not (1 <= len(toks) <= 4):
            continue
        if not all(_NAME_TOKEN.match(t) for t in toks):
            continue
        if len(re.sub(r"[^A-Za-z]", "", chunk)) < 2:
            continue
        # drop role labels masquerading as a 1-2 word caps chunk
        if chunk.lower() in ("edited by", "edited", "by", "author", "authors",
                             "editor", "editors"):
            continue
        if chunk not in seen:
            seen.add(chunk)
            out.append(chunk)
    return out


def resolve_authors(candidates: list[str], reference: list[str],
                    threshold: float = 80.0) -> dict:
    """Resolve split candidate names against a canonical author list via
    `match_entities` (rapidfuzz). Returns {resolved:[{candidate,canonical,
    score}], confirmed:int (distinct reference authors matched), unresolved:[
    candidates with no reference match]}. Degrades (no rapidfuzz) to exact,
    case-insensitive matching."""
    try:
        from features.features import Feature
        from features import match_entities
        cf = [Feature.create("cand", "PERSON_NAME", c, 0.6, 0, 0) for c in candidates]
        rf = [Feature.create("ref", "PERSON_NAME", r, 1.0, 0, 0) for r in reference]
        cid = {f.id: f.value for f in cf}
        rid = {f.id: f.value for f in rf}
        rels = match_entities.match(cf, rf, threshold=threshold)
        best: dict[str, tuple] = {}                  # candidate -> (canonical, score)
        for rel in rels:
            cand, canon, sc = cid[rel.source], rid[rel.target], rel.weight
            if cand not in best or sc > best[cand][1]:
                best[cand] = (canon, sc)
    except Exception:
        ref_l = {r.lower(): r for r in reference}
        best = {c: (ref_l[c.lower()], 1.0) for c in candidates if c.lower() in ref_l}

    resolved = [{"candidate": c, "canonical": v[0], "score": round(v[1], 3)}
                for c, v in best.items()]
    unresolved = [c for c in candidates if c not in best]
    confirmed = len({v[0] for v in best.values()})
    return {"resolved": resolved, "confirmed": confirmed, "unresolved": unresolved}
