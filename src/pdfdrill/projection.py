"""
projection — structural projection of the docmodel into an LLM context
(the `pdfdrill context` command; the module is `projection` because context.py is
the engine's DocumentContext).

PDFDRILL is a semantic CONTEXT PROVIDER: the docmodel is the canonical IR, and a
`context` query is codegen from it — a small set of typed docmodel objects rendered
to Markdown with metadata + object ids, capped to a token budget. The LLM sees a
PROJECTION, never the whole document and never a filename.

This is a deterministic, STRUCTURAL RAG retriever: same shape as embedding RAG
(query → top-k chunks → inject) but retrieval is structural (typed objects + IDF +
type/section/concept filters) and each chunk is a real object with true metadata.

Selection = filters ∩ rank. The RANKER is pluggable per ASPECT (`RANKERS` +
`register_ranker`): the default `structural` ranker reuses `retrieve`'s IDF; future
embedding rankers (SPECTER2 / math-embed for math LaTeX, crossref for citations)
register here without touching this core. A ranker is
`fn(query, units) -> units-with-score` — the ONLY contract they must satisfy.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import retrieve as _r
from .classify import _strip_latex

# Projectable object types → the prop field holding their renderable body. Wider
# than retrieve's QA-tuned set: theorems/proofs, tables, references and figures
# are first-class projection targets. Math keeps its REAL LaTeX as the body (a
# projection must be renderable), with a control-word-stripped copy for ranking.
_PROSE_TYPES = {"Paragraph", "Abstract", "Section", "ListItem", "Footnote",
                "Theorem", "Proof", "Caption"}
_MATH_TYPES = {"Formula", "Equation"}


def _gather(nodes) -> list[dict]:
    """Projectable units: {id, type, text (for ranking), body (for rendering)}.
    Unlike retrieve.gather_units, the BODY keeps real LaTeX / full prose so the
    projection is renderable; TEXT is the match form (stripped math)."""
    units = []
    for o in nodes:
        t = getattr(o, "type", "")
        p = getattr(o, "props", {})
        if t in _PROSE_TYPES:
            body = (p.get("text") or p.get("caption") or p.get("content")
                    or p.get("title") or "")
        elif t in _MATH_TYPES:
            body = p.get("latex") or p.get("latex_original") or ""
            if str(body).strip().lower() in ("", "null", "none"):
                continue
        elif t == "Concept":
            body = p.get("name") or p.get("pref") or p.get("title") or ""
        elif t == "Table":
            body = p.get("raw_text") or p.get("caption") or ""
        elif t in ("Reference", "Citation"):
            body = p.get("raw_text") or p.get("bibtex") or p.get("citekey") or ""
        elif t in ("Picture", "Diagram", "EmbeddedImage"):
            body = p.get("caption") or ""
        else:
            continue
        body = str(body).strip()
        if not body:
            continue
        text = _strip_latex(body) if t in _MATH_TYPES else body
        units.append({"id": getattr(o, "id", ""), "type": t,
                      "text": text, "body": body})
    return units

# --- the pluggable ranker seam -------------------------------------------------
Ranker = Callable[[str, list[dict]], list[dict]]


def structural_rank(query: str, units: list[dict]) -> list[dict]:
    """Default ranker: IDF over shared tokens (reuses retrieve's index). Returns
    units with a `score`, most-relevant first. No query → flow order (unchanged)."""
    if not query.strip() or not units:
        return list(units)
    idf, toksets = _r._index(units)
    q = set(_r._toks(query))
    scored = []
    for u, ts in zip(units, toksets):
        shared = q & ts
        scored.append((sum(idf.get(w, 0.0) for w in shared), u))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [{**u, "score": round(s, 4)} for s, u in scored]


RANKERS: dict[str, Ranker] = {"structural": structural_rank}


def register_ranker(aspect: str, fn: Ranker) -> None:
    """Register a per-aspect ranker (e.g. 'math' → a SPECTER2/math-embed ranker,
    'citation' → a crossref ranker). Slots into `context` with no core change."""
    RANKERS[aspect] = fn


# --- selection -----------------------------------------------------------------
# type filter tokens → DocObject type names (lowercased match, plurals tolerated)
_TYPE_ALIASES = {
    "definition": {"concept", "definition"},
    "formula": {"formula", "equation"},
    "equation": {"equation", "formula"},
    "theorem": {"theorem", "proof"},
    "figure": {"picture", "diagram", "figure", "embeddedimage"},
    "table": {"table"},
    "reference": {"reference", "citation"},
    "concept": {"concept"},
    "section": {"section"},
    "paragraph": {"paragraph", "abstract"},
}


def _wanted_types(types: Optional[list[str]]) -> Optional[set]:
    if not types:
        return None
    out: set = set()
    for t in types:
        out |= _TYPE_ALIASES.get(t.strip().lower(), {t.strip().lower()})
    return out


def _node_map(nodes) -> dict:
    return {getattr(o, "id", ""): o for o in nodes}


def _section_label(node, nmap: dict) -> str:
    """A readable section label for the metadata header / --section filter: the
    object's own section_number, or — when parent_section is an object id — the
    referenced Section's number/caption (never the opaque id)."""
    if node is None:
        return ""
    p = getattr(node, "props", {})
    if p.get("section_number"):
        return str(p["section_number"])
    parent = p.get("parent_section") or ""
    so = nmap.get(parent)
    if so is not None:
        sp = getattr(so, "props", {})
        return str(sp.get("section_number") or sp.get("caption") or "")
    return str(parent)


def select_units(nodes, query: str = "", *, types: Optional[list[str]] = None,
                 concept: Optional[str] = None, section: Optional[str] = None,
                 k: Optional[int] = None, aspect: str = "structural") -> list[dict]:
    """Filter the retrievable units (type / concept / section), then rank by the
    chosen aspect ranker (default structural/IDF). Returns units enriched with
    metadata (page/section/refnum) from the node. `k` caps the result."""
    nodes = list(nodes)
    nmap = _node_map(nodes)
    units = _gather(nodes)

    want = _wanted_types(types)
    if want is not None:
        units = [u for u in units if u["type"].lower() in want]
    if section:
        s = str(section).strip().lower()
        def _sec(uid):
            return _section_label(nmap.get(uid.split("#")[0]), nmap).lower()
        units = [u for u in units
                 if _sec(u["id"]) == s or _sec(u["id"]).startswith(s + ".")]
    if concept:
        c = concept.strip().lower()
        keep_ids = set()
        for o in nodes:
            p = getattr(o, "props", {})
            name = str(p.get("name") or p.get("pref") or "").lower()
            if getattr(o, "type", "") == "Concept" and name and (c in name or name in c):
                keep_ids.add(getattr(o, "id", ""))
        units = ([u for u in units if u["id"].split("#")[0] in keep_ids]
                 or [u for u in units if c in u["text"].lower()])

    ranker = RANKERS.get(aspect) or RANKERS["structural"]
    try:
        ranked = ranker(query, units)
    except Exception:                              # a flaky embedding ranker → structural
        ranked = structural_rank(query, units)
    if k:
        ranked = ranked[:k]
    # enrich with metadata for the markdown header
    for u in ranked:
        o = nmap.get(u["id"].split("#")[0])
        p = getattr(o, "props", {}) if o else {}
        u["page"] = p.get("page")
        u["section"] = _section_label(o, nmap)
        u["refnum"] = p.get("refnum") or ""
    return ranked


# --- rendering -----------------------------------------------------------------
def _est_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def _block(u: dict) -> str:
    parts = [f"id={u['id']}", f"type={u['type']}"]
    if u.get("page") is not None:
        parts.append(f"page={u['page']}")
    if u.get("section"):
        parts.append(f"section={u['section']}")
    if u.get("refnum"):
        parts.append(f"refnum={u['refnum']}")
    if u.get("score") is not None:
        parts.append(f"score={u['score']}")
    body = u.get("body") or u["text"]
    if u["type"] in ("Formula", "Equation"):
        body = f"$$ {body} $$"
    return f"<!-- {' '.join(parts)} -->\n{body}"


def render_markdown(units: list[dict], *, max_tokens: Optional[int] = None,
                    title: str = "") -> str:
    """Render selected units as Markdown context blocks, each with a metadata
    header + object id, greedily filling `max_tokens` and reporting the drop."""
    head = f"# Context projection{(': ' + title) if title else ''}\n"
    kept, used, dropped = [], _est_tokens(head), 0
    for u in units:
        blk = _block(u)
        cost = _est_tokens(blk) + 1
        if max_tokens is not None and used + cost > max_tokens and kept:
            dropped = len(units) - len(kept)
            break
        kept.append(blk)
        used += cost
    if max_tokens is not None and not kept and units:      # even one exceeds — keep it
        kept.append(_block(units[0]))
        dropped = len(units) - 1
    trailer = (f"\n---\n_{len(kept)} of {len(units)} unit(s) projected, "
               f"~{used} tokens" + (f"; {dropped} dropped for the "
               f"{max_tokens}-token budget" if dropped else "") + "._")
    return head + "\n\n".join(kept) + trailer


def project_context(nodes, query: str = "", *, types: Optional[list[str]] = None,
                    concept: Optional[str] = None, section: Optional[str] = None,
                    k: Optional[int] = None, max_tokens: Optional[int] = None,
                    aspect: str = "structural", title: str = "") -> str:
    """Select ∩ rank ∩ render: a query → a Markdown LLM context over the docmodel."""
    units = select_units(nodes, query, types=types, concept=concept,
                         section=section, k=k, aspect=aspect)
    return render_markdown(units, max_tokens=max_tokens, title=title)
