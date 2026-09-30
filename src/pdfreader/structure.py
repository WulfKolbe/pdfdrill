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

from docmodel_six import MATH_FAMILIES, GlyphNode, RuleNode, glyph_latex
import os as _os
import texmap
from texmap import TexToken, math_space

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
            (sup if g.baseline > glyphs[i].baseline + LEVEL_TOL * size
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
            if g.baseline > glyphs[i].baseline + LEVEL_TOL * size:
                sup.append(g); last_at, last_sz = sup, g.size
            elif g.baseline < glyphs[i].baseline - LEVEL_TOL * size:
                sub.append(g); last_at, last_sz = sub, g.size
            elif abs(g.baseline - glyphs[i].baseline) >= 0.05 * size:
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
                (sup if g.baseline > glyphs[i].baseline else sub).append(g)
                last_at = sup if g.baseline > glyphs[i].baseline else sub
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
    from project_mmd import _is_bold
    from texmap import is_italic

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
    wrapped: dict[int, tuple[str, list[int]]] = {}
    for bi, r in enumerate(bars):
        mid = 0.5 * (r.rect[1] + r.rect[3])
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
            consumed.add(sign)
            consumed.update(under)
            used.add(bi)
            wrapped[min([sign] + under)] = (r"\sqrt", sorted(under))
            continue
        consumed.update(under)
        used.add(bi)
        wrapped[min(under)] = (r"\overline", sorted(under))

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
    return out, {id(bars[b]) for b in used}


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
            row.append(
                GlyphNode(
                    id=f.rule.id, page=f.rule.page,
                    rect=(f.rule.rect[0], mid - size, f.rule.rect[2], mid + size),
                    text="", cid=-1, glyphname=None,
                    fontname="<fraction>", family="math-extension", size=size,
                    tex=TexToken(rf"\frac{{{num}}}{{{den}}}", "atom", None,
                                 "corpus"),
                    # the bar sits on the maths axis, about a quarter of the
                    # type size above the baseline it shares with its row
                    matrix=(size, 0, 0, size, f.rule.rect[0], mid - 0.25 * size),
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
    if triples is None:
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
            if marks and min(g.rect[0] for g in marks) < base.rect[2] - 0.1:
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
