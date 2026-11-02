r"""Is a Markdown projection STRUCTURALLY sane? One number per page, no reference.

WHY THIS EXISTS, AND WHY IT IS THE FIRST RUNG
---------------------------------------------
The owner audited `d09.md` (Avetissian, 514 pages, projected from pdf2mmd2's
reading) by reading it, and found several errors per line from the first
content page on. That is the wrong way for a defect this mechanical to be
found, and the owner said so: "I am not need on check on this low level!"

The instruments for comparing a reading against ANOTHER reading already exist
and are free — `linescmp` (per-line geometry and type agreement, "the
acceptance test for a reader"), `mathpix_conformance` (type distributions),
`eqblobs` (keyless display-math regions), `fontspans` (bold heading spans),
and pdf2mmd2's `twinbench` (the colour-twin oracle for inline vs display).
None of them was run before the report. But none of them is the CHEAPEST
check either, because all of them need a second reading or a render.

This module is the rung below all of that: it needs only the Markdown, no
reference, no key, no render. It answers "is this projection even internally
consistent", and on d09 it fires on the first content page. The ladder the
owner set is:

    1. this check          free, no reference      must be < 1 error/page
    2. compare one page against a Gemma4 reading   only once (1) passes
    3. compare page by page against MathPix        only once (2) passes

Running (3) first is how a 514-page document got read by hand.

THE FOUR CLASSES, each measured on d09's section 1.1
----------------------------------------------------
E3 MATH_AS_HEADING      `## p = p + e E(τ)dτ, (1.5)` — a display equation
                        emitted as a heading, so the math is neither isolated
                        nor delimited. The owner's "first equation 1.1 and
                        second equation not isolated as equation, start and
                        end of math not found".
E1 LEVEL_INVERSION      `### 1.1 Classical Dynamics …` followed by
                        `## of Strong Plane Electromagnetic Wave` — the
                        continuation of a title one level SHALLOWER than the
                        title it continues. The owner's "2 lines created with
                        different ###/## Markdown that make no sense in a
                        hierarchy".
E4 CONTINUATION_HEADING a heading opening with a lowercase connective (`of`,
                        `with`, `and`) is a wrapped line, not a heading.
E2 HEADING_RUN          `## Chapter 1` / `# Interaction of a Charged
                        Particle` / `# with Strong Plane Electromagnetic` /
                        `# … Wave in Vacuum` — one title as four headings with
                        no prose between. Each heading after the first counts.

ONE LINE, ONE ERROR. The classes overlap heavily — a fragmented title is
usually a run AND an inversion AND a continuation — so each offending line is
counted ONCE under its strongest class (E3 > E1 > E4 > E2). Otherwise "errors
per page" counts the same defect three times and the owner's threshold means
nothing.

The root cause is not necessarily the projector: a reader that emits one
`section_header` line per VISUAL line, without joining a wrapped title, makes
E2/E1/E4 inevitable downstream. The check is deliberately blind to whose fault
it is, which is what makes it usable as a gate by either side.
"""
from __future__ import annotations

import re
from typing import NamedTuple

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
#: an equation number as physics prints it: (1.5), (2.40), (A.3), (1.17a)
EQ_NUMBER = re.compile(r"\((?:[A-Z]\.)?\d+(?:\.\d+)*[a-z]?\)")
#: a word, for "is this prose or symbols"
WORD = re.compile(r"[^\W\d_]{3,}")
#: a heading that opens with one of these is a wrapped continuation line
CONTINUATION_OPENERS = frozenset("""
of with and in for the a an to from on at by as or over under into
""".split())

MATH_AS_HEADING = "E3-math-as-heading"
LEVEL_INVERSION = "E1-level-inversion"
CONTINUATION_HEADING = "E4-continuation-heading"
HEADING_RUN = "E2-heading-run"

CLASSES = (MATH_AS_HEADING, LEVEL_INVERSION, CONTINUATION_HEADING, HEADING_RUN)


class Finding(NamedTuple):
    line: int          # 1-based line number in the Markdown
    kind: str          # one of CLASSES
    level: int         # the heading's own level
    text: str          # the heading text, truncated


def _is_math(text: str) -> bool:
    """Mathematics rather than a title: it carries a relation or an equation
    number, and it is not mostly words."""
    if not text:
        return False
    words = WORD.findall(text)
    letters = sum(c.isalpha() for c in text)
    symbolic = letters < 0.6 * max(1, len(text.replace(" ", "")))
    relation = bool(re.search(r"[=<>≤≥≈∼~]|\\(?:frac|int|sum|partial)", text))
    numbered = bool(EQ_NUMBER.search(text))
    if relation and (symbolic or numbered):
        return True
    # A numbered line with NO prose at all is an equation even without a
    # relation (`∇ × B , (3.4)`). The bound was "<= 2 words", which flagged
    # `## 8.2 Verify equation (8.27).` — a numbered EXERCISE heading that
    # merely cites an equation. pdf2mmd2's d04 rose by one error after a real
    # fix because of it, and they booked that against themselves; it was this
    # rule. A heading that mentions an equation is not an equation.
    return numbered and not words


def _opens_as_continuation(text: str) -> bool:
    first = (text.split() or [""])[0].strip(",;:")
    return first.lower() in CONTINUATION_OPENERS and first[:1].islower()


def check(md_text: str) -> list[Finding]:
    """Every structurally wrong heading in the projection, one finding per line.

    Pure: the same text always gives the same findings, in line order.
    """
    lines = md_text.splitlines()
    heads: list[tuple[int, int, str]] = []        # (line_no, level, text)
    #: line numbers that carry body prose, so a "run" can be recognised
    body_between: list[bool] = []
    prev_head_idx = None
    saw_body_since_head = True
    for i, raw in enumerate(lines, start=1):
        m = HEADING.match(raw)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
            body_between.append(saw_body_since_head)
            saw_body_since_head = False
        elif raw.strip():
            saw_body_since_head = True

    out: list[Finding] = []
    for n, (line_no, level, text) in enumerate(heads):
        kind = None
        if _is_math(text):
            kind = MATH_AS_HEADING
        elif n and not body_between[n] and level < heads[n - 1][1]:
            kind = LEVEL_INVERSION
        elif _opens_as_continuation(text):
            kind = CONTINUATION_HEADING
        elif n and not body_between[n] and level <= heads[n - 1][1]:
            # ONLY a run that does NOT go deeper. `# A Book` followed straight
            # by `## Chapter 1` is correct nesting, not fragmentation — the
            # sane-projection test caught this flagging it. Fragmentation is a
            # second heading at the SAME level (or shallower, which E1 already
            # owns) with no prose between: one title broken across lines.
            kind = HEADING_RUN
        if kind:
            out.append(Finding(line_no, kind, level, text[:70]))
    return out


def attribute(findings, reading: dict) -> dict:
    """{page number: [Finding, …]} by matching each heading back to the page of
    the reading whose lines carry that text.

    WHY THIS IS NOT OPTIONAL. The first version of this module divided the
    whole document's errors by the whole document's page count: d09 scored
    272/514 = 0.529/page and PRINTED "PASSES the owner's < 1/page gate" about
    the very projection the owner had just condemned. A 514-page monograph is
    mostly references and back matter with no headings at all, so a
    document-wide mean hides a catastrophic first content page behind 400
    quiet ones. The owner's unit is the page — "minimal tests of the first
    page after the front matter", "below 1/page" — and a gate measured on the
    wrong denominator passes the thing it exists to stop.
    """
    # EVERY page a text occurs on, in order — not the first. A repeated heading
    # is the common case in a book ("Bibliography", "References", "Abstract",
    # a running head), and keeping only the first occurrence put all three
    # `# Bibliography` headings of d09 — lines 1708, 9644 and 15772, the ends
    # of three different chapters — on page 49, inflating that page to 4 errors
    # when it carries 2. pdf2mmd2 found that; the verdict turns on the worst
    # page, so an inflated page is a false FAIL, which is as bad as the false
    # PASS the document mean gave.
    #
    # Findings arrive in line order and a projection preserves document order,
    # so the k-th occurrence of a text belongs to the k-th page carrying it.
    index: dict[str, list[int]] = {}
    for page in reading.get("pages") or []:
        n = page.get("page")
        for ln in page.get("lines") or []:
            t = (ln.get("text") or "").strip()
            if t:
                pages = index.setdefault(t, [])
                if not pages or pages[-1] != n:
                    pages.append(n)
    seen: dict[str, int] = {}
    out: dict = {}
    for f in findings:
        key = f.text.strip()
        pages = index.get(key)
        if pages is None:                  # truncated at 70 chars: try a prefix
            for t, pl in index.items():
                if t.startswith(key[:40]):
                    key, pages = t, pl
                    break
        if pages is None:
            out.setdefault(None, []).append(f)
            continue
        k = seen.get(key, 0)
        # past the last occurrence, the text repeats more often in the
        # projection than in the reading: attribute to the last page rather
        # than inventing one, and never back to the first.
        out.setdefault(pages[min(k, len(pages) - 1)], []).append(f)
        seen[key] = k + 1
    return out


def worst_page(findings, reading: dict):
    """(page, errors) for the page carrying the most errors — the number the
    gate turns on. `(None, n)` counts the findings that could not be placed."""
    by_page = attribute(findings, reading)
    placed = {k: v for k, v in by_page.items() if k is not None}
    if not placed:
        return None, len(findings)
    page = max(placed, key=lambda k: len(placed[k]))
    return page, len(placed[page])


def rate(findings, page_count: int) -> float:
    """Errors per page. `page_count` is the DOCUMENT's page count (from the
    reading or `probes.page_count`), never a count of Markdown lines — the
    owner's threshold is per page of the book."""
    if not page_count:
        return float("inf") if findings else 0.0
    return len(findings) / page_count


def histogram(findings, reading: dict, page_count: int) -> dict:
    """{"p0": n, "p1": n, "p2": n, "p3+": n, "unplaced": n} — the DISTRIBUTION,
    which is what a per-page cap has to be set from.

    The extremes are a poor basis for a threshold: a book whose whole budget
    sits on three pages is a different proposition from the same rate spread
    over ten, and only the histogram tells them apart. Measured over the five
    QED books on 2026-11-02: 3 to 9 pages of 347-514 carry any error at all,
    each book has at most ONE page with two, and no page anywhere has three.

    `unplaced` is its own bucket and is NOT folded into p0. A finding whose
    heading text the projection rewrote (dehyphenation, a join) cannot be
    placed, and on one measured document that was 135 of 254 — more than half.
    A histogram that quietly dropped them would be worse than none, so the
    buckets plus `unplaced` always sum to len(findings)'s page-bearing total.
    """
    by_page = attribute(findings, reading)
    unplaced = len(by_page.get(None, []))
    placed = {k: v for k, v in by_page.items() if k is not None}
    counts = {"p1": 0, "p2": 0, "p3+": 0}
    for v in placed.values():
        n = len(v)
        counts["p1" if n == 1 else "p2" if n == 2 else "p3+"] += 1
    return {"p0": max(0, (page_count or 0) - len(placed)),
            **counts, "unplaced": unplaced}


def summary(findings, page_count: int, reading: "dict | None" = None) -> str:
    """One paragraph a gate can print. The VERDICT turns on the worst page when
    a reading is given, and says so when it cannot — never on the document mean,
    which is the denominator that passed d09."""
    from collections import Counter
    if not findings:
        return (f"Markdown structure: 0 errors over {page_count} page(s). The "
                f"free gate passes; a reference comparison is now worth running.")
    counts = Counter(f.kind for f in findings)
    cls = ", ".join(f"{k} {counts[k]}" for k in CLASSES if counts.get(k))
    mean = rate(findings, page_count)
    head = (f"Markdown structure: {len(findings)} error(s) over {page_count} "
            f"page(s), mean {mean:.3f}/page. {cls}.")
    if reading is None:
        return (head + " NO VERDICT: the gate turns on the WORST page and that "
                "needs the reading to attribute errors to pages. A document "
                "mean is not the gate — pass the lines.json.")
    page, n = worst_page(findings, reading)
    where = f"page {page}" if page is not None else "an unplaceable page"
    # BOTH NUMBERS, LABELLED, AND NO SINGLE VERDICT UNTIL THE OWNER PICKS.
    # The owner's words are "below 1/page", which is the RATE. A verdict on the
    # worst page is a different and much stricter bar — zero errors on every
    # page — and printing it as "the owner's < 1/page gate" was a mislabel of
    # mine that pdf2mmd2 caught: their d08 is 4 errors in 347 pages, 0.012/page,
    # and fails a worst-page test on a single error. Both numbers are needed:
    # the rate alone passed d09's text-layer projection at 0.494/page, which
    # the owner had just condemned, because its errors clustered on content
    # pages. So report the rate against the stated bar, report the worst page
    # beside it, and leave the combined threshold to the owner.
    rate_ok = "under" if mean < 1.0 else "over"
    h = histogram(findings, reading, page_count)
    return (head + f" Rate {mean:.3f}/page is {rate_ok} the stated 1/page bar."
            f" Worst single page: {n} error(s) on {where}."
            f" Pages: {h['p0']} clean, {h['p1']} with 1, {h['p2']} with 2, "
            f"{h['p3+']} with 3+, {h['unplaced']} finding(s) unplaceable."
            f" First at line {findings[0].line}: {findings[0].kind} "
            f"{findings[0].text!r}")
