r"""Phase 4 — which rule was drawn.

`svg.py` already injects `booktabs` when it sees `\toprule`. What it cannot
know is WHICH rule was drawn, and for a round trip `\toprule` / `\midrule` /
`\bottomrule` are three different documents.

THE DIVISION OF LABOUR IS DELIBERATE. inkdrill measures and emits
`ink.rules[].width_pt`; it never emits `"kind": "toprule"`, because the call
needs table context it does not have. pdfdrill has that context and makes the
call here.

WHY THE ORDERING AND NOT THE VALUE. The absolute width runs about 12% high —
rasteriser coverage — and the ratio between the two booktabs weights is
unstable under pixel quantisation: 1.50, 1.33, 1.67, 1.40, 1.67 measured at
five resolutions against a nominal 1.60. Any threshold on the value or on the
ratio is tuned to a resolution. What survives is the ORDER: within one table
the heavy rules are heavier than the light ones at every resolution tested.

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


def rank_rules(rules: Sequence[dict]) -> list[dict]:
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
