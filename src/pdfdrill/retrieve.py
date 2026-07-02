"""
retrieve — the question→context transformation behind the chat proxy.

The external `drillui_chat` proxy asks pdfdrill to turn a user question into a
grounded CONTEXT: the few drilled units (paragraphs / sections / abstract /
formula LaTeX / concepts) most relevant to the question, each tagged with its
object id so the LLM's answer can cite exactly which units it used (and so
`chatlog` can link the answer kitem to them). This is the prototype of the
"question transformation" that may later move into a SKILL.

Retrieval is a small IDF-weighted lexical overlap over the document's own units
(an ephemeral per-doc index — no global vocabulary, no deps). It reuses
`classify`'s tokenisation + LaTeX-command stripping so a formula matches on its
identifiers, not its `\sum`/`\partial` control words. Pure + stdlib.
"""
from __future__ import annotations

import math

from .classify import _strip_latex          # reuse: kill \cmd noise in math units

_PROSE = ("Section", "Paragraph", "Abstract", "ListItem", "Footnote", "Toc")
_MATH = ("Equation", "Formula")
_CONCEPT = ("Concept",)


def _toks(s: str) -> list[str]:
    import re
    return [t.lower() for t in re.findall(r"[^\W\d_]+", s, re.U) if len(t) >= 2]


def gather_units(nodes) -> list[dict]:
    """The retrievable units of a document: {id, type, text}. Prose by its
    text/caption/content; math by its LaTeX (control words stripped); concepts
    by name. Empty/null math and non-text objects are excluded.

    S6.1: an object carrying `props['meas']` (the measurement pass) ALSO emits
    one `Measurement` unit per bound measurement — text = "<concept> <measure>
    <value> <unit> <conditions>" — so a quantitative question lexically hits
    the Measurement itself, not just its paragraph."""
    nodes = list(nodes)
    by_id = {getattr(o, "id", ""): o for o in nodes}
    units: list[dict] = []
    for o in nodes:
        t = getattr(o, "type", "")
        p = getattr(o, "props", {})
        if t in _PROSE:
            txt = (p.get("text") or p.get("caption") or p.get("content")
                   or p.get("title") or "")
        elif t in _MATH:
            v = p.get("latex") or p.get("latex_original") or ""
            txt = _strip_latex(str(v)) if v and str(v).lower() not in ("null", "none") else ""
        elif t in _CONCEPT:
            txt = p.get("name") or p.get("pref") or p.get("title") or ""
        else:
            continue
        txt = str(txt).strip()
        if txt:
            units.append({"id": getattr(o, "id", ""), "type": t, "text": txt})
    # measurement units (any object type can carry the pass layer)
    for o in nodes:
        p = getattr(o, "props", {})
        for i, m in enumerate(p.get("meas") or []):
            qref = m.get("quantity_ref") or {}
            fo = by_id.get(qref.get("obj_id") or "")
            quants = (getattr(fo, "props", {}).get("quant") or []) if fo else []
            idx = qref.get("idx", 0)
            q = quants[idx] if idx < len(quants) else {}
            cond = " ".join(f"{k} {v}" for k, v in
                            sorted((m.get("conditions") or {}).items()))
            txt = " ".join(str(x) for x in [
                m.get("concept") or "", m.get("measure") or "",
                q.get("value", ""), q.get("unit") or "", cond] if x != "")
            txt = txt.strip()
            if txt:
                units.append({"id": f"{getattr(o, 'id', '')}#m{i}",
                              "type": "Measurement", "text": txt})
    return units


def _index(units: list[dict]) -> tuple[dict, list[set]]:
    n = max(1, len(units))
    df: dict[str, int] = {}
    toksets: list[set] = []
    for u in units:
        ts = set(_toks(u["text"]))
        toksets.append(ts)
        for w in ts:
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1.0 + n / c) for w, c in df.items()}
    return idf, toksets


def retrieve(question: str, nodes, k: int = 8) -> list[dict]:
    """Top-k units for `question`, by summed IDF of shared terms. Accepts the
    document's nodes (gathers units internally). Deterministic (ties broken by
    id); units with no shared term are dropped."""
    units = gather_units(nodes)
    if not question.strip() or not units:
        return []
    idf, toksets = _index(units)
    q = set(_toks(question))
    scored: list[tuple[float, dict]] = []
    for u, ts in zip(units, toksets):
        shared = q & ts
        if not shared:
            continue
        scored.append((sum(idf.get(w, 0.0) for w in shared), u))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [{**u, "score": round(s, 4)} for s, u in scored[:k]]


def build_context(hits: list[dict], max_chars: int = 4000) -> str:
    """Render retrieved units into a citation-labelled context block: each unit
    prefixed with its id (`[p17]`) so the LLM can ground its answer in them."""
    out, used = [], 0
    for h in hits:
        line = f"[{h['id']}] ({h['type']}) {h['text']}".strip()
        if used + len(line) > max_chars:
            break
        out.append(line)
        used += len(line)
    return "\n\n".join(out)


# Prompt the proxy wraps the retrieved context in. Kept here so it is the ONE
# place the "question transformation" prompt lives (the future-SKILL seed).
def build_prompt(question: str, hits: list[dict], *, title: str = "",
                 subjects: str = "") -> str:
    ctx = build_context(hits)
    head = f"You are answering a question about the document"
    if title:
        head += f' "{title}"'
    head += "."
    if subjects:
        head += f" Subject area: {subjects}."
    return (
        f"{head}\n\n"
        "Answer ONLY from the CONTEXT below — drilled excerpts from the document, "
        "each tagged with its unit id in [brackets]. Cite the unit ids you used, "
        "in square brackets, inline. If the context does not contain the answer, "
        "say so plainly rather than guessing.\n\n"
        f"QUESTION: {question}\n\n"
        f"CONTEXT:\n{ctx}\n"
    )
