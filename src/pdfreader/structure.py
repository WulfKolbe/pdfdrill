"""structure — rebuild maths structure from glyph geometry and rules.

This is the layout-tree unit. `docmodel` produced spans whose glyphs are
identified but whose vertical relationships were thrown away; 50.6 % of maths
spans deferred on exactly that. Here those relationships are recovered:

  U8 FRACTIONS  a rule with glyphs above and below is a `\\frac`. The rule's
                x-range bounds the numerator and denominator.
  U9 SCRIPTS    a glyph that is smaller than the row AND sits off the row's
                baseline is a super- or subscript of the nearest main glyph
                to its left.

DESIGN RULE, applied everywhere: when the geometry does not determine the
answer, return None and let the caller defer. A wrong `\\frac` or a
misattached `^{}` is valid LaTeX with different mathematics in it, and nothing
downstream can detect that. Silence is recoverable; a confident error is not.

LIMITS, stated rather than discovered later:
  - no radicals: `radicalbig` gives the sign, but the vinculum rule does not
    reliably bound the argument, so radical spans are refused outright
  - no matrices, no stacked limits above/below big operators
  - no \\left…\\right pairing across a whole expression
  - scripts attach to a single preceding glyph, not to a sub-expression
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from pdfreader.docmodel_six import MATH_FAMILIES, GlyphNode, RuleNode, glyph_latex
import os as _os
from pdfreader import texmap
from pdfreader.texmap import TexToken, math_space

# A script is smaller than its base. Measured on the corpus: 6.97pt scripts
# under 9.96pt bases, a ratio of 0.70, so 0.92 separates them with margin.
SCRIPT_SIZE_RATIO = 0.92
# Vertical offset, as a fraction of row size, beyond which a same-row glyph is
# considered shifted rather than level.
# How far two glyphs may sit apart in baseline and still count as one level.
#
# 0.12 em, by sweep. At 0.08 an author line refused to project because its
# two superscript markers -- an `a` in the body face and a `*` in STIXMath --
# sit 1.0pt apart at 7pt, which is 0.14em: different FONTS place a raised
# glyph differently, and both are the same superscript. At 0.16 the tolerance
# starts swallowing real script levels: Gallier fell 98.7% -> 79.9% and
# Mielke 85.6% -> 61.6%.
LEVEL_TOL = 0.12


@dataclass
class Frac:
    rule: RuleNode
    num: list
    den: list


#: T-0156 — how much smaller than its neighbours a fraction's numerals must
#: be before it is `\tfrac` rather than `\frac`, and how close to full size
#: that neighbour must be. MEASURED on lib:6d90e8d27b8b p174: dominant size
#: 9.6, numerals 6.7, neighbours 9.6 — 0.70, which is CMR6 against a 9.6 pt
#: line. Over the 24 board-14 extracts the rule answers 49 of 118 fractions.
_TFRAC_NUMERAL = 0.85
_TFRAC_NEIGHBOUR = 0.9


#: How many enclosing levels are a root's or a bar's body (style-keeping).
_STYLE_KEEPING = [0]


def _is_text_style(num, den, rest, size: float, depth: int) -> bool:
    r"""Is this fraction set in TEXT style — script-size numerals?

    inkdrill-10 on p174: the page sets `\tfrac` inside a display line and
    our `\frac` sets it display-size, so the glyph findings on those numerals
    are correct — the numbers really are the wrong size in our rendering.

    THE NEAREST NEIGHBOUR DECIDES, not the page and not the largest glyph in
    reach, and the first two versions of the measurement were wrong in
    opposite directions because of it:

      * against the PAGE's dominant size, a fraction inside a superscript
        looks identical to a `\tfrac` — the whole subexpression is small.
        That version counted 51 and could not see the difference.
      * against the LARGEST neighbour within reach, a nested inner fraction
        finds a full-size glyph a few em away and counts itself. p174 has
        one, numerals at 4.8 inside an outer at 6.7.

    AND ONLY THE OUTERMOST, which `depth` gives: an inner fraction inherits
    its style, and `\tfrac` inside a `\tfrac` forces textstyle where the
    context is already script, making the inner one too big.
    """
    # A root's or a bar's BODY keeps the style around it: only a script or
    # a fraction changes it. lib:6d90e8d27b8b p174's `\sqrt[3]{c -
    # \tfrac34 t^4}` sits one depth level down, inside the root, so its
    # `\tfrac` was written `\frac`, set display-size, and the radical grew
    # with it (B11).
    if depth - _STYLE_KEEPING[0] > 0 or not num or not den or not rest or size <= 0:
        return False
    small = max(g.size for g in num + den)
    x0 = min(g.rect[0] for g in num + den)
    x1 = max(g.rect[2] for g in num + den)
    near = min(rest, key=lambda g: min(abs(g.rect[0] - x1), abs(x0 - g.rect[2])))
    if near.size < _TFRAC_NEIGHBOUR * size:
        return False                 # its own neighbourhood is small: a script
    return small < _TFRAC_NUMERAL * near.size


#: T-0154 — the separators that can end a term in a display row, and how far
#: off the row's own baseline a glyph may sit and still count as one.
_TERM_SEPARATORS = frozenset(",;")
_TERM_BASELINE_EM = 0.25


#: T-0154 — when two baselines inside one construct are two ROWS rather than a
#: base and its script. MEASURED on lib:c57ac038ae5f p293: the entries of
#: `[1 / -1/2]` sit 6.6 apart at one size (7.6) in one column; a superscript
#: sits to the RIGHT of its base and is smaller.
_ROW_GAP_EM = 0.35
_ROW_OVERLAP = 0.5
_ROW_SIZE_RATIO = 0.85
#: How close to the row's own baseline counts as ON it. MEASURED on
#: p293: a column vector's entries sit 0.26 em and 0.40 em off the row
#: baseline, while an ordinary bracketed expression has body glyphs at
#: 0.00. The first version reused _ROW_GAP_EM (0.35) and refused the
#: vector itself, so the two constants are separate on purpose.
_ON_BASELINE_EM = 0.1


#: T-0154 — the sized delimiter commands `texmap._SIZE_CMD` builds, by side.
_SIZED_LEFT = (r"\Biggl", r"\biggl", r"\Bigl", r"\bigl")
_SIZED_RIGHT = (r"\Biggr", r"\biggr", r"\Bigr", r"\bigr")


def _unsized(latex: str, sides) -> "str | None":
    r"""`\bigl[` -> `[`, or None when it is not a sized delimiter of that side.

    Longest prefix first, so `\Biggl` is not read as `\Bigg` + `l`.
    """
    for prefix in sides:
        if latex.startswith(prefix):
            return latex[len(prefix):]
    return None


def _matrix_env(entry_size: float, row_size: float) -> str:
    r"""`smallmatrix` where the page set the matrix at SCRIPT size, else `array`.

    Board state 45 scored the array commit: p293 0.0791 -> 0.0668, rules
    invented 7 -> 2, flagged 30 -> 21 — but unpaired 3/22 -> 5/24, and the two
    new ones are THE SAME GLYPHS ON BOTH SIDES, a `2` and a `/` on the two
    matrix rows. A glyph unpaired on both sides is a pairing failure, not a
    loss: it is in the ink and in our rendering, at positions that do not
    match.

    MEASURED, all 12 arrays on p293: entries 7.57 against a row of 9.96 —
    ratio 0.760, every one. The page sets these matrices at script size and
    `array` sets them full size, so LaTeX positions `1/2` by its own metrics
    and those glyphs land off the ink.

    Same discriminator as `\tfrac` (`_is_text_style`): the entries' size
    against the row's full-size glyphs, same 0.85. `smallmatrix` is amsmath's,
    which the preamble loads — verified for `\tfrac`, and the second time that
    dependency paid for being checked rather than assumed.
    """
    if row_size <= 0:
        return "array"
    return "smallmatrix" if entry_size < _TFRAC_NUMERAL * row_size else "array"


def _merge_stacked_delimiters(glyphs: list[GlyphNode], depth: int):
    r"""A sized delimiter pair holding stacked rows is an ARRAY.

    `lib:c57ac038ae5f` p293 sets `t_0 = 3[1 / -1/2]` as `1` OVER `-1/2` inside
    one big bracket. Read in x order the two rows interleave to `−11/2`, which
    is what the reading carried, and the row then refused as a whole. MathPix
    writes `\left[\begin{array}{c} 1 \\ -1/2 \end{array}\right]`.

    `\left`/`\right` replaces the page's own `\big` size, because the array
    sets its own height and a fixed size would no longer fit it.

    ABSTAINS COMPLETELY rather than partly: if any row refuses, the whole run
    is left as it was, so the caller still sees the delimiters and the glyphs
    and can fall back. A half-built array would be `\begin{array}` with a
    missing row — valid LaTeX saying something else.
    """
    gs = sorted(glyphs, key=lambda g: g.rect[0])
    size = _row_size(gs)
    #: The row's own baseline, by the vote `split_terms` uses: only the
    #: full-size glyphs, because a script cannot outvote its base.
    _full = [x for x in gs if x.size >= 0.85 * size] or gs
    _votes: dict[float, int] = {}
    for x in _full:
        _votes[round(x.baseline, 1)] = _votes.get(round(x.baseline, 1), 0) + 1
    row_baseline = (max(_votes.items(), key=lambda kv: kv[1])[0]
                    if _votes else None)
    out: list[GlyphNode] = []
    i = 0
    while i < len(gs):
        g = gs[i]
        lat = (g.tex.latex or "") if g.tex else ""
        opener = _unsized(lat, _SIZED_LEFT) if (
            g.tex and g.tex.kind == "delimiter") else None
        if opener is None:
            out.append(g)
            i += 1
            continue
        #: THE MATCHING CLOSER, BY NESTING DEPTH — not the last one in the
        #: row. Taking the outermost `\bigr]` let the first `\bigl[` of
        #: p293's row swallow the three terms after it, because that row
        #: carries four bracketed terms in a line. Depth-matching is what
        #: makes a pair a pair.
        j = closer = None
        level = 0
        for k in range(i + 1, len(gs)):
            o = gs[k]
            if not (o.tex and o.tex.kind == "delimiter"):
                continue
            if _unsized((o.tex.latex or ""), _SIZED_LEFT) is not None:
                level += 1
                continue
            c = _unsized((o.tex.latex or ""), _SIZED_RIGHT)
            if c is None:
                continue
            if level:
                level -= 1
                continue
            j, closer = k, c
            break
        rows = (_stacked_rows(gs[i + 1:j], size, row_baseline)
                if j is not None else None)
        if not rows:
            out.append(g)
            i += 1
            continue
        parts = []
        for r in rows:
            one = to_tex(list(r), [], depth + 1)
            if one is None:
                parts = None
                break
            parts.append(one)
        if not parts:
            out.append(g)
            i += 1
            continue
        #: `smallmatrix` TAKES NO COLUMN SPECIFICATION, so the `{c}` that
        #: `array` needs must be dropped for it rather than carried over —
        #: passed on, it is typeset as the body's first characters.
        _env = _matrix_env(max(g.size for r in rows for g in r), size)
        _spec = "{c}" if _env == "array" else ""
        body = r"\left%s\begin{%s}%s%s\end{%s}\right%s" % (
            opener, _env, _spec, " \\\\ ".join(parts), _env, closer)
        inner = gs[i:j + 1]
        #: IT SITS ON THE ROW'S BASELINE, NOT THE BRACKET'S. A big delimiter
        #: is drawn raised — p293's `bracketleftbig` has baseline 106.9 in a
        #: row whose baseline is 98.9 — so an atom that inherited the
        #: bracket's baseline stood 8pt above its row at full size, which is
        #: neither a script nor a sibling, and `_attach_scripts` refused the
        #: whole row. The array behaves as one large symbol on the row's own
        #: baseline; its height is in the rect. Only the full-size glyphs
        #: OUTSIDE the delimiters vote, for the reason `split_terms` gives.
        _outside = [x for x in gs if x not in inner]
        _full = [x for x in _outside if x.size >= 0.85 * size] or _outside
        _votes: dict[float, int] = {}
        for x in _full:
            _votes[round(x.baseline, 1)] = _votes.get(round(x.baseline, 1), 0) + 1
        _base = (max(_votes.items(), key=lambda kv: kv[1])[0] if _votes
                 else g.baseline)
        out.append(GlyphNode(
            id=g.id, page=g.page,
            rect=(g.rect[0], min(x.rect[1] for x in inner),
                  gs[j].rect[2], max(x.rect[3] for x in inner)),
            text="", cid=-1, glyphname=None,
            fontname="<array>", family="math-extension", size=size,
            tex=TexToken(body, "atom",
                         "amsmath" if _env == "smallmatrix" else None,
                         "corpus"),
            matrix=(size, 0, 0, size, g.rect[0], _base),
            # 733 — the synthesised atom keeps the EARLIEST stream index of
            # the glyphs it replaces, as a fraction's does.
            stream=min((x.stream for x in inner if x.stream >= 0), default=-1),
        ))
        i = j + 1
    return out


def _stacked_rows(glyphs, size: float, row_baseline: float | None = None):
    r"""The rows of a stacked construct, TOP FIRST, or None if it is one row.

    A higher baseline is a higher row: the y axis grows upward here, which the
    fraction pass already relies on — `\alpha_0 = \frac{1}{2}` comes from `1`
    at baseline 105.9 over `2` at 91.8.

    TWO TESTS, BECAUSE A SCRIPT ALSO MAKES A SECOND BASELINE. `[x^2]` is one
    row and `[1 / -1/2]` is two, and what separates them is not the baseline
    gap:

      * a stacked entry shares its sibling's COLUMN — the x-ranges overlap, as
        a fraction's numerator and denominator overlap their bar;
      * a stacked entry is the same SIZE as its sibling, where a script is
        smaller than its base.

    Both are required. Without the first, every parenthesised power becomes a
    one-column array; without the second, a raised limit beside a full-size
    operand does.
    """
    if not glyphs or size <= 0:
        return None
    bands: list[list[GlyphNode]] = []
    for g in sorted(glyphs, key=lambda g: -g.baseline):
        if bands and abs(bands[-1][0].baseline - g.baseline) <= _ROW_GAP_EM * size:
            bands[-1].append(g)
        else:
            bands.append([g])
    if len(bands) < 2:
        return None
    #: AND NOTHING MAY SIT ON THE ROW'S OWN BASELINE. This is the test that
    #: separates a column vector from an ordinary parenthesised expression,
    #: and it was missing: `\biggl(-\epsilon e_i^T r(y)) + \frac{1}{2}
    #: \epsilon^2 e_i^T Ae_i\biggr)` on p293 line 8 also puts glyphs on two
    #: bands of similar size in overlapping columns, so it was read as a
    #: 2-row array and a line that had assembled CORRECTLY —
    #: `\lim\limits_{\epsilon\rightarrow0} \frac{1}{\epsilon} ...` —
    #: flattened instead. Measured as 4 lost `\epsilon` on the board.
    #:
    #: A stacked entry is NOT on the row's baseline: `3[1 / -1/2]` has its
    #: two entries at 96.3 and 102.9 inside a row at 98.9, and nothing at
    #: 98.9 between the brackets. An ordinary bracketed expression has its
    #: body ON the baseline, with scripts and fractions around it.
    if row_baseline is not None:
        for b in bands:
            if abs(b[0].baseline - row_baseline) <= _ON_BASELINE_EM * size:
                return None
    for a, b in zip(bands, bands[1:]):
        ax0, ax1 = min(g.rect[0] for g in a), max(g.rect[2] for g in a)
        bx0, bx1 = min(g.rect[0] for g in b), max(g.rect[2] for g in b)
        over = min(ax1, bx1) - max(ax0, bx0)
        if over < _ROW_OVERLAP * min(ax1 - ax0, bx1 - bx0):
            return None                   # side by side: a script, not a row
        sa, sb = max(g.size for g in a), max(g.size for g in b)
        if min(sa, sb) < _ROW_SIZE_RATIO * max(sa, sb):
            return None                   # one is smaller: a script
    return [sorted(b, key=lambda g: g.rect[0]) for b in bands]


def split_terms(glyphs: list[GlyphNode],
                rules: list[RuleNode] | None = None) -> list[list[GlyphNode]]:
    r"""A display row's independent terms, left to right.

    `lib:c57ac038ae5f` p293 sets four on one row —

        t_0 = 3[1 / -1/2],  \alpha_0 = 1/2,  x_1 = -4^{-1}[1/2],  r_1 = ...

    — and `to_tex` REFUSES the row while assembling the `\alpha_0` term alone
    correctly (`\alpha_{0} = \frac{1}{2} ,`). Measured over rows 27 and 28 of
    that page: 1 of 8 terms assembles on its own, and the single whole-row
    refusal then flattens all eight to glyph text in x order, losing `t_0`'s
    subscript, `\alpha_0`'s fraction and `-4^{-1}`'s exponent together.

    A BOUNDARY IS A SEPARATOR ON THE ROW'S OWN BASELINE, OUTSIDE EVERY RULE.
    Both halves of that are load-bearing, and each is a way to cut an
    expression in half rather than between two expressions:

      * `A_{i,j}` — the comma is a subscript. It sits off the dominant
        baseline, so the baseline test rejects it.
      * a vector `[1, 2]` over a fraction bar, or `\frac{a,b}{c}` — the comma
        lies within the x-span of the rule that binds it, so the rule test
        rejects it.

    The dominant baseline is the most common one in the row, which is what
    carries the terms; scripts and a fraction's operands are the minority by
    construction.
    """
    if not glyphs:
        return []
    gs = sorted(glyphs, key=lambda g: g.rect[0])
    size = _row_size(gs) or 1.0
    #: ONLY THE FULL-SIZE GLYPHS VOTE on where the row's baseline is. Counting
    #: every glyph let a subscript outvote its own base: `A_{i,j}` is one `A`
    #: at the baseline against `i , j` raised above it, so the majority
    #: baseline was the SUBSCRIPT's and the comma between two subscripts
    #: became a term boundary, cutting `A_{i,j}` in half. A script is smaller
    #: than its base by construction, so size settles it and a count cannot.
    body = [g for g in gs if g.size >= 0.85 * size] or gs
    counts: dict[float, int] = {}
    for g in body:
        counts[round(g.baseline, 1)] = counts.get(round(g.baseline, 1), 0) + 1
    dom = max(counts.items(), key=lambda kv: (kv[1], -abs(kv[0])))[0]
    spans = [(r.rect[0], r.rect[2]) for r in (rules or [])
             if r.role in ("fraction", "radical", "overline", "underline")]
    out: list[list[GlyphNode]] = []
    cur: list[GlyphNode] = []
    for g in gs:
        cur.append(g)
        if (g.text or "") not in _TERM_SEPARATORS:
            continue
        if abs(g.baseline - dom) > _TERM_BASELINE_EM * size:
            continue                      # a script's comma, not a separator
        mid = 0.5 * (g.rect[0] + g.rect[2])
        if any(x0 - 1 <= mid <= x1 + 1 for x0, x1 in spans):
            continue                      # bound by a rule: not top level
        out.append(cur)
        cur = []
    if cur:
        out.append(cur)
    return out


def _row_size(glyphs: list[GlyphNode]) -> float:
    return max(g.size for g in glyphs) if glyphs else 0.0


def _split_fractions(glyphs: list[GlyphNode], rules: list[RuleNode]):
    """Partition a span into fraction groups and the glyphs between them.

    A fraction's extent is its RULE's x-range: that is what the typesetter
    drew, so it needs no inference. Glyphs inside that range go above or below
    by baseline; glyphs outside stay at this level.
    """
    fracs: list[Frac] = []
    consumed: set[int] = set()
    for r in sorted(rules, key=lambda r: r.rect[0]):
        if r.role not in ("fraction",):
            continue
        x0, x1 = r.rect[0], r.rect[2]
        mid = 0.5 * (r.rect[1] + r.rect[3])
        num, den = [], []
        for i, g in enumerate(glyphs):
            if i in consumed:
                continue
            cx = 0.5 * (g.rect[0] + g.rect[2])
            if cx < x0 - 1 or cx > x1 + 1:
                continue
            (num if g.baseline > mid else den).append(i)
        if not num or not den:
            continue                     # not a fraction after all; abstain
        consumed |= set(num) | set(den)
        fracs.append(Frac(r, [glyphs[i] for i in num], [glyphs[i] for i in den]))
    rest = [g for i, g in enumerate(glyphs) if i not in consumed]
    return fracs, rest


def _weave_underscores(triples, unders, depth: int) -> str | None:
    r"""Emit the row with its underscore rules back in x-order.

    AN UNDERSCORE INSIDE A SCRIPT GOES INSIDE THE SCRIPT. This wove every
    underscore at ROW level, sorted by x against the x of each term's BASE --
    but a script's glyphs are consumed into `^{...}`, so an underscore sitting
    among them always sorts after the whole term and is emitted behind it:

        gold   y_{t}^{imp\_tot}          y_{t,est}^{gb\_imp}
        got    y_{t}^{imp tot}\_         y_{t,est}^{gb exp}\_

    which is not a near miss. The identifier `imp_tot` became `imp tot`, two
    tokens, and a stray `\_` landed outside the group -- so the name is wrong
    AND the underscore is attached to whatever follows. Measured on the two
    documents in this corpus whose variable names carry underscores,
    wzlxjtu-067 and wzlxjtu-068, every one of them was misplaced this way.

    An underscore whose centre lies within a script group's x-span is handed
    to that group's own `to_tex`, which welds it in by this same function one
    level down. Only the ones left over are woven at row level.
    """
    def _inside(gs):
        """The underscore rules whose centre falls within these glyphs."""
        if not gs:
            return []
        x0 = min(g.rect[0] for g in gs)
        x1 = max(g.rect[2] for g in gs)
        return [r for r in unders
                if x0 - 1 <= 0.5 * (r.rect[0] + r.rect[2]) <= x1 + 1]

    taken: set[int] = set()
    items: list[tuple[float, str]] = []
    for base, sup, sub in triples:
        if base is None:
            continue
        lit = glyph_latex(base)
        if lit is None:
            return None
        part = lit
        if sub:
            mine = _inside(sub)
            s = to_tex(sub, list(mine), depth + 1)
            if s is None:
                return None
            taken.update(id(r) for r in mine)
            part += f"_{{{s}}}"
        if sup:
            mine = _inside(sup)
            s = to_tex(sup, list(mine), depth + 1)
            if s is None:
                return None
            taken.update(id(r) for r in mine)
            part += f"^{{{s}}}"
        items.append((base.rect[0], part))
    for r in unders:
        if id(r) in taken:
            continue
        items.append((r.rect[0], r"\_"))
    items.sort(key=lambda t: t[0])
    # The SECOND join site, and it had no guard either. `P` `\cdot` `y` came
    # out as `P\cdoty`: the pieces loop below guards its own joins, but a row
    # carrying scripts or underscores is assembled HERE instead, so the same
    # hazard reappeared in a path the first fix never touched.
    parts: list[str] = []
    for _, piece in items:
        if parts and piece[:1].isalpha() and _ends_in_command(parts[-1]):
            parts.append(" ")
        parts.append(piece)
    return "".join(parts)


def _level(g: GlyphNode) -> float:
    r"""The height a script is judged against: the base's baseline, except
    for an operator that HANGS from its reference point.

    A display `\sum` from CMEX is drawn below the point TeX places it at:
    on lib:1a36bfe66b9c p154 its ink runs 549.0-563.0 with the reference at
    563.0, the TOP. Limits far above or below come out right against either
    height; a mark between the axis and the top does not. That page's
    `\sum'_{n \equiv d(v)}` has its prime at 561.5, which against 563.0 is
    "below", joined the subscript, and the display was refused (3 of the
    board's early refusals, B2c). Against the ink's middle, 556.0, it is the
    superscript MathPix reads.
    """
    # Only the DISPLAY size. A text-size `\sum` hangs the same way, but its
    # scripts are set beside it as an ordinary atom's are: 1805.01788 p3's
    # `\sum_m` (txexs `summationtext.1`, ink 478.8-486.7) has its `m` at
    # 483.9, above the ink's middle and a subscript all the same; measured,
    # the unrestricted rule turned 12 accepted `\sum_{m}` into `\sum^{m}`.
    k = g.ink
    if ("display" in (g.glyphname or "") and g.tex.kind == "bigop" and k is not None
            and abs(k[3] - g.baseline) <= 0.05 * g.size and k[1] < g.baseline):
        return 0.5 * (k[1] + k[3])
    return g.baseline


def _attach_scripts(glyphs: list[GlyphNode]):
    """Split a row into (main glyph, superscripts, subscripts) triples.

    Returns None when a script cannot be attributed — a script with no glyph
    to its left has no base, and guessing one would invent a relationship.
    """
    if not glyphs:
        return []
    size = _row_size(glyphs)
    # A big operator is RAISED above the text baseline by design, so that it
    # and its limits centre on the maths axis. Judged by baseline alone it is
    # a full-size glyph off the row, which this function refuses -- so every
    # inline `\sum_{J}` deferred. It counts as a main glyph whatever its
    # baseline, and its scripts are measured against ITS baseline.
    # A big DELIMITER is off the row baseline for the same reason a big
    # OPERATOR is: it is grown about the maths axis, not set on the line.
    # `\left( ... \right)` around a two-level expression puts its parens at
    # 12pt on a baseline 10pt above the row, and the guard below -- which
    # refuses a full-size glyph off the row -- then refused the whole span.
    #
    # Measured on the PDF2LaTeX dataset: `script-attachment` was 299 of 448
    # crops, the largest cause by a wide margin, and this is one of its
    # shapes.
    bigops = {i for i, g in enumerate(glyphs)
              if g.tex.kind in ("bigop", "delimiter")}
    main_idx = [i for i, g in enumerate(glyphs)
                if g.size >= SCRIPT_SIZE_RATIO * size or i in bigops]
    if not main_idx:
        # Every glyph is a script and there is no base -- a marker group that
        # follows a WORD, whose last letter belongs to the prose. LaTeX spells
        # that with an empty group: `${}^{a,*}$`. Attributing the word's last
        # letter to the maths instead broke the name and moved the marker:
        # `Montañ $\mathrm{o}^{\mathrm{a},*}$`.
        return [(None, list(glyphs), [])] if all(
            g.baseline >= glyphs[0].baseline - 0.01 for g in glyphs) else None
    # The row's baseline is the one MOST glyphs sit on, not the highest.
    # Taking the maximum lets a single full-size element that happens to sit
    # high -- a fraction, a raised full-size script -- redefine the row and
    # push every real base into a subscript.
    from collections import Counter
    # A BIG OPERATOR OR DELIMITER DOES NOT GET A VOTE. It is grown about the
    # maths axis, not set on the line -- this file says so two comments up --
    # so its baseline is off the row BY DESIGN and is no evidence of where
    # the row is. On a short row it can outvote the row itself.
    #
    # wzlxjtu-101's third display is `w_i = \left\{ \begin{array}{rcl} v_c,
    # && b_i = 1 \\ 0, && b_i = 0 \end{array} \right.`, whose brace is
    # centred between the two array rows. One span of it holds exactly two
    # glyphs:
    #
    #     braceleftbigg  base=484.31      one  base=476.04
    #
    # -- one vote each, and the brace won the tie on insertion order. The
    # row's baseline became the brace's, `1` was 8.27pt off it, and a
    # full-size glyph off the row is a refusal: the whole band deferred as
    # `script-attachment`, taking `v_c, b_i = 1` -- the first case of the
    # construct -- out of the document.
    voters = [i for i in main_idx if i not in bigops] or main_idx
    votes = Counter(round(glyphs[i].baseline / max(LEVEL_TOL * size, 0.01))
                    for i in voters)
    top = votes.most_common(1)[0][0]
    base_line = top * max(LEVEL_TOL * size, 0.01)
    # a full-size glyph that is nonetheless shifted is still a script
    main_idx = [i for i in main_idx
                if i in bigops
                or abs(glyphs[i].baseline - base_line) <= LEVEL_TOL * size]
    if not main_idx:
        return None

    # BINDING BY EMISSION ORDER WAS TRIED HERE AND REVERTED.
    #
    # 725 and 726 both concluded that `_attach_scripts` binding by x rather
    # than by stream was what blocked `_merge_stream_lines`; 696 had reached
    # the same conclusion from the other direction. Implemented -- a script
    # attaches to the main glyph most recently emitted before it, falling
    # back to x where any glyph lacks a stream index -- and measured:
    #
    #     merge OFF   blocks 817 -> 801   crops 548 -> 588   proj 86.4 -> 85.4
    #     merge ON    blocks  95          crops 1349         proj 60.9
    #
    # The merge still collapsed. The stream path WAS being taken (every
    # glyph on those pages carries an index) and it still refused, so the
    # binding rule was never the blocker.
    #
    # Instrumented, 17 of 18 refusals on 91.pdf are the "same baseline but
    # excluded" case below, not the off-baseline guard: a merged display
    # line contains whole sub-expressions set at script size on their OWN
    # baselines -- a fraction's numerator and denominator -- and this pass
    # models one baseline with scripts around it. That is a different pass,
    # not a different binding rule.
    #
    # The plan in 725/726 is falsified. Recorded here rather than in a note
    # alone, because the next person to read those notes will otherwise
    # implement it again.

    # 733 — BINDING BY STREAM INSIDE THIS PASS WAS TRIED AGAIN, AND AGAIN
    # IT IS NOT THE FIX. Recorded with numbers so it is not attempted a
    # fourth time.
    #
    # The stream genuinely carries the box structure -- measured on
    # wzlxjtu-010, `\sigma'=2\eta\sqrt{N_0^2+N_3^2}`:
    #
    #   by x       sigma prime equal two eta radicalBig N zero two plus N three two
    #   by stream  radicalBig sigma prime equal two eta N two zero plus N two three
    #
    # `N two zero` is base, superscript, subscript in TeX's own order, while
    # by x the two scripts are 1.2pt apart and stacked. It looks decisive.
    # It is not, because THIS PASS NEVER HAD TO ORDER THEM: it takes every
    # glyph between one main glyph and the next and sorts them into sup and
    # sub by BASELINE, so their order among themselves never mattered.
    #
    # Implemented as attach-by-stream / order-by-x, whole corpus:
    #
    #     attachment by x       whole 34   crops 452   flat exact 18
    #     attachment by stream  whole 28   crops 481   flat exact 13
    #
    # It loses, because the most recent main glyph IN THE STREAM is not
    # always the base: a producer ships an extensible glyph ahead of the run
    # it covers (`radicalBig` first, at x=286.3, before the `sigma` at 248.7
    # that starts the expression), and a script following it in the stream
    # then binds to the wrong thing.
    #
    # Where the stream DOES decide is one step earlier, in which glyphs form
    # a row at all -- see the band merge in docmodel_six. Same corpus, same
    # day: whole 34 -> 38. The evidence was always about grouping, never
    # about binding, and that is the distinction three notes have missed.

    # 740 — CLAIMING A LIMIT THAT OVERHANGS ITS OPERATOR WAS TRIED AND
    # LOSES. Recorded with the numbers, because it is correct in isolation.
    #
    # Scripts are claimed from the x-range AFTER a main glyph, which is right
    # for `x^2` and wrong for a stacked limit: TeX centres the condition under
    # the operator, so a condition wider than the operator begins to its LEFT.
    # `\sup_{C^\beta(F_0)}` on wzlxjtu-070 sets `C` at [204.4,210.4] against a
    # `\sup` at [209.4,227.0] and came out
    #
    #     {}_{C}\!\sup_{{}^{\beta}(F_{0})}
    #
    # -- the `C` an orphan with an empty base. Claiming script-size glyphs
    # that overlap the operator horizontally fixes that line exactly, to
    # `\sup_{C^{\beta}(F_{0})}`. Whole corpus, against the same build:
    #
    #     without   whole 47   crops 418   dialect-correct 69
    #     with      whole 46   crops 422   dialect-correct 67
    #     below the baseline only   whole 46   crops 422   correct 68
    #
    # It takes scripts that belong to the preceding term more often than it
    # rescues a limit, and restricting it to the lower limit recovers only
    # half the loss. The shape is real and the rule is not sharp enough to
    # separate it from an ordinary neighbouring script; that needs to come
    # from somewhere other than x-overlap.

    # 741 — A LIMIT IS CENTRED ON ITS OPERATOR, SO IT BEGINS TO ITS LEFT.
    #
    # Scripts are claimed from the x-range AFTER a main glyph, which is right
    # for `x^2` and for `\log_2`, and wrong for every operator that takes
    # LIMITS: TeX centres those below the word, so a condition wider than the
    # word starts left of it. `\sup_{C^\beta(F_0)}` on wzlxjtu-070 sets `C` at
    # [204.4,210.4] against a `\sup` at [209.4,227.0], and the `C` became an
    # orphan with an empty base: `{}_{C}\!\sup_{{}^{\beta}(F_{0})}`.
    #
    # 740 tried this for every `bigop` and LOST -- whole 47 -> 46, crops 418
    # -> 422 -- because `bigop` also covers `\sin`, `\log`, `\tanh`, whose
    # scripts sit BESIDE them, so claiming backwards stole the preceding
    # term's scripts. The distinction is not geometric and cannot be
    # recovered from the page: both are upright roman letter runs. It is a
    # property of the operator, and LaTeX states it: `texmap.takes_limits`
    # answers from a table taken out of `amsopn.sty`, where every name is
    # declared `\qopname\relax m{...}` (movable limits) or `o{...}`. Nothing
    # here is inferred from the page.
    # WHICH operator a left-overhanging limit belongs to is decided by the
    # STREAM, not by x. Two limit operators in one row make x useless:
    # wzlxjtu-072 sets `\max \biggl( \sup_{t \leq -\eta_{\beta,j}} ...` as
    #
    #     s649  m (\max)   x=[135.0,155.3]
    #     s652  s (\sup)   x=[170.7,187.1]
    #     s655  t          x=[163.3,166.4]      the condition
    #     s656  lessequal  x=[166.4,173.0]
    #
    # -- the condition BEGINS to the left of the `\sup` it belongs to, and so
    # falls inside `\max`'s reach; by x alone it went to `\max`. TeX emitted
    # it after the `\sup`, which is the statement of what it belongs to, and
    # the nearest limit operator preceding it in the stream is the owner.
    # DECIDING THE OWNER BY STREAM WAS TRIED AND LOSES, with the numbers here
    # because the case for it is strong and it is correct on the row it was
    # built for.
    #
    # Two limit operators in one row make x useless. wzlxjtu-072 sets
    # `\max \biggl( \sup_{t \leq -\eta_{\beta,j}} ...`:
    #
    #     s649  m (\max)   x=[135.0,155.3]
    #     s652  s (\sup)   x=[170.7,187.1]
    #     s655  t          x=[163.3,166.4]     the condition
    #
    # The condition BEGINS left of the `\sup` it belongs to and inside
    # `\max`'s reach, so by x it goes to `\max`. TeX emitted it after the
    # `\sup`, and "the nearest limit operator preceding it in the stream"
    # names the right one. Implemented -- both as the sole test and paired
    # with a widened x window -- it fixes that display exactly, to
    # `\max \sup_{t\leq-\eta_{\beta,j}} \{...\}^{+} ; \sup_{...}`, and over
    # the corpus:
    #
    #     x only              whole 50   stacked exact 12   correct 72
    #     stream names owner  whole 48   stacked exact 10   correct 70
    #
    # The stream names an owner for every script in the row, including ones
    # no operator should claim, and the rule has no way to decline. What it
    # needs is a notion of where a limit group ENDS, which emission order
    # does not carry either. Not the binding rule -- the extent.
    limit_ops = [i for i in main_idx
                 if i in bigops and texmap.may_take_limits(
                     glyphs[i].tex.latex, glyphs[i].glyphname)]

    # 760 -- AND THE STREAM DOES DECIDE WHOSE, NOW THAT IT IS THE STREAM.
    #
    # The note above records stream ownership as tried and beaten (whole
    # 50 -> 48). That experiment ran against an index built from
    # `extract_pages`, which REORDERS at the BT/ET boundary -- 746 measured
    # it and moved the index to `render_char`. The rule was judged on a
    # stream that was not the stream.
    #
    # What x cannot do, on wzlxjtu-031's first display:
    #
    #     stream 179  infinity  x=156.54  base=730.34   upper of sum1
    #     stream 180  SUM 1     x=153.32  base=727.35
    #     stream 181  s   182 =   183 1                 lower of sum1
    #     stream 184  SUM 2     x=173.07
    #     stream 185..189  | m | < s                    lower of sum2
    #
    # sum1's `s=1` ends at x=168 and sum2's `|m|<s` begins at x=169.4 -- 1.4pt
    # apart, well inside the 0.3 em contiguity that holds a condition
    # together. So the backward walk from sum2 ran through sum2's own limit,
    # through sum1's, and took the `\infty` too:
    #
    #     C = \sum \sum\limits_{s=1 \mid m\mid<s}^{\infty} C_m^s V_m^s
    #
    # one bare operator and one carrying everything. TeX's vbox order for a
    # display operator is UPPER, OPERATOR, LOWER, so the stream says which
    # operator emitted each limit and the baseline says which side it is on.
    # This is ownership only -- the x window and the contiguity run still
    # decide WHETHER a glyph is a limit at all.
    _has_stream = all(getattr(g, "stream", -1) >= 0 for g in glyphs)
    _op_by_stream = sorted(((glyphs[i].stream, i) for i in limit_ops)) \
        if _has_stream else []

    def _stream_owner(j: int):
        """The limit operator that emitted glyph j, or None if unknown."""
        if not _op_by_stream:
            return None
        s = glyphs[j].stream
        before = [i for st, i in _op_by_stream if st < s]
        after = [i for st, i in _op_by_stream if st > s]
        if before and glyphs[j].baseline < glyphs[before[-1]].baseline:
            return before[-1]            # below the operator: a lower limit
        if after and glyphs[j].baseline > glyphs[after[0]].baseline:
            return after[0]              # above it: an upper limit
        return before[-1] if before else (after[0] if after else None)

    claimed: dict[int, list] = {}
    for i in limit_ops:
        ox0, ox1 = glyphs[i].rect[0], glyphs[i].rect[2]
        for j in range(i - 1, -1, -1):
            if j in main_idx:
                break
            g = glyphs[j]
            if g.size >= SCRIPT_SIZE_RATIO * size:
                break
            # BOTH, not either. The stream names the owner -- which operator
            # the condition was emitted after -- and that is what x cannot
            # do when two limit operators share a row: wzlxjtu-072 sets
            # `\max \biggl( \sup_{t \leq -\eta_{\beta,j}}` with the condition
            # beginning at 163.3, left of its own `\sup` at 170.7 and inside
            # `\max`'s reach at 135.0. But the stream alone is too generous:
            # it names an owner for a glyph anywhere in the row, and trusting
            # it without a distance cost 2 whole equations and 2 stacked ones.
            # So the stream decides WHOSE, and x still decides WHETHER -- with
            # a wider window once the stream has agreed, since `t` falls 1.6pt
            # short of overlapping the operator it demonstrably belongs to.
            # 0.25 em of reach, and no more. wzlxjtu-011's fifth display is
            # `\lim_{\phi^0_0 \rightarrow -\infty} f(\phi^0_0)`, whose `\phi`
            # is the leftmost glyph of a condition wider than the `\lim` and
            # falls outside this window -- it is emitted as the orphan
            # `{}_{\phi}` while the rest of the condition is claimed. Widening
            # the window to reach it was measured at 1.0 and 2.0 em: both cost
            # a whole equation and a stacked one (53 -> 52) elsewhere. The
            # fix for that row is not a bigger window.
            # EXTENT BY CONTIGUITY once the run has started. The window is
            # how a condition is RECOGNISED; it is not how far one reaches.
            # TeX sets the condition as one horizontal list, so its glyphs
            # abut: wzlxjtu-011's `\lim_{\phi^0_0 \rightarrow -\infty}` has
            # its `\phi` at [175.1,180.1] against a window opening at 180.3 --
            # 0.2pt short -- and touching the `0` already claimed at 180.1.
            # Widening the window instead was measured at 1.0 and 2.0 em and
            # cost a whole equation each time; adjacency to what is already
            # claimed costs nothing, because it cannot wander.
            owner = _stream_owner(j)
            if owner is not None and owner != i:
                break                    # emitted by a different operator
            run = claimed.get(i)
            if run:
                nearest = glyphs[run[0]].rect[0]
                if g.rect[2] < nearest - 0.3 * size:
                    break
            elif not (g.rect[2] > ox0 - 0.25 * size and g.rect[0] < ox1):
                break
            claimed.setdefault(i, []).insert(0, j)

    stolen = {j for js in claimed.values() for j in js}
    out = []
    for pos, i in enumerate(main_idx):
        nxt = main_idx[pos + 1] if pos + 1 < len(main_idx) else len(glyphs)
        sup, sub = [], []
        for j in claimed.get(i, []):
            g = glyphs[j]
            (sup if g.baseline > _level(glyphs[i]) + LEVEL_TOL * size
             else sub).append(g)
        last_at = None                   # the list the previous script joined
        last_sz = None
        for j in range(i + 1, nxt):
            if j in stolen:
                continue
            g = glyphs[j]
            # Only a SMALLER glyph may be a script. A full-size glyph sitting
            # off the row baseline is structure this pass does not model --
            # a fraction whose numerator escaped its rule's x-range, a stacked
            # limit, a matrix row. Calling it a script produced `+^{( -}` from
            # `+\frac{(-1)^{s}}{2}`: confident, valid, wrong.
            if g.size >= SCRIPT_SIZE_RATIO * size and j not in bigops:
                return None
            # T-0159 — A BIG DELIMITER'S SCRIPT BELONGS TO THE ROW, NOT TO
            # THE DELIMITER, and that is the one place this reference is not
            # the base's own baseline.
            #
            # This file says two comments above that a big delimiter "is off
            # the row baseline for the same reason a big OPERATOR is: it is
            # grown about the maths axis, not set on the line". For an
            # OPERATOR that makes its own baseline the right reference —
            # `\sum_j^n` centres its limits on its axis, so a limit below
            # that axis is a subscript however it sits against the row. A
            # DELIMITER has no limits: the exponent of `\right)` is an
            # ordinary script of the bracketed group and sits on the ROW's
            # levels.
            #
            # MEASURED on arxiv.1710.04811 page 37, line p37l23, and checked
            # against the author with the frozen labeller (drillgroup
            # eq_calibrate.py at 1ae04df):
            #
            #     parenrightbig   baseline 372.50   +9.70 from the row
            #     the `2` after   baseline 369.82   +7.02 from the row
            #
            #     against the delimiter   -2.68  -> subscript   (wrong)
            #     against the row         +7.02  -> superscript (the author's)
            #
            # The author wrote `\left(S_R^2\right)^2`; we wrote
            # `\bigl(S_{R}^{2} \bigr)_{2}`, on two objects of that page, and
            # the judge scored BOTH 0.0000 — sub and super are not identical
            # ink, so that zero is the T-0158 judge defect, not a pass.
            #
            # The inner exponents of the same line, +4.95 over an `S` at
            # +0.02, were never affected: only a script after a RAISED
            # delimiter is.
            _ref = (base_line if glyphs[i].tex.kind == "delimiter"
                    else _level(glyphs[i]))
            if g.baseline > _ref + LEVEL_TOL * size:
                sup.append(g); last_at, last_sz = sup, g.size
            elif g.baseline < _ref - LEVEL_TOL * size:
                sub.append(g); last_at, last_sz = sub, g.size
            elif abs(g.baseline - _ref) >= 0.05 * size:
                # A SMALLER GLYPH THAT IS DISPLACED AT ALL is a script, and
                # which one is the SIGN of the displacement.
                #
                # `LEVEL_TOL * size` is how far a FULL-SIZE glyph may stray
                # and still be on the row. Applied to a script it is simply
                # too big: wzlxjtu-033 sets `\phi_{\bar z \ldots \bar z}` with
                # the subscript 1.5pt below a row baseline of 742.63, against
                # a tolerance of 2.49 -- so a plain subscript fell in the gap
                # and refused the display. Everything reaching here is already
                # script-size, having survived the full-size test above; the
                # only question left is up or down, and the page answers it.
                (sup if g.baseline > _ref else sub).append(g)
                last_at = sup if g.baseline > _ref else sub
                last_sz = g.size
            elif last_at is not None and last_sz and g.size < last_sz - 0.5:
                # A SECOND-LEVEL SCRIPT sits near the ROW's baseline.
                #
                # `\partial_{\phi^0}` lowers the `\phi` to 8pt and then raises
                # its `0` to 6pt -- and the raise cancels the lower, so the
                # `0` lands at 528.07 against a row baseline of 527.81. By
                # level it is neither above the row nor below it, and this
                # refused the whole display as "same baseline but excluded".
                #
                # Its SIZE says what it is. TeX shrinks at every script level
                # (12 -> 8 -> 6), so a glyph smaller than the script before it
                # belongs to that script, not to the row, and the recursion
                # into `to_tex` places it correctly one level down.
                last_at.append(g); last_sz = g.size
            else:
                return None              # same baseline but excluded: unclear
        out.append((glyphs[i], sup, sub))

    # 735 — A LEADING SCRIPT IS NOT A REASON TO DROP THE ROW.
    #
    # This refused whenever the leftmost glyph was a script, and it was the
    # largest single cause of deferral after the band merge: 4,573 of them
    # across the 102 documents, each one taking a whole display with it.
    #
    # The row is not unreadable. LaTeX has a spelling for a script with no
    # base -- `{}^{x}` -- and this pass ALREADY emits it, three branches up,
    # for a marker group whose base belongs to the prose. What was missing is
    # that a row can begin that way and still be a row: `(\phi^0)'` whose
    # prime was carried in from another band, a continuation whose base sits
    # on the line above.
    #
    # Emitting `{}` is not a guess. It says exactly what is true -- these
    # scripts have no base HERE -- which is the distinction this file keeps:
    # a wrong `\frac` is worse than a crop, and an honest `{}` is neither.
    if main_idx and main_idx[0] != 0:
        lead_sup, lead_sub = [], []
        for _j, g in enumerate(glyphs[:main_idx[0]]):
            if _j in stolen:
                continue
            if g.size >= SCRIPT_SIZE_RATIO * size:
                return None              # a full-size leading glyph is structure
            if g.baseline > base_line + LEVEL_TOL * size:
                lead_sup.append(g)
            elif g.baseline < base_line - LEVEL_TOL * size:
                lead_sub.append(g)
            else:
                return None
        # Every leading script may have been claimed by a big operator to its
        # right, in which case there is no leading group left to emit -- and
        # an empty one crashes the caller on `(sup or sub)[0]`.
        if lead_sup or lead_sub:
            return [(None, lead_sup, lead_sub)] + out
        return out
    return out


# Computer Modern builds `\mapsto` from TWO glyphs: the bar (`mapsto`) and an
# arrow (`arrowright`). Projected separately they read `\mapsto \rightarrow`,
# which is one arrow too many.
_TWO_GLYPH = {("mapsto", "arrowright"): r"\mapsto",
              ("mapsto", "arrowdblright"): r"\Mapsto"}

# `negationslash` is a ZERO-WIDTH overlay: TeX draws it across the relation it
# negates, so the pair is one symbol. Its box says nothing about which side the
# relation is on -- measured, it appears immediately before an `equal` in some
# places and immediately after one in others -- so both orders are accepted and
# the neighbour it TOUCHES is the one it belongs to.
_NEGATED = {
    "equal": r"\neq", "element": r"\notin", "similar": r"\nsim",
    "equivalence": r"\not\equiv", "propersubset": r"\not\subset",
    "propersuperset": r"\not\supset", "reflexsubset": r"\nsubseteq",
    "lessequal": r"\nleq", "greaterequal": r"\ngeq",
    "bar": r"\nmid", "arrowright": r"\nrightarrow",
}


def _merge_negations(glyphs: list[GlyphNode]) -> list[GlyphNode]:
    """Fuse a negation slash with the relation it strikes through.

    Decided in one pass and built in a second. Building as it went emitted the
    relation twice whenever the slash's partner was the PRECEDING glyph: that
    glyph had already been appended, giving `= \\neq`.
    """
    replace: dict[int, str] = {}
    drop: set[int] = set()
    for i, g in enumerate(glyphs):
        if g.tex.kind != "overlay" or i in drop:
            continue
        for j in (i + 1, i - 1):        # `\not` precedes, so look right first
            if not 0 <= j < len(glyphs) or j in drop or j in replace:
                continue
            n = glyphs[j]
            latex = _NEGATED.get(n.glyphname or "")
            if not latex:
                continue
            gap = max(g.rect[0], n.rect[0]) - min(g.rect[2], n.rect[2])
            if gap <= 0.35 * max(g.size, n.size):
                replace[j] = latex
                drop.add(i)
                break

    out: list[GlyphNode] = []
    for i, g in enumerate(glyphs):
        if i in drop:
            continue                     # the slash itself is consumed
        if i in replace:
            out.append(GlyphNode(
                id=g.id, page=g.page, rect=g.rect, text=g.text, cid=-1,
                glyphname=g.glyphname, fontname=g.fontname, family=g.family,
                size=g.size, tex=TexToken(replace[i], "atom", None, "corpus"),
                matrix=g.matrix, upright=g.upright, stream=g.stream))
            continue
        out.append(g)
    return out


def _merge_mapsto(glyphs: list[GlyphNode]) -> list[GlyphNode]:
    """Collapse the glyph PAIRS that TeX uses to build one symbol."""
    out: list[GlyphNode] = []
    i = 0
    while i < len(glyphs):
        if i + 1 < len(glyphs):
            key = (glyphs[i].glyphname, glyphs[i + 1].glyphname)
            latex = _TWO_GLYPH.get(key)
            if latex and (glyphs[i + 1].rect[0] - glyphs[i].rect[2]
                          < 0.6 * glyphs[i].size):
                a, b = glyphs[i], glyphs[i + 1]
                out.append(GlyphNode(
                    id=a.id, page=a.page,
                    rect=(a.rect[0], min(a.rect[1], b.rect[1]),
                          b.rect[2], max(a.rect[3], b.rect[3])),
                    text=a.text + b.text, cid=-1, glyphname=key[0],
                    fontname=a.fontname, family=a.family, size=a.size,
                    tex=TexToken(latex, "atom", None, "corpus"),
                    matrix=a.matrix, upright=a.upright,
                    stream=min((x.stream for x in (a, b) if x.stream >= 0),
                               default=-1)))
                i += 2
                continue
        out.append(glyphs[i])
        i += 1
    return out


def _merge_accents(glyphs: list[GlyphNode],
                   depth: int = 0) -> list[GlyphNode]:
    """Wrap the glyphs an accent sits over.

    A wide accent is a SEPARATE glyph drawn above its base: `\\widehat{\\otimes}`
    is cmex10's `hatwide` over cmsy10's `circlemultiply`. Projected side by
    side it yields `\\widehat \\otimes`, which is not valid LaTeX -- `\\widehat`
    takes an argument -- and because the accent sits on its own raised
    baseline the span defers instead.

    The base is whatever the accent SPANS horizontally. An accent may also
    carry zero advance width, in which case its box says nothing about extent,
    so the nearest glyph below it is taken instead.
    """
    accents = [i for i, g in enumerate(glyphs) if g.tex.kind == "accent"
               and g.tex.latex]
    if not accents:
        return glyphs

    consumed: set[int] = set()
    wrapped: dict[int, tuple[str, list[int]]] = {}
    for i in accents:
        a = glyphs[i]
        width = a.rect[2] - a.rect[0]
        under = []
        for j, g in enumerate(glyphs):
            if j == i or j in consumed or g.tex.kind == "accent":
                continue
            # A CMEX accent carries its raise INSIDE the glyph, so its origin
            # sits on the text baseline -- exactly level with the letter it
            # covers. Measured: `tildewide` and its `gamma` both at 675.7.
            # Requiring the base to be strictly lower found nothing, and every
            # `\widetilde{\gamma}` deferred. Only a base clearly ABOVE the
            # accent is excluded.
            if g.baseline > a.baseline + 0.3 * a.size:
                continue
            # 774 -- A SUBSCRIPT IS NOT UNDER THE ACCENT.
            #
            # The base is whatever the accent spans horizontally, tested by
            # CENTRE-IN-RANGE, and a subscript's centre falls in that range
            # too. Page 673 of Obertelli & Sagawa sets the beta-equilibrium
            # reaction `n + e^+ \rightleftharpoons p + \bar{\nu}_e`:
            #
            #     nu      [243.98, 248.90]  10.0pt   centre 246.44
            #     macron  [246.65, 249.96]  10.0pt   window [245.15, 251.46]
            #     e       [248.90, 252.00]   7.0pt   centre 250.45  <- swept in
            #
            # and it came out `\bar{\nu_{e}}` -- the bar drawn over the
            # subscript as well, which is a different symbol. MathPix reads
            # the same snippet `\bar{\nu}_e`, and the page agrees with
            # MathPix.
            #
            # TeX SCALES AN ACCENT TO ITS BASE, so a base is never materially
            # smaller than the accent over it; 7.0 against 10.0 is a script.
            # The baseline says the same thing -- the `e` sits 1.49pt low
            # where a base is exactly level (the CMEX note above) -- but the
            # size has the clearer margin, 0.70 against a 0.92 threshold, and
            # it is scale-free: an accent inside an exponent is set small
            # along with everything it covers.
            if g.size < SCRIPT_SIZE_RATIO * a.size:
                continue
            if width > 0.1 * a.size:
                cx = 0.5 * (g.rect[0] + g.rect[2])
                if a.rect[0] - 0.15 * a.size <= cx <= a.rect[2] + 0.15 * a.size:
                    under.append(j)
            else:
                # zero-width accent: it marks a position, not an extent
                if abs(g.rect[0] - a.rect[0]) <= 0.6 * a.size:
                    under.append(j)
                    break
        if not under:
            continue
        consumed.update(under)
        consumed.add(i)
        wrapped[min(under)] = (a.tex.latex, sorted(under))

    if not wrapped:
        return glyphs

    out: list[GlyphNode] = []
    for i, g in enumerate(glyphs):
        if i in wrapped:
            cmd, idxs = wrapped[i]
            # ordinary recursion: the accent itself is already consumed,
            # so this cannot re-enter on the same glyph
            inner = to_tex([glyphs[k] for k in idxs], [], depth + 1)
            if inner is None:
                return glyphs              # cannot build it: let the span defer
            base = glyphs[idxs[0]]
            rect = (min(glyphs[k].rect[0] for k in idxs),
                    min(glyphs[k].rect[1] for k in idxs),
                    max(glyphs[k].rect[2] for k in idxs),
                    max(glyphs[k].rect[3] for k in idxs))
            out.append(GlyphNode(
                id=base.id, page=base.page, rect=rect, text=base.text,
                cid=-1, glyphname=base.glyphname, fontname=base.fontname,
                family=base.family, size=base.size,
                tex=TexToken(rf"{cmd}{{{inner}}}", "atom", None, "corpus"),
                matrix=base.matrix, upright=base.upright,
                stream=min((glyphs[k].stream for k in idxs
                            if glyphs[k].stream >= 0), default=-1)))
            continue
        if i in consumed:
            continue
        out.append(g)
    return out


#: A small capital is set at about 0.7-0.85 of its word's capital, on the SAME
#: baseline. Measured on 0864 p4: 7.17 pt after an 8.97 pt capital, 0.80.
SMALL_CAPS_RATIO = (0.6, 0.9)


def _merge_small_caps(glyphs: list[GlyphNode]) -> list[GlyphNode]:
    r"""A capital followed by SMALLER capitals on its own baseline, in the same
    face, is one small-capital word: `\textsc{Opus}`. (B2; see the commit.)"""
    from pdfreader.project_mmd import _is_bold
    from pdfreader.texmap import is_italic

    def cap(g: GlyphNode) -> bool:
        return (g.family not in MATH_FAMILIES and not is_italic(g.fontname)
                and len(g.text) == 1 and g.text.isascii() and g.text.isupper())

    def face(g: GlyphNode) -> str:
        return (g.fontname or "").split("+")[-1]

    lo, hi = SMALL_CAPS_RATIO
    out: list[GlyphNode] = []
    i = 0
    while i < len(glyphs):
        g = glyphs[i]
        if not cap(g):
            out.append(g)
            i += 1
            continue
        run: list[GlyphNode] = []
        j = i + 1
        while j < len(glyphs):
            n = glyphs[j]
            last = run[-1] if run else g
            if (not cap(n) or face(n) != face(g)
                    or not (lo * g.size <= n.size <= hi * g.size)
                    or (run and abs(n.size - run[0].size) > 0.05 * run[0].size)
                    or abs(n.baseline - g.baseline) > 0.05 * g.size
                    or n.rect[0] - last.rect[2] > 0.28 * g.size):
                break
            run.append(n)
            j += 1
        if not run:
            out.append(g)
            i += 1
            continue
        word = g.text + "".join(x.text.lower() for x in run)
        body = rf"\textsc{{{word}}}"
        if _is_bold(g.fontname):
            body = rf"\textbf{{{body}}}"
        members = [g] + run
        rect = (g.rect[0], min(x.rect[1] for x in members),
                run[-1].rect[2], max(x.rect[3] for x in members))
        out.append(GlyphNode(
            id=g.id, page=g.page, rect=rect, text=g.text + "".join(x.text for x in run),
            cid=-1, glyphname=None, fontname=g.fontname, family=g.family,
            size=g.size, tex=TexToken(rf"\text{{{body}}}", "atom", "amsmath", "corpus"),
            matrix=g.matrix, upright=True,
            stream=min((x.stream for x in members if x.stream >= 0), default=-1)))
        i = j
        # ITS SCRIPT, IN THE PAGE'S TEXT FONT, IS TEXT. inkdrill-80 counted the
        # judge's findings for this word: OPUS matched the page exactly and the
        # +27 were exactly the subscripts `spc` and `mon`, which the print sets
        # in its TEXT face and `\mathrm{...}` sets in Computer Modern (a
        # `\usepackage{times}` reading leaves maths in CM). The run must follow
        # the word directly, be upright text letters smaller than its capital,
        # and sit off the word's baseline — the shape of a script and nothing
        # else; `_attach_scripts` still decides that it is one.
        k = i
        script: list[GlyphNode] = []
        while k < len(glyphs):
            n = glyphs[k]
            prev = script[-1] if script else run[-1]
            if (n.family not in ("text", "text-cm") or is_italic(n.fontname)
                    or len(n.text) != 1 or not n.text.isascii()
                    or not n.text.isalpha()
                    or n.size >= SCRIPT_SIZE_RATIO * g.size
                    or abs(n.baseline - g.baseline) < 0.05 * g.size
                    or (script and abs(n.baseline - script[0].baseline) > 0.05 * g.size)
                    or n.rect[0] - prev.rect[2] > 0.28 * g.size):
                break
            script.append(n)
            k += 1
        if script:
            txt = "".join(x.text for x in script)
            cmd = "textbf" if _is_bold(script[0].fontname) else "text"
            srect = (script[0].rect[0], min(x.rect[1] for x in script),
                     script[-1].rect[2], max(x.rect[3] for x in script))
            out.append(GlyphNode(
                id=script[0].id, page=script[0].page, rect=srect, text=txt,
                cid=-1, glyphname=None, fontname=script[0].fontname,
                family=script[0].family, size=script[0].size,
                tex=TexToken(rf"\{cmd}{{{txt}}}", "atom", "amsmath", "corpus"),
                matrix=script[0].matrix, upright=True,
                stream=min((x.stream for x in script if x.stream >= 0), default=-1)))
            i = k
    return out


def _merge_function_names(glyphs: list[GlyphNode]) -> list[GlyphNode]:
    r"""A spelled-out function name is one word in its own face.

    1805.01788 p3's equation (1) opens `unfairness(\rho^1, ..., \rho^m)`, the
    word set in the TEXT italic (LinLibertineTI) flush against its `(`. Read
    letter by letter it was ten maths variables, `unfairness`, with maths
    italic spacing between them. Four or more letters of one text face, with
    no gap between them, standing directly before a `(`, are one
    `\mathit{...}` (`\mathrm{...}` when upright): the face the page used.
    """
    from pdfreader.texmap import is_italic

    def letter(g: GlyphNode) -> bool:
        return (g.family in ("text", "text-cm") and len(g.text) == 1
                and g.text.isascii() and g.text.isalpha())

    out: list[GlyphNode] = []
    i = 0
    while i < len(glyphs):
        j = i
        while (j + 1 < len(glyphs) and letter(glyphs[i]) and letter(glyphs[j + 1])
               and glyphs[j + 1].fontname == glyphs[i].fontname
               and glyphs[j + 1].rect[0] - glyphs[j].rect[2]
               < 0.12 * glyphs[i].size):
            j += 1
        nxt = glyphs[j + 1] if j + 1 < len(glyphs) else None
        if (letter(glyphs[i]) and j - i + 1 >= 4 and nxt is not None
                and nxt.text == "("
                and nxt.rect[0] - glyphs[j].rect[2] < 0.12 * glyphs[i].size):
            run = glyphs[i:j + 1]
            word = "".join(g.text for g in run)
            cmd = "mathit" if is_italic(run[0].fontname) else "mathrm"
            g = run[0]
            out.append(GlyphNode(
                id=g.id, page=g.page,
                rect=(g.rect[0], min(x.rect[1] for x in run),
                      run[-1].rect[2], max(x.rect[3] for x in run)),
                text=word, cid=-1, glyphname=None, fontname=g.fontname,
                family=g.family, size=g.size,
                tex=TexToken(rf"\{cmd}{{{word}}}", "atom", None, "corpus"),
                matrix=g.matrix, upright=True,
                stream=min((x.stream for x in run if x.stream >= 0), default=-1)))
            i = j + 1
            continue
        out.append(glyphs[i])
        i += 1
    return out


def _merge_operator_runs(glyphs: list[GlyphNode]) -> list[GlyphNode]:
    """Collapse runs of upright letters into one operator token.

    `Spin`, `Cl`, `Tr`, `det` are set in an UPRIGHT text face inside
    mathematics. Emitted letter by letter they become `S p i n`, which is a
    product of four variables, not an operator name. LaTeX writes them
    `\\mathbf{Spin}` or `\\mathrm{Cl}`, and the face says which: bold for a
    group name, roman for an operator.

    Italic letters are NOT merged: those are variables, and each can carry its
    own script.
    """
    from pdfreader.project_mmd import _is_bold
    from pdfreader.texmap import is_italic

    def upright(g: GlyphNode) -> bool:
        if g.family in MATH_FAMILIES:
            return False
        if is_italic(g.fontname):
            return False
        return len(g.text) == 1 and g.text.isalpha() and g.text.isascii()

    out: list[GlyphNode] = []
    i = 0
    while i < len(glyphs):
        g = glyphs[i]
        if not upright(g):
            out.append(g)
            i += 1
            continue
        run = [g]
        j = i + 1
        while j < len(glyphs):
            n = glyphs[j]
            if (not upright(n) or n.fontname != g.fontname
                    or abs(n.size - g.size) > 0.05 * g.size
                    or abs(n.baseline - g.baseline) > 0.05 * g.size
                    or n.rect[0] - run[-1].rect[2] > 0.28 * g.size):
                break
            run.append(n)
            j += 1
        if len(run) < 2:
            out.append(g)
            i += 1
            continue
        name = "".join(x.text for x in run)
        cmd = "mathbf" if _is_bold(g.fontname) else "mathrm"
        rect = (run[0].rect[0], min(x.rect[1] for x in run),
                run[-1].rect[2], max(x.rect[3] for x in run))
        out.append(GlyphNode(
            id=run[0].id, page=run[0].page, rect=rect, text=name,
            cid=-1, glyphname=None, fontname=g.fontname, family=g.family,
            size=g.size, tex=TexToken(rf"\{cmd}{{{name}}}", "atom", None,
                                      "corpus"),
            matrix=run[0].matrix, upright=True,
            stream=min((x.stream for x in run if x.stream >= 0), default=-1)))
        i = j
    return out


import os


def _merge_radicals(glyphs: list[GlyphNode], rules: list[RuleNode], depth: int):
    r"""Build `\sqrt{...}` where the radicand is itself a fraction.

    `_merge_overlines` handles the plain root: a radical sign with a VINCULUM
    over its argument, the vinculum being an `overline` rule starting at the
    sign's right edge. That covers `\sqrt{\gamma}` and it covered 8 of the 70
    roots this corpus contains.

    The other 62 are `\sqrt{a \over b}`, and they have NO vinculum to find.
    Measured on wzlxjtu-025, which sets `x_* = \sqrt{9+2\mu^2 \over 2(8-N_f)}`:
    page 1 carries nine rule objects in total and exactly one anywhere near
    the radical --

        radicalBigg  x=[435.9,447.9]  y=[368.1,380.1]
        LTLine       x=[447.9,500.5]  y=375.52          role "fraction"

    -- which is the radicand's own FRACTION BAR, at mid height, with glyphs
    above and below it. The producer draws no separate vinculum at all.

    The bar is still decisive about EXTENT: TeX sizes it to the radicand, and
    it begins exactly at the sign's right edge, 447.9 to 447.9. So the
    radicand is what lies within the bar's x-range at the sign's height --
    and the bar is handed DOWN to the recursive call rather than consumed,
    so the fraction inside the root is still built by the machinery that
    already builds fractions.

    Without this the radical stayed unpaired, `to_tex` refused the span, and
    the reading stopped dead at `x_{\ast} =`.
    """
    if not rules:
        return glyphs, set()
    size = max((g.size for g in glyphs), default=10.0)
    used: set[int] = set()
    consumed: set[int] = set()
    built: dict[int, tuple[str, RuleNode, list[int]]] = {}
    for i, g in enumerate(glyphs):
        if i in consumed or not (g.glyphname or "").startswith("radical"):
            continue
        for ri, r in enumerate(rules):
            if r.role != "fraction" or ri in used:
                continue
            mid = 0.5 * (r.rect[1] + r.rect[3])
            if abs(r.rect[0] - g.rect[2]) > 0.6 * size:
                continue
            # Measured against the sign's BASELINE, not its box. An
            # extensible radical's bbox is its hook only: `radicalBigg` on
            # wzlxjtu-025 reports y=[368.1,380.1], twelve points, while the
            # display fraction it covers has its bar at 357.13 -- eleven
            # points BELOW the box supposed to contain it. Testing
            # containment rejected every root of this shape.
            if abs(mid - g.baseline) > 2.0 * size:
                continue
            # The radicand is what the BAR spans, at the bar's own height:
            # both halves of the fraction. Taking the window around the sign
            # instead missed the denominator entirely.
            inner = [j for j, h in enumerate(glyphs)
                     if j != i and j not in consumed
                     and r.rect[0] - 1 <= 0.5 * (h.rect[0] + h.rect[2])
                     <= r.rect[2] + 1
                     and abs(h.baseline - mid) <= 2.5 * size]
            if not inner:
                continue
            consumed.add(i)
            consumed.update(inner)
            used.add(ri)
            built[min([i] + inner)] = (i, r, sorted(inner))
            break
    if not built:
        return glyphs, set()
    out: list[GlyphNode] = []
    for i, g in enumerate(glyphs):
        if i in built:
            si, r, idxs = built[i]
            body = to_tex([glyphs[k] for k in idxs], [r], depth + 1)
            if body is None:
                return glyphs, set()
            # The SIGN is what the root sits on -- its size and its baseline.
            # Built from the first radicand glyph instead, the atom inherited
            # a numerator's 8pt and a numerator's baseline, so `_attach_scripts`
            # read the whole root as a script of whatever followed it and the
            # span refused: `\sqrt{\frac{9+2\mu^2}{2(8-N_f)}}` assembled
            # correctly and was thrown away one pass later.
            base = glyphs[si]
            out.append(GlyphNode(
                id=base.id, page=base.page,
                rect=(min(glyphs[k].rect[0] for k in idxs),
                      min(glyphs[k].rect[1] for k in idxs),
                      max(glyphs[k].rect[2] for k in idxs),
                      max(glyphs[k].rect[3] for k in idxs)),
                text=base.text, cid=-1, glyphname=base.glyphname,
                fontname=base.fontname, family=base.family, size=base.size,
                tex=TexToken(rf"\sqrt{{{body}}}", "atom", None, "corpus"),
                matrix=base.matrix, upright=base.upright,
                stream=min((glyphs[k].stream for k in idxs
                            if glyphs[k].stream >= 0), default=-1)))
            continue
        if i in consumed:
            continue
        out.append(g)
    return out, {id(rules[u]) for u in used}


def _merge_overlines(glyphs: list[GlyphNode],
                     rules: list[RuleNode], depth: int):
    """Wrap the glyphs a bar sits over, and report which bars were used.

    `\\bar{x}` and `\\overline{A}` are a rule with glyphs BELOW it and nothing
    above. The conjugate in a Cayley-algebra text is written that way
    throughout, and ignoring the rule turned every `\\bar{x}` into a plain `x`
    -- the bar vanished with no trace that anything had been dropped.
    """
    bars = [r for r in rules if r.role == "overline"]
    if not bars:
        return glyphs, set()

    used: set[int] = set()
    consumed: set[int] = set()
    wrapped: dict[int, tuple[str, list[int], int]] = {}
    # THE RULES UNDER A BAR GO DOWN WITH ITS GLYPHS. The body was built with
    # no rules at all, so a fraction inside a root -- lib:6d90e8d27b8b p174,
    # `\sqrt[3]{3c - \frac{3}{4}t^4}` -- lost its bar: the digits were taken
    # into the root, the bar stayed at this level with nothing above or below
    # it, and the span was refused (3 of the board's early refusals, B2c).
    below: dict[int, list[RuleNode]] = {}
    roots: dict[int, list[int]] = {}
    for bi, r in enumerate(bars):
        mid = 0.5 * (r.rect[1] + r.rect[3])
        below[bi] = [q for q in rules if q is not r and q.role == "fraction"
                     and 0.5 * (q.rect[1] + q.rect[3]) < mid
                     and r.rect[0] - 1 <= q.rect[0] and q.rect[2] <= r.rect[2] + 1]
        under = [i for i, g in enumerate(glyphs)
                 if i not in consumed and g.baseline < mid
                 and r.rect[0] - 1 <= 0.5 * (g.rect[0] + g.rect[2])
                 <= r.rect[2] + 1]
        if not under:
            continue
        # A RADICAL is this same shape with a sign in front of it: TeX draws
        # `\sqrt{x}` as the radical glyph plus a vinculum over the radicand,
        # and the vinculum is an overline in every respect the classifier can
        # see. Told apart by what stands immediately to the bar's LEFT.
        #
        # `to_tex` refused any span containing a radical outright ("see
        # LIMITS"), which cost 828 spans across the 102 documents -- the
        # author wrote 70 roots in 41 equations, 9.7% of the corpus, and not
        # one of them could ever be read. The machinery was already here.
        size = max((g.size for g in glyphs), default=10.0)
        sign = None
        for i, g in enumerate(glyphs):
            if i in consumed or not (g.glyphname or "").startswith("radical"):
                continue
            if abs(g.rect[2] - r.rect[0]) > 0.6 * size:
                continue
            if not (g.rect[1] - size <= mid <= g.rect[3] + size):
                continue
            sign = i
            break
        if sign is not None:
            # ITS INDEX: a smaller glyph centred over the SIGN itself, not
            # over the bar (6d90 p174's `\sqrt[3]{...}` came out `=^{3}
            # \sqrt{...}`: the 3 was left to hang on the glyph before it).
            sg = glyphs[sign]
            idx = [i for i, g in enumerate(glyphs)
                   if i not in consumed and i != sign and i not in under
                   and g.size <= 0.7 * sg.size
                   and sg.rect[0] <= 0.5 * (g.rect[0] + g.rect[2]) <= sg.rect[2]]
            consumed.add(sign)
            consumed.update(under)
            consumed.update(idx)
            used.add(bi)
            roots[min([sign] + under + idx)] = sorted(idx)
            wrapped[min([sign] + under + idx)] = (r"\sqrt", sorted(under), bi)
            continue
        consumed.update(under)
        used.add(bi)
        wrapped[min(under)] = (r"\overline", sorted(under), bi)

    if not wrapped:
        return glyphs, set()

    out: list[GlyphNode] = []
    for i, g in enumerate(glyphs):
        if i in wrapped:
            cmd, idxs, bi = wrapped[i]
            _STYLE_KEEPING[0] += 1
            try:
                inner = to_tex([glyphs[k] for k in idxs], below[bi], depth + 1)
            finally:
                _STYLE_KEEPING[0] -= 1
            if inner is None:
                return glyphs, set()
            if roots.get(i):
                deg = to_tex([glyphs[k] for k in roots[i]], [], depth + 1)
                if deg is None:
                    return glyphs, set()
                cmd = rf"\sqrt[{deg}]"
            base = glyphs[idxs[0]]
            out.append(GlyphNode(
                id=base.id, page=base.page,
                rect=(min(glyphs[k].rect[0] for k in idxs),
                      min(glyphs[k].rect[1] for k in idxs),
                      max(glyphs[k].rect[2] for k in idxs),
                      max(glyphs[k].rect[3] for k in idxs)),
                text=base.text, cid=-1, glyphname=base.glyphname,
                fontname=base.fontname, family=base.family, size=base.size,
                tex=TexToken(rf"{cmd}{{{inner}}}", "atom", None, "corpus"),
                matrix=base.matrix, upright=base.upright,
                stream=min((glyphs[k].stream for k in idxs
                            if glyphs[k].stream >= 0), default=-1)))
            continue
        if i in consumed:
            continue
        out.append(g)
    return out, ({id(bars[b]) for b in used}
                 | {id(q) for b in used for q in below[b]})


def _merge_underlines(glyphs: list[GlyphNode],
                      rules: list[RuleNode], depth: int):
    r"""Wrap the glyphs a bar sits UNDER, and report which bars were used.

    T-0162 — the mirror of `_merge_overlines`. `\underline{e}` is a rule with
    glyphs ABOVE it and nothing below, and until `_rule_role` grew a branch
    for that shape no such rule was ever classified, so this pass had nothing
    to do and no `\underline` was emitted anywhere in the corpus.

    MEASURED AND CHECKED AGAINST THE AUTHOR (standing rule, 2026-11-23):
    arxiv.gr-qc_0212041 p1 draws three of them, 4.7 pt wide, each exactly
    spanning a CMMI10 `e`; the author's own source (CG.tex from the e-print)
    holds exactly three `\underline`, every one `\underline{e}`.

    NO RADICAL CASE, which is the one way this is not a mirror: TeX draws a
    vinculum OVER a radicand, never under it, so the sign-to-the-left test
    that `_merge_overlines` needs has no counterpart here.
    """
    bars = [r for r in rules if r.role == "underline"]
    if not bars:
        return glyphs, set()

    used: set[int] = set()
    consumed: set[int] = set()
    wrapped: dict[int, tuple[str, list[int]]] = {}
    for bi, r in enumerate(bars):
        mid = 0.5 * (r.rect[1] + r.rect[3])
        over = [i for i, g in enumerate(glyphs)
                if i not in consumed and g.baseline > mid
                and r.rect[0] - 1 <= 0.5 * (g.rect[0] + g.rect[2])
                <= r.rect[2] + 1]
        if not over:
            continue
        consumed.update(over)
        used.add(bi)
        wrapped[min(over)] = (r"\underline", sorted(over))

    if not wrapped:
        return glyphs, set()

    out: list[GlyphNode] = []
    for i, g in enumerate(glyphs):
        if i in wrapped:
            cmd, idxs = wrapped[i]
            inner = to_tex([glyphs[k] for k in idxs], [], depth + 1)
            if inner is None:
                return glyphs, set()
            base = glyphs[idxs[0]]
            out.append(GlyphNode(
                id=base.id, page=base.page,
                rect=(min(glyphs[k].rect[0] for k in idxs),
                      min(glyphs[k].rect[1] for k in idxs),
                      max(glyphs[k].rect[2] for k in idxs),
                      max(glyphs[k].rect[3] for k in idxs)),
                text=base.text, cid=-1, glyphname=base.glyphname,
                fontname=base.fontname, family=base.family, size=base.size,
                tex=TexToken(rf"{cmd}{{{inner}}}", "atom", None, "corpus"),
                matrix=base.matrix, upright=base.upright,
                stream=min((glyphs[k].stream for k in idxs
                            if glyphs[k].stream >= 0), default=-1)))
            continue
        if i in consumed:
            continue
        out.append(g)
    # ids, not indices — the caller filters with `id(r)`, exactly as it does
    # for `_merge_overlines` and `_merge_radicals`.
    return out, {id(bars[b]) for b in used}


#: HOW OFTEN THIS READER BUILDS NOTHING — B2's instrument.
#:
#: `to_tex` returns None when `_attach_scripts` cannot attribute a script, and
#: the row then carries NO structure at all. That refusal was invisible: it is
#: not a wrong answer, so no test and no board number reports it, and B2 was
#: argued for three attempts without anyone able to say how often it happens.
#:
#: MEASURED, 2026-11-24, over the 21 born pages of board75, through
#: `project_mmd.to_markdown` — THE PATH THE PIPELINE TAKES:
#:
#:     1237 groups offered to `to_tex`, 25 refused        2.0%
#:     and 18 of those 25 are on ONE page, 0864 p4       11.0% of its 164
#:     1511.08771 p2709 2/98, lib:3fe71b4ef018 p328 3/53,
#:     lib:6d90e8d27b8b p174 2/68, every other born page 0.
#:
#: A FIRST VERSION OF THIS MEASUREMENT SAID 19%, and it was measuring
#: something the pipeline never does: it fed WHOLE ROWS to `_attach_scripts`,
#: while the projection feeds it SPANS, which are smaller and succeed far more
#: often. The counter lives here, at the real call, for that reason — a figure
#: taken by calling an inner function directly is not this reader's behaviour.
#:
#: So B2's defect is RARE and CONCENTRATED, which is itself the finding: it
#: lives on pages whose rows merge two printed lines (0864 p4 is a two-column
#: paper whose figure captions run into small-caps body lines).
#:
#: `reset_report()` then read `REPORT` around a build to get the same number
#: for any document. Counting only — it changes no decision.
REPORT = {"rows": 0, "refused": 0}


def reset_report() -> None:
    REPORT.update(rows=0, refused=0)


def to_tex(glyphs: list[GlyphNode], rules: list[RuleNode] | None = None,
           depth: int = 0) -> str | None:
    """LaTeX for a glyph group, or None if the geometry is not decisive."""
    if depth > 6:
        return None
    # 734 — SORTING BY STREAM HERE WAS TRIED AND LOSES. The numbers, so
    # it is not tried a fourth time, and the distinction, which is real.
    #
    # The stream IS reading order inside a horizontal list. Measured,
    # wzlxjtu-009:
    #
    #   x        psi macron A ... psi B T      sigma A three B
    #   stream   macron psi A ... psi T B      sigma three A B
    #   author   \bar\psi_A ... \psi_B^T        \sigma^3_{AB}
    #
    # The accent precedes its base and the superscript precedes the
    # subscript, exactly as written -- and x cannot recover either, because
    # `\sigma`'s two scripts are 1.2pt apart and stacked.
    #
    # But a VERTICAL box is not shipped in reading order. TeX builds
    # `\prod_{i=0}^{3}` as a vbox and ships it top to bottom: upper limit,
    # operator, lower limit. Sorting the row by stream therefore puts the
    # limit before the operator that owns it:
    #
    #   gold   L=\prod_{i=0}^3 e^{\phi^i K^i}
    #   got    L =^{3} \prod_{i=0} e^{\phi^i K^i}
    #   gold   4(S_0^2+S_3^2)
    #   got    4 \bigl(S^{2}\bigr)_{0} + S_3^2
    #
    # Whole corpus: 38 delivered whole by x order, 34 by stream order, and
    # 6 equations lost against 1 gained -- every loss a stacked construction.
    #
    # So the stream decides WHICH GLYPHS BELONG TOGETHER, which is a local
    # question it answers exactly (see the band merge in docmodel_six,
    # whole 34 -> 38); x decides WHAT ORDER THE ROW READS IN, because that
    # is the question the page answers and the stream does not.
    glyphs = sorted(glyphs, key=lambda g: g.rect[0])
    if not glyphs:
        return ""
    glyphs = _merge_mapsto(glyphs)
    glyphs = _merge_negations(glyphs)
    glyphs = _merge_accents(glyphs, depth)
    glyphs = _merge_small_caps(glyphs)
    glyphs = _merge_function_names(glyphs)
    glyphs = _merge_operator_runs(glyphs)
    if any(g.tex.kind == "fragment" for g in glyphs):
        return None

    rules = rules or []
    glyphs, used_rad = _merge_radicals(glyphs, rules, depth)
    rules = [r for r in rules if id(r) not in used_rad]
    glyphs, used_bars = _merge_overlines(glyphs, rules, depth)
    # A radical that found no vinculum is still structure this pass cannot
    # describe, and it defers exactly as it always did. The check moved BELOW
    # the merge rather than away: what changed is that a root which WAS
    # assembled no longer counts against the span.
    if any(g.glyphname and g.glyphname.startswith("radical") for g in glyphs):
        return None                      # see LIMITS
    rules = [r for r in rules if id(r) not in used_bars]
    glyphs, used_unders = _merge_underlines(glyphs, rules, depth)
    rules = [r for r in rules if id(r) not in used_unders]

    # Any rule still unaccounted for is structure this pass does not model.
    # Ignoring it is how `\bar{x}` became `x`: valid output, silently missing
    # the bar, with nothing to show a reader that anything was lost.
    # A separator is a frame edge or a rule between blocks: it says nothing
    # about the mathematics beside it, so it neither composes nor blocks.
    # An underscore is CONTENT, not structure: it is drawn as a rule but it
    # is a character. It joins the glyph stream in x-order rather than
    # blocking the span.
    unders = [r for r in rules if r.role == "underscore"]
    rules = [r for r in rules if r.role not in ("separator", "underscore")]
    if any(r.role not in ("fraction",) for r in rules):
        return None

    # T-0154 — a delimiter pair holding stacked rows becomes one array
    # atom before anything else reads the row, so its entries are never
    # walked in x order and interleaved.
    glyphs = _merge_stacked_delimiters(glyphs, depth)

    fracs, rest = _split_fractions(glyphs, rules)

    # A fraction rule that did not resolve into a numerator AND a denominator
    # must not be ignored. If it is, its numerator and denominator fall through
    # to `_attach_scripts` as ordinary glyphs on different baselines and come
    # out as `1_{\beta\gamma}` -- valid LaTeX with the fraction silently gone.
    # Deferring keeps the rectangle and the reason instead.
    if any(r.role == "fraction" for r in rules) and \
            len(fracs) != sum(1 for r in rules if r.role == "fraction"):
        return None

    if fracs:
        # A fraction is a single object in its row, so it must take part in
        # script attachment rather than short-circuiting it. Emitting `rest`
        # glyph-wise here would silently drop the scripts on the fraction's
        # neighbours — turning `\Gamma_{\alpha}^{\star}` into
        # `\Gamma \alpha \star`, which is valid LaTeX saying something else.
        row: list[GlyphNode] = list(rest)
        size = _row_size(glyphs)
        for f in fracs:
            num = to_tex(f.num, [], depth + 1)
            den = to_tex(f.den, [], depth + 1)
            if num is None or den is None:
                return None
            mid = 0.5 * (f.rule.rect[1] + f.rule.rect[3])
            # T-0156 — `\tfrac` where the page set one; see `_is_text_style`.
            _cmd = "tfrac" if _is_text_style(f.num, f.den, rest, size,
                                             depth) else "frac"
            # A FRACTION IN A SCRIPT IS SCRIPT-SIZED. Its node took the ROW's
            # size, so lib:6d90e8d27b8b p174's `e^{(\frac12 t^2 - t)}` -- a
            # 4.8 pt fraction in a 6.72 pt exponent -- became a full-size
            # atom off the baseline and the whole row was refused (written
            # as characters, `ece(21t2-t)`). TeX sets a fraction's parts one
            # step below its own level (scriptscript in a script, ratio 0.7),
            # so the node's size is theirs / 0.7, capped at the row's; inside
            # a script `\frac` shrinks by itself, and `\tfrac` would not.
            _part = max((g.size for g in f.num + f.den), default=size)
            fsize = min(size, _part / 0.7)
            if fsize < SCRIPT_SIZE_RATIO * size:
                _cmd = "frac"
            else:
                fsize = size
            row.append(
                GlyphNode(
                    id=f.rule.id, page=f.rule.page,
                    rect=(f.rule.rect[0], mid - fsize, f.rule.rect[2], mid + fsize),
                    text="", cid=-1, glyphname=None,
                    fontname="<fraction>", family="math-extension", size=fsize,
                    tex=TexToken(
                        rf"\{_cmd}{{{num}}}{{{den}}}", "atom",
                        "amsmath" if _cmd == "tfrac" else None, "corpus"),
                    # the bar sits on the maths axis, about a quarter of the
                    # type size above the baseline it shares with its row
                    matrix=(fsize, 0, 0, fsize, f.rule.rect[0], mid - 0.25 * fsize),
                    # 733 — the synthesised atom keeps the EARLIEST stream
                    # index of the glyphs it replaces, so a row carrying a
                    # fraction can still be read in emission order. Without
                    # it every such row fell back to the x walk, which is
                    # exactly the row that needs the stream most.
                    stream=min((g.stream for g in (f.num + f.den)
                                if g.stream >= 0), default=-1),
                )
            )
        glyphs = sorted(row, key=lambda g: g.rect[0])
        rules = []

    triples = _attach_scripts(glyphs)
    if depth == 0:
        REPORT["rows"] += 1
    if triples is None:
        if depth == 0:
            REPORT["refused"] += 1
        return None
    if unders:
        return _weave_underscores(triples, unders, depth)

    out: list[str] = []
    bases: list = []
    for base, sup, sub in triples:
        if base is None:                 # a marker group with an empty base
            lit = "{}"
        else:
            lit = glyph_latex(base)
            if lit is None:
                return None
        part = lit
        # `\limits` WHEN THE PAGE PUTS THEM THERE.
        #
        # `\lim_{x}` sets its condition BELOW in display style and BESIDE in
        # inline style -- same source, two renderings -- and a span projected
        # here becomes `$...$` or `$$...$$` depending on what the row was.
        # So `\lim_{...}` alone cannot express what the page shows: an inline
        # `\lim` whose condition is underneath needs `\lim\limits_{...}`, and
        # in display `\limits` is what it would have done anyway.
        #
        # Emitted whenever the scripts are UNDER the operator rather than
        # beside it, which is a measurement, not an assumption: their centres
        # fall within its x-range. The same test the claim above uses.
        if base is not None and texmap.may_take_limits(
                base.tex.latex, base.glyphname):
            # A BESIDE script sits entirely to the RIGHT of the operator; an
            # UNDER one is centred on it and so begins left of its right edge.
            # Requiring every script to fall INSIDE the operator was tried and
            # never fired: a condition is usually WIDER than the word it sits
            # under -- `\lim` spans [183.3,199.6] while
            # `\phi^0_0 \rightarrow -\infty` runs [175.1,207.8].
            marks = sup + sub
            # A LIMIT UNDER AND A MARK BESIDE: `\sideset{}{'}\sum_{...}`.
            # lib:1a36bfe66b9c p154 sets the prime of a restricted sum at the
            # operator's upper RIGHT while its condition is centred under it;
            # `\limits` alone put the prime on top (the judge's one unpaired
            # glyph of that page, 47 px left of and 24 px above the print's).
            if (sub and sup and base.tex.kind == "bigop"
                    and min(g.rect[0] for g in sub) < base.rect[2] - 0.1
                    and min(g.rect[0] for g in sup) >= base.rect[2] - 0.1):
                s_up = to_tex(sup, [], depth + 1)
                if s_up is None:
                    return None
                part = rf"\sideset{{}}{{^{{{s_up}}}}}{part}\limits"
                sup = []
            elif marks and min(g.rect[0] for g in marks) < base.rect[2] - 0.1:
                part += r"\limits"
        bases.append(base if base is not None else (sup or sub)[0])
        if sub:
            s = to_tex(sub, [], depth + 1)
            if s is None:
                return None
            part += f"_{{{s}}}"
        if sup:
            s = to_tex(sup, [], depth + 1)
            if s is None:
                return None
            part += f"^{{{s}}}"
        out.append(part)

    # Join by the MEASURED gap, not with a blank. A LaTeX space emits no
    # glyph -- every one is a pure advance of the current point -- and the
    # advances are quantised in em, so the command is recoverable. Joining
    # with " " lost `\!` (a deliberate NEGATIVE space) and could not tell
    # `$ab$` from `$a\quad b$`.
    pieces: list[str] = []
    for i, part in enumerate(out):
        if i:
            prev, cur = bases[i - 1], bases[i]
            size = max(prev.size, cur.size, 1.0)
            gap = math_space((cur.rect[0] - prev.rect[2]) / size)
            # A multi-letter command needs a separator before a letter, or
            # `\quad` + `b` becomes the undefined control sequence
            # `\quadb`. TeX ends a control word at the first non-letter.
            if gap[-1:].isalpha() and part[:1].isalpha():
                gap += " "
            # The same hazard on the OTHER side, and it is the common one.
            # This test asked whether the GAP ends in a letter, which catches
            # `\quad` + `b`; it never asked whether the PREVIOUS PART does.
            # A measured gap of zero -- which 694 renders as "" so that `$ab$`
            # stays `$ab$` -- then glues `\mid` to the letter after it:
            # `|x - y|` came out as `\midx - y\mid`, an undefined command.
            # Measured: 66 occurrences across 19 of 30 documents, `\right`,
            # `\mid`, `\in`, `\ell` and `\langle` among them.
            elif not gap and part[:1].isalpha() and _ends_in_command(
                    pieces[-1] if pieces else ""):
                gap = " "
            pieces.append(gap)
        pieces.append(part)
    return "".join(pieces)


_COMMAND_TAIL = re.compile(r"\\[a-zA-Z]+$")


def _ends_in_command(text: str) -> bool:
    """Does this piece end with a multi-letter control word?

    TeX ends a control word at the first NON-LETTER, so a letter placed
    straight after one extends its name instead of following it.
    """
    return bool(_COMMAND_TAIL.search(text))


def span_to_tex(span) -> str | None:
    """Entry point for a docmodel Span. None means: defer, keep the blobs."""
    if span.kind != "math" or not span.glyphs:
        return None
    body = to_tex(span.glyphs, span.rules)
    if body is None:
        return None

    # A span made up ENTIRELY of raised, script-size glyphs is a marker group
    # whose base is the word before it -- `Montaño` with `a,*` above the line.
    # Judged inside the span the glyphs all look full size, because they are
    # full size relative to EACH OTHER; the raise is only visible against the
    # LINE. LaTeX spells a script with no base as an empty group.
    size = getattr(span, "line_size", 0.0) or 0.0
    if size > 0 and len(span.glyphs) <= 4:
        base = min(g.baseline for g in span.glyphs)
        if (all(g.size <= 0.85 * size for g in span.glyphs)
                and base >= span.rect[1] - 0.01
                and all(g.baseline >= base - 0.01 for g in span.glyphs)):
            return "{}^{" + body + "}"
    return body
