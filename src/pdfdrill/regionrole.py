r"""563 — what a region of the document IS: body, toc, bibliography, index.

Detected ONCE, from the section heading that opens it, and from the author's
own `\tableofcontents` / `\bibliography` where a source exists. Everything
from a heading until the next heading carries that heading's role; a document
with no such heading is entirely body.

WHY A ROLE RATHER THAN A TEST AT EACH SITE. 564 wants one rule — no
transclusion into a non-body region — and a rule that has to re-derive
"is this the bibliography" at every call site is a rule that will disagree
with itself. The role is decided once and read thereafter.

THE GERMAN BRANCH IS TESTED, on five documents in this library:

  BH1, bh2, BH3FR, WDorg4, BH1org_OCR — 42,143 lines, 538 in a non-body
  region. Every one opens with `INHALTSVERZEICHNIS` as a `section_header`,
  and WDorg4 also carries `LITERATURVERZEICHNIS` on page 169.

Two things in those documents validate rules that were otherwise only
asserted:

  * `Inhaltsverzeichnis` ALSO appears as a `page_info` line on the page
    after each TOC heading — the running header. It repeats and opens
    nothing. Reading only `section_header` is what keeps it out.
  * WDorg4 page 10 has `Literaturverzeichnis` as a
    `table_of_contents_item`: the TOC's own entry NAMING the bibliography,
    120 pages before the bibliography starts. Matching it would put the
    whole book in a bibliography region.

The headings are UPPERCASE, which the case-insensitive patterns take.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BODY, TOC, BIBLIOGRAPHY, INDEX = "body", "toc", "bibliography", "index"

#: Anchored at the start and allowed a leading number, because a heading is
#: "5 Bibliography" as often as "Bibliography". NOT a substring search: 
#: `Literatur` occurs inside German prose and `Index` inside "Index Theorem".
_ROLE_PATTERNS = (
    (BIBLIOGRAPHY, re.compile(
        r"^\s*(?:\d+(?:\.\d+)*\.?\s*)?"
        r"(references|bibliography|works\s+cited"
        r"|literatur|literaturverzeichnis|quellenverzeichnis)\s*$", re.I)),
    (TOC, re.compile(
        r"^\s*(?:\d+(?:\.\d+)*\.?\s*)?"
        r"(contents|table\s+of\s+contents|inhalt|inhaltsverzeichnis)\s*$", re.I)),
    (INDEX, re.compile(
        r"^\s*(?:\d+(?:\.\d+)*\.?\s*)?"
        r"(index|subject\s+index|stichwortverzeichnis|sachverzeichnis"
        r"|namenverzeichnis|register)\s*$", re.I)),
)


def role_of_heading(text: str) -> str:
    """The role a heading opens, or BODY when it opens nothing special."""
    for role, pat in _ROLE_PATTERNS:
        if pat.match(text or ""):
            return role
    return BODY


def roles_for(lines_path) -> list:
    r"""[(page, line_index, type, role)] for every line, in document order.

    A `section_header` decides the role from that point on. Lines before the
    first heading are body. `page_info` is never a heading: it is the running
    header, it repeats on every page, and on the one German document in this
    library it carries the word `Inhaltsverzeichnis` on a page that is not
    the table of contents.
    """
    j = json.loads(Path(lines_path).read_text(encoding="utf-8",
                                              errors="replace"))
    out, role = [], BODY
    for page, pg in enumerate(j.get("pages") or [], 1):
        for i, ln in enumerate(pg.get("lines") or []):
            t = ln.get("type")
            if t == "section_header":
                found = role_of_heading(ln.get("text") or "")
                role = found          # BODY resets, which is what ends a region
            out.append((page, i, t, role))
    return out


def tex_declares(source_dir) -> dict:
    r"""{toc: bool, bibliography: bool} from the author's own source.

    `\tableofcontents` and `\bibliography`/`\printbibliography` say a region
    EXISTS without saying where it starts, so this corroborates the heading
    scan rather than replacing it: a document whose source declares a
    bibliography and whose headings show none is a detection failure worth
    seeing, not a document without references.
    """
    out = {TOC: False, BIBLIOGRAPHY: False}
    p = Path(source_dir)
    if not p.exists():
        return out
    files = [p] if p.is_file() else list(p.rglob("*.tex"))
    for f in files[:400]:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"\\tableofcontents\b", t):
            out[TOC] = True
        if re.search(r"\\(?:bibliography|printbibliography|thebibliography)\b", t):
            out[BIBLIOGRAPHY] = True
    return out
