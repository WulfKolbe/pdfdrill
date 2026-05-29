"""Enriched links layer.

`pdfinfo -url` gives us page + URL but no anchor rectangle. pdfplumber's
`page.annots` gives us URL + rect; intersecting the rect with the page's
char positions yields the *anchor text* — the visible text under the
link. For internal cross-references (annotations with no URI), we resolve
the destination name against the `dests` layer to recover what the link
points to.

Output records:
    {
      "page": 1,
      "kind": "url" | "internal" | "javascript",
      "uri": "https://...",            # for url kind
      "dest_name": "theorem.1.1",      # for internal kind
      "dest_page": 5,                  # resolved from dests
      "rect": [x0, y0, x1, y1],
      "anchor_text": "here",
      "context": "...the source code could be found here...",
    }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def fetch_links(pdf: Path, dests: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return enriched link records from pdfplumber's annots."""
    import pdfplumber

    dest_index = _index_dests(dests or [])
    records: list[dict[str, Any]] = []

    with pdfplumber.open(pdf) as pdf_obj:
        for page in pdf_obj.pages:
            for annot in (page.annots or []):
                rec = _record_from_annot(annot, page, dest_index)
                if rec is not None:
                    records.append(rec)
    return records


def _index_dests(dests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {d.get("name", ""): d for d in dests if d.get("name")}


def _record_from_annot(
    annot: dict[str, Any],
    page: Any,
    dest_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Convert one pdfplumber annot dict into our link record shape."""
    # Only handle Link annotations
    subtype = annot.get("data", {}).get("Subtype")
    sub_name = _strip_pdfname(str(subtype)) if subtype else ""
    if sub_name not in ("Link", "Widget"):
        return None

    x0 = float(annot.get("x0", 0))
    y0 = float(annot.get("top", annot.get("y0", 0)))
    x1 = float(annot.get("x1", 0))
    y1 = float(annot.get("bottom", annot.get("y1", 0)))

    uri = annot.get("uri")
    if uri:
        kind = "url"
        dest_name = ""
        dest_page = None
    else:
        kind = "internal"
        dest_name, dest_page = _resolve_dest(annot, dest_index)
        if not dest_name:
            return None  # neither URL nor resolvable destination

    anchor, context = _anchor_and_context(page, (x0, y0, x1, y1))

    return {
        "page": page.page_number,
        "kind": kind,
        "uri": uri or "",
        "dest_name": dest_name,
        "dest_page": dest_page,
        "rect": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
        "anchor_text": anchor,
        "context": context,
    }


def _strip_pdfname(s: str) -> str:
    # pdfplumber/pdfminer prints names as `/'Link'`. Strip wrapper.
    s = s.strip()
    if s.startswith("/'"):
        s = s[2:]
    if s.endswith("'"):
        s = s[:-1]
    return s


def _resolve_dest(
    annot: dict[str, Any],
    dest_index: dict[str, dict[str, Any]],
) -> tuple[str, int | None]:
    """Find the named destination an internal link points to."""
    data = annot.get("data", {}) or {}
    # PDF link annotations carry either /Dest (a name) or /A → /D (action).
    for key_path in (("Dest",), ("A", "D")):
        target = data
        for key in key_path:
            target = target.get(key) if isinstance(target, dict) else None
            if target is None:
                break
        if target is None:
            continue
        name = _dest_name_from_value(target)
        if name and name in dest_index:
            return name, dest_index[name].get("page")
        if name:
            return name, None
    return "", None


def _dest_name_from_value(value: Any) -> str:
    """Extract a name string from a pdfminer dest value."""
    s = str(value)
    # Examples: "/Doc-Start", "'theorem.1.1'", "(b'theorem.1.1',)" etc.
    m = re.search(r"['\"/]([A-Za-z0-9._*-]+)", s)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Anchor text and context extraction
# ---------------------------------------------------------------------------

def _anchor_and_context(
    page: Any,
    rect: tuple[float, float, float, float],
    context_radius: int = 60,
) -> tuple[str, str]:
    """Return (anchor_text, surrounding_context)."""
    x0, y0, x1, y1 = rect
    chars = page.chars or []
    if not chars:
        return "", ""

    inside_idx: list[int] = []
    for i, c in enumerate(chars):
        cx0 = float(c.get("x0", 0))
        cy0 = float(c.get("top", 0))
        if x0 <= cx0 <= x1 and y0 <= cy0 <= y1:
            inside_idx.append(i)

    if not inside_idx:
        return "", ""

    anchor = "".join(chars[i].get("text", "") for i in inside_idx).strip()

    # Build context by walking left/right from the inside indices along the
    # natural reading order, ignoring positional gaps within a line.
    first = inside_idx[0]
    last = inside_idx[-1]
    left = "".join(chars[i].get("text", "")
                   for i in range(max(0, first - context_radius), first))
    right = "".join(chars[i].get("text", "")
                    for i in range(last + 1, min(len(chars), last + 1 + context_radius)))
    context = (left + "[" + anchor + "]" + right).replace("\n", " ").strip()
    context = re.sub(r"\s+", " ", context)
    return anchor, context


# ---------------------------------------------------------------------------
# Prose formatting
# ---------------------------------------------------------------------------

def summarize_links(links: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in links:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return counts
