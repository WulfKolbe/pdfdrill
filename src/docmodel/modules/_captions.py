"""
Shared caption parsing for image-bearing lines (figures, diagrams, pictures).

MathPix encodes an image two equivalent ways in a line's text fields:

  - LaTeX form:     `\\begin{figure} \\includegraphics{<cdn>} \\caption{<text>} \\end{figure}`
  - Markdown form:  `![](<cdn>)`

The caption (when present) lives inside `\\caption{...}` of the LaTeX form, and
its braces can be unbalanced by a naive regex because captions routinely embed
inline math (`\\(2^{\\text{nd}}\\)`, `\\(\\mathrm{R}_{6}\\)`). So we extract it
with a balanced-brace walk, then parse the leading `Kind N: body` label.

Mirrors the TS `PictureProcessor` (`FIG_RE` caption group + the
`/^\\s*(Abbildung|Figure)\\s+([0-9.]+)\\s*:\\s*(.*)$/i` parser), widened to the
kinds real documents use (Picture / Sketch / Table / Diagram …) and a refnum
that allows a trailing letter (`5b`) and dotted numbers (`1.2`).
"""
from __future__ import annotations

import re
from typing import Optional

# `\caption`, optional `*`, optional `[short]`, then the `{` whose matching
# `}` we walk to (so nested braces from inline math don't end it early).
_CAPTION_START = re.compile(r"\\caption\*?\s*(?:\[[^\]]*\])?\s*\{")

# `Picture 5b: ...`, `Sketch 2: ...`, `Table 1: ...`, `Figure 1.2: ...`,
# `Abbildung 3: ...`. Kind set widened well beyond the TS Figure|Abbildung.
#: The kinds a label may name. Named once, so `TABLE_KINDS`/`FIGURE_KINDS`
#: below cannot list a kind this pattern can never produce — `TABLE_KINDS` held
#: `Tab` and `Tafel` while the pattern knew neither, so two of its three entries
#: were dead.
_KINDS = (r"Abbildung|Abb\.?|Figure|Fig\.?|Picture|Sketch|Diagram|Diagramm"
          r"|Table|Tabelle|Image|Photo|Chart")

#: The number: arabic (`1`, `1.2`, `5b`) or ROMAN (`I`, `IV`, `XII`). Roman is
#: not decoration — 14 `figure_label` lines in the corpus read `Table I. Power
#: rating of different components`, and without it they parse as no label at all
#: and the table loses its caption.
_NUM = r"[0-9]+(?:\.[0-9]+)*[A-Za-z]?|[IVXLC]{1,6}"

_LABEL = re.compile(
    r"^\s*(" + _KINDS + r")\s*"
    r"(" + _NUM + r")\s*[:.]\s*(.*)$",
    re.I | re.S,
)


def extract_figure_caption(text: str) -> str:
    """Return the balanced-brace body of the first `\\caption{...}`, or ''."""
    if not text:
        return ""
    m = _CAPTION_START.search(text)
    if not m:
        return ""
    start = m.end()
    depth = 1
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i].strip()
    return ""  # unbalanced — give up rather than capture past the figure


def parse_caption(caption: str) -> tuple[Optional[str], Optional[str], str]:
    """Parse 'Picture 5b: body' → (kind, refnum, body).

    Returns (None, None, caption.strip()) when there is no recognizable label.
    """
    if not caption:
        return None, None, ""
    m = _LABEL.match(caption)
    if not m:
        return None, None, caption.strip()
    kind = m.group(1).strip().rstrip(".").capitalize()
    return kind, m.group(2), m.group(3).strip()

#: A line that is ONLY a label — `Table 2`, `Fig. 3.` — with no caption body on
#: it. Measured over 260 corpus documents: 95 such lines in 29 documents, and
#: 87 of the 95 are followed by a prose line that IS the caption body. This is
#: the shape `_CAPTION_START` cannot take, because it requires a `.`/`:`
#: terminator after the number — which is exactly what keeps prose like
#: `Table 4 shows the results.` out, and that guard must not be weakened.
_BARE_LABEL = re.compile(r"^(?:" + _KINDS + r")\s*\.?\s*(" + _NUM + r")\s*\.?$",
                         re.I)

#: Caption kinds that belong to a TABLE, spelled as `parse_caption` returns them
#: (`.capitalize()`), and drawn from `_KINDS` so none of them is dead.
TABLE_KINDS = frozenset({"Table", "Tabelle"})

#: …and to a figure. Everything `_KINDS` can name that is not a table.
FIGURE_KINDS = frozenset({"Figure", "Fig", "Abbildung", "Abb", "Picture",
                          "Sketch", "Diagram", "Diagramm", "Image", "Photo",
                          "Chart"})


def adjacent_label_caption(stream, anchor, kinds=None, allow_bare: bool = False) -> str:
    """The caption text from a labelled line NEXT TO `anchor`, or "".

    819b — promoted out of `diagram.py`, where it was a private static method,
    so the table module can use the same rule instead of a second detector.
    `line_types.caption_anchors` states the principle this follows: "One
    authority, no second detector."

    253 established that a `figure_label` CHILD is the figure's own text — an
    axis label, a legend entry — not its caption. This is the SIBLING case:
    MathPix emits the float and its caption as two lines under one `column`, so
    the child loop never sees it. Measured for tables: 5,166 of 6,789 `table`
    container lines have a labelled line IMMEDIATELY above, and 5,168 of those
    are typed `figure_label`.

    Bounded three ways, each one load-bearing:

      * the IMMEDIATE neighbour only, and only on the SAME page — a label
        further away belongs to another float, and a caption that has to be
        searched for is a guess;
      * it must PARSE as a caption (a kind and a number), which is what
        separates `Fig. 8. Delta life span over time…` from an axis label;
      * `kinds` restricts which labels count, so a `Table 1` caption sitting
        beside a diagram is not taken as the diagram's own. Pass None to accept
        any kind, which is what the caller did before this was shared.

    `allow_bare` adds the label-only shape (`Table 2` on its own line, the body
    on the next). It cannot match prose: prose continues on the SAME line, and a
    bare label by definition does not.
    """
    anchors = list(stream.anchors)
    try:
        i = anchors.index(anchor)
    except ValueError:
        return ""
    here = stream.payload[anchor].get("_page")

    def _ok(kind) -> bool:
        return bool(kind) and (kinds is None or kind in kinds)

    for j in (i + 1, i - 1):                 # below first: the usual place
        if not (0 <= j < len(anchors)):
            continue
        cand = stream.payload[anchors[j]]
        if cand.get("_page") != here:
            continue
        txt = (cand.get("text_display") or cand.get("text") or "").strip()
        if cand.get("type") == "figure_label":
            kind, refnum, body = parse_caption(txt)
            if _ok(kind) and refnum and body.strip():
                return txt
        if allow_bare and _BARE_LABEL.match(txt):
            kind, _r, _b = parse_caption(txt + ".")
            if not _ok(kind):
                continue
            # The body always FOLLOWS the label, whichever side of the float
            # the caption is on: label/body/table when it is above, and
            # table/label/body when it is below. (Written the other way first,
            # and a test for the below-the-table arrangement caught it — the
            # body slot resolved to the table's own line.)
            body = _body_at(stream, anchors, j + 1, here)
            if body:
                return f"{txt.rstrip('.')}. {body}"

    if not allow_bare:
        return ""
    # THE LABEL ONE FURTHER OUT, with the caption body between it and the float.
    # `Table 2` / `Description for all message types.` / the table — measured:
    # 54 occurrences in 12 documents, and every one is a caption. Bounded to
    # distance two: this is a recognised ARRANGEMENT, not a search outward.
    for lab_j, body_j in ((i - 2, i - 1), (i + 2, i + 1)):
        if not (0 <= lab_j < len(anchors) and 0 <= body_j < len(anchors)):
            continue
        lab = stream.payload[anchors[lab_j]]
        if lab.get("_page") != here:
            continue
        txt = (lab.get("text") or "").strip()
        if not _BARE_LABEL.match(txt):
            continue
        kind, _r, _b = parse_caption(txt + ".")
        if not _ok(kind):
            continue
        body = _body_at(stream, anchors, body_j, here)
        if body:
            return f"{txt.rstrip('.')}. {body}"
    return ""


def _body_at(stream, anchors, k: int, page) -> str:
    """The caption body on line `k`, or "" — prose on the same page, long
    enough to be a caption rather than a stray fragment."""
    if not (0 <= k < len(anchors)):
        return ""
    rec = stream.payload[anchors[k]]
    if rec.get("_page") != page or rec.get("type") not in ("text", "caption"):
        return ""
    body = (rec.get("text") or "").strip()
    return body if len(body) >= 3 else ""
