# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), psred/mathrows.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""mathrows -- T3: split a multi-row display into its rows.

CONTRACT
    region(atoms) -> (left, inner, right) | None
        the content enclosed by a TALL delimiter: a big delimiter atom
        (cls openbig/closebig) or a STACK of open/close pieces at the same x
        (TeX assembles tall parentheses). 'right' may be None (cases: a brace
        without partner). None when the display has no such delimiter.
    split_rows(atoms, bars, size) -> [(row_atoms, row_bars), ...] top to bottom
        every atom and every bar in exactly one row; one row -> unchanged.

HOW (measured on fixtures/mathrows, TeX's own output):
    anchors   a full-size atom anchors at its axis (base + 0.25 em); every atom
              in a FRACTION ZONE -- within the bar's width, numerator up to
              0.8 em above it, denominator down to 1.1 em below -- anchors at
              the bar (a matrix of text-style fractions has NO full-size glyph,
              J := (du/du' ...); display numerators are full size and must not
              open rows of their own); bars anchor at their own height
    rows      anchors sorted top-down; a gap > 0.6 em starts a new row (rows
              are >= \\baselineskip apart, ~1.2 em; parts of one row <= 0.3 em)
    the rest  scripts and limits join the row of the nearest anchor; a small
              atom centred over/under a big operator joins the operator's row
"""
from __future__ import annotations

AXIS = 0.25            # em: maths axis above the baseline (cmsy: 0.25 em)
GAP = 0.6              # em: anchor gap that starts a new row


def _xc(a):
    return (a["x0"] + a["x1"]) / 2


def _stacks(atoms):
    """tall delimiters: one big atom (openbig/closebig), or a STACK of >= 2 CMEX
    pieces at one x on different baselines (TeX assembles tall ( | { from
    pieces; ordinary '(' of aligned rows also share an x -- r01 -- but are
    CMR, not CMEX; vmatrix bars arrive as unmapped 'vextendsingle' -- r07)"""
    out = [[a] for a in atoms if a["cls"] in ("openbig", "closebig")]
    pieces = sorted([a for a in atoms if a.get("fam") == "CMEX" and a["cls"] not in ("openbig", "closebig", "op", "bigop")],
                    key=lambda a: a["x0"])
    k = 0
    while k < len(pieces):
        grp = [pieces[k]]
        while k + 1 < len(pieces) and abs(pieces[k + 1]["x0"] - grp[0]["x0"]) < 0.5:
            k += 1; grp.append(pieces[k])
        if len({round(a["base"], 1) for a in grp}) >= 2:
            out.append(grp)
        k += 1
    return sorted(out, key=lambda g: g[0]["x0"])


def region(atoms):
    stacks = _stacks(atoms)
    if not stacks:
        return None
    left = stacks[0]
    lx = max(a["x1"] for a in left)
    right = next((g for g in stacks[1:] if g[0]["x0"] >= lx - 0.5), None)
    rx = min(a["x0"] for a in right) if right else float("inf")
    used = {id(a) for a in left} | ({id(a) for a in right} if right else set())
    inner = [a for a in atoms if id(a) not in used and a["x0"] >= lx - 0.5 and a["x1"] <= rx + 0.5]
    return left, inner, right


def _zone_bar(a, bars, size):
    """the bar whose fraction zone holds atom a, nearest first"""
    best = None
    for b in bars:
        if not (b["x0"] - 1.0 <= _xc(a) <= b["x1"] + 1.0):
            continue
        # pdf2mmd2: a big operator is placed by its middle (see _anchor); by
        # its origin a \sum in a numerator stood outside the fraction zone
        h = a.get("axis", a["base"])
        d = h - b["y"]
        if (0 < d <= 0.8 * size) or (-1.1 * size <= d <= 0):
            if best is None or abs(d) < abs(h - best["y"]):
                best = b
    return best


def _radicals(atoms, bars):
    """radical signs and their vinculum (a bar starting at the sign's right
    end): TeX sets the sign's reference point at its TOP, so neither is an
    anchor (r01: \\sqrt{2} opened a row of its own); they follow the radicand"""
    rad = [a for a in atoms if a["tex"].startswith("\\sqrt") or "radical" in a["tex"]]
    vinc = [b for b in bars if any(abs(b["x0"] - r["x1"]) < 1.5 for r in rad)]
    return rad, vinc


def _anchor(a):
    """pdf2mmd2: the height an atom anchors at. A big operator's origin is at
    its top, so its baseline plus AXIS is most of an em above its row: every
    display with a sum or product got a row for the operator alone. The
    adapter gives such an atom the height of its middle (`axis`)."""
    return a["axis"] if "axis" in a else a["base"] + AXIS * a["size"]


def _sides(b, atoms, size):
    """pdf2mmd2: the atoms in a bar's zone, above it and below it"""
    up, down = [], []
    for a in atoms:
        if b["x0"] - 1.0 <= _xc(a) <= b["x1"] + 1.0:
            d = a.get("axis", a["base"]) - b["y"]
            if 0 < d <= 0.8 * size:
                up.append(a)
            elif -1.1 * size <= d <= 0:
                down.append(a)
    return up, down


def split_rows(atoms, bars, size):
    rad, vinc = _radicals(atoms, bars)
    rid, vid = {id(a) for a in rad}, {id(b) for b in vinc}
    late = [a for a in atoms if id(a) in rid]
    atoms = [a for a in atoms if id(a) not in rid]
    lbars = [b for b in bars if id(b) in vid]
    bars = [b for b in bars if id(b) not in vid]
    # pdf2mmd2: only a fraction bar anchors a row. A bar with glyphs on one
    # side only is drawn over or under them (\overline, \underline) and
    # follows them like a vinculum: it stands 0.5-0.65 em above the axis of
    # its own row and opened a row for itself. A fraction of script-size
    # glyphs beside full-size ones is part of a script (x^{1/2} set as a
    # stack) unless such fractions stand one above the other (a matrix of
    # text-style fractions, which has its rows where its bars are).
    full_size = [a for a in atoms if a["size"] >= 0.85 * size
                 and a.get("fam") != "CMEX"]
    fraction, script = [], []
    for b in bars:
        up, down = _sides(b, atoms, size)
        if not (up and down):
            # ... but a bar on the axis of the glyphs beside it is a
            # fraction bar whose other side was not read
            beside = [a for a in full_size
                      if not b["x0"] - 1.0 <= _xc(a) <= b["x1"] + 1.0]
            if any(abs(_anchor(a) - b["y"]) <= 0.2 * size for a in beside):
                fraction.append(b)
            else:
                lbars.append(b)
        elif full_size and all(a["size"] < 0.85 * size for a in up + down):
            script.append(b)
        else:
            fraction.append(b)
    stacked = [b for b in script if any(
        c is not b and c["x0"] < b["x1"] and b["x0"] < c["x1"]
        and abs(c["y"] - b["y"]) > GAP * size for c in script)]
    if stacked:
        fraction += script
    else:
        lbars += script
    bars = fraction
    anchored, loose = [], []
    for a in atoms:
        zb = _zone_bar(a, bars, size)
        if zb is not None:
            anchored.append((zb["y"], a))
        elif (a["size"] >= 0.85 * size and a["cls"] not in ("openbig", "closebig")
              # pdf2mmd2: an extension glyph's origin is at its top, and a
              # piece of a tall delimiter belongs to no one row
              and (a.get("fam") != "CMEX" or "axis" in a)):
            anchored.append((_anchor(a), a))
        else:
            loose.append(a)
    ys = sorted([y for y, _ in anchored] + [b["y"] for b in bars], reverse=True)
    if not ys:
        return [(list(atoms), list(bars))]
    groups = [[ys[0]]]
    for y in ys[1:]:
        if groups[-1][-1] - y <= GAP * size:
            groups[-1].append(y)
        else:
            groups.append([y])
    centres = [sum(g) / len(g) for g in groups]
    nearest = lambda y: min(range(len(centres)), key=lambda k: abs(centres[k] - y))
    rows = [([], []) for _ in centres]
    for y, a in anchored:
        rows[nearest(y)][0].append(a)
    ops = [a for _, a in anchored if a["cls"] in ("op", "bigop")]
    for a in loose:
        op = next((o for o in ops if o["x0"] - 1.0 <= _xc(a) <= o["x1"] + 1.0
                   and abs(a["base"] - o["base"]) < 1.5 * size), None)
        y = _anchor(op) if op else a.get("axis", a["base"] + AXIS * size)
        rows[nearest(y)][0].append(a)
    for b in bars:
        rows[nearest(b["y"])][1].append(b)
    # radicals and vincula: the row holding most glyphs under the vinculum
    def row_under(x0, x1, y):
        votes = [k for k, (ra, _) in enumerate(rows) for a in ra if x0 - 0.5 <= _xc(a) <= x1 + 0.5]
        return max(set(votes), key=votes.count) if votes else nearest(y)
    for b in lbars:
        rows[row_under(b["x0"], b["x1"], b["y"])][1].append(b)
    for r in late:
        v = next((b for b in lbars if abs(b["x0"] - r["x1"]) < 1.5), None)
        rows[row_under(v["x0"], v["x1"], v["y"]) if v else nearest(r["base"])][0].append(r)
    return [r for r in rows if r[0] or r[1]]
