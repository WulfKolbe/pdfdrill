"""
Genre inference — the BibTeX entrytype as an INFERRED certificate (SO.GENRE.INFER).

The Axe-Fx-manual lesson: the toolchain applied an @article grammar to an
@manual document — `[VOL]`-style block codes became hundreds of bogus
citations, dotted-leader TOC rows were mangled, multi-column body demoted to
sidenotes. The fix is never a CLI switch ("--manual"): GENRE is a document
property the compiler infers, records with confidence + evidence, and passes
gate on via `applies()`/early-return.

The oracle ladder, cheapest first (the state-machine discipline):
  1. a DECLARED record — `doc.meta['bibtex']['entrytype']` (from a sibling
     .bib, the frontmatter pass, or an LLM bibfetch — data, not a flag) wins
     with high confidence;
  2. LOCAL structural evidence, folded: title tokens (owner's manual / user
     guide / handbook / thesis), arXiv id, abstract+References presence,
     equation density, dotted-leader TOC-row density (`..... 124`), bracketed
     BLOCK-CODE density (`[VOL]` — a controlled vocabulary, i.e. CONCEPTS, not
     citations), ISBN;
  3. ambiguity → `misc` at LOW confidence — an honest "don't know" keeps both
     interpretations alive for the compiler to judge, never a silent guess.

The decision is a weighted-vote fold with confidence = top/total — the
aggregation-algebra shape, registered as an FnSpec with declared laws.
"""
from __future__ import annotations

import re
from typing import Any

from .registry import FnSpec, register_fn

_PROSE_FIELD = {"Paragraph": "text", "Abstract": "text", "ListItem": "content",
                "Footnote": "content", "Sidenote": "content"}

_MANUAL_TITLE = re.compile(
    r"(?i)\b(owner'?s manual|user (guide|manual)|instruction manual|handbook|"
    r"reference guide|quick ?start|bedienungsanleitung|benutzerhandbuch|"
    r"handbuch)\b")
_THESIS_TITLE = re.compile(r"(?i)\b(thesis|dissertation)\b")
_MANUAL_WORD = re.compile(r"(?i)\bmanual\b")
_DOTTED_ROW = re.compile(r"\.{4,}\s*\d+\s*$")
_BLOCK_CODE = re.compile(r"\[([A-Z]{2,6}[0-9]{0,2}(?:/[A-Z0-9]+)?)\]")
_REF_CAPTION = re.compile(r"(?i)\b(references|bibliograph|literatur)\b")

_CONFIDENT = 0.7            # below this, callers must keep both readings alive


def _signals(doc) -> list[tuple[str, str, float]]:
    """[(entrytype, evidence-string, weight)] — the raw votes."""
    votes: list[tuple[str, str, float]] = []
    meta = getattr(doc, "meta", {}) or {}
    title = str(meta.get("title") or "")

    # 1) a declared record is the gold certificate
    bib = meta.get("bibtex") or {}
    et = (bib.get("entrytype") or "").lower()
    if et and et != "misc":
        votes.append((et, f"declared bibtex entrytype '{et}'", 4.0))

    if _MANUAL_TITLE.search(title):
        votes.append(("manual", f"title token ({title[:40]!r})", 2.0))
    elif _MANUAL_WORD.search(title):
        votes.append(("manual", "title contains 'manual'", 1.0))
    else:
        # no usable title (OCR models often have none): the FILENAME/bibkey is
        # legitimate evidence — "Axe-Fx-II-Owners-Manual" names its genre.
        fname = str(meta.get("bibkey") or "").replace("-", " ").replace("_", " ")
        if _MANUAL_TITLE.search(fname) or _MANUAL_WORD.search(fname):
            votes.append(("manual", f"filename token ({fname[:40]!r})", 1.5))
    if _THESIS_TITLE.search(title):
        votes.append(("phdthesis", "thesis/dissertation in title", 2.0))
    if meta.get("arxiv_id"):
        votes.append(("article", f"arxiv id {meta['arxiv_id']}", 2.0))
    if meta.get("isbn"):
        votes.append(("book", f"isbn {meta['isbn']}", 2.0))

    objs = list(getattr(doc, "objects", {}).values())
    has_abstract = any(o.type == "Abstract" for o in objs)
    has_refs = (any(o.type == "Reference" for o in objs)
                or any(o.type == "Section"
                       and _REF_CAPTION.search(o.props.get("caption") or "")
                       for o in objs))
    n_eq = sum(1 for o in objs if o.type in ("Equation", "Formula"))

    dotted = 0
    codes: set[str] = set()
    for o in objs:
        field = _PROSE_FIELD.get(o.type)
        if not field:
            continue
        text = o.props.get(field) or ""
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            if _DOTTED_ROW.search(line):
                dotted += 1
        codes.update(_BLOCK_CODE.findall(text))

    if has_abstract:
        votes.append(("article", "abstract present", 0.75))
    if has_refs:
        votes.append(("article", "references present", 0.75))
    if n_eq >= 5:
        votes.append(("article", f"{n_eq} equations/formulas", 0.5))
    if dotted >= 10:
        votes.append(("manual", f"{dotted} dotted-leader TOC rows", 1.0))
    if len(codes) >= 8:
        # scaled: a paper rarely carries 8 distinct [CAPS] codes; 25+ is a
        # controlled vocabulary beyond doubt (the Axe manual has 35)
        w = 2.0 if len(codes) >= 25 else 1.0
        votes.append(("manual", f"{len(codes)} distinct bracketed block codes "
                                f"(a controlled vocabulary, not citations)", w))
    return votes


def infer_genre(doc) -> dict[str, Any]:
    """{entrytype, confidence, evidence} — the genre certificate. `misc` at low
    confidence when the evidence does not decide (grounded absence: an unsure
    verdict must never suppress an interpretation downstream).

    A DECLARED record (doc.meta['bibtex']['entrytype'], from a .bib / the
    frontmatter pass / an LLM bibfetch) is the gold certificate: it SHORT-
    CIRCUITS the structural fold — data the user or a trusted source supplied
    outranks heuristics (conflicting structural signals are still listed in
    the evidence so a wrong record is visible)."""
    meta = getattr(doc, "meta", {}) or {}
    declared = ((meta.get("bibtex") or {}).get("entrytype") or "").lower()
    if declared and declared != "misc":
        others = [f"{why} (+{w:g} {et})" for et, why, w in _signals(doc)
                  if not why.startswith("declared")]
        return {"entrytype": declared, "confidence": 0.95,
                "evidence": [f"declared bibtex entrytype '{declared}'"] + others}

    votes = _signals(doc)
    score: dict[str, float] = {}
    for et, _why, w in votes:
        score[et] = score.get(et, 0.0) + w
    total = sum(score.values())
    if not score or total <= 0:
        return {"entrytype": "misc", "confidence": 0.0, "evidence": []}
    top = max(score, key=lambda k: score[k])
    confidence = score[top] / total
    if score[top] < 1.5 or confidence < 0.5:
        return {"entrytype": "misc", "confidence": min(confidence, 0.5),
                "evidence": [f"{why} (+{w:g} {et})" for et, why, w in votes]}
    return {"entrytype": top, "confidence": round(confidence, 3),
            "evidence": [f"{why} (+{w:g} {et})" for et, why, w in votes]}


def is_confident(genre: dict, entrytype: str) -> bool:
    """True when the certificate confidently names `entrytype` — the gate
    predicate passes use (never gate on a low-confidence verdict)."""
    return bool(genre and genre.get("entrytype") == entrytype
                and genre.get("confidence", 0) >= _CONFIDENT)


register_fn(FnSpec(
    fid="SO.GENRE.INFER",
    description="Infer the document's BibTeX entrytype (the genre certificate) "
                "from a declared record + structural evidence; misc at low "
                "confidence when undecided.",
    version="1",
    params={"confident_threshold": _CONFIDENT},
    laws=("no-guess",),
    space_in="status", space_out="ratio",
), infer_genre)
