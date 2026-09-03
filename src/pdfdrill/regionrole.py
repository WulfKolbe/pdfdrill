r"""563 — what a region of the document IS: body, toc, bibliography, index.

Detected ONCE, from the section heading that opens it, and from the author's
own `\tableofcontents` / `\bibliography` where a source exists. Everything
from a heading until the next heading carries that heading's role; a document
with no such heading is entirely body.

WHY A ROLE RATHER THAN A TEST AT EACH SITE. 564 wants one rule — no
transclusion into a non-body region — and a rule that has to re-derive
"is this the bibliography" at every call site is a rule that will disagree
with itself. The role is decided once and read thereafter.

THE GERMAN BRANCH IS WRITTEN AND UNTESTED, and this is not a formality:

  German section headings in the 21 published documents      0
  Heim folders on disk                                      42
  ... drilled, with a lines.json                            12
  ... carrying a GERMAN heading in a `section_header` line   0

The Heim scans are the intended population and they cannot serve as one.
39% of their `section_header` lines carry EMPTY TEXT — 80 of 205 — so a
heading-based detector has nothing to read. The one structural German word
sitting in a structural position is `Inhaltsverzeichnis` on page 11 of
`Elementarstrukturen der Materie`, and it is in a `page_info` line: a
RUNNING HEADER, which repeats and does not open a region. Matching it would
mark the wrong thing. The only other hit is `Literatur` inside ordinary
prose — "die betreffende Literatur als Metapher" — which is the false
positive the word invites.

So: the patterns are here, they are believed correct, and nothing in this
corpus exercises them. That is stated rather than implied.
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
