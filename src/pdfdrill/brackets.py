r"""696 — brackets counted per TYPE, not in one global counter.

TeX pairs `\left` with `\right` regardless of the delimiter each carries, so
`\left. … D[(n\rfloor\Psi) … \right]` compiles: the typeless `\left.` absorbs
the typed `\right]` and the plain `[` is left unmatched. The existing gate,
`report_tex._lr_balanced` (618), walks \left/\right DEPTH with one counter for
every kind of delimiter, so it cannot see this. Found by the user on
mielke-geometrodynamics_EQ0393; MathPix's own reading.

This module keeps a separate counter per bracket TYPE (paren, brack, brace,
angle, ceil, floor, vert, Vert), plain and sized (`\left`/`\right`, `\bigl`…)
apart, `\left.` / `\right.` typeless.

WHERE A DELIMITER STANDS MATTERS AS MUCH AS ITS TYPE (inkdrill 672). TeX pairs
\left/\right only inside ONE brace group and ONE alignment cell. The first cut
of the repair ignored both and promoted a plain opener that stood in another
group or cell: `\pi^{( } \gamma\right)`, `k_J^{-1}( & A … \right)`,
`\overbrace{\left.P^{-1}\right)(P}`. 14 of 25 recorded repairs then failed to
compile where MathPix's reading had compiled. Every delimiter now carries its
LOCATION — the path of enclosing brace groups and environments, each with its
alignment-cell number (`&` / `\\` bump it) — and an opener is promoted only when
its location equals the `\right`'s.

Categories:
    repairable_left_null   `\left.` paired by TeX with a typed `\right X`, and a
                           plain X-opener unmatched IN THE SAME LOCATION
    left_null_elsewhere    the same, but the unmatched opener stands in another
                           group or cell — a real mismatch no promotion can fix
    extra_right            a `\right` with nothing open (618 refuses these)
    sized_type_mismatch    mostly legitimate: \left[a,b\right), bra-kets
    right_null             mostly legitimate: \left\{ … \right. (cases)
    plain_imbalance        intervals like [0,1), inline fragments

Only `repairable_left_null` is refused by a gate. A repair is a CANDIDATE: the
caller must still compile it (out/696.txt — `display_safe` screens syntax, it
does not typeset, and that is what let 14 broken repairs through).

`\rfloor` is counted as `floor`; in mielke it is the interior-product hook, not
a bracket, so a floor imbalance there is expected and is not an error.
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
#: alternatives, in order: sized left, sized right, \text{…} (skipped: prose),
#: \begin{env}, \end{env}, row break `\\[..]`, a bare `&`, a brace, a plain delimiter
_TOK = re.compile(
    r"(?P<sl>%s)\s*(?P<sld>%s)|(?P<sr>%s)\s*(?P<srd>%s)"
    r"|(?P<text>\\text\s*\{[^{}]*\})"
    r"|(?P<begin>\\begin\s*\{[^}]*\})|(?P<end>\\end\s*\{[^}]*\})"
    r"|(?P<row>\\\\(?:\[[^\]]*\])?)|(?P<amp>(?<!\\)&)"
    r"|(?P<ob>(?<!\\)\{)|(?P<cb>(?<!\\)\})"
    r"|(?P<d>%s)"
    % (_SIZE_L, _DELIM.replace("(", "(?:", 1), _SIZE_R, _DELIM.replace("(", "(?:", 1),
       _DELIM.replace("(", "(?:", 1)))

REPAIRABLE = "repairable_left_null"
ELSEWHERE = "left_null_elsewhere"
EXTRA_RIGHT = "extra_right"


def _type_of(d: str, prefer: dict):
    if d == ".":
        return "."
    return prefer.get(d) or AMBI.get(d) or OPEN.get(d) or CLOSE.get(d)


def _scan(lx: str):
    """(issues, edits) — one walk yields both the report and the repair."""
    s = lx or ""
    issues, edits = [], []
    # location: a stack of [group id, cell number] per enclosing group or
    # environment. The id is unique per group, so two SIBLING groups at the
    # same depth (johnston EQ0909's two \overbrace{…}) are different places.
    groups = [[0, 0]]
    next_id = [1]

    def loc():
        return tuple((g[0], g[1]) for g in groups)

    lr = []                               # TeX's \left stack: (type, start, end, loc)
    plain = {}                            # type -> [(start, end, loc)] unmatched openers
    plain_close = {}
    for m in _TOK.finditer(s):
        k = m.lastgroup
        if m.group("text"):
            continue
        if m.group("begin") or m.group("ob"):
            groups.append([next_id[0], 0])
            next_id[0] += 1
            continue
        if m.group("end") or m.group("cb"):
            if len(groups) > 1:
                groups.pop()
            continue
        if m.group("row") or m.group("amp"):
            groups[-1][1] += 1
            continue
        if m.group("sl"):
            if m.group("sl").startswith(r"\left"):
                lr.append((_type_of(m.group("sld"), OPEN), m.start(), m.end(), loc()))
            continue
        if m.group("sr"):
            if not m.group("sr").startswith(r"\right"):
                continue
            t = _type_of(m.group("srd"), CLOSE)
            if not lr:
                issues.append((EXTRA_RIGHT, t, m.start()))
                continue
            lt, ls, le, lloc = lr.pop()
            here = loc()
            if lt == "." and t not in (".", None) and plain.get(t):
                same = [o for o in plain[t] if o[2] == here and o[2] == lloc]
                if same:
                    ps, _pe, _ploc = same[-1]
                    plain[t].remove(same[-1])
                    issues.append((REPAIRABLE, t, ps))
                    edits += [(ls, le - ls, ""), (ps, 0, r"\left")]
                else:
                    issues.append((ELSEWHERE, t, plain[t][-1][0]))
            elif lt not in (".", None) and t == ".":
                issues.append(("right_null", lt, ls))
            elif "." not in (lt, t) and lt != t and not {lt, t} <= {"vert"}:
                issues.append(("sized_type_mismatch", "%s/%s" % (lt, t), ls))
            continue
        d = m.group("d")
        if d is None or d == ".":
            continue
        if d in OPEN:
            plain.setdefault(OPEN[d], []).append((m.start(), m.end(), loc()))
        elif d in CLOSE:
            t = CLOSE[d]
            here = loc()
            same = [o for o in plain.get(t, []) if o[2] == here]
            if same:
                plain[t].remove(same[-1])
            elif plain.get(t):
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
    """True when the value carries the one PRECISE, promotable defect."""
    return any(i[0] == REPAIRABLE for i in issues(latex))


def repair(latex: str) -> "tuple[str, int]":
    r"""(candidate value, pairs repaired). Deletes each `\left.` that TeX pairs
    with a typed `\right X` while a plain X-opener is unmatched in the SAME
    group and alignment cell, and promotes that opener to `\left X`. The result
    is a candidate: compile it before recording it."""
    _issues, edits = _scan(latex)
    out = latex or ""
    for pos, n, new in sorted(edits, key=lambda e: -e[0]):
        out = out[:pos] + new + out[pos + n:]
    return out, len(edits) // 2
