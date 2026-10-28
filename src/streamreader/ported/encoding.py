# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/encoding.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""encoding - math structure as ChartKG-style visual encoding mappings.

Layers (ChartKG terms -> here):
  VE    visual element            glyph dict (x0, x1, base, size, name) or rule
  VEPV  property value            properties(a, b): dbase_em, size_ratio, dx_em
  rel   semantic relation         RELATIONS
  map   visual encoding mapping   RULES: (rule id, relation, {property: (lo, hi)})

CONTRACT
    properties(a, b) -> dict(dbase_em=(b.base-a.base)/a.size,
                             size_ratio=b.size/a.size, dx_em=(b.x0-a.x1)/a.size)
    RULES: every relation is produced by exactly one named rule; a rule fires
      when every listed property lies in [lo, hi].
    relate(glyphs) -> [dict(rel, a, b, rule, evidence)] for every ordered pair
      (a, b) a rule fires on; a, b are indices into glyphs; evidence = the
      measured properties (all three).
    explain(a, b, rel) -> dict(ok, rule, failed=[property names out of range])
      for the rule of `rel` with the fewest failures (the user-facing hint).
    relate_fraction(rule, glyphs) -> frac-num / frac-den relations for glyphs
      whose x-centre lies over the rule (rule = dict(x0, x1, y, width)):
      numerator 0 < base - y <= F1_UP*size, denominator 0 < y - base <=
      F1_DOWN*size; rule id 'F1'; a = 'rule'.
    is_operator(g): cls bigop, or the font glyph name (`glyph`, else `name`)
      starting with OP_NAMES.
    runs(glyphs) -> runs of same baseline and size, gaps <= RUN_GAP em.
    limits(a, b, bink=None, op_ok=False) -> (rule, rel, evidence) or None:
      L1 lim-over / L2 lim-under, b's RUN (ink union, bink) centred over a's
      ink x-range and entirely above / below it
      (tolerance L_TOUCH, gap at most L_OVER_GAP / L_UNDER_GAP em). Checked
      before the script rules; needs ink on both. A run whose letters spell a
      word in LIM_WORDS (a maximal sequence of single ASCII letters inside a
      run - the run may continue with other glyphs) is a named operator: limits under/over it attach to
      its LAST letter (rules L1w/L2w), as TeX's nucleus base is its last char.
    relate: an operator or a big delimiter (is_big_delimiter: glyph name ends
      big/Big/bigg/Bigg) WITH ink uses S1op/S2op (properties from the ink
      centre - CMEX glyphs hang below their baseline), every other base S1/S2.
      Limits (L1/L2) stay operators-only.
    resolve(rels, glyphs) -> rels after the constraints:
      C2 an accent (is_accent: glyph name in ACCENT_NAMES) is never a base;
         applied before C1.
      C3 punctuation (, ; . by glyph name) is never a base; before C1.
      C1 one base per script: among SCRIPT_RELS candidates with the same script b,
         keep a LIMIT relation first (centred and entirely outside the operator's
         ink is stronger evidence than a script candidate), else the one whose
         base ends nearest to b (smallest dx_em; ties: the larger base size). Other relation types pass unchanged.
    why_dropped(rel, kept) -> constraint id that removed `rel` ("C2", "C1"),
      or None. (resolve marks C2 drops on the relation dict.)
Thresholds are first guesses, to be measured (tests pin behaviour, not truth).
"""
RELATIONS = ("sup", "sub", "frac-num", "frac-den", "lim-over", "lim-under")
SCRIPT_RELS = ("sup", "sub", "lim-over", "lim-under")
OP_NAMES = ("summation", "product", "coproduct", "integral", "contourintegral",
            "union", "intersection", "circledot", "circleplus", "circlemultiply",
            "logicaland", "logicalor", "unionsq", "unionmulti")
ACCENT_NAMES = ("caron", "tilde", "hat", "circumflex", "macron", "breve", "dotaccent",
                "dieresis", "acute", "grave", "ring", "vector", "check")
RULES = (
    ("S1", "sup", {"dbase_em": (0.15, 0.9), "size_ratio": (0.4, 0.85), "dx_em": (-0.3, 0.6)}),
    ("S2", "sub", {"dbase_em": (-0.7, -0.1), "size_ratio": (0.4, 0.85), "dx_em": (-0.3, 0.6)}),
    # operator base with ink: dbase from the INK CENTRE, dx from the ink's right edge
    ("S1op", "sup", {"dbase_em": (0.05, 1.2), "size_ratio": (0.4, 0.85), "dx_em": (-0.6, 0.6)}),
    ("S2op", "sub", {"dbase_em": (-1.2, -0.05), "size_ratio": (0.4, 0.85), "dx_em": (-0.6, 0.6)}),
)
OP_RULES = ("S1op", "S2op")
L_TOUCH, L_OVER_GAP, L_UNDER_GAP = 0.1, 1.0, 1.2      # in em of the operator
RUN_GAP = 0.35            # em: glyphs of one run (same baseline and size) are at most this far apart
LIM_WORDS = {"lim", "liminf", "limsup", "sup", "inf", "max", "min", "det", "Pr", "gcd"}
F1_UP, F1_DOWN = 1.5, 2.0


def is_accent(g):
    n = (g.get("glyph") or g.get("name") or "").lower()
    return any(n.startswith(k) for k in ACCENT_NAMES)


PUNCT_NAMES = {"comma", "semicolon", "period", ",", ";", "."}


def is_punct(g):
    return (g.get("glyph") or g.get("name")) in PUNCT_NAMES


def is_operator(g):
    n = (g.get("glyph") or g.get("name") or "").lower()
    return g.get("cls") == "bigop" or any(n.startswith(k) for k in OP_NAMES)


BIG_SUFFIXES = ("big", "Big", "bigg", "Bigg")


def is_big_delimiter(g):
    """CMEX-sized delimiter by glyph name (parenrightBig, bracketleftbigg, ...)."""
    n = g.get("glyph") or ""
    return n.endswith(BIG_SUFFIXES) and not is_operator(g)


def properties(a, b):
    """Plain glyphs: as before (3 keys). Operator base: adds ref='ink' (dbase
    from the ink centre, dx from the ink's right edge; measured: a CMEX
    operator's baseline is its ink TOP) or ref='baseline' when it has no ink."""
    s = a["size"]
    if (is_operator(a) or is_big_delimiter(a)) and a.get("ink"):
        x0, y0, x1, y1 = a["ink"]
        return dict(dbase_em=(b["base"] - (y0 + y1) / 2) / s, size_ratio=b["size"] / s,
                    dx_em=(b["x0"] - x1) / s, ref="ink")
    p = dict(dbase_em=(b["base"] - a["base"]) / s, size_ratio=b["size"] / s,
             dx_em=(b["x0"] - a["x1"]) / s)
    if is_operator(a) or is_big_delimiter(a):
        p["ref"] = "baseline"
    return p


def runs(glyphs):
    """-> list of runs (index lists): same baseline (0.1 pt) and size, x-ordered,
    each glyph at most RUN_GAP em right of the run's right edge SO FAR (an
    overlaid zero-width glyph must not cut the run)."""
    by = {}
    for i, g in enumerate(glyphs):
        by.setdefault((round(g["base"], 1), round(g["size"], 2)), []).append(i)
    out = []
    for idx in by.values():
        idx.sort(key=lambda i: glyphs[i]["x0"])
        cur, right = [idx[0]], glyphs[idx[0]]["x1"]
        for i in idx[1:]:
            if glyphs[i]["x0"] - right <= RUN_GAP * glyphs[cur[-1]]["size"]:
                cur.append(i)
                right = max(right, glyphs[i]["x1"])
            else:
                out.append(cur)
                cur, right = [i], glyphs[i]["x1"]
        out.append(cur)
    return out


def _union_ink(glyphs, idx):
    inks = [glyphs[i].get("ink") for i in idx]
    if not all(inks):
        return None
    return (min(k[0] for k in inks), min(k[1] for k in inks), max(k[2] for k in inks), max(k[3] for k in inks))


def limits(a, b, bink=None, op_ok=False):
    """L1/L2: b (or its run: bink) centred over/under an operator's ink and
    entirely outside it. op_ok: a is a named-operator word (caller checked)."""
    bink = bink or b.get("ink")
    if not ((op_ok or is_operator(a)) and a.get("ink") and bink):
        return None
    ax0, ay0, ax1, ay1 = a["ink"]
    bx0, by0, bx1, by1 = bink
    if not ax0 <= (bx0 + bx1) / 2 <= ax1:
        return None
    s = a["size"]
    if by0 >= ay1 - L_TOUCH * s and by0 - ay1 <= L_OVER_GAP * s:
        return ("L1", "lim-over", dict(gap_em=(by0 - ay1) / s))
    if by1 <= ay0 + L_TOUCH * s and ay0 - by1 <= L_UNDER_GAP * s:
        return ("L2", "lim-under", dict(gap_em=(ay0 - by1) / s))
    return None


def _failed(p, ranges):
    return [k for k, (lo, hi) in ranges.items() if not lo <= p[k] <= hi]


def relate(glyphs):
    out = []
    rs = runs(glyphs)
    run_of = {i: r for r in rs for i in r}
    rink = {id(r): _union_ink(glyphs, r) for r in rs}
    words = []                                  # named operators: (run, pseudo-operator)
    for r in rs:                                # letter sequences inside a run
        seq = []
        for i in r + [None]:
            n = None if i is None else (glyphs[i].get("glyph") or glyphs[i].get("name") or "")
            if n is not None and len(n) == 1 and n.isascii() and n.isalpha():
                seq.append(i)
                continue
            t = "".join(glyphs[k].get("glyph") or glyphs[k].get("name") for k in seq)
            if t in LIM_WORDS and _union_ink(glyphs, seq):
                words.append((seq, dict(ink=_union_ink(glyphs, seq), size=glyphs[seq[-1]]["size"])))
            seq = []
    taken = set()
    for r, pseudo in words:
        for j, b in enumerate(glyphs):
            if j in r:
                continue
            lim = limits(pseudo, b, bink=rink[id(run_of[j])], op_ok=True)
            if lim:
                out.append(dict(rel=lim[1], a=r[-1], b=j, rule=lim[0] + "w", evidence=lim[2]))
                taken.add((r[-1], j))
    for i, a in enumerate(glyphs):
        for j, b in enumerate(glyphs):
            if i == j or (i, j) in taken:
                continue
            lim = limits(a, b, bink=rink[id(run_of[j])])
            if lim:
                out.append(dict(rel=lim[1], a=i, b=j, rule=lim[0], evidence=lim[2]))
                continue
            p = properties(a, b)
            use_op = p.get("ref") == "ink"
            for rid, rel, ranges in RULES:
                if (rid in OP_RULES) != use_op:
                    continue
                if not _failed(p, ranges):
                    out.append(dict(rel=rel, a=i, b=j, rule=rid,
                                    evidence={k: v for k, v in p.items() if k != "ref"}))
    return out


def explain(a, b, rel):
    p = properties(a, b)
    best = min(((len(_failed(p, r)), rid, _failed(p, r)) for rid, x, r in RULES if x == rel))
    return dict(ok=not best[2], rule=best[1], failed=best[2], evidence=p)


def relate_fraction(rule, glyphs):
    out = []
    for j, g in enumerate(glyphs):
        cx = (g["x0"] + g["x1"]) / 2
        if not rule["x0"] <= cx <= rule["x1"]:
            continue
        up, down = g["base"] - rule["y"], rule["y"] - g["base"]
        ev = dict(dy=g["base"] - rule["y"], size=g["size"])
        if 0 < up <= F1_UP * g["size"]:
            out.append(dict(rel="frac-num", a="rule", b=j, rule="F1", evidence=ev))
        elif 0 < down <= F1_DOWN * g["size"]:
            out.append(dict(rel="frac-den", a="rule", b=j, rule="F1", evidence=ev))
    return out


def resolve(rels, glyphs):
    keep, best = [], {}
    for r in rels:
        if r["rel"] in SCRIPT_RELS and isinstance(r["a"], int) and is_accent(glyphs[r["a"]]):
            r["_c2"] = True                                     # C2: an accent is never a base
            continue
        if r["rel"] in SCRIPT_RELS and isinstance(r["a"], int) and is_punct(glyphs[r["a"]]):
            r["_c3"] = True                                     # C3: punctuation is never a base
            continue

        if r["rel"] not in SCRIPT_RELS:
            keep.append(r)
            continue
        lim = r["rel"].startswith("lim")
        k = (0 if lim else 1, r["evidence"].get("dx_em", 0.0), -glyphs[r["a"]]["size"])
        if r["b"] not in best or k < best[r["b"]][0]:
            best[r["b"]] = (k, r)
    return keep + [r for _, r in best.values()]


def why_dropped(rel, kept, glyphs=None):
    if rel in kept:
        return None
    if rel.get("_c2"):
        return "C2"
    if rel.get("_c3"):
        return "C3"
    if rel["rel"] in SCRIPT_RELS and any(k["b"] == rel["b"] and k["rel"] in SCRIPT_RELS for k in kept):
        return "C1"
    return None
