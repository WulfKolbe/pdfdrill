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


CONTENT_TYPES = {
    "Section", "Paragraph", "Equation", "Formula", "Table",
    "Picture", "Diagram", "Footnote", "Sidenote", "ListItem",
    "Abstract", "Toc",
}


def flow_ordered_content(doc: Document) -> list[DocObject]:
    """
    Return content objects sorted by their flow position. Uses the
    `flow_index` prop if it was set by DocumentFlowProcessor; otherwise
    falls back to (page, line_index) of the first surface realization.
    """
    items: list[tuple[tuple, DocObject]] = []
    lines = doc.streams.get("mathpix_lines")
    for obj in doc.objects.values():
        if obj.type not in CONTENT_TYPES:
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
