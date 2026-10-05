r"""880 — TEXT THE TYPESETTER GENERATED, not text the author wrote.

A table of contents, a bibliography entry, a list label, an equation number, a
page number: LaTeX produced every one of them from counters and cross
references. The author wrote `\section{Results}` and `\cite{knuth}`; the
`3.2 Results .......... 14` and the `[7]` are the typesetter's.

MATHPIX CANNOT TELL, AND WE WERE ABOUT TO COPY THAT. Measured over the four
MathPix readings this library holds:

    1908.11415        43 bibliography lines  -> type "text"
    2609.24972       122                     -> "text"
    3395027.3419580   65                     -> "text"
    sigma26-075       68 -> "text", 11 -> "list_item"

298 bibliography lines flattened into prose. Our own reader types the same
lines `text` 70 times — the error is not inherited, we have it independently,
and `docmodel/line_types.py` already knows a `toc` family nothing emits.

(A first pass here also claimed a TOC dot-leader line was typed `math`. It was
not: the regex included `\\ldots` and matched ordinary prose carrying inline
maths, which MathPix typed correctly. sigma26-075 has no table of contents.
The bibliography number is the real finding and it did not need the other.)

WHY A PROPERTY AND NOT A TYPE. The `type` field belongs to MathPix: every
consumer in `src/docmodel/` was written against their vocabulary, and a type
they have never seen is a line those consumers drop. So the type stays
whatever MathPix would call it and this is an ADDITIONAL field — the same
contract as every other extra key we emit. A MathPix consumer ignores it; a
consumer that wants to know reads it. Being better than the reference must
not mean being incompatible with it.

WHAT THE PROPERTY SAYS. Not "this is a table of contents" but "this text was
GENERATED, and here is by what". The distinction matters because the generated
part is usually a fragment of the line: in `[7] D. Knuth, The TeXbook, 1984.`
the `[7]` is generated and the rest is a reference the author's `.bib` holds.
LaTeX "only organises the counters" — so the counter is the generated thing.

DELIBERATELY NOT A GUESS. Each rule below is a shape that only a typesetter
produces, and a line that does not match is left alone. An unmarked line is
not a claim that it is prose; it is the absence of evidence that it is not.
"""
from __future__ import annotations

import re

#: `3.2  Introduction . . . . . . . . . 14` — a dot leader joining a title to
#: a page number. No author types this; `\tableofcontents` emits it, and it is
#: the one TOC shape that needs no knowledge of where the TOC is.
_LEADER = re.compile(r"(?:\.\s*){4,}\s*\d+\s*$|…{2,}\s*\d+\s*$")

#: `[7]` or `[Knu84]` opening a line: a `\bibitem` label. The brackets are
#: generated; what follows is the entry.
_BIB_LABEL = re.compile(r"^\s*\[(\d{1,3}|[A-Za-z]{1,4}\d{2,4})\]\s+\S")

#: `7.` or `(iv)` or `(a)` opening a line, followed by real text: an `\item`
#: counter. Narrower than it looks — a sentence starting `1. ` is the same
#: shape, which is why the following token must not itself be a digit and the
#: label must be short.
_LIST_LABEL = re.compile(r"^\s*(?:\(?(?:\d{1,2}|[ivxlc]{1,5}|[a-z])\)|\d{1,2}\.)\s+(?=[^\d\s])")

#: A page number alone on its line.
_PAGE_NUMBER = re.compile(r"^\s*(?:\d{1,4}|[ivxlcdm]{1,7})\s*$", re.I)


def generated_by(text: str, *, line_type: str = "") -> "str | None":
    r"""What typeset the generated part of this line, or None.

    Returns the NAME of the generator, never a boolean: a consumer that knows
    it is looking at a `toc_entry` can do something a consumer told merely
    "generated" cannot.
    """
    t = (text or "").strip()
    if not t:
        return None
    # Order matters only where shapes overlap: a TOC entry can also open with
    # a section number that looks like a list label, and the dot leader is the
    # stronger evidence, so it is asked first.
    if _LEADER.search(t):
        return "toc_entry"
    if _BIB_LABEL.match(t):
        return "bib_entry"
    if line_type == "page_info" or _PAGE_NUMBER.match(t):
        return "page_number"
    if _LIST_LABEL.match(t) and len(t) > 12:
        # The length floor keeps `1. ` fragments and stray enumerations out:
        # a real list item carries content after its counter.
        return "list_label"
    return None


#: Everything this module can report. Named so a consumer can switch on it
#: exhaustively and a test can assert the set has not quietly grown.
GENERATORS = ("toc_entry", "bib_entry", "glossary_entry", "symbol_entry",
              "list_label", "page_number", "equation_number")

#: THE LaTeX OF GENERATED TEXT IS THE COMMAND THAT GENERATES IT.
#:
#: This is the whole point of marking it. A table of contents round-trips as
#: `\tableofcontents`, not as the expanded entries — re-typeset the document
#: and LaTeX rebuilds them from the counters, with the page numbers the NEW
#: layout produces. Emitting the expanded text as if it were source would
#: freeze last build's page numbers into the document, and they would be wrong
#: the first time anything above them changed length.
#:
#: So a generated line carries BOTH: `latex` is the command, and the text
#: field keeps what the command produced on this build. The reader records
#: what it saw; the command says how to make it again.
GENERATOR_LATEX = {
    "toc_entry": r"\tableofcontents",
    "bib_entry": r"\bibliography{}",
    "glossary_entry": r"\printglossary",
    "symbol_entry": r"\printnomenclature",
    "list_label": r"\item",
    "page_number": r"\thepage",
    "equation_number": r"\theequation",
}


#: Headings after which the body is a GENERATED LIST rather than prose.
#: LaTeX "only organises the counters" — a glossary and a symbol table are
#: lists whose entries the author supplied and whose ORDER and NUMBERING the
#: package produced. The heading is the only reliable signal that a run of
#: short entries is one of them rather than a paragraph.
SECTION_GENERATORS = (
    (re.compile(r"^\s*(?:list of )?(?:symbols?|notation|nomenclature)\b", re.I),
     "symbol_entry"),
    (re.compile(r"^\s*(?:glossary|abbreviations?|acronyms?)\b", re.I),
     "glossary_entry"),
    (re.compile(r"^\s*(?:contents|table of contents)\s*$", re.I), "toc_entry"),
    (re.compile(r"^\s*(?:references|bibliography|literature)\s*$", re.I),
     "bib_entry"),
)


def section_generator(heading: str) -> "str | None":
    """What the body under this heading is generated by, or None."""
    h = (heading or "").strip()
    for rx, name in SECTION_GENERATORS:
        if rx.match(h):
            return name
    return None
