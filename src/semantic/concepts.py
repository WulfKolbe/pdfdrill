"""
Named-concept extraction — the "named concepts and their abstractions" layer.

A *named concept* is a term the document introduces ONCE and refers to MANY
times: an acronym (the LaTeX `\\acro`/`\\newacronym` idea), a glossary / notation
/ nomenclature entry (`\\newglossaryentry`), or an index term (`\\index`). This is
exactly the declaration/use split the semantic graph already models — one
resolved entity, one *definition* occurrence, many *reference* occurrences — so
each named concept becomes a `CONCEPT` entity (subtype `acronym`/`term`) with L3
occurrences, dual-positioned (PDF page + the containing logical section node).

This is the prerequisite for the sTeX projector: a named concept maps to
`\\symdecl{name}` + an `sdefinition` at its definition site + `\\symref` at each
reference site.

Deterministic, no LLM:
  * acronyms — the Schwartz-Hearst long-form/short-form algorithm over prose
    ("Convolutional Neural Network (CNN)" -> defines CNN; later "CNN" -> uses),
  * glossary/notation/nomenclature/abbreviation/symbol-list/index SECTIONS — each
    `TERM — definition` entry becomes a concept.

`concept_records(doc)` is pure over the docmodel (no graph); `semantic.build`
turns the records into entities + occurrences through the existing layers.
"""
from __future__ import annotations

import re
from typing import Optional

# Section captions that hold a list of named concepts (the LaTeX "lists").
_CONCEPT_SECTION = re.compile(
    r"(?i)\b(glossary|acronyms?|abbreviations?|nomenclature|notation|"
    r"list of symbols|symbol table|index)\b")

# A parenthetical short-form candidate: 2-10 chars, <=2 tokens, >=2 capitals.
_PAREN = re.compile(r"\(([^)]{2,40})\)")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.\-']*")


def _is_short_form(s: str) -> bool:
    s = s.strip()
    if not (2 <= len(s) <= 10) or len(s.split()) > 2:
        return False
    if not re.match(r"^[A-Za-z][A-Za-z0-9.\-/]*$", s):
        return False
    return sum(c.isupper() for c in s) >= 2          # acronym-ish


def _find_long_form(short: str, pre: str) -> Optional[str]:
    """Schwartz-Hearst: find the short form's long form in the text preceding the
    parenthesis. Each short-form alphanumeric char must match a char in the long
    form, scanning right-to-left, and the first (leftmost) short char must align
    to a word-initial. Returns the long form, or None."""
    s = [c.lower() for c in short if c.isalnum()]
    if not s:
        return None
    long = pre.rstrip()
    # bound the search window to a few words more than the short form length
    words = _WORD.findall(long)
    if len(words) < len(s):
        return None
    window = " ".join(words[-(len(s) + 5):])
    l = window.lower()
    si, li = len(s) - 1, len(l) - 1
    while si >= 0:
        while li >= 0 and l[li] != s[si]:
            li -= 1
        if li < 0:
            return None
        if si == 0 and not (li == 0 or not l[li - 1].isalnum()):
            li -= 1                                   # first char must be word-initial
            continue
        si -= 1
        li -= 1
    cand = window[li + 1:].strip()
    # plausibility: not absurdly longer than the acronym
    return cand if cand and len(cand.split()) <= len(s) + 4 else None


def extract_acronyms(text: str) -> dict[str, str]:
    """`{short: long}` for every "Long Form (SHORT)" acronym definition in `text`
    (Schwartz-Hearst). First definition wins."""
    out: dict[str, str] = {}
    for m in _PAREN.finditer(text):
        short = m.group(1).strip()
        if not _is_short_form(short):
            continue
        long = _find_long_form(short, text[:m.start()])
        if long and short not in out:
            out[short] = long
    return out


# ---------------------------------------------------------------------------
# Prose blocks + concept records over the docmodel
# ---------------------------------------------------------------------------

_PROSE_FIELD = {"Paragraph": "text", "Abstract": "text", "ListItem": "content",
                "Footnote": "content", "Sidenote": "content"}


def _prose_blocks(doc) -> list[dict]:
    """Prose units in flow order: {text, page, section_id}."""
    blocks = []
    for o in sorted(doc.objects.values(), key=lambda o: o.props.get("flow_index") or 0):
        field = _PROSE_FIELD.get(o.type)
        if not field:
            continue
        text = o.props.get(field) or ""
        if isinstance(text, str) and text.strip():
            blocks.append({"text": text, "page": o.props.get("page"),
                           "section_id": o.props.get("parent_section")})
    return blocks


_SYMBOL_SECTION = re.compile(r"(?i)\b(nomenclature|notation|list of symbols|"
                             r"symbol table|symbols)\b")


def _section_kind(caption: str) -> str:
    """Which named-concept list a SECTION caption denotes: symbol-list sections
    (Notation / Nomenclature / List of Symbols) hold `symbol`s for the Table of
    Symbols; glossary / acronym / abbreviation / index sections hold `term`s."""
    return "symbol" if _SYMBOL_SECTION.search(caption or "") else "term"


def _glossary_records(doc) -> list[dict]:
    """Entries of a glossary/notation/nomenclature/index SECTION → concept seeds.
    Each ListItem (`TERM — def` / `TERM: def`) becomes a `{name, expansion, kind,
    section_id, page}` seed; `kind` is `symbol` for a symbol-list section else
    `term`."""
    seeds = []
    secs = {s.id: _section_kind(s.props.get("caption", "")) for s in doc.objects.values()
            if s.type == "Section" and _CONCEPT_SECTION.search(s.props.get("caption", ""))}
    if not secs:
        return seeds
    for o in doc.objects.values():
        if o.type != "ListItem" or o.props.get("parent_section") not in secs:
            continue
        body = (o.props.get("content") or "").strip()
        m = re.match(r"\s*(.{1,60}?)\s*[—:–\-]\s+(.+)", body)
        if m:
            name, expansion = m.group(1).strip(), m.group(2).strip()
        else:
            name, expansion = body.split("  ")[0].strip(), body
        if 1 <= len(name) <= 60:
            seeds.append({"name": name, "expansion": expansion,
                          "kind": secs[o.props.get("parent_section")],
                          "section_id": o.props.get("parent_section"),
                          "page": o.props.get("page")})
    return seeds


def _token_re(name: str):
    # whole-token match: the name surrounded by non-word chars (acronyms/terms)
    return re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")


def concept_records(doc) -> list[dict]:
    """Named concepts with a definition site + reference sites, located in the
    docmodel prose. Each record:
        {name, kind, expansion,
         define: {page, section_id},
         occurrences: [{page, section_id}, ...]}        # in reading order
    The definition is the introducing site (the acronym parenthetical / the
    glossary entry); occurrences are later whole-token mentions in prose."""
    blocks = _prose_blocks(doc)
    full = "\n".join(b["text"] for b in blocks)

    seeds: dict[str, dict] = {}
    for short, long in extract_acronyms(full).items():
        seeds[short] = {"name": short, "expansion": long, "kind": "acronym"}
    for g in _glossary_records(doc):
        seeds.setdefault(g["name"], {"name": g["name"], "expansion": g["expansion"],
                                     "kind": g["kind"], "def_site": g})

    records = []
    for name, seed in seeds.items():
        rx = _token_re(name)
        hits = [{"page": b["page"], "section_id": b["section_id"]}
                for b in blocks if rx.search(b["text"])]
        if not hits:
            # a glossary term with no prose mention: still a concept, defined at
            # its glossary entry only.
            ds = seed.get("def_site")
            if ds:
                records.append({**{k: seed[k] for k in ("name", "expansion", "kind")},
                                "define": {"page": ds.get("page"), "section_id": ds.get("section_id")},
                                "occurrences": []})
            continue
        ds = seed.get("def_site")
        define = ({"page": ds.get("page"), "section_id": ds.get("section_id")} if ds
                  else hits[0])                        # acronym defined at first mention
        further = hits if ds else hits[1:]
        records.append({**{k: seed[k] for k in ("name", "expansion", "kind")},
                        "define": define, "occurrences": further})
    return records
