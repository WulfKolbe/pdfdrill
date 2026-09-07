r"""636 — where one footnote body ends and the next begins.

MathPix puts every footnote of a page into ONE `\footnotetext{...}` group, one
printed number after another, so a body ran to the end of the GROUP instead of
stopping before the next number. 29 of penev_A's 53 Footnote bodies were that
shape — footnote 3 ended

    "...(Deco and Obradovic 1996).\({ }^{4}\) PCA has also been utilized..."

with footnote 4's printed number and its first words merged in. That is why
the running text reads as though a footnote had been spliced into mid-sentence,
and it is the same defect `pdfdrill conserve` sees from the anchor side as a
line claimed by a Footnote and a Paragraph at once.

THE CUT IS EXACT, NEVER A GUESS. A footnote LABEL is `{ }^{n}` at the HEAD of
an inline-math span (`\(...\)` or `$...$`): a superscript with an EMPTY BASE,
which is how a printed footnote number reaches MathPix. `\(\sigma_{r}{ }^{2}\)`
is a real exponent — a base precedes the superscript — and is never a cut
point; penev_A carries 52 of those, some inside footnote bodies.

MEASURED, not assumed: the head-of-span rule finds an interior label in exactly
the 29 bodies the user counted, where the looser "any `{ }^{n}`" rule finds 30.
The extra one is a `\(\sigma_{r}{ }^{2}\)` inside a body, which must not be cut.

A body runs from just after its own label to just before the NEXT label, or to
the end of the block. What is cut off belongs to the next footnote and is never
dropped: the caller creates a Footnote for it — except when the next label
REPEATS a number already emitted from the same block, where a second object
would give two bodies one printed number on one page (the title collision 644
removed). There the tail stays on the earlier body, which is marked
`tail_unassigned`, and it is counted as an `orphan_tail`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# `{ }^{n}` at the HEAD of an inline-math span. The opening delimiter is part
# of the match, which is what makes "empty base" decidable: in
# `\(\sigma_{r}{ }^{2}\)` the superscript does not follow the delimiter.
LABEL = re.compile(r"(?:\\\(|\$)\s*\{\s*\}\s*\^\s*\{(\d+)\}")


@dataclass
class Segment:
    """One footnote's share of a block."""

    refnum: str
    start: int                 # the cut in the source text (0 for the first)
    end: int                   # where the NEXT cut is (or len(text))
    body: str                  # own label stripped, as bodies are today
    tail_unassigned: bool = False


def find_labels(text: str) -> list[tuple[int, str]]:
    """Every footnote label in `text`, as (position of the math delimiter, n)."""
    return [(m.start(), m.group(1)) for m in LABEL.finditer(text or "")]


def _strip_own_label(body: str, refnum: str) -> str:
    """Drop the body's OWN number, exactly as bodies have always dropped it:
    only the CLOSED spelling `\\({ }^{n}\\)` / `${ }^{n}$`. When the number
    shares its span with the body's maths (`\\({ }^{21} \\mathbf{K}^{2}\\)`)
    nothing is removed — cutting inside that span would unbalance it."""
    own = re.compile(r"\\\(\s*\{\s*\}\s*\^\s*\{" + re.escape(refnum) + r"\}\s*\\\)"
                     r"|\$\s*\{\s*\}\s*\^\s*\{" + re.escape(refnum) + r"\}\s*\$")
    return own.sub("", body).strip()


def split_bodies(text: str) -> list[Segment]:
    """Split one footnote block's text at every label. `[]` when there is none.

    The FIRST segment starts at 0, not at its label: whatever precedes the
    first number is a body that began earlier (a footnote spilling from the
    previous page), and this function invents no owner for it — it stays where
    it already was, which is what the block's own Footnote has always held.
    """
    labels = find_labels(text)
    if not labels:
        return []
    segs: list[Segment] = []
    seen: set[str] = set()
    for pos, refnum in labels:
        if segs and refnum in seen:
            # A repeated number: refuse to make a second object for it.
            segs[-1].tail_unassigned = True
            continue
        seen.add(refnum)
        start = 0 if not segs else pos
        if segs:
            segs[-1].end = pos
        segs.append(Segment(refnum=refnum, start=start, end=len(text), body=""))
    for s in segs:
        s.body = _strip_own_label(text[s.start:s.end], s.refnum)
    return segs


def orphan_tails(segs: list[Segment]) -> int:
    """How many tails could not be given a footnote of their own."""
    return sum(1 for s in segs if s.tail_unassigned)
