r"""Phase 4 — which rule was drawn.

`svg.py` already injects `booktabs` when it sees `\toprule`. What it cannot
know is WHICH rule was drawn, and for a round trip `\toprule` / `\midrule` /
`\bottomrule` are three different documents.

THE DIVISION OF LABOUR IS DELIBERATE. inkdrill measures and emits
`ink.rules[].width_pt`; it never emits `"kind": "toprule"`, because the call
needs table context it does not have. pdfdrill has that context and makes the
call here.

WHY THE ORDERING AND NOT THE VALUE — AND WHY MORE RESOLUTION DOES NOT FIX IT.
The absolute width is never trustworthy. Measured on a compiled booktabs
fixture against pdflatex's own linewidths:

    dpi    measured heavy widths      error vs truth
    400    0.90, 1.08 pt              +24.2%
    600    0.84, 0.84                  +5.4%
    800    0.90, 0.90                 +12.9%
   1200    0.84, 0.84                  +5.4%

The error does NOT shrink with resolution, because it is quantisation rather
than a bias: the measured width is the true width rounded up to a whole pixel,
so the error oscillates with how the two happen to line up. There is no factor
to correct for. What survives every resolution is the ORDER — within one table
the heavy rules measure heavier than the light ones.

THE SEPARATION MARGIN IS RESOLUTION-DEPENDENT, NOT A CONSTANT. Same fixture,
margin between the lightest heavy rule and the heaviest light one:

    400 dpi   0.180 pt   1.0 px          <- one pixel of noise flips a toprule
    600 dpi   0.240 pt   2.0 px
    800 dpi   0.360 pt   4.0 px
   1200 dpi   0.300 pt   5.0 px

At 400 dpi the two IDENTICAL midrules of that table measured 0.54 and 0.72 —
33% apart. At 800 they both measure 0.54. **If the classification matters,
render the rule measurement at 800 dpi even when everything else runs at 400**:
it is one extra rasterisation, and only of pages that have tables. The margin
is reported per table so a reader knows when it is worth doing.

THE RULE. Cluster the rules of ONE table into weight classes; the heavier class
at the TOP is `\toprule` and at the BOTTOM is `\bottomrule`; the lighter class
in the interior is `\midrule`. Position CONFIRMS the weight rather than being
overruled by it — a heavy rule in the middle is a real thing (a group
separator), and naming it `toprule` would move it to the top of the
reconstructed table.

RULE 5 THROUGHOUT. Where the evidence does not separate, nothing is named and
the reason is carried:
  * one weight class (a table ruled with `\hline` throughout) — no heavier
    cluster exists, so there is nothing to rank, and naming the first rule
    `toprule` on position alone would be a guess wearing a measurement's
    clothes
  * a heavy rule that is not at an edge
  * a vertical rule — booktabs draws none; a `v` rule is a `|` separator and
    belongs to a different reconstruction
  * fewer than two rules

Ground truth for the tests is a compiled booktabs table: `\toprule` 0.7970 pt,
two `\midrule` 0.4980 pt, `\bottomrule` 0.7970 pt — ratio 1.60.
"""
from __future__ import annotations

from typing import Any, Sequence

TOPRULE = "toprule"
MIDRULE = "midrule"
BOTTOMRULE = "bottomrule"
CMIDRULE = "cmidrule"
UNKNOWN = "unknown"

# Two widths belong to the same class when they differ by less than this
# FRACTION of the larger. Deliberately generous: the two booktabs weights sit
# 37% apart (0.498 vs 0.797) while repeated measurements of ONE weight vary by
# a pixel, so anything from ~5% to ~25% separates them identically. It is not a
# tuned threshold, and the tests inflate every width by 12% to prove the names
# do not move.
_SAME_CLASS = 0.20

# A horizontal rule spanning less than this fraction of the table's widest rule
# is partial — a `\cmidrule{i-j}`, not a `\midrule`. Measured on 2409.18839
# p9: the two cmidrules span 95.6 pt of a 346.4 pt table (0.28) and 93.1/73.8
# of 306.8 (0.30 / 0.24), while every full-width rule is exactly 1.00. There is
# no evidence anywhere near the boundary, so the value is not tuned.
_FULL_SPAN = 0.90


def _classes(widths: Sequence[float]) -> list[int]:
    """Weight-class index per rule, 0 = lightest. Order, not value."""
    order = sorted(range(len(widths)), key=lambda i: widths[i])
    cls = [0] * len(widths)
    k = 0
    for pos, i in enumerate(order):
        if pos:
            prev = widths[order[pos - 1]]
            if widths[i] - prev > _SAME_CLASS * max(widths[i], prev):
                k += 1
        cls[i] = k
    return cls


# Below this many pixels of separation, one pixel of extra noise flips a
# `\toprule` into a `\midrule`. Measured: 400 dpi gives 1.0 px on a real
# booktabs table, 800 dpi gives 4.0.
_THIN_PX = 2.0


def rank_rules(rules: Sequence[dict],
               render_dpi: "float | None" = None) -> list[dict]:
    """Name each rule of ONE table, top to bottom, or say why it cannot be.

    Input is inkdrill's `rule_record` shape: `width_pt`, `orient`, `x0/y0/x1/y1`.
    Output is the same records, ordered top to bottom, each with `kind`,
    `weight_class` and — when nothing is named — `reason`. The measured width
    travels with the name, because a reader who wants to check the call needs
    the evidence next to the conclusion.
    """
    out = [dict(r) for r in rules]
    out.sort(key=lambda r: (float(r.get("y0", 0.0)), float(r.get("x0", 0.0))))

    horiz = [r for r in out if r.get("orient", "h") == "h"]
    for r in out:
        if r.get("orient") != "v":
            continue
        r["kind"] = UNKNOWN
        r["weight_class"] = None
        r["reason"] = "vertical rule — booktabs draws none; this is a column separator"

    if len(horiz) < 2:
        for r in horiz:
            r["kind"] = UNKNOWN
            r["weight_class"] = 0
            r["reason"] = "too few rules to rank"
        return out

    # span relative to the widest rule of THIS table — the discriminator
    # between `\midrule` (full width) and `\cmidrule` (a range of columns)
    lengths = [float(r["x1"]) - float(r["x0"]) for r in horiz]
    widest = max(lengths) or 1.0
    for r, ln in zip(horiz, lengths):
        r["span"] = ln / widest

    widths = [float(r["width_pt"]) for r in horiz]
    cls = _classes(widths)
    for r, c in zip(horiz, cls):
        r["weight_class"] = c

    if max(cls) == 0:
        for r in horiz:
            r["kind"] = UNKNOWN
            r["reason"] = "one weight class"
        return out

    # The separation the whole classification rests on, reported rather than
    # kept private: at 400 dpi it is one pixel on a real booktabs table.
    hw = [w for w, c in zip(widths, cls) if c == max(cls)]
    lw = [w for w, c in zip(widths, cls) if c < max(cls)]
    margin_pt = (min(hw) - max(lw)) if hw and lw else None
    px = (72.0 / float(render_dpi)) if render_dpi else None
    margin_px = (margin_pt / px) if (margin_pt is not None and px) else None
    sep = {"margin_pt": margin_pt, "margin_px": margin_px,
           "thin": (margin_px < _THIN_PX) if margin_px is not None else None}
    if sep["thin"]:
        sep["advice"] = (f"{margin_px:.1f} px of separation at {render_dpi:g} dpi — "
                         "one pixel of noise flips a rule. Re-render this page at "
                         "800 dpi for the rule measurement; it is one extra "
                         "rasterisation and only of pages with tables.")
    for r in horiz:
        r["separation"] = sep

    heavy = max(cls)
    first, last = horiz[0], horiz[-1]
    for i, r in enumerate(horiz):
        if r["weight_class"] < heavy:
            # A partial-width interior rule is a `\cmidrule`; calling it a
            # `\midrule` draws a line across the whole table.
            r["kind"] = MIDRULE if r["span"] >= _FULL_SPAN else CMIDRULE
            continue
        if r is first:
            r["kind"] = TOPRULE
        elif r is last:
            r["kind"] = BOTTOMRULE
        else:
            # A heavy interior rule is a real thing — a group separator — and
            # the weight alone must not move it to an edge it is not at.
            r["kind"] = UNKNOWN
            r["reason"] = "heaviest class but not at an edge"
    return out
