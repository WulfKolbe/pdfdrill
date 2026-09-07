r"""637 — which `mathpix_lines` a Footnote covers, and when two Footnote
objects are the SAME footnote.

MEASURED ON penev_A, NOT ASSUMED (rule 14). After 636 the document carried 93
Footnote objects for 48 printed footnotes: 45 (page, refnum) pairs held two
objects each and 3 held one. The duplication is not two REALIZATIONS on one
object — every Footnote carries exactly one `surface` and one `cleaned`
realization, and the projector reads a body TEXT, not a realization — it is two
OBJECTS, one per creator:

  * `docmodel.modules.footnote.FootnoteProcessor` reads MathPix's `footnote`
    line, the PARENT of the block;
  * `pdfdrill.heading_cleanup.extract_footnote_paragraphs` reads the
    `\footnotetext{…}` MathPix ALSO left in the Paragraph built over that
    parent's CHILD `text` lines.

So the two objects for one footnote NEVER SHARE A LINE. Comparing extents
plainly identifies 20 of the 45 pairs; expanding a `footnote` line to its own
children identifies all 45 and joins nothing else — the 3 single footnotes stay
single. That expansion is the whole of the rule, and it is applied ONLY to a
line MathPix typed `footnote`: growing a prose line to its children would make
a paragraph swallow whatever MathPix hung off it.

`refnum` alone is never enough — it restarts per chapter and 16 penev_A refnums
name more than one Footnote (638). `(page, refnum)` alone is not enough either:
a number that repeats within a page is 644's collision class. The extent is
what keeps them apart, and where there is no extent nothing is adopted.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .core import Document, DocObject


#: The stream the claim lives on. Same name every module uses.
LINES_STREAM = "mathpix_lines"

#: The MathPix line type whose CHILDREN are the same block. Only this type is
#: expanded; see the module docstring for why that matters.
BLOCK_TYPE = "footnote"


def _anchor_by_line_id(stream) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in stream.anchors:
        lid = stream.payload[a].get("id")
        if lid and lid not in out:
            out[lid] = a
    return out


def covered_anchors(doc: Document, obj: DocObject, expand: bool = True) -> set:
    """The `mathpix_lines` anchors `obj`'s SURFACE realizations cover.

    With `expand`, a `footnote` line is grown to the child lines MathPix hangs
    the block's text off — the one step that makes the two creators' extents
    comparable. An inline sub-anchor (offset/length) still covers its line
    here: this asks WHICH LINES the object sits on, not who claims them, which
    is `docops.conserve`'s question and keeps its own rule.
    """
    st = doc.streams.get(LINES_STREAM)
    if st is None:
        return set()
    out: set = set()
    for r in obj.realizations:
        if r.stream != LINES_STREAM or r.role != "surface" or r.start is None:
            continue
        end = r.end if r.end is not None else r.start
        try:
            out.update(st.slice_anchors(r.start, end))
        except KeyError:                       # an anchor from another document
            continue
    if not expand or not out:
        return out
    by_id = _anchor_by_line_id(st)
    for a in list(out):
        payload = st.payload.get(a) or {}
        if payload.get("type") != BLOCK_TYPE:
            continue
        for cid in (payload.get("children_ids") or []):
            child = by_id.get(cid)
            if child is not None:
                out.add(child)
    return out


def adopt_target(doc: Document, page: Any, refnum: Any, want: Iterable,
                 exclude: Iterable[str] = ()) -> Optional[DocObject]:
    """The Footnote already in `doc` that IS this footnote, or None.

    THE RULE, in one sentence: same `page`, same non-empty `refnum`, and an
    extent that overlaps `want` once a `footnote` line is grown to its own
    children. All three conditions, never two — and `want` empty means the body
    was not located, so nothing is adopted rather than something guessed.

    `exclude` holds the ids already adopted in this pass: a paragraph carrying
    two `\\footnotetext{…}` groups can repeat a number, and one host must not
    be filled twice.
    """
    want = set(want or ())
    rn = str(refnum or "").strip()
    if not want or not rn:
        return None
    skip = set(exclude or ())
    for obj in doc.objects.values():
        if obj.type != "Footnote" or obj.id in skip:
            continue
        if str(obj.props.get("refnum") or "").strip() != rn:
            continue
        if obj.props.get("page") != page:
            continue
        if covered_anchors(doc, obj) & want:
            return obj
    return None
