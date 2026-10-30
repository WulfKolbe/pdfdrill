"""
Shared helpers for projectors.

The most useful primitive is `flow_ordered_content(doc)`, which returns all
content DocObjects in their document-flow position (using `flow_index` if
present, falling back to surface anchor position).
"""
from __future__ import annotations

import base64
import urllib.request

from docmodel.core import Document, DocObject


# Cache so a repeated crop URL is fetched only once per run.
_embed_cache: dict[str, str] = {}


def embed_image(url: str, timeout: float = 30.0) -> str:
    """Return a `data:` URI for an image URL (base64), or the URL unchanged on
    failure. Used by projectors' `--embed` mode so the emitted HTML/tiddlers
    are self-contained (no live CDN dependency)."""
    if not url or url.startswith("data:"):
        return url
    if url in _embed_cache:
        return _embed_cache[url]
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ctype = r.headers.get_content_type() or "image/jpeg"
            b64 = base64.b64encode(r.read()).decode("ascii")
        data = f"data:{ctype};base64,{b64}"
    except Exception:
        data = url  # graceful: keep the URL if the fetch fails
    _embed_cache[url] = data
    return data


#: The types every flow consumer renders.
#:
#: `Theorem`, `Proof` and `Algorithm` are deliberately NOT here, and their
#: absence was defect 3's second half: seven projectors take their flow from
#: this set, and a projector cannot render an object its flow never yields, so
#: 66 theorem statements and 23 proofs were invisible to all of them at once.
#: Only the projectors that HAVE a branch for those types ask for them, by
#: name, through `flow_ordered_content(doc, types=…)` — because a flow object
#: nobody renders is at best nothing and at worst noise, and four of the seven
#: still have no branch. Add a type here only together with a branch in every
#: consumer. (`CodeListing` is missing for the same reason and is the next one.)
CONTENT_TYPES = {
    "Section", "Paragraph", "Equation", "Formula", "Table",
    "Picture", "Diagram", "Footnote", "Sidenote", "ListItem",
    "Abstract", "Toc",
}


def theorem_head(obj: DocObject, clean=None) -> str:
    """What the paper calls this block: `Theorem 3 (Hirzebruch)`, `Satz`.

    ONE implementation for every projection, because the head is what a reader
    (and an LLM handed `<bibkey>_THM0003`) uses to tell a Lemma from a
    Conjecture, and four projectors now print it. The printed title is the
    author's own (`\\newtheorem{lemma}{Lemma}` → "Lemma"); the number follows
    the shared-counter chain the reader resolved, and a starred environment has
    none. Each caller supplies its own emphasis — bold, brackets, or a LaTeX
    environment — so only the words live here.

    `clean` is the caller's own prose pass, applied to the BRACKET TITLE alone:
    an author writes `\\begin{theorem}[The $L^2$ case]`, so that argument is
    prose and needs the same treatment as any other — which only the projector
    knows how to give it.
    """
    p = obj.props or {}
    head = (str(p.get("printed_title") or "").strip()
            or str(p.get("kind") or "Theorem").strip().title())
    num = p.get("number")
    if num is not None and not p.get("starred"):
        head = f"{head} {num}"
    bracket = str(p.get("title") or "").strip()
    if bracket and clean is not None:
        bracket = clean(bracket).strip()
    return f"{head} ({bracket})" if bracket else head


def flow_ordered_content(doc: Document,
                         types: "tuple[str, ...] | None" = None) -> list[DocObject]:
    """
    Return content objects sorted by their flow position. Uses the
    `flow_index` prop if it was set by DocumentFlowProcessor; otherwise
    falls back to (page, line_index) of the first surface realization.

    `types` adds types to `CONTENT_TYPES` for this call: the caller states which
    further types IT renders, so one projector gaining a branch cannot change
    what another one is handed. See `CONTENT_TYPES`.
    """
    wanted = CONTENT_TYPES if not types else (CONTENT_TYPES | set(types))
    items: list[tuple[tuple, DocObject]] = []
    lines = doc.streams.get("mathpix_lines")
    for obj in doc.objects.values():
        if obj.type not in wanted:
            continue
        fi = obj.props.get("flow_index")
        if isinstance(fi, int):
            key = (0, fi, 0)
        else:
            # Fallback to first surface anchor's (_page, _line_index).
            surface = next(
                (r for r in obj.realizations
                 if r.stream == "mathpix_lines" and r.start is not None),
                None,
            )
            if surface is None or lines is None:
                continue
            p = lines.payload[surface.start]
            key = (1, p.get("_page", 0), p.get("_line_index", 0))
        items.append((key, obj))
    items.sort(key=lambda t: t[0])
    return [o for _, o in items]


def reconstruct_text_from_chars(doc: Document, stream_name: str,
                                 start, end) -> str:
    """Read a slice of a char-level stream back into a Python string."""
    s = doc.streams.get(stream_name)
    if s is None or start is None or end is None:
        return ""
    return "".join(
        s.payload[a].get("codepoint", "") for a in s.slice_anchors(start, end)
    )


def equation_label(eq: DocObject) -> str:
    """Render an equation reference number for inline display."""
    refnum = eq.props.get("refnum") or ""
    # Some refnums come in like '\1.1\' from MathPix display strings; strip.
    refnum = refnum.replace("\\", "").strip()
    return refnum


def is_derived(obj) -> bool:
    """True when the object duplicates content that exists elsewhere in the
    same document (262).

    A projection must CHOOSE what to do with one — show it because it is on
    the page, or omit it and rebuild the real thing from the source it was
    derived from. What it must not do is decide by accident, which is what
    happens when the only signal is a type name each projector tests for
    itself.
    """
    return bool(getattr(obj, "props", {}).get("derived"))
