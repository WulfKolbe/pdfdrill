# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), psred/mathparse.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""mathparse - 2-D layout of maths glyphs -> LaTeX, from TeX-set output.

CONTRACT
    atoms_from_marks(marks) -> (atoms, bars)
        atoms: one per glyph: dict(tex, cls, x0, x1, base, size, ic, op, seq)
               (x from the glyph's advance, base = its baseline, PDF points;
               op = the show's op id = byte offset in the ORIGINAL stream,
               seq = glyph index in the show: (op, seq) is the drawing order)
        bars:  thin horizontal paths (short side <= 1.5pt): dict(x0, x1, y, op, seq)
    parse(atoms, bars) -> str (LaTeX, canonical form: every script, fraction
                               part and radicand braced)
Order of recognition (each removes what it consumed):
    1 radicals  a radical glyph whose right edge meets a bar's left end
                (within 1.5pt); radicand = everything horizontally under
                the bar and below it
    2 fractions remaining bars, longest first, with atoms both above and
                below within the bar's x-range
    3 rm words  adjacent upright letters on one baseline -> \\lim, \\sin,..
                or \\mathrm{..}
    4 limits    off-baseline atoms overlapping a nucleus' x-range (grown
                along their own baseline) -> nucleus_{..}^{..}
    5 scripts   off-baseline atoms after a nucleus: above the main baseline
                by > 0.15 em -> ^{..}, below by > 0.1 em -> _{..}
Big operators, radicals, fractions are always nuclei (CMEX/radical glyph
origins are NOT on the main baseline). Measured on TeX output only.
"""
from __future__ import annotations

import os
import re
from collections import Counter

from .mathsym import tok
from . import tfm

COMPOSITE_REL = {("=", "."): "\\doteq", ("=", "\\sim"): "\\cong"}
OPNAMES = set("lim sin cos tan cot sec csc log ln exp max min sup inf det dim ker arg deg "
              "gcd lg Pr sinh cosh tanh arcsin arccos arctan liminf limsup hom mod".split())


# TeX builds these from TWO glyphs pushed together by \\joinrel (-3 mu):
# \\hookrightarrow = \\lhook\\joinrel\\rightarrow, \\hookleftarrow =
# \\leftarrow\\joinrel\\rhook, \\mapsto = \\mapstochar\\rightarrow (CMSY's
# 'mapsto' glyph is the bar alone). 1407.7814 EQ1100 p15 (pdfdrill's reader
# stopped at the hook; psred wrote \\lhook\\!\\to).
XARROW_PAD = 0.637          # em: \\xrightarrow length - label width (measured, 10..80 bp)
JOINED_ARROWS = {("\\lhook", "\\to"): "\\hookrightarrow", ("\\lhook", "\\rightarrow"): "\\hookrightarrow",
                 ("\\leftarrow", "\\rhook"): "\\hookleftarrow",
                 ("\\mapsto", "\\to"): "\\mapsto", ("\\mapsto", "\\rightarrow"): "\\mapsto"}


def _join_long_arrows(out):
    """minus pieces touching/overlapping on one baseline and ending in an
    arrowhead are ONE arrow (sigma26-073 p11/p12: '-\\!-\\!-\\!\\to' for the
    author's \\xrightarrow). Atoms on OTHER baselines inside the run are its
    labels and stay atoms (they attach later as \\xrightarrow[below]{above}).
    One minus overlapped by exactly \\joinrel (-3 mu) and no labels is
    \\longrightarrow (= \\relbar\\joinrel\\rightarrow); otherwise \\xrightarrow{}."""
    res, k = [], 0
    while k < len(out):
        a = out[k]
        # the MINIMAL \\xrightarrow{} lays its minus piece entirely UNDER the
        # arrowhead, so the head sorts first
        if (a["tex"] in ("\\to", "\\rightarrow") and k + 1 < len(out) and out[k + 1]["tex"] == "-"
                and abs(out[k + 1]["base"] - a["base"]) < 0.1 * a["size"]
                and out[k + 1]["x0"] >= a["x0"] - 0.3 and out[k + 1]["x1"] <= a["x1"] + 0.3):
            res.append(dict(a, tex="\\xrightarrow{}", cls="rel", ic=0.0)); k += 2; continue
        if a["tex"] != "-":
            res.append(a); k += 1; continue
        same = lambda x: abs(x["base"] - a["base"]) < 0.1 * a["size"]
        pieces, labels, m = [a], [], k + 1
        while m < len(out):
            x = out[m]
            if not same(x):
                labels.append(x); m += 1; continue
            if x["tex"] == "-" and x["x0"] <= pieces[-1]["x1"] + 0.3:
                pieces.append(x); m += 1; continue
            break
        head = out[m] if m < len(out) else None
        if head is not None and head["tex"] in ("\\to", "\\rightarrow") and head["x0"] <= pieces[-1]["x1"] + 0.3:
            joinrel = 3.0 / 18.0 * a["size"]
            one = len(pieces) == 1 and not labels and abs((pieces[-1]["x1"] - head["x0"]) - joinrel) < 0.35 * joinrel
            res.extend(labels)
            tex = "\\longrightarrow" if one else "\\xrightarrow{}"
            L = head["x1"] - a["x0"]
            # labels can sort AFTER the head (\\xrightarrow{f}): any atom on another
            # baseline centred within the arrow's width is a label
            labelled = labels or any(not same(x) and a["x0"] <= (x["x0"] + x["x1"]) / 2 <= head["x1"]
                                     for x in out)
            if tex == "\\xrightarrow{}" and not labelled and L > a["size"] + 0.5:
                # no labels: the length alone is the author's (\\xrightarrow{\\rule..})
                tex = "\\xrightarrow{\\rule{%gbp}{0pt}}" % round(L - XARROW_PAD * a["size"], 2)
            res.append(dict(head, tex=tex, cls="rel", x0=a["x0"], x1=head["x1"], ic=0.0))
            k = m + 1
        else:
            res.append(a); k += 1
    return sorted(res, key=lambda a: a["x0"])


def _join_arrows(atoms):
    """two glyphs that touch or overlap on the same baseline and form one of
    JOINED_ARROWS become one relation atom spanning both"""
    out = sorted(atoms, key=lambda a: a["x0"])
    out = _join_long_arrows(out)
    k = 0
    while k + 1 < len(out):
        a, b = out[k], out[k + 1]
        name = JOINED_ARROWS.get((a["tex"], b["tex"]))
        if name and abs(a["base"] - b["base"]) < 0.1 * a["size"] and b["x0"] <= a["x1"] + 0.5:
            out[k] = dict(a, tex=name, cls="rel", x1=max(a["x1"], b["x1"]), ic=0.0)
            del out[k + 1]
            continue
        k += 1
    return out


def _family(font):
    from .adapter import family          # pdf2mmd2: was psred.lines.family
    return family(font or "")


def atoms_from_marks(marks):
    atoms, bars = [], []
    for m in marks:
        if m.kind == "text":
            for seq, (name, a, b) in enumerate(m.glyphs):
                t, cl = tok(name, m.font_base)
                mt = tfm.metrics(m.font_base, name)
                gf = (getattr(m, "gfonts", None) or [None] * len(m.glyphs))[seq] or m.font_base
                atoms.append(dict(tex=t, cls=cl, x0=a, x1=b, base=m.origin[1], size=m.size,
                                  ic=(mt["ic"] * m.size) if mt else 0.0,
                                  op=m.id, seq=seq,           # drawing order (T2)
                                  fam=_family(gf)))           # T3: CMEX pieces form tall delimiters
        elif m.kind == "path":
            x0, y0, x1, y1 = m.bbox
            if y1 - y0 <= 1.5 and x1 - x0 > y1 - y0:
                bars.append(dict(x0=x0, x1=x1, y=(y0 + y1) / 2, op=m.id, seq=0))
    atoms = _join_arrows(atoms)
    return atoms, bars


def _xc(a):
    return (a["x0"] + a["x1"]) / 2


def _composite(tex, x0, x1, base, size):
    return dict(tex=tex, cls="ord", x0=x0, x1=x1, base=base, size=size, fixed=True)


SCRIPT_RATIO = 0.85     # pdf2mmd2: a script is at most this x its base's size
                        # (featjudge encoding rules S1/S2: 0.4 .. 0.85)

# pdf2mmd2 (T-0037): Appendix G Rule 18 as a veto in script attachment.
# TeX sets a script of a character nucleus at the nucleus' width w, a
# superscript further by its italic correction; a list nucleus ending in
# that character is w + ic wide. A script group that starts outside
# [w, w + ic] is not that nucleus' but has an empty base of its own,
# written as MathPix does: G_{2}{ }^{C}. Needs the nucleus' TFM metrics
# (atom 'wd'); without them the parser decides as before. X tolerance:
# dvips sets glyph origins on its device grid, 600 dpi = 0.12 bp, some y
# on 300 dpi (bench/results/rule18-dvips-2026-10-18.json: residuals of
# script pairs
# median 0.054 bp; 0902.0431 15814 of 17214 and 1701.02095 1087 of 1087
# within 0.25 bp). pdflatex and LuaTeX keep it to 0.005 bp (T-0036).
RULE18 = os.environ.get("PDF2MMD2_RULE18") == "1"     # default off
RULE18_TOL = 0.25       # bp


def _rule18_fits(n, a, sup) -> bool | None:
    """Whether a script group starting with `a` can be nucleus n's by Rule
    18's horizontal placement; None when n's metrics are unknown or n is
    not a single glyph as the font set it."""
    w = n.get("wd")
    if (w is None or n.get("fixed") or n.get("limits") or n.get("accented")
            or n["cls"] in ("bigop", "radical", "openbig", "closebig")
            or abs((n["x1"] - n["x0"]) - w) > RULE18_TOL):
        return None
    # a subscript of a character at w; a list ending in the character
    # (\boldsymbol{\gamma}_{0}) is w + ic wide, so its scripts start there
    dx = a["x0"] - (n["x0"] + w)
    return -RULE18_TOL <= dx <= n.get("ic", 0.0) + RULE18_TOL


def _rule18_box(n, a, k, box, trail, S):
    """(script box, side) that atom `a` joins, a script that its baseline
    puts on side k (0 sub, 1 sup) and no script of a script: the group of
    nucleus n's own `box` or of the last empty-base box of `trail` that it
    goes on (on either side: the "ery" of V_{a_{t}^{qu}ery} stands above
    the row), else n's box on side k, or a new empty-base box."""
    def goes_on(group):
        # on a member's baseline, after the group's right end (scripts of
        # its own included: E_{\tau\sim\pi_{\theta}(...)}), or where a
        # script of a member stands, within the member's size of its
        # baseline (scriptscript is the smallest size: C_{Q_{0}} in a limit
        # sets Q and 0 alike; the b of \int_{a}^{b} is far above the a)
        before = [p["x1"] for p in group if p["x0"] <= a["x0"]]
        on = any(abs(a["base"] - p["base"]) < 0.05 * S for p in group)
        return ((on and before and -RULE18_TOL <= a["x0"] - max(before) < 0.3 * S)
                or any(abs(a["base"] - p["base"]) <= p["size"]
                       and _rule18_fits(p, a, a["base"] > p["base"]) for p in group))
    for bx in [box] + trail[-1:]:
        for side in (k, 1 - k):
            if bx[side] and goes_on(bx[side]):
                return bx, side
    if trail:
        last = trail[-1]
        if not last[k] and last[1 - k] and abs(
                a["x0"] - min(p["x0"] for p in last[1 - k])) <= RULE18_TOL:
            return last, k                  # {}_{b}^{a}: both at the same x
    fits = _rule18_fits(n, a, k == 1)
    if fits is None or (fits and not box[k]):
        return box, k
    trail.append(([], []))
    return trail[-1], k


def parse(atoms, bars, style="D") -> str:
    """style: D display, T text, S script (TeX's; scripts and limits are S,
    fraction parts one step down: D->T, T->S)."""
    down = {"D": "T", "T": "S", "S": "S"}[style]
    atoms = [dict(a) for a in atoms]
    bars = [dict(b) for b in bars]
    if not atoms:
        return ""
    S = max((a["size"] for a in atoms if a["cls"] not in ("bigop", "radical", "openbig", "closebig")),
            default=max(a["size"] for a in atoms))

    # 0 accents: an accent glyph wraps the atom it overlaps most, at or below
    #   its baseline (TeX sets lower-case accents on the nucleus baseline and
    #   raises them for capitals)
    for acc in [a for a in atoms if a["cls"] == "accent"]:
        w = acc["x1"] - acc["x0"]
        cand = [a for a in atoms if a is not acc and a["cls"] != "accent"
                and a["base"] <= acc["base"] + 0.1 * acc["size"]
                and min(a["x1"], acc["x1"]) - max(a["x0"], acc["x0"]) > 0.3 * w]
        if not cand:
            continue
        if acc["tex"] in ("\\widehat", "\\widetilde"):
            # a WIDE accent covers a group: everything whose centre lies under
            # it, parsed as one argument (EQ0232: \\widehat{\\mathbb{S}^1}, not
            # \\mathbb{S}^{\\widehat{1}} -- the raised '1' was 'nearest')
            inner = [a for a in cand if acc["x0"] - 1 <= _xc(a) <= acc["x1"] + 1]
            if inner:
                main = max(inner, key=lambda a: a["size"])
                grp = dict(main, tex=acc["tex"] + "{" + parse(inner, []) + "}",
                           x0=min(a["x0"] for a in inner), x1=max(a["x1"] for a in inner),
                           cls="ord", ic=0.0, accented=True)
                ids = {id(a) for a in inner} | {id(acc)}
                atoms = [a for a in atoms if id(a) not in ids] + [grp]
                continue
        # nearest BELOW first, x only qualifies: in \\frac{\\tilde Y}{\\sin\\phi}
        # an x-first choice put the tilde on the 'n' of sin (sigma26-075 (8.1))
        nuc = min(cand, key=lambda a: (round(acc["base"] - a["base"], 1), abs(_xc(a) - _xc(acc))))
        nuc["tex"] = acc["tex"] + "{" + nuc["tex"] + "}"
        nuc["ic"] = 0.0
        nuc["accented"] = True      # pdf2mmd2: Rule 12 reboxes it (T-0037)
        atoms = [a for a in atoms if a is not acc]

    # 1 radicals
    for r in sorted([a for a in atoms if a["cls"] == "radical"], key=lambda a: -a["x0"]):
        bar = next((b for b in bars if abs(b["x0"] - r["x1"]) <= 1.5), None)
        if bar is None:
            continue
        inner = [a for a in atoms if a is not r and bar["x0"] - 1 <= _xc(a) <= bar["x1"] + 1
                 and a["base"] < bar["y"]]
        ib = [b for b in bars if b is not bar and bar["x0"] - 1 <= (b["x0"] + b["x1"]) / 2 <= bar["x1"] + 1
              and b["y"] < bar["y"]]
        body = parse(inner, ib, style)
        atoms = [a for a in atoms if a is not r and not any(a is i for i in inner)]
        bars = [b for b in bars if b is not bar and not any(b is i for i in ib)]
        base = Counter(round(a["base"], 1) for a in inner).most_common(1)[0][0] if inner else r["base"]
        atoms.append(_composite("\\sqrt{" + body + "}", r["x0"], bar["x1"], base, S))

    # 2 fractions, longest bar first
    for bar in sorted(bars, key=lambda b: -(b["x1"] - b["x0"])):
        if not any(bar is b for b in bars):
            continue
        inx = lambda o: bar["x0"] - 1 <= _xc(o) <= bar["x1"] + 1
        num = [a for a in atoms if inx(a) and a["base"] > bar["y"]]
        den = [a for a in atoms if inx(a) and a["base"] < bar["y"]]
        if not num or not den:
            continue
        nb = [b for b in bars if b is not bar and inx(b) and b["y"] > bar["y"]]
        db = [b for b in bars if b is not bar and inx(b) and b["y"] < bar["y"]]
        tex = "\\frac{" + parse(num, nb, down) + "}{" + parse(den, db, down) + "}"
        used = num + den
        atoms = [a for a in atoms if not any(a is u for u in used)]
        bars = [b for b in bars if b is not bar and not any(b is u for u in nb + db)]
        # box = numerator/denominator box +- \\nulldelimiterspace (the bar is
        # drawn ~0.2pt wider than that box); LaTeX's \\frac wraps the fraction
        # in braces, so it is an ORD atom, not TeX's Inner (measured: corpus f23)
        c = _composite(tex, min(a["x0"] for a in used) - NULLDELIM,
                       max(a["x1"] for a in used) + NULLDELIM, bar["y"], S)
        atoms.append(c)

    # 2b overlines: a bar with glyphs directly BELOW it and none above (the
    # fraction stage skipped it, and the bar was lost: wzlxjtu-030 EQ0013
    # D\\overline{A} came out as DA). One ORD atom at the CONTENT's baseline.
    for bar in sorted(bars, key=lambda b: -(b["x1"] - b["x0"])):
        if not any(bar is b for b in bars):
            continue
        inx = lambda o: bar["x0"] - 1 <= _xc(o) <= bar["x1"] + 1
        under = [a for a in atoms if inx(a) and bar["y"] - 1.2 * S < a["base"] < bar["y"]]
        if not under or any(inx(a) and 0 < a["base"] - bar["y"] <= 0.8 * S for a in atoms):
            continue
        ub = [b for b in bars if b is not bar and inx(b) and b["y"] < bar["y"]]
        main = max(under, key=lambda a: a["size"])
        c = _composite("\\overline{" + parse(under, ub, style) + "}", min(a["x0"] for a in under),
                       max(a["x1"] for a in under), main["base"], S)
        atoms = [a for a in atoms if not any(a is u for u in under)] + [c]
        bars = [b for b in bars if b is not bar and not any(b is u for u in ub)]

    # main baseline: most frequent baseline of full-size, non-fixed atoms
    full = [a for a in atoms if not a.get("fixed") and a["cls"] not in ("bigop", "radical", "openbig", "closebig")
            and a["size"] >= 0.95 * S]
    if full:
        B = Counter(round(a["base"], 1) for a in full).most_common(1)[0][0]
    else:
        B = None
    # pdf2mmd2: a script-size glyph is never a nucleus of the row, even when
    # its baseline falls on the row's: the prime of a subscript does
    # (S_{\mu'\nu'} read as S_{\mu}\prime_{\nu}\prime, round-trip formula 40)
    on = lambda a: a.get("fixed") or a["cls"] in ("bigop", "radical", "openbig", "closebig") or \
        (B is not None and abs(a["base"] - B) <= 0.1 * S and a["size"] > SCRIPT_RATIO * S)

    # 3 rm words on the main line
    # merge among MAIN-LINE atoms only: lim's limits (n, ->, inf) interleave
    # with l, i, m in x and broke the word apart (corpus f10)
    main = sorted([a for a in atoms if on(a)], key=lambda a: a["x0"])
    rest = [a for a in atoms if not on(a)]
    merged = []
    for a in main:
        p = merged[-1] if merged else None
        if (p and a["cls"] == "rm" and p["cls"] == "rm" and on(a) and on(p)
                and abs(a["base"] - p["base"]) < 0.05 * S and a["x0"] - p["x1"] < 0.1 * S):
            p["tex"] += a["tex"]; p["x1"] = a["x1"]
        else:
            merged.append(dict(a))
    for a in merged:
        if a["cls"] == "rm":
            if a["tex"] not in OPNAMES and len(a["tex"]) >= 2:
                a["word"] = a["tex"]            # pdf2mmd2: see TEXTSPACE
            a["tex"] = ("\\" + a["tex"]) if a["tex"] in OPNAMES else "\\mathrm{" + a["tex"] + "}"
            a["cls"] = "op" if a["tex"][1:] in OPNAMES else "ord"
    atoms = merged + rest

    nuclei = [a for a in atoms if on(a)]
    off = [a for a in atoms if not on(a)]

    # 4 limits: off-line atoms overlapping an operator nucleus, grown along baseline
    out_of = set()
    for n in nuclei:
        if n["cls"] not in ("bigop", "op", "rel"):
            continue
        seed = [a for a in off if id(a) not in out_of and n["x0"] - 1 <= _xc(a) <= n["x1"] + 1]
        grp = []
        for s0 in seed:
            if any(s0 is g for g in grp):
                continue
            row = [a for a in off if id(a) not in out_of and abs(a["base"] - s0["base"]) < 0.05 * S]
            row.sort(key=lambda a: a["x0"])
            i = next(k for k, a in enumerate(row) if a is s0)
            lo = hi = i
            while lo > 0 and row[lo]["x0"] - row[lo - 1]["x1"] < 0.3 * S: lo -= 1
            while hi < len(row) - 1 and row[hi + 1]["x0"] - row[hi]["x1"] < 0.3 * S: hi += 1
            grp += row[lo:hi + 1]
        if not grp:
            continue
        # pdf2mmd2: a limit can hold scripts of its own (\sup_{\|u_0-v\|=1}).
        # They sit on another baseline, so the row above stopped at them and
        # lost what follows; take in what is set against a member - on its
        # baseline, or as its script - until nothing more joins.
        grown = True
        while grown:
            grown = False
            for a in off:
                if id(a) in out_of or any(a is g for g in grp):
                    continue
                for g in grp:
                    if max(a["x0"] - g["x1"], g["x0"] - a["x1"]) >= 0.3 * S:
                        continue
                    d = abs(a["base"] - g["base"])
                    big, small = (g, a) if g["size"] >= a["size"] else (a, g)
                    if d < 0.05 * S or (small["size"] <= SCRIPT_RATIO * big["size"]
                                        and d <= 0.6 * big["size"]):
                        grp.append(a)
                        grown = True
                        break
        ref = B if B is not None else n["base"]
        up = [a for a in grp if a["base"] > ref]; dn = [a for a in grp if a["base"] <= ref]
        if n["cls"] == "rel":            # \stackrel / \overset: text over a relation
            t = n["tex"]
            # LaTeX composites stack a FULL-size glyph over a relation (\doteq =
            # \buildrel\textstyle.\over=, \cong = \sim over =); \stackrel and
            # \overset set the upper part at SCRIPT size
            comp = COMPOSITE_REL.get((t, up[0]["tex"])) if len(up) == 1 and not dn else None
            if comp and up[0]["size"] >= 0.95 * n["size"]:
                n["tex"] = comp
                up = []
                t = comp
            if t == "\\xrightarrow{}":
                # an extensible arrow carries its labels as arguments; an arrow
                # LONGER than its labels make it gets an invisible spacer above
                # (measured: length = spacer + 0.637 em, amsmath's padding;
                # PDF points are TeX bp)
                L = n["x1"] - n["x0"]
                wid = lambda g: (max(x["x1"] for x in g) - min(x["x0"] for x in g)) if g else 0.0
                expect = max(max(wid(up), wid(dn)) + XARROW_PAD * n["size"], n["size"])
                upper = parse(up, [], "S") if up else ""
                if not up and L > expect + 0.5:
                    upper = "\\rule{%gbp}{0pt}" % round(L - XARROW_PAD * n["size"], 2)
                t = ("\\xrightarrow" + ("[" + parse(dn, [], "S") + "]" if dn else "") + "{" + upper + "}")
                up = dn = []
            if up:
                t = "\\stackrel{" + parse(up, [], "S") + "}{" + t + "}"   # LaTeX core, no amsmath
            if dn:
                t = "\\underset{" + parse(dn, [], "S") + "}{" + t + "}"
            n["tex"] = t
        else:
            n["tex"] += ("_{" + parse(dn, [], "S") + "}" if dn else "") + ("^{" + parse(up, [], "S") + "}" if up else "")
        n["limits"] = True
        # TeX centres limits over/under the operator: its box is as wide as the
        # widest part (lim: n->inf 289-309.8 is wider than 'lim' 292.5-306.4)
        n["x0"] = min([n["x0"]] + [a["x0"] for a in grp])
        n["x1"] = max([n["x1"]] + [a["x1"] for a in grp])
        out_of |= {id(a) for a in grp}
    off = [a for a in off if id(a) not in out_of]

    # 5 scripts: attach each off-line atom to the nearest nucleus on its left
    nuclei.sort(key=lambda a: a["x0"])
    scripts = {id(n): ([], []) for n in nuclei}
    # pdf2mmd2 (T-0037): script groups with an empty base after a nucleus
    trails = {id(n): [] for n in nuclei}
    lead = ([], [])
    ref = B if B is not None else 0.0
    for a in sorted(off, key=lambda a: a["x0"]):
        left = [n for n in nuclei if n["x0"] <= a["x0"] + 0.5]
        box = scripts[id(left[-1])] if left else lead
        boxes = [box] + (trails[id(left[-1])] if left else [])
        # pdf2mmd2: a script of a script goes where its own base went, not
        # where its baseline falls: the 2 of y_{b^2} stands above the row
        # (of two candidates, an index and an exponent stacked on one base,
        # the one whose baseline is nearer: the k of A_{i_k}^{j} is i's)
        side = None
        for bx in boxes:
            for k in (0, 1):
                for p in bx[k]:
                    d = abs(a["base"] - p["base"])
                    if (a["size"] <= SCRIPT_RATIO * p["size"] and p["x0"] <= a["x0"]
                            and a["x0"] - p["x1"] < 0.4 * S
                            and (side is None or d < side[1])):
                        side, box = (k, d), bx
        if side is None:
            side = (1 if a["base"] > ref else 0, 0.0)
            if RULE18 and left:
                box, s = _rule18_box(left[-1], a, side[0], box, trails[id(left[-1])], S)
                side = (s, 0.0)
        box[side[0]].append(a)
    parts = []
    if lead[0] or lead[1]:
        parts.append("{}" + _scr(lead))
    groups = []
    for n in nuclei:
        sc = scripts[id(n)][0] + scripts[id(n)][1]
        sc += [a for t in trails[id(n)] for a in t[0] + t[1]]
        end = max([n["x1"] + (0.0 if sc or n.get("limits") else n.get("ic", 0.0))] +
                  # a script box carries its glyph's italic correction too (TeX
                  # adds it after a lone script char: W^V -- 1706.03762, the
                  # merged line exposed '\\,' before ')' where the gap was ic)
                  [a["x1"] + a.get("ic", 0.0) + SCRIPTSPACE for a in sc])
        groups.append((n, end))
    # pdf2mmd2 (T-0037): after an empty-base group the atom spaced against
    # is that group, an Ord
    spaced = [(dict(n, cls="ord") if trails[id(n)] else n, end) for n, end in groups]
    for k, (n, end) in enumerate(groups):
        if k:
            sp = _space(spaced[k - 1][0], spaced[k - 1][1], n, style, S, spaced[:k])
            if sp == TEXTSPACE:
                # pdf2mmd2: an upright word after an interword space is
                # text with its leading space, \text{ simple}
                parts.append("\\text{ " + n["word"] + "}" + _scr(scripts[id(n)])
                             + "".join("{ }" + _scr(t) for t in trails[id(n)]))
                continue
            if sp:
                parts.append(sp)
        parts.append(n["tex"] + _scr(scripts[id(n)])
                     + "".join("{ }" + _scr(t) for t in trails[id(n)]))
    return _join(parts)


# TeX spacing: TeXbook ch. 18 table; 1 thin, 2 med, 3 thick; negative = only
# in D/T styles (parenthesised entries). Classes: ord op bin rel open close punct inner
_T = {
    "ord":   dict(op=1, bin=-2, rel=-3, inner=-1),
    "op":    dict(ord=1, op=1, rel=-3, inner=-1),
    "bin":   dict(ord=-2, op=-2, open=-2, inner=-2),
    "rel":   dict(ord=-3, op=-3, open=-3, inner=-3),
    "open":  dict(),
    "close": dict(op=1, bin=-2, rel=-3, inner=-1),
    "punct": dict(ord=-1, op=-1, rel=-1, open=-1, close=-1, punct=-1, inner=-1),
    "inner": dict(ord=-1, op=1, bin=-2, rel=-3, open=-1, punct=-1, inner=-1),
}
MU = {1: 3, 2: 4, 3: 5}
STRETCH = {1: 0, 2: 2, 3: 5}               # plain TeX medmuskip plus 2mu, thickmuskip plus 5mu
NULLDELIM, SCRIPTSPACE = 1.2, 0.5          # plain TeX \nulldelimiterspace, \scriptspace
EXPLICIT = [("\\,", 3), ("\\:", 4), ("\\;", 5), ("\\quad", 18), ("\\qquad", 36)]
INTERWORD = 6.0                            # pdf2mmd2: cmr interword space, in mu
TEXTSPACE = "\\text "                      # pdf2mmd2: marker, never emitted


def _cls(a, before):
    c = {"bigop": "op", "radical": "ord", "rm": "ord", "op": "op",
         "openbig": "open", "closebig": "close"}.get(a["cls"], a["cls"])
    if c == "bin" and (not before or _cls(before[-1][0], before[:-1]) in ("bin", "op", "rel", "open", "punct")):
        return "ord"                        # TeX rule 5: a leading/after-operator bin is ord
    return c


def _space(prev, prev_end, n, style, S, before):
    """explicit space between two nuclei = measured gap - TeX's own spacing"""
    pc = _cls(prev, before[:-1]); nc = _cls(n, before)
    v = _T.get(pc, {}).get(nc, 0)
    if v < 0:
        v = -v if style in ("D", "T") else 0
    mu = S / 18.0
    extra = (n["x0"] - prev_end) - MU.get(v, 0) * mu
    # justified lines stretch med/thick glue (1706.03762: '$h=8$' read as h\;=\;8)
    if extra <= -1.5 * mu:
        # a gap ~3mu SMALLER than TeX's rule: the author suppressed a space
        # (sigma26-075 (3.7): '-{\\tanh}' makes \\tanh an Ord, no thin space)
        return "\\!"
    # pdf2mmd2: glue stretches only in a line of a justified paragraph, so
    # only an inline formula gets that allowance. A display is set at its
    # natural width, and there `a\,=b` is 3mu more than `a=b` and must be
    # read as such (6 of the 49 generated cases next to a relation).
    stretch = STRETCH.get(v, 0) if style == "T" else 0
    if extra <= (stretch + 1.5) * mu:
        return ""
    best = min(EXPLICIT, key=lambda e: abs(e[1] * mu - extra))
    # pdf2mmd2: cmr's interword space is 1/3 em = 6mu; before an upright
    # word it is the space of \text{ word}, where the nearest command would
    # be \; (sigma26-073 EQ0495, "\mathbb{S}_i\text{ simple}")
    if n.get("word") and abs(INTERWORD * mu - extra) < abs(best[1] * mu - extra):
        return TEXTSPACE
    return best[0]


def _scr(box):
    sub, sup = box
    return ("_{" + parse(sub, [], "S") + "}" if sub else "") + ("^{" + parse(sup, [], "S") + "}" if sup else "")


def _join(parts):
    out = ""
    for p in parts:
        if out and re.search(r"\\[A-Za-z]+$", out) and re.match(r"[A-Za-z]", p):
            out += " "
        out += p
    return out


def normalize(tex: str) -> str:
    """For comparison with a source: drop spacing commands and whitespace."""
    t = re.sub(r"\\[,;!:]|\\ |\\displaystyle|\\left|\\right", "", tex)
    return re.sub(r"\s+", "", t)
