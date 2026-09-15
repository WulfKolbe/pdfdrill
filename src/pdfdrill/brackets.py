r"""696 — brackets counted per TYPE, not in one global counter.

TeX pairs `\left` with `\right` regardless of the delimiter each carries, so
`\left. … D[(n\rfloor\Psi) … \right]` compiles: the typeless `\left.` absorbs
the typed `\right]` and the plain `[` is left unmatched. The existing gate,
`report_tex._lr_balanced` (618), walks \left/\right DEPTH with one counter for
every kind of delimiter, so it cannot see this. Found by the user on
mielke-geometrodynamics_EQ0393; MathPix's own reading.

This module keeps a separate counter per bracket TYPE (paren, brack, brace,
angle, ceil, floor, vert, Vert), plain and sized (`\left`/`\right`, `\bigl`…)
apart, `\left.` / `\right.` typeless. Measured over the 20 published documents
(out/696.txt), by category:

    repairable_left_null   25  PRECISE: `\left.` paired by TeX with a typed
                               `\right X` while a plain X-opener is unmatched
    extra_right            16  a `\right` with nothing open (618 refuses these)
    sized_type_mismatch   124  mostly legitimate: \left[a,b\right), bra-kets
    right_null            284  mostly legitimate: \left\{ … \right. (cases)
    plain_imbalance       816  intervals like [0,1), inline fragments

Only the first is an error signal, and it has one repair: delete that `\left.`
and promote the plain opener to `\left X` (25 of 25 render after, and the walk
is clean). The other categories are REPORTED, never refused: `[0,1)` is correct
mathematics with an unbalanced bracket count.

`\rfloor` is counted as `floor`; in mielke it is the interior-product hook, not
a bracket, so a floor imbalance there is expected and is not an error.

A `\left.` that MathPix invents to balance a `\right` it produced from a glyph
misread as CJK (mielke EQ0857: `\left.\mathbf{匕}_n … n\right\rfloor`) has the
same shape; corpus-wide 3 such pairs enclose CJK, and no recorded refinement
removed the CJK while keeping the `\left.` (out/696.txt).
"""
from __future__ import annotations

import re

OPEN = {"(": "paren", "[": "brack", r"\{": "brace", r"\lbrace": "brace",
        r"\lbrack": "brack", r"\langle": "angle", r"\lceil": "ceil",
        r"\lfloor": "floor"}
CLOSE = {")": "paren", "]": "brack", r"\}": "brace", r"\rbrace": "brace",
         r"\rbrack": "brack", r"\rangle": "angle", r"\rceil": "ceil",
         r"\rfloor": "floor"}
AMBI = {"|": "vert", r"\|": "Vert", r"\vert": "vert", r"\Vert": "Vert"}

_SIZE_L = r"\\(?:left|bigl|Bigl|biggl|Biggl)(?![a-zA-Z])"
_SIZE_R = r"\\(?:right|bigr|Bigr|biggr|Biggr)(?![a-zA-Z])"
_DELIM = (r"(\\\{|\\\}|\\\||\\(?:lbrace|rbrace|lbrack|rbrack|langle|rangle|"
          r"lceil|rceil|lfloor|rfloor|vert|Vert)(?![a-zA-Z])|[()\[\]|.])")
#: one token: a sized left + delimiter, a sized right + delimiter, a plain
#: delimiter, or a \text{…} group to skip (prose brackets are not maths)
_TOK = re.compile(r"(%s)\s*%s|(%s)\s*%s|%s|\\text\s*\{[^{}]*\}"
                  % (_SIZE_L, _DELIM, _SIZE_R, _DELIM, _DELIM))
#: `\\` and `\\[2pt]` row breaks: masked with same-length filler so offsets hold
_ROWBREAK = re.compile(r"\\\\(\[[^\]]*\])?")

REPAIRABLE = "repairable_left_null"
EXTRA_RIGHT = "extra_right"


def _type_of(d: str, prefer: dict):
    if d == ".":
        return "."
    return prefer.get(d) or AMBI.get(d) or OPEN.get(d) or CLOSE.get(d)


def _scan(lx: str):
    """(issues, edits) — one walk yields both the report and the repair."""
    s = _ROWBREAK.sub(lambda m: "\x00" * len(m.group(0)), lx or "")
    issues, edits = [], []
    lr = []                               # TeX's own \left/\right stack
    plain = {}                            # type -> [(start, end)] unmatched plain openers
    plain_close = {}                      # type -> count of unmatched plain closers
    for m in _TOK.finditer(s):
        if m.group(0).startswith("\\text"):
            continue
        if m.group(1):                                        # sized left
            if m.group(1).startswith(r"\left"):
                lr.append((_type_of(m.group(2), OPEN), m.start(), m.end()))
        elif m.group(3):                                      # sized right
            if not m.group(3).startswith(r"\right"):
                continue
            t = _type_of(m.group(4), CLOSE)
            if not lr:
                issues.append((EXTRA_RIGHT, t, m.start()))
                continue
            lt, ls, le = lr.pop()
            if lt == "." and t not in (".", None) and plain.get(t):
                ps, _pe = plain[t].pop()
                issues.append((REPAIRABLE, t, ps))
                edits += [(ls, le - ls, ""), (ps, 0, r"\left")]
            elif lt not in (".", None) and t == ".":
                issues.append(("right_null", lt, ls))
            elif "." not in (lt, t) and lt != t and not {lt, t} <= {"vert"}:
                issues.append(("sized_type_mismatch", "%s/%s" % (lt, t), ls))
        else:
            d = m.group(5)
            if d in OPEN:
                plain.setdefault(OPEN[d], []).append((m.start(), m.end()))
            elif d in CLOSE:
                t = CLOSE[d]
                if plain.get(t):
                    plain[t].pop()
                else:
                    plain_close[t] = plain_close.get(t, 0) + 1
    for t in sorted(set(plain) | set(plain_close)):
        o, c = len(plain.get(t, [])), plain_close.get(t, 0)
        if o or c:
            issues.append(("plain_imbalance", "%s open%+d close%+d" % (t, o, c), None))
    return issues, edits


def issues(latex: str) -> list:
    """[(category, type, offset)] for every per-type bracket finding."""
    return _scan(latex)[0]


def repairable(latex: str) -> bool:
    """True when the value carries the one PRECISE defect (see module doc)."""
    return any(i[0] == REPAIRABLE for i in issues(latex))


def repair(latex: str) -> "tuple[str, int]":
    r"""(repaired value, pairs repaired). Deletes each `\left.` that TeX pairs
    with a typed `\right X` while a plain X-opener is unmatched, and promotes
    that opener to `\left X`. A value without the defect comes back unchanged."""
    _issues, edits = _scan(latex)
    out = latex or ""
    for pos, n, new in sorted(edits, key=lambda e: -e[0]):
        out = out[:pos] + new + out[pos + n:]
    return out, len(edits) // 2
