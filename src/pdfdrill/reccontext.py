"""487 — the document context a recovery prompt may carry, and its provenance.

488 and 492 measured what is actually available and it is uneven: an Abstract
object in 67% of documents and NONE in johnston, `parent_section` resolving
below level 1 for 0.32% of paper rows, and `flow_index` on 100% of math
objects everywhere. 506 added a gated section path for books.

So every field here is optional and NONE OF THEM IS EMITTED AS A PLACEHOLDER.
A prompt that says "section: (unknown)" teaches the model that the section is
called unknown; a prompt that omits the line teaches it nothing, which is
correct when nothing is known.

THE NEIGHBOURS ARE THE SAME READER'S OUTPUT. That has to be said in the
prompt, not just here: a neighbouring `\\nvdash` is MathPix's error, and
offered as context without a warning it is an instruction to produce another.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TYPED = re.compile(r"_(EQ|FOX?|TAB)\d")

#: shorter than this and the "prose" is a heading, not a description
MIN_PROSE = 40


def _first_prose(model: dict) -> "tuple[str, str] | None":
    """(role, text) — the Abstract if there is one, else the first Section."""
    for o in model.get("objects", []):
        if o.get("type") == "Abstract":
            txt = (o.get("props") or {}).get("text") or ""
            if txt.strip():
                return ("abstract", txt.strip())
    best = None
    for o in model.get("objects", []):
        if o.get("type") != "Section":
            continue
        p = o.get("props") or {}
        try:
            lvl = int(p.get("level") or 99)
        except (TypeError, ValueError):
            lvl = 99
        cap = (p.get("caption") or "").strip()
        if cap and (best is None or lvl < best[0]):
            best = (lvl, cap)
    # A caption of "Introduction" is a line that says nothing, and the
    # no-placeholder rule applies to content as well as to absence: a
    # one-word heading offered as "the document's first section" spends a
    # line of the prompt to convey no document.
    if best and len(best[1]) >= MIN_PROSE:
        return ("first section", best[1])
    return None


def neighbours(model: dict, obj_id: str, k: int = 4) -> list:
    """The k nearest math objects either side of `obj_id` in FLOW order.

    Flow, not page: 488 measured flow_index on 100% of math objects and page
    on 95.4%, and two of the six test-bed rows have no page at all. Ordering
    by the field that is always there means the neighbour list exists for
    every row, including the ones that can never have a section path.
    """
    math = []
    for o in model.get("objects", []):
        if o.get("type") not in ("Equation", "Formula"):
            continue
        p = o.get("props") or {}
        fi = p.get("flow_index")
        if fi is None:
            continue
        try:
            math.append((int(fi), o["id"], p.get("latex") or "", p.get("page")))
        except (TypeError, ValueError):
            continue
    math.sort()
    idx = next((i for i, m in enumerate(math) if m[1] == obj_id), None)
    if idx is None:
        return []
    lo, hi = max(0, idx - k), min(len(math), idx + k + 1)
    return [{"latex": lx, "page": pg, "before": i < idx}
            for i, (_fi, oid, lx, pg) in enumerate(math[lo:hi], lo)
            if oid != obj_id and lx]


def build(doc_dir, obj_id: str, page=None, k: int = 4) -> dict:
    """Every context field that is KNOWN. Absent fields are absent, not blank."""
    doc_dir = Path(doc_dir)
    ctx: dict = {}
    mp = doc_dir / "model.docmodel.json"
    if not mp.is_file():
        return ctx
    try:
        model = json.loads(mp.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ctx
    pr = _first_prose(model)
    if pr:
        ctx["prose_role"], ctx["prose"] = pr[0], pr[1][:1200]
    nb = neighbours(model, obj_id, k)
    if nb:
        ctx["neighbours"] = nb
    pdfs = [p for p in doc_dir.glob("*.pdf") if not p.name.startswith("report")]
    if pdfs and str(page or "").isdigit():
        from . import sectionpath as sp
        table = sp.build(pdfs[0], mp)
        p = sp.path_for(table, int(page))
        if p:
            ctx["section"] = p
    return ctx


def render(ctx: dict) -> str:
    """The context block for the prompt. Empty string when nothing is known."""
    out = []
    if ctx.get("prose"):
        out.append("The document's %s reads:\n%s" % (ctx["prose_role"],
                                                     ctx["prose"]))
    s = ctx.get("section")
    if s:
        qual = {"section": "", "chapter": " (a chapter heading, not a section)",
                "distant": " (the nearest heading, %d pages earlier — it may "
                           "not describe this equation)" % s["pages_since_heading"]}
        out.append("This equation appears under %s %s%s."
                   % (s["number"], s["title"], qual.get(s["granularity"], "")))
    nb = ctx.get("neighbours") or []
    if nb:
        lines = ["Nearby formulas in the same document, in reading order:"]
        for n in nb:
            lines.append("  %s %s" % ("before:" if n["before"] else "after: ",
                                      n["latex"][:200]))
        lines.append(
            "These neighbours are the SAME OCR reader's output as the value "
            "you are checking. They may contain the same kinds of error. Use "
            "them for the document's notation and conventions, never as "
            "evidence that a symbol is correct.")
        out.append("\n".join(lines))
    return "\n\n".join(out)
