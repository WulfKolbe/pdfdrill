"""docmodel_six — build the document model from a born-digital PDF, then project.

The model is built ONCE and every output format is a projection from it
(guarantee G4). Nothing here is produced in parallel with anything else.

SCOPE: born-digital only. A page whose glyphs are invisible (Tr 3/7) is an OCR
layer over a raster; its glyph identities are another tool's guess, so this
module refuses it rather than projecting confident nonsense.

UNITS
  U2  glyphs()        LTChar        -> GlyphNode, one per glyph, none dropped
  U3  rules()         LTLine/LTRect -> RuleNode  (the \\frac and \\sqrt bars)
  U4  merge_fragments()             -> collapse extensible delimiter pieces
  U5  lines()                       -> LineNode, marked text or formula
  U6  to_lines_json()               -> MathPix-shaped geometry
  U7  to_markdown()                 -> Markdown with LaTeX injected

WHAT THIS DOES NOT DO
  Structure. Superscripts, subscripts, fractions and radicals need a layout
  tree, which is not built here. A formula is emitted as LaTeX only when it is
  FLAT: one baseline, no rules, no fragments, every glyph projectable. Every
  other formula is emitted as an explicit deferred marker carrying its node id
  and rect, never as silently missing text (guarantee G3).
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import Iterable

import logging

from pdfminer.high_level import extract_pages
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.layout import LTChar, LTCurve, LTImage, LTLine, LTRect

import listings
import texmap
from texmap import (TexToken, family_of, greek_latex, is_drawing, space_class,
                    tex_slot, untrusted_name,
                    is_italic, is_monospace, measure_monospace, project,
                    set_measured_monospace, unicode_latex)

# pdfminer logs every content-stream operator at DEBUG. On a page with tens
# of thousands of path objects that is millions of calls into the logging
# machinery for output nobody reads -- measured at 3.1M calls on one page.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

MATH_FAMILIES = frozenset(
    # `doublestroke` belongs here for the same reason `fraktur` and `script`
    # do: it is a MATHS font, every glyph of which is the double-struck form
    # of a character. Left out, its glyphs landed in TEXT spans, which carry
    # no LaTeX -- so the eighth `\mathds{1}` of wzlxjtu-026, the one sitting
    # in an inline formula rather than a display, was dropped with no trace.
    {"math-italic", "math-symbol", "math-extension", "ams-symbol",
     "fraktur", "script", "doublestroke"}
)

Rect = tuple[float, float, float, float]

# Pixels per PDF point for the coordinate space used by lines.json regions and
# by crop URLs. MathPix renders at a constant 250 dpi (measured: 250.05 dpi on
# every page of a 377-page book), and matching it means a rectangle taken from
# either lines.json can be handed to a crop server unchanged.
#
# This constant MUST be shared with the crop-URL builder. When lines.json was
# written in points while crop URLs were written in pixels, a server given
# both computed a scale of 3.47 and every crop landed off the page.
PX_PER_PT = 250.0 / 72.0


# --------------------------------------------------------------------- nodes
@dataclass
class GlyphNode:
    id: str
    page: int
    rect: Rect
    text: str
    cid: int
    glyphname: str | None
    fontname: str
    family: str
    size: float
    tex: TexToken
    matrix: tuple = (1, 0, 0, 1, 0, 0)
    upright: bool = True
    color: tuple[float, float, float] | None = None   # None == black
    stream: int = -1            # position in the content stream, -1 unknown

    @property
    def is_math(self) -> bool:
        # A Greek letter is mathematics whatever font carries it: TeX puts
        # uppercase Greek in the ROMAN font, so going by font alone left
        # `\Gamma^{+}` and `\Phi` sitting in prose spans.
        return (self.family in MATH_FAMILIES
                or greek_latex(self.glyphname) is not None)

    @property
    def baseline(self) -> float:
        """The glyph's text-space origin, which IS the baseline.

        The bounding box bottom is not a baseline: it includes the descent,
        scaled by font size, so a smaller superscript can sit BELOW its base's
        box bottom while being typographically raised. Using the box bottom
        made a superscript look level with its base and let `\vartheta^\alpha`
        project as `\vartheta \alpha` — silently wrong LaTeX.
        """
        return self.matrix[5]


@dataclass
class RuleNode:
    id: str
    page: int
    rect: Rect
    role: str = "unknown"       # fraction | radical | overline | table | unknown

    @property
    def thickness(self) -> float:
        return self.rect[3] - self.rect[1]

    @property
    def span(self) -> float:
        return self.rect[2] - self.rect[0]


# Characters that are already valid LaTeX inside maths mode, written as
# themselves. A glyph set in a TEXT font inside a maths span -- a digit, an
# operator, a parenthesis -- is not a maths-alphabet glyph and so has no
# TexToken, but it still has a correct and unambiguous maths-mode form.
# Anything outside this set is deferred rather than escaped by guesswork.
_SAFE_LITERAL = set("0123456789+-=()[]/.,;:<>!|*?'")


def glyph_latex(g: "GlyphNode") -> str | None:
    """LaTeX for one glyph inside a maths span, or None to defer."""
    if g.tex.kind in ("fragment", "overlay", "accent", "rule"):
        # All of these need COMPOSITION, not emission. An accent left
        # uncomposed emitted a bare `\widetilde`, which KaTeX rejects with
        # "Missing argument for \widetilde" -- invalid LaTeX is worse than a
        # crop, because it breaks the renderer rather than the reader.
        return None
    if g.tex.latex is not None:
        return g.tex.latex
    greek = greek_latex(g.glyphname)
    if greek:
        return greek
    # A publisher's maths font names its glyphs by CODEPOINT -- STIXMath
    # emits `u1D460` and `uni2032` where Computer Modern emits `s` and
    # `prime`. Measured across three journal papers, that dialect was the
    # single largest cause of deferral.
    uni = unicode_latex(g.glyphname or "")
    if uni is not None:
        return uni
    # NO GLYPH NAME, but a usable CHARACTER.
    #
    # A 1997 Distiller PDF embeds its Type 1 fonts with a builtin encoding
    # and no /Differences, so pdfminer resolves the character but not the
    # PostScript name -- measured, every font on the page, including CMTT10.
    # The maths italic still yields real letters (`ABdhswxy`), and a letter
    # in a maths italic font IS its own LaTeX.
    #
    # Only where the character is trustworthy: a letter or a digit, not a
    # `(cid:15)` placeholder, and not a SYMBOL font, whose character mapping
    # in this state is meaningless -- mtsy10 gave nothing but `(cid:15)`.
    # Only the MATHS ITALIC. A text family already has its own path -- an
    # upright letter inside maths is `\mathrm{d}`, not `d` -- and running
    # ahead of it turned every one of those into a bare letter.
    if (not g.glyphname and g.family == "math-italic"
            and len(g.text) == 1
            and (g.text.isalnum() or g.text in "+-=<>()[],.:;/|")):
        return g.text

    # A SPACE is not an unmapped glyph. Measured: 15 spaces in Times-Roman
    # deferred every maths span in one paper -- 0% projected, with nothing
    # wrong but the gaps between the symbols.
    if (g.glyphname or "").lower() in ("space", "uni0020") or g.text == " ":
        return " "
    if g.family in MATH_FAMILIES:
        return None                      # a maths glyph we could not identify
    t = g.text
    if len(t) == 1 and t in _SAFE_LITERAL:
        return t
    if len(t) == 1 and t.isalpha() and t.isascii():
        # A letter from a TEXT font inside maths. If that font is italic it is
        # a variable: maths italic is the default, so it is emitted bare. Only
        # an upright letter is genuinely roman (an operator name, a unit) and
        # needs \mathrm. Wrapping variables would upright every `E`, `d` and
        # `x` in a MathTime document, where Latin variables come from the text
        # italic font rather than from the maths font.
        if is_italic(g.fontname):
            return t
        return rf"\mathrm{{{t}}}"
    return None


def _is_level(glyphs: list["GlyphNode"]) -> bool:
    """True if every glyph shares one baseline AND one type size.

    Two independent signals, because either alone is fooled. A script is both
    raised (or lowered) and SMALLER; a same-size glyph on a shifted baseline is
    still a script. Requiring both to be uniform means a span is called flat
    only when there is no vertical structure to lose.
    """
    if not glyphs:
        return False
    sizes = [g.size for g in glyphs]
    if max(sizes) - min(sizes) > 0.08 * max(sizes):
        return False
    base = [g.baseline for g in glyphs]
    return max(base) - min(base) <= 0.08 * max(sizes)


@dataclass
class Span:
    """A maximal run of glyphs of one kind within a line.

    A line is not the unit of mathematics. `Since the coframe ϑ^α has ...` is
    prose with an inline maths span inside it; requiring the whole line to
    project would defer it forever, and emitting the whole line as maths
    would wrap the prose in `$...$`.
    """
    id: str
    kind: str                    # "text" | "math"
    rect: Rect
    glyphs: list[GlyphNode] = field(default_factory=list)
    rules: list[RuleNode] = field(default_factory=list)
    line_size: float = 0.0       # dominant type size of the containing line
    word_gap: float = 0.0        # word-space width, measured on the whole line

    @property
    def flat(self) -> bool:
        if self.kind != "math" or not self.glyphs:
            return False
        if self.rules:
            return False
        # A span set entirely SMALLER than its line is a script attached to a
        # neighbour. Projecting it as a standalone `$\alpha$` would silently
        # drop the superscript relation, so it is deferred like any other
        # structure this module cannot yet build.
        if self.line_size and max(g.size for g in self.glyphs) < 0.92 * self.line_size:
            return False
        if any(glyph_latex(g) is None for g in self.glyphs):
            return False
        return _is_level(self.glyphs)


def _spans(line: "LineNode") -> list[Span]:
    """Split a line into alternating text and maths runs, in x-order.

    Digits and common operators between two maths runs belong to the maths:
    in `E = mc2` the `2` is set in a text font but is part of the expression.
    A run is only absorbed that way when maths sits on BOTH sides, so prose
    is never swallowed.
    """
    out: list[Span] = []
    if not line.glyphs:
        return out

    if line.rotated:
        # Sideways text is a stamp or a margin note, never an equation.
        # Parsing it as mathematics turns `arXiv:0805.0311v3` into LaTeX and
        # loses the one thing it is useful for: being readable.
        g = sorted(line.glyphs, key=lambda x: x.rect[0])
        return [Span(id=f"{line.id}s0", kind="text", rect=line.rect,
                     glyphs=line.glyphs, rules=[],
                     line_size=max(x.size for x in g))]

    if line.verbatim:
        # A verbatim line is one text span, whatever fonts its punctuation
        # was borrowed from. Nothing in it is mathematics.
        ordered_v = sorted(line.glyphs, key=lambda g: g.rect[0])
        return [Span(id=f"{line.id}s0", kind="text", rect=line.rect,
                     glyphs=ordered_v, rules=[],
                     line_size=_dominant_size(ordered_v),
                     word_gap=_word_gap(ordered_v))]

    # A line carrying a FRACTION cannot be segmented by x. The numerator and
    # denominator share a column, so ordering by x interleaves them with
    # whatever sits either side and no span ends up holding both halves plus
    # the bar. A display like `(1,0) |-> 1/2 (1 (x) 1 + i (x) i)` came out as
    # the orphan `( 1 , 2` and a deferred remainder. When the line is mostly
    # mathematics, keep it whole and let the structure pass do the splitting.
    if any(r.role == "fraction" for r in line.rules) and line.glyphs:
        mathy = sum(1 for g in line.glyphs if g.is_math)
        letters = sum(1 for g in line.glyphs
                      if not g.is_math and g.text.strip().isalpha())
        if mathy >= 0.25 * len(line.glyphs) and letters <= 0.35 * len(line.glyphs):
            whole = sorted(line.glyphs, key=lambda g: g.rect[0])
            return [Span(id=f"{line.id}s0", kind="math", rect=line.rect,
                         glyphs=whole, rules=list(line.rules),
                         line_size=_dominant_size(whole),
                         word_gap=_word_gap(whole))]

    # A SCRIPT proves its base is mathematics. `(e_2 e_3)^2` sets the bases in
    # an italic TEXT font and the subscripts in a maths font, so splitting by
    # font alone puts base and script in different spans -- and a script with
    # no base in its span can never be attached, so it defers as a crop. On a
    # dense page that is most of the line.
    dom = _dominant_size(line.glyphs)
    ordered = sorted(line.glyphs, key=lambda g: g.rect[0])
    mathish = {id(g) for g in ordered if g.is_math}
    # 775 -- IS THIS LINE A DISPLAY? The absorption rules below are calibrated
    # against a WORD SPACE, and a line with no words in it has none: `_word_gap`
    # on page 673 of Obertelli & Sagawa measures 1.42pt, which is the kerning
    # between letters, while TeX's space around a binary operator is 2.5-4.1pt.
    # Every variable on that line therefore failed `_tight`.
    #
    # The test is WORDS, not a letter ratio. Borrowing the fraction rule's
    # `letters <= 0.35 * glyphs` refused this very line: `n + e^+ <-> p +
    # \bar{\nu}_e` is 4 letters in 11 glyphs against a bound of 3.85, because
    # an equation written in particle symbols is mostly Latin letters by
    # construction. Its SECOND line passed and its first did not -- one
    # display, two spellings.
    #
    # What separates prose from a display is that prose has words: three or
    # more letters running together. A display has single variables. That is
    # the line-scale form of what `_is_variable_run` already says about a run.
    _n_math = sum(1 for g in ordered if g.is_math)
    _word_run = _longest = 0
    _prev = None
    for _g in ordered:
        _alpha = (not _g.is_math) and _g.text.strip().isalpha()
        if _alpha and _prev is not None and (
                _g.rect[0] - _prev.rect[2] < 0.3 * max(dom, 1.0)):
            _word_run += 1
        elif _alpha:
            _word_run = 1
        else:
            _word_run = 0
        _prev = _g if _alpha else None
        _longest = max(_longest, _word_run)
    _mostly_math = bool(ordered) and _n_math >= 0.25 * len(ordered) and _longest < 3
    # Glyphs forced to TEXT regardless of the font they came from. `is_math`
    # follows the font family, and a `<` borrowed from the maths font is
    # still punctuation when it is glued to a word.
    textish: set[int] = set()
    # A monospace glyph is NEVER mathematics, whatever its family says. A
    # `\texttt{fermion_state_generator}` caption arrives with its underscores
    # as maths-font glyphs, and the script machinery turned it into
    # `\mathrm{fermion}_{s} t a t e_{g} e n e r a t o r`.
    for _g in ordered:
        if is_monospace(_g.fontname):
            textish.add(id(_g))

    # AN ACCENT BELONGS WITH WHAT IT COVERS, whatever font drew it.
    #
    # TeX takes `\bar` from the ROMAN font: wzlxjtu-008 sets `\bar\psi_A` as
    # `psi` from CMMI12 with a `macron` from CMR12 directly over it. `is_math`
    # follows the font family, so the accent landed in a TEXT span while its
    # base stayed in the maths span -- and `_merge_accents` runs inside
    # `to_tex` on ONE span's glyphs, so the two never met. The reading came
    # out `\psi \text{¯}`, and the span deferred as `accent-not-composed`:
    # 47 crops across the corpus, the fourth largest cause.
    #
    # The geometry was never in doubt -- the macron spans [261.4,267.3] over
    # a psi centred at 262.8. It is the span boundary that separated them.
    for _g in ordered:
        if _g.tex.kind == "accent":
            mathish.add(id(_g))

    # AN OVERLAY NEEDS THE GLYPH IT STRIKES, and that glyph is often TEXT.
    #
    # `\neq` is drawn as a zero-width `negationslash` plus an `=`, and the `=`
    # of a relation comes from the roman font. wzlxjtu-014 puts the slash at
    # x=[347.7,347.7] as the LAST glyph of its maths span with the `=` in the
    # next span, so `_merge_negations` -- which runs inside `to_tex` on one
    # span -- never saw the pair and the span deferred as
    # `overlay-not-composed:negationslash`.
    #
    # Both go into the maths span: the overlay, and the one glyph beside it
    # that it can actually negate.
    from structure import _NEGATED
    for _i, _g in enumerate(ordered):
        if _g.tex.kind != "overlay":
            continue
        mathish.add(id(_g))
        for _j in (_i + 1, _i - 1):
            if not 0 <= _j < len(ordered):
                continue
            _n = ordered[_j]
            if (_n.glyphname or "") not in _NEGATED:
                continue
            gap = (max(_g.rect[0], _n.rect[0])
                   - min(_g.rect[2], _n.rect[2]))
            if gap <= 0.35 * max(_g.size, _n.size):
                mathish.add(id(_n))
                break

    def _ismath(g) -> bool:
        return (g.is_math or id(g) in mathish) and id(g) not in textish

    # A SCRIPT is a short run. A long run of smaller glyphs at one size is a
    # separate text block sharing the line -- the line-number gutter of a code
    # listing -- and treating each of its digits as a script produced
    # `\mathrm{L}_{1} \mathrm{istin}_{\mathrm{u}} \mathrm{g}_{\mathbf{si}}`
    # from a caption sitting beside it.
    small_run: dict[int, int] = {}
    run_start = 0
    for idx in range(len(ordered) + 1):
        same = (idx < len(ordered)
                and ordered[idx].size < 0.92 * dom
                and (idx == run_start
                     or abs(ordered[idx].size - ordered[run_start].size)
                     <= 0.05 * dom))
        if not same:
            for k in range(run_start, idx):
                small_run[id(ordered[k])] = idx - run_start
            run_start = idx + 1 if idx < len(ordered) else idx

    for i, g in enumerate(ordered):
        if g.size >= 0.92 * dom or not g.text.strip():
            continue
        if small_run.get(id(g), 1) > 3:
            continue                     # a block, not a script
        # A script attaches to a base on its LEFT. Looking right as well made
        # a footnote marker at the start of a line adopt the first letter of
        # the text as its base: `1http://...` became a maths span `1h`
        # followed by the text `ttp://...`.
        for j in (i - 1,):
            if not 0 <= j < len(ordered):
                continue
            a, b = (ordered[j], g) if j < i else (g, ordered[j])
            if b.rect[0] - a.rect[2] < 0.2 * max(a.size, b.size):
                mathish.add(id(g))
                # A marker after a WORD attaches to the word, not to its last
                # letter. Pulling the letter in split the name and changed
                # its spacing: `Montañ $\\mathrm{o}^{\\mathrm{a},*}$`. The
                # script keeps an EMPTY base instead -- `${}^{a,*}$` -- and
                # the letter stays in the prose where it belongs.
                base = ordered[j]
                in_word = (base.family == "text" and j > 0
                           and ordered[j - 1].family == "text"
                           and base.rect[0] - ordered[j - 1].rect[2]
                           < 0.2 * max(base.size, ordered[j - 1].size, 1.0))
                if base.size >= 0.92 * dom and not in_word:
                    mathish.add(id(base))
                break

    # A structural piece that cannot project -- a radical sign, a fence
    # fragment -- must not be allowed to BREAK A WORD. One from the row below
    # sat between the `n` and the `l` of `only` in x-order, splitting the word
    # into `on` and `ly` and dragging half of it into a deferred span. They
    # are set aside here and rejoin as their own run at the end.
    orphans = [gl for gl in line.glyphs
               if gl.is_math and gl.tex.kind in ("rule", "fragment")
               and glyph_latex(gl) is None]
    skip = {id(gl) for gl in orphans}
    runs: list[list[GlyphNode]] = []
    for g in line.glyphs:
        if id(g) in skip:
            continue
        kind = "math" if _ismath(g) else "text"
        prev = "math" if (runs and _ismath(runs[-1][0])) else "text"
        if runs and prev == kind:
            runs[-1].append(g)
        else:
            runs.append([g])

    # absorb short neutral runs that sit between two maths runs
    NEUTRAL = set("0123456789()[]+-=/.,|<>")

    # Measured on the WHOLE line: a single span rarely holds enough gaps to
    # find the bimodal split, and guessing per span reintroduces the fixed
    # threshold this exists to replace.
    wg = _word_gap(sorted(line.glyphs, key=lambda g: g.rect[0]))

    def _splittable(run: list[GlyphNode]) -> list[list[GlyphNode]]:
        """Split a text run at word gaps.

        `dxi and` is one text run but two things: three maths variables and an
        English word. Absorbing the whole run would wrap the word in maths;
        absorbing none of it leaves the variables stranded outside.
        """
        parts: list[list[GlyphNode]] = [[run[0]]]
        for prev, cur in zip(run, run[1:]):
            gap = cur.rect[0] - prev.rect[2]
            if gap > wg:
                parts.append([cur])
            else:
                parts[-1].append(cur)
        return parts

    def _is_variable_run(run: list[GlyphNode]) -> bool:
        """A short run of single italic letters, digits or operators.

        In MathTime and similar setups the maths font holds Greek and symbols
        while Latin VARIABLES come from the text italic font, so `E`, `d`, `x`
        arrive with family `text`. Upright runs qualify too -- `Spin`, `Cl`,
        `det` are operator names -- but only when they ABUT the mathematics
        (see `_tight`), which is what separates an operator from a prose word
        sitting next to an equation.
        """
        if len(run) > 6:
            return False
        for g in run:
            t = g.text
            if len(t) != 1:
                return False
            if t in NEUTRAL or not t.strip():
                continue
            if not (t.isalpha() and t.isascii()):
                return False
        return True

    # (1) expand text runs into word-level sub-runs so absorption is precise
    expanded: list[list[GlyphNode]] = []
    for run in runs:
        if _ismath(run[0]):
            expanded.append(run)
        else:
            expanded.extend(_splittable(run))
    runs = expanded

    def _tight(a: list[GlyphNode], b: list[GlyphNode]) -> bool:
        """True if two runs abut with no word space between them.

        An operator name is kerned against its argument -- `Spin(n)`, `Cl_n`,
        `det(A)` -- while a prose word is separated by a word space. Without
        this test, absorbing upright runs next to mathematics would swallow
        `on`, `and` and `is` and render them as `\\mathrm{on}`.
        """
        gap = b[0].rect[0] - a[-1].rect[2]
        # Scaled to the word space MEASURED on this line, not a fixed
        # fraction of the type size. An operator name is kerned against its
        # argument and sits far closer than a word space; a fixed threshold
        # let short words -- `the`, `of`, `is` -- next to an equation be
        # absorbed as operator names once run-splitting got finer.
        if gap >= 0.35 * (wg or 0.22 * max(a[-1].size, b[0].size)):
            return False
        # ... and the two runs must actually MEET on the page. A big CMEX
        # radical descends far below its origin: its baseline sits on this
        # line while its ink is 30pt lower, so both an x-gap test and a
        # baseline test accept it. `only` lost its `on` to a radical on the
        # line below, and the deferred span's crop then covered both lines.
        top = min(max(x.rect[3] for x in a), max(x.rect[3] for x in b))
        bot = max(min(x.rect[1] for x in a), min(x.rect[1] for x in b))
        return top - bot > 0.25 * max(a[-1].size, b[0].size)

    # A relation with NO SPACE on either side is punctuation, not mathematics.
    # `a < b` is a comparison; `<omtext` is the start of an XML tag, and this
    # book sets its listings in small roman so the `<` arrives from the maths
    # font (OT1 has no angle brackets). Emitted as maths it became
    # `$<$ omtext xml:id="foo" $>$` and the listing was destroyed.
    GLUED = set("<>=|/")
    i = 0
    while i < len(runs):
        run = runs[i]
        # The whole run, not just a single glyph: `><` between two tags is
        # two relation glyphs side by side, and `.../>` is three.
        if (run and len(run) <= 3 and _ismath(run[0])
                and all(g.text.strip() in GLUED for g in run)):
            tight_l = (i > 0 and not _ismath(runs[i - 1][0])
                       and run[0].rect[0] - runs[i - 1][-1].rect[2]
                       < 0.25 * (wg or 2.0))
            tight_r = (i + 1 < len(runs) and not _ismath(runs[i + 1][0])
                       and runs[i + 1][0].rect[0] - run[-1].rect[2]
                       < 0.25 * (wg or 2.0))
            if tight_l or tight_r:
                for gl in run:
                    mathish.discard(id(gl))
                    textish.add(id(gl))
                merged = list(run)
                lo, hi = i, i + 1
                if tight_l:
                    merged = runs[i - 1] + merged
                    lo = i - 1
                if tight_r:
                    merged = merged + runs[i + 1]
                    hi = i + 2
                runs[lo:hi] = [sorted(merged, key=lambda g: g.rect[0])]
                i = max(lo, 0)
                continue
        i += 1

    # (2) absorb sub-runs that are maths material, not prose.
    #
    # NEUTRALS FIRST, then names. An operator name takes the maths run beside
    # it, and if that happens first the chain breaks: in `Cl_{p+1,q}` the name
    # `Cl` swallowed the `p`, so `+1,` no longer had maths on its left and was
    # stranded, leaving `+1,q` to defer as its own crop.
    def _mathy(idx: int, runs: list) -> bool:
        return 0 <= idx < len(runs) and _ismath(runs[idx][0])

    for names_pass in (False, True):
        i = 0
        while i < len(runs):
            run = runs[i]
            if run[0].is_math or id(run[0]) in mathish:
                i += 1
                continue
            left_any, right_any = _mathy(i - 1, runs), _mathy(i + 1, runs)
            left = left_any and _tight(runs[i - 1], run)
            right = right_any and _tight(run, runs[i + 1])
            neutral = all(g.text.strip() in NEUTRAL or not g.text.strip()
                          for g in run)
            if not names_pass:
                absorb = left_any and right_any and neutral
                take_left, take_right = left_any, right_any
            else:
                # Only absorb into a maths run that can actually be PROJECTED.
                # A radical, a fence piece or a bare accent is not a symbol a
                # name attaches to; letting one absorb prose is how `only`
                # lost its `on` to a `\sqrt` sign on the line below.
                def _solid(idx: int) -> bool:
                    run2 = runs[idx]
                    nearest = run2[-1] if idx < i else run2[0]
                    return glyph_latex(nearest) is not None

                # A run already forced to text -- monospace, or a glued
                # relation -- must not be absorbed back into mathematics.
                forced = any(id(gl) in textish for gl in run)
                # 775 -- A SINGLE ITALIC LETTER ON A DISPLAY LINE IS A
                # VARIABLE, and it is not kerned against its neighbour.
                #
                # `_tight` exists to keep prose words -- `on`, `and`, `is` --
                # out of the mathematics beside them, and it measures the
                # line's own word space. On a line that is ALL mathematics
                # there is no word space to measure, so the threshold comes
                # out at kerning scale and the ordinary spacing TeX puts
                # around an operator looks like a paragraph break.
                #
                # Obertelli & Sagawa page 673: `n + e^+ <-> p + \bar{\nu}_e`.
                # The `e` was rescued by the script rule above (its `+` proves
                # its base is maths); `n` and `p` carry no script, so they
                # stayed prose and came out `\text{n}`, `\text{p}` -- upright,
                # where the page sets them italic, in a book whose maths Latin
                # letters ARE Times-Italic (MathTime: the maths font holds the
                # Greek and the symbols). One line, two spellings of the same
                # kind of thing.
                #
                # ONE letter, not a run: `and` is three, and no relaxation
                # here can reach it. Adjacency to mathematics is still
                # required, and the line must be a display.
                _solo = (_mostly_math and len(run) == 1
                         and run[0].text.strip().isalpha()
                         and is_italic(run[0].fontname))
                _l_ok = left_any and _solid(i - 1) and (left or _solo)
                _r_ok = right_any and _solid(i + 1) and (right or _solo)
                absorb = (not forced and (_l_ok or _r_ok)
                          and _is_variable_run(run))
                take_left = _l_ok
                take_right = _r_ok
            if absorb:
                # 775 -- ABSORBED MEANS MATHEMATICAL, and the next run along
                # has to be able to see that. A run's kind is read off its
                # FIRST glyph, so a text glyph absorbed on the LEFT of a maths
                # run leaves the merged run starting with text -- and the next
                # letter over then finds no mathematics beside it and stays
                # prose. `n + p` came out `$n+$ \text{p}`: one absorbed, one
                # not, for no reason on the page.
                mathish.update(id(gl) for gl in run)
                merged = list(run)
                if take_left:
                    merged = runs[i - 1] + merged
                if take_right:
                    merged = merged + runs[i + 1]
                lo = i - 1 if take_left else i
                hi = i + 2 if take_right else i + 1
                runs[lo:hi] = [sorted(merged, key=lambda g: g.rect[0])]
                i = max(lo, 0)
                continue
            i += 1

    if orphans:
        # Orphans are kept OUT of run-building so they cannot break a word,
        # but they must still block projection: a fence fragment is half of a
        # built-up bracket, and a span that ignores it emits `\{ ( ) \}` with
        # the matrix entries scattered beside it. Nonsense is worse than a
        # crop, so each orphan rejoins the nearest maths run and makes it
        # defer.
        for orph in orphans:
            best, best_d = None, None
            for r_i, r in enumerate(runs):
                if not (r[0].is_math or id(r[0]) in mathish):
                    continue
                d = min(abs(orph.rect[0] - x.rect[2]) for x in r)
                if best_d is None or d < best_d:
                    best, best_d = r_i, d
            # ... but only to a run it genuinely ABUTS. A radical belonging
            # to another row is near nothing on this line; attaching it to
            # the nearest maths run regardless made that span defer and its
            # crop cover the prose around it.
            if best is None or best_d > 1.0 * orph.size:
                runs.append([orph])
            else:
                runs[best] = sorted(runs[best] + [orph],
                                    key=lambda g: g.rect[0])
    # 747 -- AN ACCENT MUST NOT BE SEPARATED FROM WHAT IT ACCENTS.
    #
    # TeX emits `\hat{F}` as the circumflex and then the letter, adjacent in
    # the stream and stacked in the page:
    #
    #     stream 595  circumflex  x=347.02  base=504.23   run A
    #     stream 596  F           x=346.15  base=501.34   run B
    #
    # A run boundary fell between them, so the accent could never be composed
    # -- `accent-not-composed:circumflex`, five crops on one page, and with
    # them four of wzlxjtu-074's six equations, because a display broken by a
    # crop is emitted as inline fragments instead.
    #
    # The evidence that they belong together is not the boundary's to
    # overrule: the next glyph in the STREAM, sitting UNDER the accent and
    # centred on it. Moved across, so the accent pass can see its base.
    for i in range(len(runs) - 1):
        if not runs[i] or not runs[i + 1]:
            continue
        acc = max(runs[i], key=lambda g: g.rect[0])
        if acc.tex.kind != "accent":
            continue
        base = min(runs[i + 1], key=lambda g: g.rect[0])
        if getattr(base, "stream", -1) < 0 or getattr(acc, "stream", -1) < 0:
            continue
        if base.stream != acc.stream + 1:
            continue                      # not the glyph it was drawn for
        if abs(0.5 * (base.rect[0] + base.rect[2])
               - 0.5 * (acc.rect[0] + acc.rect[2])) > 0.6 * acc.size:
            continue                      # not centred over it
        if not (acc.baseline > base.baseline):
            continue                      # an accent sits ABOVE its base
        runs[i] = [g for g in runs[i] if g is not acc]
        runs[i + 1] = sorted(runs[i + 1] + [acc], key=lambda g: g.rect[0])
    runs = [r for r in runs if r]

    dominant = max(g.size for g in line.glyphs)
    for n, run in enumerate(runs):
        rect = (min(g.rect[0] for g in run), min(g.rect[1] for g in run),
                max(g.rect[2] for g in run), max(g.rect[3] for g in run))
        kind = "math" if any(_ismath(g) for g in run) else "text"
        # A span claims a rule that lies within it HORIZONTALLY and
        # VERTICALLY. The vertical test was missing, so one rule was claimed
        # by every span beneath it that shared its x-range: measured on a
        # page of stacked fractions, a single 3.7pt bar at y=707.6 attached
        # to three spans whose glyphs sat at baselines 705.5, 701.1 and
        # 686.7 -- twenty-one points below it. Each of those spans then
        # deferred with reason `fraction`, for a bar belonging to another.
        mine = [r for r in line.rules
                if r.rect[0] >= rect[0] - 4 and r.rect[2] <= rect[2] + 4
                and rect[1] - 0.5 * dominant <= 0.5 * (r.rect[1] + r.rect[3])
                <= rect[3] + 0.5 * dominant] \
            if kind == "math" else []
        out.append(Span(id=f"{line.id}s{n}", kind=kind, rect=rect,
                        glyphs=run, rules=mine, line_size=dominant,
                        word_gap=wg))
    return out


@dataclass
class LineNode:
    id: str
    page: int
    rect: Rect
    type: str                    # "text" | "formula"
    glyphs: list[GlyphNode] = field(default_factory=list)
    rules: list[RuleNode] = field(default_factory=list)
    merged: int = 0              # fragments collapsed into delimiters
    rotated: bool = False        # sideways text: a stamp, a margin note

    @property
    def stream(self) -> int:
        """Earliest content-stream position in this line, or -1."""
        known = [g.stream for g in self.glyphs if g.stream >= 0]
        return min(known) if known else -1

    @property
    def verbatim(self) -> bool:
        """Is this line set in a typewriter face?

        Judged on the LETTERS, not every glyph: the punctuation of a code
        listing is borrowed from other fonts -- `<` and `>` come from the
        maths font, since OT1 has no angle brackets -- so counting those
        would hide the monospace body.
        """
        letters = [g for g in self.glyphs if g.text.strip().isalnum()]
        if len(letters) < 3:
            return False
        mono = sum(1 for g in letters if is_monospace(g.fontname))
        return mono >= 0.6 * len(letters)

    @property
    def spans(self) -> list[Span]:
        return _spans(self)

    @property
    def flat(self) -> bool:
        """True if this line can be projected to LaTeX without a layout tree.

        Requires one baseline, no rules, and every glyph projectable. A line
        that fails this is NOT emitted as LaTeX — it is deferred.
        """
        if self.rules:
            return False
        if any(g.tex.latex is None for g in self.glyphs):
            return False
        if not self.glyphs:
            return False
        return _is_level(self.glyphs)


@dataclass
class FillNode:
    """A filled rectangle: a cell background, a highlight, a rule of colour.

    Captured because the fill often CARRIES MEANING that the glyphs do not.
    In a heatmap table the cell colour is the result -- green for the best,
    red for the worst -- and a reader who gets only the numbers loses the
    comparison the table was built to show.
    """
    rect: Rect
    color: tuple[float, float, float] | None = None


@dataclass
class LinkNode:
    """A PDF link ANNOTATION: a rectangle plus where it points.

    Annotations live outside the content stream, so nothing in the drawn page
    reveals them -- yet they carry what the text cannot. A citation `[22]` is
    just two digits on the page; its annotation says `cite.polly`, the
    author's own BibTeX key. A footnote marker points at `Hfootnote.1`, and an
    external reference carries its URI.
    """
    rect: Rect
    uri: str | None = None
    dest: str | None = None

    @property
    def citekey(self) -> str | None:
        """The BibTeX key, for a citation link."""
        if self.dest and self.dest.startswith("cite."):
            return self.dest[5:]
        return None


@dataclass
class PageNode:
    page: int
    rect: Rect
    lines: list[LineNode] = field(default_factory=list)
    diagrams: list[Rect] = field(default_factory=list)
    links: list[LinkNode] = field(default_factory=list)
    fills: list[FillNode] = field(default_factory=list)
    invisible: bool = False      # an OCR layer: refuse to project
    #: 781 -- the grid properties of every code listing on this page, read
    #: off the glyphs by `listings.accumulate` once the lines exist. The
    #: projectors READ this; none of them measures a listing itself.
    listings: list = field(default_factory=list)
    #: Rectangles DRAWN on the page that enclose something -- a listing's
    #: `frame=single`, a table cell. The only boundary that does not depend
    #: on the font, and the only one that separates a listing from the
    #: caption above it. `listings.frames` assembles them from the rules.
    frames: list = field(default_factory=list)


# ------------------------------------------------------------------ U2 / U3
def _walk(obj, out: list) -> None:
    # LTImage is included because a TeX rule does not always arrive as a path.
    # Measured on a dvips-derived PDF: every `\hrule` -- the bar of a
    # fraction, an overline, a radical vinculum -- is a 0.5pt-tall IMAGE
    # inside an LTFigure. Looking only at LTLine/LTRect made every one of
    # them invisible, so `\overline{x}` silently lost its bar and no `\frac`
    # could ever be built on that producer.
    if isinstance(obj, (LTChar, LTLine, LTRect, LTImage)):
        out.append(obj)
        if isinstance(obj, LTChar):
            return
    elif isinstance(obj, LTCurve):
        out.append(obj)
        return
    if hasattr(obj, "__iter__"):
        for child in obj:
            _walk(child, out)


#: How far above its contents' baseline TeX sets each size of big
#: delimiter, in ems. Measured; see `key` in the row grouper.
#: How far above its row's baseline TeX sets each big operator, in ems.
#: Measured; see `key` in the row grouper. An operator built from letters --
#: `\cos`, `\max` -- is not raised at all.
_BIGOP_RAISE = {"summationdisplay": 0.95, "integraldisplay": 1.36}


def _bigop_raise(glyphname: str | None) -> float:
    if not glyphname:
        return 0.0
    if glyphname in _BIGOP_RAISE:
        return _BIGOP_RAISE[glyphname]
    # the rest of CMEX's display-size operators -- product, coproduct, the
    # big set operators -- are cut on the same design size as the summation.
    if glyphname.endswith("display"):
        return 0.95
    return 0.0


#: Longest suffix first: `parenleftbigg` ends with `bigg`, not `big`.
_BIG_DELIM_RAISE = (("bigg", 1.41), ("Bigg", 1.71),
                    ("big", 0.81), ("Big", 1.11))


def _big_delim_raise(glyphname: str | None) -> float:
    """Ems this delimiter is set above the baseline it encloses; 0 if none."""
    if not glyphname:
        return 0.0
    for suffix, ems in _BIG_DELIM_RAISE:
        if glyphname.endswith(suffix):
            return ems
    return 0.0


def _covers_as_overline(rule: "RuleNode", mid: float,
                        group: "list[GlyphNode]") -> bool:
    """Is this rule the `\\overline` drawn on top of a glyph of this group?

    TeX draws the bar to the WIDTH OF THE BOX it covers and places it just
    above that box's top. So it is contained in the glyph's x-range and sits
    within a small band above its top edge -- which is where nothing else in
    a row is: a fraction bar lies on the maths axis, a quarter em above the
    BASELINE and nowhere near the top of anything.

    `_rule_role` must have said overline first; this only asks which line.
    """
    if getattr(rule, "role", None) != "overline":
        return False
    return any(rule.rect[0] >= g.rect[0] - 0.5
               and rule.rect[2] <= g.rect[2] + 0.5
               and -0.10 * g.size <= mid - g.rect[3] <= 0.40 * g.size
               for g in group)


def _off_row_band(grp: list, rules: list, span_pt: float) -> bool:
    r"""Is every glyph of this band OFF-ROW material?

    767 -- "off-row" is not "smaller than the row". A DISPLAY-STYLE FRACTION
    SETS ITS PARTS AT TEXT SIZE: `\frac{1}{2}` beside a 9.96pt row draws its
    `1` and its `2` at 9.96pt, one above the maths axis and one below. So a
    band carrying a fraction fails a pure size test and 733 -- which places
    each script on the band holding its base, by stream -- never looks at it.

    wzlxjtu-031's eighth display is the case:

        band   s m | s-1 m+1 | 1 2 | 2s 2 | s m+1     15 glyphs at 6.97pt
                                                       and 2 at 9.96pt
        row    \partial C - e^{\rho}(C - g (-1, m+1)C

    -- every script of the equation on a line of its own, so the row was
    emitted WITHOUT them and the band as a second block of its own.

    A full-size glyph is off-row when a fraction RULE says so: its centre
    falls in the bar's x-range and its baseline is not the bar's axis, which
    is what makes it a numerator or a denominator rather than a term of the
    row. That is evidence the page drew, not an inference about size.
    """
    # 780 -- A CODE LISTING IS NOT A BAND OF SCRIPTS.
    #
    # 733 places a band of scripts onto the row holding their bases, and asks
    # whether a row is such a band by SIZE alone. A listing is set smaller
    # than the body -- `\ttfamily\tiny` is the ordinary choice -- so on a
    # 10pt page every 6pt line of code qualified, and 733 dissolved it,
    # placing its glyphs per-glyph onto whatever rows the stream pointed at.
    #
    # 2604.22294 sets 25 `lstlisting` blocks that way. Page 19 came out as 14
    # lines where the page has 28, with every other line break gone and the
    # spaces with it:
    #
    #     ## Ordering and Retrieval Questions- The schema should not contain…
    #
    # In a listing a line break is CONTENT. `_spans` already refuses to call
    # a monospace glyph mathematics whatever its family says; the same holds
    # a level up -- a row set in a typewriter face is a line of code, and a
    # script inside code is still code.
    if any(is_monospace(g.fontname) for g in grp):
        return False

    for g in grp:
        if g.size < 0.95 * span_pt:
            continue                     # a script: off-row by size
        cx = 0.5 * (g.rect[0] + g.rect[2])
        if any(r.role == "fraction"
               and r.rect[0] - 1 <= cx <= r.rect[2] + 1
               and abs(g.baseline - 0.5 * (r.rect[1] + r.rect[3]))
               > 0.12 * span_pt
               for r in rules):
            continue                     # a fraction part: off-row by rule
        return False                     # a term of the row itself
    return True


def _rule_role(node: RuleNode, glyphs: list[GlyphNode],
               size: float = 10.0, others: "list[RuleNode]" = ()) -> str:
    """Classify a rule by what sits above and below it.

    A fraction bar has glyphs on both sides; an overline or a radical vinculum
    has glyphs below only. This is geometry, not recognition, and it abstains
    by returning "unknown" rather than picking the likelier option.
    """
    x0, y0, x1, y1 = node.rect
    mid = 0.5 * (y0 + y1)

    # A VINCULUM, named by the sign it starts at. TeX begins the bar exactly
    # at the radical's right edge, and the bar lies within the sign's own box.
    # Classified by CONTENT instead, it fails: the window below is 1.2 em and
    # a radicand can be taller -- wzlxjtu-014's `\sqrt{S_0^2 + S_3^2}` sets its
    # bar 14.8pt above the row, so nothing was found beneath it, the rule came
    # back "unknown", and an unaccounted rule defers the whole span.
    for g in glyphs:
        if not (g.glyphname or "").startswith("radical"):
            continue
        if abs(x0 - g.rect[2]) > 0.6 * max(g.size, 1.0):
            continue
        if g.rect[1] - 1 <= mid <= g.rect[3] + 1:
            return "overline"

    # An UNDERSCORE is drawn as a rule, not a glyph. `took_*` reaches the
    # model as a 3.14pt zero-height rule at the baseline followed by an
    # asterisk, and an unmodelled rule makes the whole span defer -- so a
    # word with an underscore in it came out as a crop.
    #
    # It is told from a fraction bar by HEIGHT: a bar sits on the maths axis,
    # about a quarter em above the baseline, while an underscore sits on or
    # just below the baseline itself.
    near = [g for g in glyphs
            if g.rect[0] < x1 + 2.0 * size and g.rect[2] > x0 - 2.0 * size]
    if near and (x1 - x0) <= 1.2 * size:
        base = min(near, key=lambda g: abs(g.rect[0] - x1)).baseline
        if base - 0.30 * size <= mid <= base + 0.12 * size:
            return "underscore"
    # The search window is VERTICAL, so it must be scaled by the type size.
    # It used the rule's WIDTH: a 5.7pt-wide overline got a 14pt window that
    # reached the line above, found glyphs on both sides, and was called a
    # fraction -- so `\overline{x}` could never be built.
    window = 1.2 * size
    above_b: list[float] = []
    below_b: list[float] = []
    for g in glyphs:
        gx0, gy0, gx1, gy1 = g.rect
        # Centre-in-range, not full containment: the bar of an overline is
        # often a shade NARROWER than the letter under it.
        if not (x0 - 1 <= 0.5 * (gx0 + gx1) <= x1 + 1):
            continue
        # Compare BASELINES, not box edges. An LTChar box is the advance box
        # and spans the whole em, so the bar of an overline falls INSIDE the
        # box of the letter it covers: the box is neither above nor below it,
        # and the rule was classified "unknown". The baseline is unambiguous.
        d = g.baseline - mid
        if 0 < d < window:
            above_b.append(g.baseline)
        elif -window < d < 0:
            below_b.append(g.baseline)
    # A frame rule is not a fraction bar. The border of a code listing runs
    # the width of the text block with code above and below it, which is
    # exactly the geometry of a fraction -- and merging those two rows glued
    # consecutive code lines together: `5 f2(x) = f(x,2)67 xVals, yVals =`.
    # No real fraction bar is tens of ems wide.
    # 735 -- A FRACTION BAR IS ALLOWED TO BE WIDE.
    #
    # This guard was `> 12 em`, to stop a code listing's border being read as
    # a fraction. But TeX sets the fraction rule AS WIDE AS THE WIDER OF
    # NUMERATOR AND DENOMINATOR, so a long denominator makes a long bar.
    # wzlxjtu-045 sets
    #
    #     \frac{1}{\sum_{i=1}^{n} I\{D_i=1, M_i=0, T_i=1\}}
    #
    # whose bar is 160.2pt in 12pt type -- 13.35 em against a 12 em test. It
    # failed by 16pt, was called a separator, and WITH NO BAR THERE IS NO
    # FRACTION: the numerator, the denominator and the head of the equation
    # stayed three separate bands and one two-row display came apart into
    # nine pieces.
    #
    # So the width alone cannot decide it, and the way out is the same rule
    # TeX used to draw it: the bar is the width of the wider group, so one of
    # the two groups must REACH BOTH ITS ENDS. A listing border is the width
    # of the block and the code inside it is inset from both margins, so
    # nothing reaches its ends and it is still a separator.
    if (x1 - x0) > 12.0 * max(size, 1.0):
        span = 0.0
        for side in (1, -1):
            xs = [g.rect for g in glyphs
                  if 0 < side * (g.baseline - mid) < window
                  and x0 - 1 <= 0.5 * (g.rect[0] + g.rect[2]) <= x1 + 1]
            if not xs:
                continue
            reach = max(r[2] for r in xs) - min(r[0] for r in xs)
            span = max(span, reach / max(x1 - x0, 1.0))
        if span < 0.85:
            return "separator"

    # A VERTICAL rule is not a fraction bar, an overline or a radical
    # vinculum -- all of those lie across the text. It is a frame edge or a
    # table border. Measured: a framed code listing draws a zero-width,
    # 11pt-tall rule once PER LINE, 76 on one page, and treating each as an
    # unmodelled rule made every span on the page defer.
    if (y1 - y0) > (x1 - x0):
        return "separator"

    def _is_own_row(baselines: list[float]) -> bool:
        """Do the glyphs on this baseline belong to the bar, or to a line
        that merely passes over or under it?

        Distance cannot tell them apart. Measured: a real numerator sits
        +4.58 above its bar and the denominator -9.50 below; an overline's
        base sits -9.83 below and the TEXT LINE ABOVE lands at +4.57. The
        numbers are the same to within a tenth of a point.

        What differs is extent. TeX sets a fraction bar at least as wide as
        both parts, so a numerator is CONTAINED by the bar. A text line runs
        clean across the page and continues well past it on both sides.
        """
        if not baselines:
            return False
        want = max(set(baselines), key=baselines.count)

        def _belongs_to_another_bar(g, cx) -> bool:
            """Is this glyph a NEIGHBOURING FRACTION's part, not this line?

            `\\frac{a}{b} + \\frac{c}{d}` is an ordinary display, and its two
            numerators share one baseline. Judged by extent alone, `c` lies
            outside bar 1 and looks exactly like a text line running across
            it -- so both bars were demoted and neither fraction was ever
            built. Measured over the PDF2LaTeX gold set: the author wrote
            1,157 fraction bars, 489 were classified `fraction` and 685
            `overline`, and this is what separated them.

            The evidence that settles it is the OTHER BAR. A glyph covered
            by a different rule at the same offset is that fraction's
            numerator or denominator. A text line passing over this bar has
            no bar of its own.
            """
            for o in others:
                if o is node:
                    continue
                ox0, oy0, ox1, oy1 = o.rect
                if not (ox0 - 1 <= cx <= ox1 + 1):
                    continue
                if abs(g.baseline - 0.5 * (oy0 + oy1)) < window:
                    return True
            return False

        outside = 0
        for g in glyphs:
            if abs(g.baseline - want) > 0.1 * max(size, 1.0):
                continue
            cx = 0.5 * (g.rect[0] + g.rect[2])
            if cx < x0 - 1 or cx > x1 + 1:
                # only nearby glyphs count: something on the far side of the
                # page is a different column, not this line continuing
                if abs(cx - 0.5 * (x0 + x1)) < 6.0 * size:
                    if _belongs_to_another_bar(g, cx):
                        continue
                    # 768 -- A SCRIPT IS NOT A TEXT LINE RUNNING ACROSS.
                    #
                    # This counts what else sits on the numerator's baseline
                    # to tell a numerator from a line of text passing over
                    # the bar. A DISPLAY'S SUPERSCRIPTS SIT AT THAT HEIGHT
                    # TOO: wzlxjtu-015 sets
                    #
                    #   S^{(W)}_{ct}=4\int d^5x\sqrt{\gamma}
                    #       [\frac12\sigma^2+\frac34(\phi^0)^2- ...]
                    #
                    # whose numerators `1` and `3` share baseline 190.38 with
                    # the exponents of `\sigma^2` and `(\phi^0)^2`. Those
                    # exponents are outside the bars and have no bar of their
                    # own, so the count was never zero and TWO fraction bars
                    # were classified `overline` -- after which the span
                    # carried an unaccounted rule and refused.
                    #
                    # An overline's base is part of a RUNNING TEXT LINE, and
                    # a running text line is not set in script type. So a
                    # glyph smaller than the surrounding type cannot be the
                    # evidence this test is looking for.
                    if g.size < 0.95 * max(size, 1.0):
                        continue
                    outside += 1
        return outside == 0

    def _sits_under(baselines: list[float]) -> bool:
        """Is there a glyph tucked directly under the bar, about as wide?

        An overline's base is part of a RUNNING TEXT LINE -- `Z X \\bar{Z}` in
        the middle of a sentence -- so it can never be its own row. What marks
        it is local: the bar covers it and is about as wide as it is, because
        TeX draws the accent to the width of what it accents.
        """
        if not baselines:
            return False
        want = max(set(baselines), key=baselines.count)
        bar_w = max(x1 - x0, 0.1)
        # The COMBINED width of what sits under the bar, not the widest single
        # glyph. `\overline{e_1 e_2 e_3}` covers six narrow glyphs and none of
        # them is anywhere near the bar's width, so a single-glyph test found
        # nothing and the rule was left "unknown".
        covered = 0.0
        for g in glyphs:
            if abs(g.baseline - want) > 0.1 * max(size, 1.0):
                continue
            if not (x0 - 1 <= 0.5 * (g.rect[0] + g.rect[2]) <= x1 + 1):
                continue
            covered += g.rect[2] - g.rect[0]
        return covered >= 0.45 * bar_w

    # A numerator must be its OWN row; an overline's base need only sit under
    # the bar. The asymmetry is the point: distance cannot separate the two
    # cases, and extent can, but only on the side where TeX constrains it.
    def _script_fraction() -> bool:
        r"""A `\frac{1}{2}` set in an exponent, judged LOCALLY.

        742 -- wzlxjtu-091 sets eight `(pq)^{\frac12}` on one row. All eight
        bars are 3.7pt wide, all at y=614.7, all with `above_b=[616.0]` and
        `below_b=[609.6]` -- IDENTICAL EVIDENCE -- and `_is_own_row` called
        the first a fraction and the other seven overlines.

        It is not inconsistent, it is non-local: `_is_own_row` counts the
        glyphs on the numerator's baseline that fall OUTSIDE this bar within
        six ems, to catch a text line running across. In a row packed with
        other superscripts there is always something out there, so the
        verdict turns on which neighbours happen to be in range. Seven
        `\frac12` became `\overline{}` and every span holding one refused:
        `fraction` 8 and `fraction+overline` 6 on that page alone.

        What a text line running over a bar CANNOT do is be set at script
        size. TeX sets a fraction inside an exponent smaller than the type
        around it, and it sets the rule to the width of its parts. So:
        material above AND below, both contained by the bar, both smaller
        than the surrounding type, is a fraction -- and no neighbour can
        change that answer.
        """
        if not (above_b and below_b):
            return False
        small = 0.8 * max(size, 1.0)
        for side in (above_b, below_b):
            want = max(set(side), key=side.count)
            near = [g for g in glyphs
                    if abs(g.baseline - want) <= 0.1 * max(size, 1.0)
                    and x0 - 1 <= 0.5 * (g.rect[0] + g.rect[2]) <= x1 + 1]
            if not near or max(g.size for g in near) >= small:
                return False
        return True

    above = _is_own_row(above_b) or _script_fraction()
    below_row = _is_own_row(below_b)
    if above and (below_row or below_b):
        return "fraction"
    if _sits_under(below_b) and not above:
        return "overline"
    return "unknown"


# ----------------------------------------------------------------------- U4
def merge_fragments(glyphs: list[GlyphNode]) -> tuple[list[GlyphNode], int]:
    """Collapse extensible-delimiter pieces into one delimiter glyph.

    Pieces of one built-up fence share an x-range and stack vertically. The
    merged node keeps the union rect and takes `\\left`/`\\right`, whose size
    is set by the content rather than by a size command.
    """
    frags = [g for g in glyphs if g.tex.kind == "fragment"]
    if not frags:
        return glyphs, 0
    rest = [g for g in glyphs if g.tex.kind != "fragment"]
    used: set[int] = set()
    merged: list[GlyphNode] = []
    for i, a in enumerate(frags):
        if i in used:
            continue
        group = [a]
        used.add(i)
        for j, b in enumerate(frags):
            if j in used:
                continue
            # x-overlap: the pieces of one fence sit in the same column
            if min(a.rect[2], b.rect[2]) - max(a.rect[0], b.rect[0]) > 0:
                group.append(b)
                used.add(j)
        rects = [g.rect for g in group]
        union = (min(r[0] for r in rects), min(r[1] for r in rects),
                 max(r[2] for r in rects), max(r[3] for r in rects))
        name = group[0].glyphname or ""
        side = "left" if "left" in name else ("right" if "right" in name else "")
        shape = ""
        for s, tex in (("bracket", "["), ("brace", r"\{"), ("paren", "("),
                       ("angbracket", r"\langle")):
            if name.startswith(s):
                shape = tex
                break
        if side == "right":
            shape = {"[": "]", r"\{": r"\}", "(": ")",
                     r"\langle": r"\rangle"}.get(shape, shape)
        latex = (rf"\{side}{shape}" if side and shape else None)
        kind = "delimiter" if latex else "fragment"
        merged.append(
            GlyphNode(
                id=group[0].id, page=group[0].page, rect=union,
                text="".join(g.text for g in group), cid=group[0].cid,
                glyphname=name, fontname=group[0].fontname,
                family=group[0].family, size=group[0].size,
                tex=TexToken(latex, kind, None, group[0].tex.confidence),
                # A reassembled delimiter keeps the EARLIEST index of the
                # pieces it was built from. Without it the glyph reads -1,
                # and one such glyph makes a whole row fall off every path
                # that needs emission order -- which is why wzlxjtu-072's
                # third display still resolved its limits by x while the
                # fourth, with no extensible delimiter in it, did not.
                stream=min((g.stream for g in group if g.stream >= 0),
                           default=-1),
            )
        )
    out = sorted(rest + merged, key=lambda g: (g.rect[0], g.rect[1]))
    return out, len(frags) - len(merged)


# ----------------------------------------------------------------------- U5
def _is_plain_rule(rect: Rect) -> bool:
    """A thin, axis-aligned bar: a fraction bar, a table rule, an overline."""
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    return (h <= 2.0 and w > 2.0) or (w <= 2.0 and h > 2.0)


def _tiles(rects: list[Rect]) -> set:
    """Indices of marks that STACK into a contiguous band of one width.

    781d — THE DISCRIMINATING FEATURE, WHICH THE NOTE BELOW SAYS WAS NEVER
    FOUND: a listing's marks TILE and a figure's do not.

    listings sets a framed, backgrounded listing LINE BY LINE. Measured on
    a four-line listing with `frame=single` and `backgroundcolor`:

        LTRect  56.69 715.48 555.31 725.35    the background behind line 1
        LTRect  56.69 705.62 555.31 715.48    ... line 2, abutting exactly
        LTRect  56.69 695.76 555.31 705.62    ... line 3
        LTLine  51.51 715.48  51.51 725.35    the left frame, line 1
        LTLine  51.51 705.62  51.51 715.48    ... line 2

    Every one shares an x-range with its neighbours and begins where the
    one above ended. Counting them as drawing made a four-line listing look
    like a figure of twenty marks around forty glyphs, so the whole listing
    was cropped away as a diagram -- glyphs and frame rules together, which
    is why nothing downstream could see either.

    A box-and-arrow figure has marks at many x-ranges and heights and
    stacks nowhere. Three is the smallest run that can be a band rather
    than a coincidence.
    """
    by: dict = {}
    for i, r in enumerate(rects):
        by.setdefault((round(r[0]), round(r[2])), []).append(i)
    out: set = set()
    for idx in by.values():
        if len(idx) < 3:
            continue
        idx.sort(key=lambda i: rects[i][1])
        run = [idx[0]]
        for j in idx[1:]:
            if rects[j][1] <= rects[run[-1]][3] + 1.0:
                run.append(j)
            else:
                if len(run) >= 3:
                    out |= set(run)
                run = [j]
        if len(run) >= 3:
            out |= set(run)
    return out


def _diagram_regions(glyphs: list["GlyphNode"],
                     strokes: list[Rect] | None = None) -> list[Rect]:
    """Bounding rectangles of the diagrams on a page.

    A diagram made with Xy-pic or LaTeX's picture environment contains NO path
    operators: the arrow shaft is a dash glyph stamped repeatedly along the
    line and the head is an arrow-tip glyph. Those glyphs are found first, then
    the box is grown to take in the labels sitting inside it -- `E x F`,
    `E (x) F`, `f (x) f` -- because a diagram without its labels is useless.

    The result is ONE rectangle per diagram, which is what MathPix emits for
    these: a crop, not an attempt at LaTeX.
    """
    # Two ways a figure is drawn, and both occur in the same corpus:
    #   * GLYPH STAMPS -- Xy-pic repeats a dash glyph along the line and caps
    #     it with an arrow-tip glyph. No path operators at all.
    #   * REAL PATHS -- dvips emits `np ... a ... li ... st` (newpath, moveto,
    #     lineto, stroke) and `arc`, which pdfminer reports as LTLine/LTCurve.
    marks: list[Rect] = [g.rect for g in glyphs if is_drawing(g.fontname)]
    marks += list(strokes or [])
    if not marks:
        return []
    size = _dominant_size(glyphs)
    gap = 3.0 * size

    # Clustering on a GRID, not all-pairs. A dense vector figure can carry
    # tens of thousands of path objects -- one page of this corpus has 30,065
    # LTCurves -- and comparing every mark against every cluster member took
    # 83 seconds and 263 million comparisons for that single page.
    #
    # Cell size is the join distance, so any two marks within `gap` are in the
    # same cell or in neighbouring ones. Cells are unioned when their bounding
    # boxes are within `gap`, which is a handful of comparisons per cell
    # rather than per mark.
    cells: dict[tuple[int, int], list[Rect]] = {}
    for r in marks:
        key = (int((0.5 * (r[0] + r[2])) // gap),
               int((0.5 * (r[1] + r[3])) // gap))
        cells.setdefault(key, []).append(r)

    cbox = {k: (min(x[0] for x in v), min(x[1] for x in v),
                max(x[2] for x in v), max(x[3] for x in v))
            for k, v in cells.items()}

    parent = {k: k for k in cells}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for key in cells:
        kx, ky = key
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                other = (kx + dx, ky + dy)
                if other == key or other not in cells:
                    continue
                a, b = cbox[key], cbox[other]
                if (a[0] - gap < b[2] and b[0] - gap < a[2]
                        and a[1] - gap < b[3] and b[1] - gap < a[3]):
                    union(key, other)

    grouped: dict[tuple[int, int], list[Rect]] = {}
    for key, rects in cells.items():
        grouped.setdefault(find(key), []).extend(rects)
    clusters = list(grouped.values())

    # A cluster is a FIGURE only if it has several marks and at least one that
    # is not a plain bar. Without that test a display with two fraction bars
    # close together would be cropped as a diagram and its mathematics lost.
    clusters = [cl for cl in clusters
                if len(cl) >= 3 and any(not _is_plain_rule(r) for r in cl)]
    if not clusters:
        return []

    boxes = []
    counts = []
    cluster_of = list(clusters)
    for cl in clusters:
        boxes.append((min(x[0] for x in cl), min(x[1] for x in cl),
                      max(x[2] for x in cl), max(x[3] for x in cl)))
        counts.append(len(cl))
    # A FRAME is not a figure. A framed code listing is a handful of rules and
    # rounded corners enclosing a page of text -- measured: 7 marks around 850
    # glyphs. Treating it as a diagram deletes the listing from the document.
    # A real figure is the other way round: many strokes, few labels.
    keep = []
    keep_counts = []
    for box, n, cl in zip(boxes, counts, cluster_of):
        enclosed = sum(1 for g in glyphs
                       if box[0] <= 0.5 * (g.rect[0] + g.rect[2]) <= box[2]
                       and box[1] <= 0.5 * (g.rect[1] + g.rect[3]) <= box[3])
        # Count only the marks that are actually DRAWING. A framed listing
        # emits one vertical rule per line -- 76 on one page -- and counting
        # those made the frame look like a dense figure, so the whole listing
        # was cropped as a diagram.
        # A FRAME is not a figure: a framed code listing is a handful of
        # rules and rounded corners enclosing a page of text -- measured, 7
        # marks around 850 glyphs. A real figure is the other way round.
        #
        # This ratio does NOT separate every case. A box-and-arrow figure
        # measured 384 labels around 50 marks (7.7x) and is rejected here,
        # while a framed listing in another document measured 17x and is
        # kept. Marks-on-the-border versus marks-inside was tried as a
        # replacement and separated neither cleanly. The cases overlap, and
        # the discriminating feature has not been found yet.
        _tiled = _tiles(cl)
        drawn = sum(1 for i, r in enumerate(cl)
                    if not _is_plain_rule(r) and i not in _tiled)
        if enclosed > 25 and enclosed > 5 * max(drawn, 1):
            continue
        # Nor is a sliver a figure. The gutter rule of a framed listing is a
        # few points wide and hundreds tall; cropping it yields a picture of
        # a line.
        if min(box[2] - box[0], box[3] - box[1]) < 20.0:
            continue
        keep.append(box)
        keep_counts.append(n)
    boxes, counts = keep, keep_counts
    if not boxes:
        return []

    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if (a[0] - gap < b[2] and b[0] - gap < a[2]
                        and a[1] - gap < b[3] and b[1] - gap < a[3]):
                    boxes[i] = (min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3]))
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break

    out = []
    for box in boxes:
        x0, y0, x1, y1 = box
        # Absorb the labels ONCE, measured against the ORIGINAL drawing box.
        # Growing iteratively cascades: each newly absorbed label extends the
        # box, which reaches further, and the region swallowed the whole page
        # (1623x2265 px where the diagram is 355x188).
        m = 1.2 * size

        def _continues_outside(g) -> bool:
            """Is this glyph part of a line that runs past the figure?

            A figure's label sits inside it; a CAPTION is a line of the
            document that happens to start beside it. Absorbing one glyph of
            the caption drags the whole middle of that line into the region,
            where it is removed from the text flow -- measured: a caption came
            out as `Fig. 6: A heatma` with `p comparing the normalized ...`
            lost inside the picture.
            """
            tol = 0.3 * max(g.size, 1.0)
            for o in glyphs:
                if abs(o.baseline - g.baseline) > tol:
                    continue
                if o.rect[0] < box[0] - m or o.rect[2] > box[2] + m:
                    return True
            return False

        for g in glyphs:
            cx = 0.5 * (g.rect[0] + g.rect[2])
            cy = 0.5 * (g.rect[1] + g.rect[3])
            if box[0] - m <= cx <= box[2] + m and box[1] - m <= cy <= box[3] + m:
                if _continues_outside(g):
                    continue
                x0, y0 = min(x0, g.rect[0]), min(y0, g.rect[1])
                x1, y1 = max(x1, g.rect[2]), max(y1, g.rect[3])
        out.append((x0, y0, x1, y1))
    return out


def _advance_samples(path: str, pages):
    """(font, advance, size, text) for every glyph, for width measurement."""
    try:
        for layout in extract_pages(path, page_numbers=pages, laparams=None):
            stack = list(layout)
            while stack:
                obj = stack.pop()
                if isinstance(obj, LTChar):
                    yield (obj.fontname, obj.adv, obj.size, obj.get_text())
                elif hasattr(obj, "__iter__"):
                    stack.extend(obj)
    except Exception:
        return


def _line_bands(path: str, pages) -> dict[int, list[float]]:
    """Per page, the y BOUNDARIES between the producer's own lines.

    A display equation has no end marker: the producer saves the graphics
    state, draws the expression -- closing and reopening the text object
    around every fraction rule -- and pops it, restoring the current point.
    The only statement of where a line ends is the command that starts the
    NEXT one, and `psstream.line_starts` reads those.

    Measured: page 1 of 91.pdf has 22 line returns and my baseline
    clustering made 85 rows of it. A fraction's numerator, rule and
    denominator are three y values and ONE line.

    The boundary between two lines is the MIDPOINT of their baselines, which
    puts a numerator (above its own baseline) on the right side of it while
    the extra leading of a display keeps it clear of the line above.
    """
    out: dict[int, list[float]] = {}
    try:
        import psstream
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdfdocument import PDFDocument
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdftypes import stream_value
        with open(path, "rb") as fh:
            doc = PDFDocument(PDFParser(fh))
            for idx, page in enumerate(PDFPage.create_pages(doc)):
                if pages is not None and idx not in pages:
                    continue
                pno = idx + 1
                cs = page.contents if isinstance(page.contents, list) \
                    else [page.contents]
                data = b"".join(stream_value(x).get_data() for x in cs)
                ys = psstream.line_starts(psstream.read(data))
                ys = sorted({round(y, 2) for y in ys}, reverse=True)
                out[pno] = [0.5 * (a + b) for a, b in zip(ys, ys[1:])]
    except Exception:
        return {}
    return out


def _stream_index(path: str, pages) -> dict[int, dict[tuple, int]]:
    """Content-stream position for every glyph, keyed by page and position.

    Recorded at `render_char`, which is the interpreter's own callback and
    therefore the producer's order exactly.

    746 -- IT USED TO WALK `extract_pages(laparams=None)`, on the reasoning
    that switching layout analysis off leaves the producer's order alone. It
    does not, and it goes wrong at the one place that matters. wzlxjtu-006
    draws a fraction like this:

        [(+)]TJ 12.956 8.088 Td [(1)]TJ     <- numerator
        ET
        q  1 0 0 1 193.406 525.446 cm
           []0 d 0 J 0.478 w 0 0 m 5.853 0 l S      <- the bar, a STROKED LINE
        Q
        BT
        /F15 11.9552 Tf 193.406 514.256 Td [(8)]TJ  <- denominator, absolute
        /F20 11.9552 Tf 7.049 8.201 Td [(me)]TJ ...

    The text object is ENDED and RESTARTED around the rule, because the rule
    is a path and paths cannot be drawn inside one. Compare the two readings
    of the glyphs after that `+`:

        render_char      +  1  8  m  e  -  6  sigma  [  -  3  2
        extract_pages    +  [  m  e  -  6  sigma  1  8  -  3  2

    The numerator and denominator are moved SEVEN PLACES LATER and the big
    bracket seven places earlier. A fraction and a big delimiter are exactly
    what a BT/ET boundary wraps, so the index was wrong precisely where the
    layout is hard -- and every pass that trusts it (the row sort of 741, the
    script-band merge, the sandwich of 744) inherited that.

    The key is the pen position and the character, which is unique on a page
    in practice.
    """
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager

    out: dict[int, dict[tuple, int]] = {}

    class _Recorder(PDFLayoutAnalyzer):
        """Records every glyph in the order the interpreter draws it."""

        def __init__(self, rm):
            super().__init__(rm, pageno=1, laparams=None)
            self.seen: dict[tuple, int] = {}
            self.n = 0

        def render_char(self, matrix, font, fontsize, scaling, rise, cid,
                        *args, **kw):
            w = super().render_char(matrix, font, fontsize, scaling, rise,
                                    cid, *args, **kw)
            try:
                text = font.to_unichr(cid)
                if not isinstance(text, str):
                    raise TypeError
            except Exception:
                text = "(cid:%d)" % cid
            key = (round(matrix[4], 1), round(matrix[5], 1), text)
            if key not in self.seen:
                self.seen[key] = self.n
            self.n += 1
            return w

    try:
        with open(path, "rb") as fh:
            want = None if pages is None else set(pages)
            for i, page in enumerate(PDFPage.get_pages(fh, pagenos=want)):
                pno = (sorted(want)[i] + 1) if want is not None else i + 1
                rm = PDFResourceManager()
                rec = _Recorder(rm)
                PDFPageInterpreter(rm, rec).process_page(page)
                out[pno] = rec.seen
    except Exception:
        return {}
    return out


def _page_links(path: str, pages: "range | None") -> dict[int, list[LinkNode]]:
    """Link annotations per page number, 1-based.

    Read separately from the layout because annotations are not part of the
    content stream: `extract_pages` never sees them.
    """
    out: dict[int, list[LinkNode]] = {}
    try:
        with open(path, "rb") as fh:
            doc = PDFDocument(PDFParser(fh))
            for i, page in enumerate(PDFPage.create_pages(doc)):
                if pages is not None and i not in pages:
                    continue
                raw = resolve1(page.annots) if page.annots else None
                if not raw:
                    continue
                found: list[LinkNode] = []
                for a in raw:
                    try:
                        a = resolve1(a)
                        sub = a.get("Subtype")
                        if getattr(sub, "name", sub) != "Link":
                            continue
                        rect = [float(v) for v in resolve1(a.get("Rect"))]
                        act = resolve1(a.get("A")) or {}
                        uri = act.get("URI")
                        dest = a.get("Dest") or act.get("D")
                        found.append(LinkNode(
                            rect=(min(rect[0], rect[2]), min(rect[1], rect[3]),
                                  max(rect[0], rect[2]), max(rect[1], rect[3])),
                            uri=uri.decode("latin1") if isinstance(uri, bytes)
                            else uri,
                            dest=dest.decode("latin1")
                            if isinstance(dest, bytes) else
                            (str(dest) if dest is not None else None)))
                    except (TypeError, ValueError, AttributeError):
                        continue
                if found:
                    out[i + 1] = found
    except Exception:
        return {}
    return out


def to_rgb(value) -> tuple[float, float, float] | None:
    """A PDF colour operand as RGB, or None for plain black.

    The operand's shape says which colour space set it, matching the
    operators that produced it:

        g  / G   one number      DeviceGray
        rg / RG  three numbers   DeviceRGB
        k  / K   four numbers    DeviceCMYK

    Lower case sets the non-stroking colour -- the fill, which is what paints
    text -- and upper case the stroking colour, which paints rules and
    borders. Black returns None so that the overwhelmingly common case costs
    nothing downstream.
    """
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            g = float(value)
            return None if g <= 0.001 else (g, g, g)
        parts = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if len(parts) == 1:
        g = parts[0]
        return None if g <= 0.001 else (g, g, g)
    if len(parts) == 3:
        r, g, b = parts
        return None if max(parts) <= 0.001 else (r, g, b)
    if len(parts) == 4:
        c, m, y, k = parts
        rgb = ((1.0 - c) * (1.0 - k), (1.0 - m) * (1.0 - k),
               (1.0 - y) * (1.0 - k))
        return None if max(rgb) <= 0.001 else rgb
    return None


def _sane_rect(bbox, baseline: float, size: float):
    """Repair a vertical box built from a font-wide descent.

    pdfminer sets an LTChar's box to (0, descent, adv, descent + fontsize)
    with `descent` taken from the FONT, not the glyph. For CMEX10 that descent
    is -2.359em, because the font carries the huge extensible pieces -- so
    every big operator, radical and fence reports a box about 28pt below where
    its ink actually is. Measured: a `summationtext` with origin at y=503.4
    reports ink at 475.2-487.2.

    A box that far below its own origin cannot be right, so it is replaced by
    a plausible one around the baseline. Only the vertical extent is touched;
    x is the advance width and is correct.
    """
    x0, y0, x1, y1 = bbox
    if size <= 0:
        return bbox
    if (y0 - baseline) / size > -0.6:
        return bbox                       # an ordinary descent: leave it
    return (x0, baseline - 0.3 * size, x1, baseline + 1.0 * size)


def _dominant_baseline(glyphs: list["GlyphNode"]) -> float:
    """The baseline most of a line's glyphs sit on."""
    if not glyphs:
        return 0.0
    counts: dict[float, int] = {}
    for g in glyphs:
        k = round(g.baseline, 1)
        counts[k] = counts.get(k, 0) + 1
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _dominant_size(glyphs: list["GlyphNode"]) -> float:
    """The type size MOST glyphs are set in (not the largest -- see below)."""
    counts: dict[float, int] = {}
    for g in glyphs:
        k = round(g.size, 1)
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return 10.0
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _group_rotated(glyphs: list["GlyphNode"]) -> list[list["GlyphNode"]]:
    """Group sideways glyphs into runs, ordered along their own writing axis.

    A glyph's text matrix gives the direction it advances in: (a, b) for a
    matrix (a, b, c, d, e, f). For the 90-degree rotation an arXiv stamp uses,
    (a, b) is (0, 1), so the run advances up the page and must be ordered by
    y, not x. Ordering it by x reverses it -- which is why the stamp came out
    as `4102peS82]...viXra`.
    """
    if not glyphs:
        return []
    runs: dict[tuple, list] = {}
    for g in glyphs:
        a, b = round(g.matrix[0], 3), round(g.matrix[1], 3)
        # column key: the coordinate perpendicular to the writing direction
        perp = round(g.rect[0], 0) if abs(b) > abs(a) else round(g.rect[1], 0)
        runs.setdefault((a, b, perp), []).append(g)

    out = []
    for (a, b, _), run in runs.items():
        if abs(b) > abs(a):                       # advances along y
            run.sort(key=lambda g: g.matrix[5], reverse=b < 0)
        else:                                     # advances along x
            run.sort(key=lambda g: g.matrix[4], reverse=a < 0)
        out.append(run)
    return out


def _column_edge(rows: list[list["GlyphNode"]], rect: Rect) -> float | None:
    """Where the SECOND column starts, or None for a single-column page.

    Found from the distribution of row LEFT EDGES, which is what a column
    layout really is: two strong modes, one per column. Coverage-based
    detection fails on a paper like this one, whose full-width tables and
    figures cross the gutter on most pages, so no vertical band is ever
    quiet.
    """
    edges: dict[int, int] = {}
    for r in rows:
        if len(r) <= 8:
            continue
        k = int(min(g.rect[0] for g in r) // 12) * 12
        edges[k] = edges.get(k, 0) + 1
        # A row that ALREADY spans both columns contributes the x just after
        # its widest internal gap. Without this the detection is circular: a
        # page whose rows are all merged shows only one left-edge mode, so no
        # boundary is found, so the rows stay merged.
        ordered = sorted(r, key=lambda g: g.rect[0])
        size = max(g.size for g in r)
        widest, at = 0.0, None
        for a, b in zip(ordered, ordered[1:]):
            gap = b.rect[0] - a.rect[2]
            if gap > widest:
                widest, at = gap, b.rect[0]
        if at is not None and widest >= 1.5 * size:
            k2 = int(at // 12) * 12
            edges[k2] = edges.get(k2, 0) + 1
    if len(edges) < 2:
        return None
    # The first column is the LEFTMOST strong mode, not the most frequent.
    # The two columns of a paper carry almost the same number of lines -- 43
    # and 43 on one page -- and taking the most frequent picked the RIGHT
    # column as "first", after which no second mode could exist and the page
    # fell back to reading across the gutter.
    strongest = max(edges.values())
    strong = [k for k, n in edges.items() if n >= 0.5 * strongest]
    first = min(strong)
    ordered = sorted(((k, n) for k, n in edges.items() if k > first),
                     key=lambda kv: kv[0])
    mid = 0.5 * (rect[0] + rect[2])
    for k, n in ordered:
        # a second mode, well to the right of the first and past the middle,
        # carrying a real share of the rows
        # 748 -- A SECOND COLUMN CARRIES A REAL SHARE OF THE PAGE'S ROWS.
        #
        # The test was `n >= 0.1 * ordered[0][1]` -- a tenth of the FIRST
        # CANDIDATE's own count, which is itself often 1, so any single piece
        # of evidence passed. One display equation's internal `\quad` counts
        # here (a row that spans both columns contributes the x after its
        # widest gap), and on wzlxjtu-058 that produced a gutter at x=280.8
        # on a ONE-COLUMN page whose text runs 85..510 unbroken.
        #
        # What it cost: every row straddling 280.8 was cut. The denominator
        # of equation 4 is `p_{0|0} - p_{0|1}`, drawn as one stream run
        # 403..411; the cut took `p_{0|0}` into one row and `- p_{0|1}` into
        # another, and the equation came out
        #
        #     \frac{p_{0\mid0}}{- p} E[...]  \\  p 0|0 0|1
        #
        # Equation 3 of the same page, identical but for a `+` instead of the
        # `-`, is correct -- its gap at the gutter is 3.4pt against this
        # one's 5.0pt, and that is the whole difference between them.
        #
        # Measured against the SAME mode the `strong` set above uses: the two
        # columns of a real two-column page carry almost the same number of
        # rows (the comment above says 43 and 43). Here the page's dominant
        # mode has 7 rows and the accepted "column" had 1.
        if k > first + 0.25 * (rect[2] - rect[0]) and k > mid * 0.9 \
                and n >= 2:
            # A SMALL margin left of the second column, not the midpoint to
            # the first column's widest line. The midpoint is computed from
            # rows that may still be fragments at this stage, and it landed
            # at x=121 on a page whose columns divide at 312 -- cutting a
            # bullet item in half after `We evaluate T`.
            size = max((max(g.size for g in r) for r in rows if r),
                       default=10.0)
            return float(k) - 0.5 * size
    return None


def _split_local_columns(rows: list[list["GlyphNode"]],
                        rect: Rect) -> list[list["GlyphNode"]]:
    """Split rows inside a full-width REGION that has its own columns.

    Column structure is per-region, not per-page. A figure spanning the text
    width can carry its own two panels -- scheduling commands beside the code
    they generate -- and the page's gutter says nothing about where those
    panels divide. Measured: panel rows merged as
    `1 // Scheduling commands for targeting 8 int i = i0*32+i1`.

    Wide rows are banded by vertical adjacency, and each band is asked where
    ITS text never goes.
    """
    page_w = rect[2] - rect[0]
    wide = [r for r in rows
            if r and (max(g.rect[2] for g in r)
                      - min(g.rect[0] for g in r)) > 0.55 * page_w]
    if len(wide) < 3:
        return rows

    wide.sort(key=lambda r: -max(g.baseline for g in r))
    bands: list[list[list[GlyphNode]]] = []
    for r in wide:
        top = max(g.baseline for g in r)
        size = max(g.size for g in r)
        if bands and abs(max(x.baseline for x in bands[-1][-1])
                         - top) <= 3.0 * size:
            bands[-1].append(r)
        else:
            bands.append([r])

    split_map: dict[int, list[list[GlyphNode]]] = {}
    for band in bands:
        if len(band) < 3:
            continue
        gl = [g for r in band for g in r]
        step = 2.0
        n = max(int(page_w / step) + 1, 1)
        hit = bytearray(n)
        for g in gl:
            a = max(int((g.rect[0] - rect[0]) / step), 0)
            b = min(int((g.rect[2] - rect[0]) / step) + 1, n)
            for i in range(a, b):
                hit[i] = 1
        size = _dominant_size(gl)
        lo = min(g.rect[0] for g in gl)
        hi = max(g.rect[2] for g in gl)
        best = None
        i = 0
        while i < n:
            if hit[i]:
                i += 1
                continue
            j = i
            while j < n and not hit[j]:
                j += 1
            left, right = rect[0] + i * step, rect[0] + j * step
            if (right - left) >= 1.0 * size and left > lo + 4.0 * size \
                    and right < hi - 4.0 * size:
                if best is None or (right - left) > (best[1] - best[0]):
                    best = (left, right)
            i = j
        if best is None:
            continue
        cut = 0.5 * (best[0] + best[1])
        for r in band:
            a = [g for g in r if g.rect[2] <= cut]
            b = [g for g in r if g.rect[0] >= cut]
            if not (a and b and len(a) + len(b) == len(r)):
                continue
            # A real GAP is required, as for the page-level split. Without it
            # the cut lands wherever a glyph edge happens to fall and can go
            # THROUGH A WORD: a full-width caption came out as
            # `Fig. 6: A heatma` and `p comparing the normalized execution`.
            gap = min(g.rect[0] for g in b) - max(g.rect[2] for g in a)
            if gap < 0.8 * max(g.size for g in r):
                continue
            split_map[id(r)] = [a, b]

    if not split_map:
        return rows
    out: list[list[GlyphNode]] = []
    for r in rows:
        out.extend(split_map.get(id(r), [r]))
    return out


# The EXTENDER pieces a delimiter is built from. `vextendsingle` is
# U+23D0 VERTICAL LINE EXTENSION -- not a character, the middle section of a
# scalable bar. `\left| ... \right|` reaches the page as a COLUMN of them
# at one x, each overlapping the next, and every piece was deferred on its
# own: 690 on a single paper, the largest class left in the user's
# 11,716-crop list.
_EXTENDERS = {
    "vextendsingle": "|", "vextenddouble": r"\|",
    "arrowvertex": "|", "arrowvertexdbl": r"\|",
    "bracketleftex": "[", "bracketrightex": "]",
    "parenleftex": "(", "parenrightex": ")",
    "braceex": r"\{", "bracehtipdownleft": r"\{",
}


def _merge_extenders(glyphs: list["GlyphNode"]) -> list["GlyphNode"]:
    """Collapse a vertical stack of delimiter extenders into one delimiter.

    Measured: three `vextendsingle` at x=214.0, boxes 10pt tall stepping 6pt,
    together spanning y 290.1..312.1 -- one bar, drawn in overlapping
    sections because that is how a scalable delimiter is built.

    The stack becomes a single glyph carrying the delimiter's LaTeX and the
    stack's full extent. The extent matters: it is what tells a later pass
    what the delimiter spans.
    """
    by_col: dict[tuple, list[GlyphNode]] = {}
    rest: list[GlyphNode] = []
    for g in glyphs:
        name = (g.glyphname or "").split(".")[0]
        if name in _EXTENDERS:
            by_col.setdefault((round(g.rect[0], 1), name), []).append(g)
        else:
            rest.append(g)
    if not by_col:
        return glyphs
    for (x0, name), col in by_col.items():
        col.sort(key=lambda g: -g.rect[3])
        runs: list[list[GlyphNode]] = [[col[0]]]
        for prev, cur in zip(col, col[1:]):
            # contiguous or overlapping in y continues the same delimiter
            if prev.rect[1] - cur.rect[3] <= 0.5 * max(cur.size, 1.0):
                runs[-1].append(cur)
            else:
                runs.append([cur])
        for run in runs:
            top = max(g.rect[3] for g in run)
            bot = min(g.rect[1] for g in run)
            head = run[-1]                       # the lowest piece
            head.rect = (head.rect[0], bot, max(g.rect[2] for g in run), top)
            head.tex = TexToken(_EXTENDERS[name], "delimiter", None, "corpus")
            rest.append(head)
    return sorted(rest, key=lambda g: (-g.baseline, g.rect[0]))


def _merge_operator_names(glyphs: list["GlyphNode"]) -> list["GlyphNode"]:
    """Collapse a run of upright roman letters spelling a log-like operator.

    TeX sets `\\sup`, `\\min`, `\\lim` in UPRIGHT ROMAN, so they arrive as
    ordinary letters with nothing marking them as one token. Read letter by
    letter they became `\\mathrm{m}\\mathrm{in}`, and a neighbouring glyph
    then attached to one letter as a script: `\\sup` came out as
    `\\mathrm{s}_{<}\\mathrm{u}_{i}\\mathrm{p}_{-}`.

    Only a run that EXACTLY spells a name is merged. `supp` stays as it is,
    because turning a variable name into an operator would be the confident
    wrong answer this project refuses.
    """
    from texmap import operator_name
    # BY LINE, not page-wide.
    #
    # This pass walks a SEQUENCE and asks whether consecutive entries spell a
    # name. It is handed the whole page's upright glyphs, so sorting them by
    # x alone interleaves lines: measured on 72.pdf, the `s`,`u`,`p` of a
    # `\\sup` are adjacent within their line -- baselines all 427.74, sizes
    # all 10.91, gaps 0.00 -- and NOT adjacent in the page-wide x-order.
    # Every precondition the pass tests was satisfied; the ordering never
    # presented the run, which is why it fired zero times corpus-wide.
    #
    # The sibling passes here (`_merge_enclosures`, `_merge_extenders`) use
    # explicit geometric tests and are order-independent. This one is not,
    # so it has to group first.
    by_line: dict[int, list[GlyphNode]] = {}
    for g in glyphs:
        by_line.setdefault(round(g.baseline * 4), []).append(g)
    if len(by_line) > 1:
        out: list[GlyphNode] = []
        for row in by_line.values():
            out.extend(_merge_operator_names(row))
        return out

    ordered = sorted(glyphs, key=lambda g: g.rect[0])
    out: list[GlyphNode] = []
    i = 0
    while i < len(ordered):
        best = None
        # a run is contiguous, same size, same baseline, all upright roman
        for j in range(i + 2, min(i + 10, len(ordered)) + 1):
            run = ordered[i:j]
            if any(g.family not in ("text", "text-cm") or len(g.text) != 1
                   or not g.text.isalpha() for g in run):
                break
            # 781g — NOT IN A TYPEWRITER FACE. TeX sets `\min` from the
            # ROMAN maths font; it has no way to set an operator name in
            # a monospace one. So three typewriter letters spelling `min`
            # are three letters of CODE, and merging them wrote a LaTeX
            # macro into a verbatim line -- page 5 of 1804.10694v5 came
            # back as `for(i1 in 0..\min  ((N-2)%32,32)+2)`, which is the
            # same defect MathPix reported to us from the other side:
            # a code line that picked up maths habits. It also corrupts
            # the SPACING, because the merged glyph keeps the first
            # letter's x and the grid then counts two cells of gap.
            if any(is_monospace(g.fontname) for g in run):
                break
            size = run[0].size
            if any(abs(g.size - size) > 0.1
                   or abs(g.baseline - run[0].baseline) > 0.1 for g in run):
                break
            if any(b.rect[0] - a.rect[2] > 0.12 * size
                   for a, b in zip(run, run[1:])):
                break
            cmd = operator_name("".join(g.text for g in run))
            if cmd:
                # The run must END here. TeX never sets `\sup` immediately
                # followed by another upright roman letter at a tight gap --
                # that is a WORD. `supp` is a variable name, and reading it
                # as `\sup p` would be the confident wrong answer.
                nxt = ordered[j] if j < len(ordered) else None
                if (nxt is not None
                        and nxt.family in ("text", "text-cm")
                        and len(nxt.text) == 1 and nxt.text.isalpha()
                        and abs(nxt.size - run[0].size) <= 0.1
                        and abs(nxt.baseline - run[0].baseline) <= 0.1
                        and nxt.rect[0] - run[-1].rect[2]
                        <= 0.12 * run[0].size):
                    continue
                best = (j, cmd, run)
        if best:
            j, cmd, run = best
            head = run[0]
            head.rect = (run[0].rect[0], min(g.rect[1] for g in run),
                         run[-1].rect[2], max(g.rect[3] for g in run))
            head.text = cmd
            head.tex = TexToken(cmd, "bigop", None, "corpus")
            # `\\max` is MATHS, not text. Left in the text family it came out
            # as `\\text{\\max}`, which renders the command literally.
            head.family = "math-symbol"
            out.append(head)
            i = j
        else:
            out.append(ordered[i])
            i += 1
    return out


def _merge_enclosures(glyphs: list["GlyphNode"]) -> list["GlyphNode"]:
    """Compose an overlay with the glyph it ENCLOSES.

    `\\copyright` in Computer Modern is a ring from the MATHS SYMBOL font
    with a `c` from the TEXT font inside it. Measured on a journal front
    page:

        circlecopyrt  CMSY7  x=[177.6, 185.6]
        c             CMR7   x=[179.8, 183.4]

    Two fonts, so the two glyphs land in different SPANS -- one maths, one
    text -- and no pass that works inside a span can ever see them together.
    It has to happen here, on the raw glyphs, before spans exist.
    """
    from texmap import OVERLAY_PAIRS
    inner_of: dict[int, int] = {}
    for i, g in enumerate(glyphs):
        if not g.glyphname:
            continue
        for j, h in enumerate(glyphs):
            if j == i:
                continue
            if ((g.glyphname, h.text) in OVERLAY_PAIRS
                    and h.rect[0] >= g.rect[0] - 0.5
                    and h.rect[2] <= g.rect[2] + 0.5
                    and abs(h.baseline - g.baseline)
                    <= 0.25 * max(g.size, 1.0)):
                inner_of[i] = j
                break
    if not inner_of:
        return glyphs
    dropped = set(inner_of.values())
    out: list[GlyphNode] = []
    for i, g in enumerate(glyphs):
        if i in dropped:
            continue
        if i in inner_of:
            latex = OVERLAY_PAIRS[(g.glyphname, glyphs[inner_of[i]].text)]
            g.tex = TexToken(latex, "atom", None, "corpus")
            # The composed symbol is TEXT, whatever font its ring came from.
            # Left in the maths family it came out as `$©$` in a copyright
            # line.
            g.family = "text"
            g.text = latex
        out.append(g)
    return out


def _merge_stream_lines(rows: list[list["GlyphNode"]],
                       bands: list[float]) -> list[list["GlyphNode"]]:
    """Merge rows the PRODUCER says are one line.

    `bands` are the y boundaries between the producer's lines. Rows whose
    baselines fall between the same pair of boundaries belong to one line,
    however many y values they occupy -- which is what a fraction and its
    scripts always do.

    Conservative by construction: it only ever JOINS rows that baseline
    clustering separated. It never splits one, so a producer whose stream
    does not express line breaks this way (dvips places absolutely -- 703)
    yields no bands and nothing changes.
    """
    if not bands or len(rows) < 2:
        return rows

    def band_of(row) -> int:
        b = max((g.baseline for g in row), default=0.0)
        n = 0
        for edge in bands:
            if b < edge:
                n += 1
        return n

    merged: dict[int, list] = {}
    order: list[int] = []
    for row in rows:
        if not row:
            continue
        k = band_of(row)
        if k not in merged:
            merged[k] = []
            order.append(k)
        merged[k].extend(row)
    out = []
    for k in order:
        out.append(sorted(merged[k], key=lambda g: g.rect[0]))
    return out


def _rejoin_accents(rows: list[list["GlyphNode"]]) -> list[list["GlyphNode"]]:
    """Move an accent into the row of its base.

    Two routes, in that order:

    STREAM. `\\widetilde{O}` is emitted as the accent at 2635 and the `O` at
    2636 -- adjacent, 2.52pt apart in baseline, which is past the row window.

    GEOMETRY, when the stream cannot answer. Two reasons it cannot: a wide
    accent carries EMPTY TEXT, so the stream index (keyed on position and
    text) never matched it; and a producer may emit the accent several
    positions from its base -- measured, `tildewide` at stream 2337 whose
    base `U` was neither 2336 nor 2338.

    Both routes apply the same three conditions: the base overlaps the accent
    in x, sits BELOW it, and is the nearest such glyph. Those are what makes
    an accent an accent; the stream is only a faster way to find it.
    """
    where: dict[int, int] = {}
    for i, row in enumerate(rows):
        for g in row:
            if g.stream >= 0:
                where[g.stream] = i

    def over(acc, base) -> bool:
        return (base.rect[0] <= acc.rect[2] and base.rect[2] >= acc.rect[0]
                and base.baseline < acc.baseline
                and acc.baseline - base.baseline <= 1.2 * max(acc.size, 1.0))

    moved = False
    for i, row in enumerate(list(rows)):
        for g in list(row):
            if g.tex.kind != "accent":
                continue
            target = None
            for nb in (g.stream + 1, g.stream - 1):
                if g.stream < 0 or nb < 0:
                    continue
                j = where.get(nb)
                if j is None or j == i:
                    continue
                base = next((x for x in rows[j] if x.stream == nb), None)
                if base is not None and over(g, base):
                    target = j
                    break
            if target is None:
                best_d = None
                for j, other in enumerate(rows):
                    if j == i:
                        continue
                    for b in other:
                        if not over(g, b):
                            continue
                        d = g.baseline - b.baseline
                        if best_d is None or d < best_d:
                            target, best_d = j, d
            if target is not None:
                rows[target].append(g)
                rows[i].remove(g)
                where[g.stream] = target
                moved = True
    if moved:
        rows = [r for r in rows if r]
    return rows


def _stream_span(row) -> tuple[int, int] | None:
    """The content-stream range a row occupies, or None if unknown."""
    known = [g.stream for g in row if g.stream >= 0]
    return (min(known), max(known)) if known else None


def _split_by_stream(rows: list[list["GlyphNode"]],
                     max_gap: int = 100) -> list[list["GlyphNode"]]:
    """Split a row where the stream jumps AND the page has a gap.

    Within a real line the producer emits glyphs consecutively. Two panels of
    a figure that share a baseline are hundreds of positions apart, and
    grouping them into one row interleaves them on output:

        1 // Scheduling commands for targeting 8 int i = i0*32+i1

    Geometry alone cannot separate those -- same size, same font, same
    baseline. The stream alone cannot either: a display equation legitimately
    jumps in the stream while staying one line, and splitting on that cost
    Gallier 16 extra crops. BOTH conditions together identify a panel
    boundary: the run changes and the page shows a space where it changes.
    """
    out: list[list[GlyphNode]] = []
    for row in rows:
        ordered = sorted(row, key=lambda g: g.rect[0])
        if len(ordered) < 2 or any(g.stream < 0 for g in ordered):
            out.append(row)
            continue
        groups: list[list[GlyphNode]] = [[ordered[0]]]
        for prev, cur in zip(ordered, ordered[1:]):
            size = max(prev.size, cur.size, 1.0)
            # A listing's line number and its code are ONE line however far
            # apart they sit and however separately they were emitted. The
            # gutter is a small non-monospace numeral; the code is
            # monospace. Measured: a gutter 34pt from its code, emitted 1460
            # stream positions earlier, was split off and its five lines came
            # out as bare numbers with the code in a fence of its own.
            if (prev.text.strip().isdigit()
                    and not is_monospace(prev.fontname)
                    and is_monospace(cur.fontname)
                    and prev.size < cur.size
                    and abs(prev.baseline - cur.baseline) < 0.5):
                groups[-1].append(cur)
                continue
            stream_jump = abs(cur.stream - prev.stream) > max_gap
            # 4 em, chosen by sweep. At 1.5 a listing's line-number gutter
            # was cut from its code (the gutter is its own stream run too,
            # but only a small gap away); at 8 the figure panels merged
            # again. 4 keeps both, on three documents.
            spatial_gap = (cur.rect[0] - prev.rect[2]) > 4.0 * size
            if stream_jump and spatial_gap:
                groups.append([cur])
            else:
                groups[-1].append(cur)
        out.extend(groups if len(groups) > 1 else [row])
    return out


def _split_at_columns(rows: list[list["GlyphNode"]],
                      edge: float | None) -> list[list["GlyphNode"]]:
    """Cut any row that straddles a column gutter.

    A row is split only where it has an INTERNAL GAP over the gutter, so a
    full-width title or caption -- whose text runs straight across -- is left
    whole. Without this, a table row in the left column and a listing line in
    the right arrive as one row and are sorted together by x:
    `GPU code generation Yes No Yes Yes Yes 45 Computation bx(i, j, c)`.
    """
    if edge is None:
        return rows
    out: list[list[GlyphNode]] = []
    for row in rows:
        row = sorted(row, key=lambda g: g.rect[0])
        left = [g for g in row if g.rect[2] <= edge + 0.5]
        right = [g for g in row if g.rect[0] >= edge - 0.5]
        # Split only when there is a real GAP at the boundary. "Cleanly on
        # both sides" is not enough: a full-width row of continuous text also
        # satisfies it, and gets cut wherever a glyph edge happens to fall.
        # A column break has a gutter; running text does not.
        gap = (min(g.rect[0] for g in right) - max(g.rect[2] for g in left)
               if left and right else 0.0)
        size = max((g.size for g in row), default=10.0)
        if (left and right and len(left) + len(right) == len(row)
                and gap >= 0.8 * size):
            out.append(left)
            out.append(right)
        else:
            out.append(row)
    return out


def _group_lines(glyphs: list[GlyphNode],
                 tol_factor: float = 0.45,
                 rect: Rect | None = None,
                 line_bands: list | None = None) -> list[list[GlyphNode]]:
    """Group glyphs into visual lines by BASELINE, not by box overlap.

    Box overlap fails on mathematics: a display equation is two or three times
    the height of a text line, so its box overlaps the prose above and below
    and sorting the merged result by x interleaves two sentences character by
    character. Baselines do not have that problem.

    EVERY glyph gets a row of its own first, and script rows are folded back
    into their base afterwards. The earlier version picked "anchor" glyphs by
    size relative to the page's dominant size and attached the rest to the
    nearest anchored row -- which works only while there is ONE body size. A
    page carrying 1472 glyphs at 10.9pt and 1259 at 10.0pt anchors only the
    first, and the entire second block was distributed into whatever rows lay
    nearest, scrambling a chapter of prose and a code listing together.
    """
    if not glyphs:
        return []

    def key(g: "GlyphNode") -> float:
        # A big operator carrying limits is raised above the text baseline so
        # that operator and limits centre on the maths axis.
        #
        # 750 -- BY HOW MUCH DEPENDS ON THE OPERATOR, and it was one blanket
        # 0.7 em for all of them. Measured over 60 documents, as the raise
        # above the baseline of the nearest full-size glyph beside it:
        #
        #     summationdisplay   n=18   0.95 em   (17 of 18 exactly)
        #     integraldisplay    n=14   1.361 em  (10 of 14 exactly)
        #     c P l m s d t e k i        0.000 em  (exact, 100+ samples)
        #
        # The last row is every operator built from LETTERS -- `\cos`, `\max`,
        # `\sup`; the merge marks the head letter `bigop`, and it sits on the
        # ordinary baseline like the text it is. Lowering it 0.7 em was
        # moving it off its own row.
        #
        # An integral is raised HALF AN EM MORE than a sum, which is why one
        # constant could not serve both: wzlxjtu-024 sets
        # `\int dx\,\rho(x) = 1` with the integral at baseline 446.22 and its
        # body at 431. Corrected by 0.7 em the integral keys to 437.8 and
        # landed in the PROSE LINE above -- "...normalized as" -- so the
        # equation came out as `dx \rho(x) = 1` with no integral at all.
        #
        # The box centre was tried instead of a table, since TeX centres these
        # on the maths axis: it fits the letter operators (0.06 em, tight) and
        # NOT the CMEX ones (sum 1.05, int 1.23), because pdfminer's box for a
        # CMEX glyph does not report its real depth. Measured, not assumed.
        if g.tex.kind == "bigop":
            return g.baseline - _bigop_raise(g.glyphname) * g.size
        # 743 -- AND SO IS A BIG DELIMITER, BY A MEASURED AMOUNT.
        #
        # `\bigl(` is set on the maths axis, not on the baseline of what it
        # encloses, so baseline clustering put a row's big parentheses ONE
        # BAND ABOVE their own contents. When the contents happened to fall
        # in the same merged band it worked; when the band boundary fell
        # between them the delimiters were orphaned and came out as EMPTY
        # PAIRS -- `\bigl( \bigr)\bigl( \bigr)` with the mathematics gone.
        # 75 of those over the corpus, in 14 documents.
        #
        # wzlxjtu-093's first line is the clean case: everything below its
        # fraction bar is TEN DELIMITERS AND NOTHING ELSE, on baseline 670.0,
        # while the denominator they enclose sits on 660.3 in the next band.
        #
        # MEASURED over the corpus, as the raise in ems of a delimiter above
        # the nearest full-size glyph beside it:
        #
        #     big    n=67   0.81 em   (39 of 67 exactly)
        #     Big    n=12   1.11 em   ( 9 of 12 exactly)
        #     bigg   n=37   1.41 em
        #     Bigg   n=2    1.71 em
        #
        # 0.81, 1.11, 1.41, 1.71 -- a step of 0.30 em per size, which is how
        # TeX grows \big \Big \bigg \Bigg. The table is that progression, not
        # four independent constants.
        if g.tex.kind == "delimiter":
            raise_em = _big_delim_raise(g.glyphname)
            if raise_em:
                return g.baseline - raise_em * g.size
        return g.baseline

    # Compare against each row's FIRST glyph, not a running mean, and take
    # the NEAREST row rather than the first that fits. A mean drifts as
    # glyphs join: one 2.5pt below pulls it down, the next 2.5pt below that
    # still fits, and the chain walks from one line into the next. Whole code
    # listings merged that way -- `5 f2(x) = f(x,2)67 xVals, yVals = ...`.
    rows: list[list[GlyphNode]] = []
    row_key: list[float] = []
    for g in sorted(glyphs, key=lambda g: (-key(g), g.rect[0])):
        k = key(g)
        # A TIGHT tolerance, and it has to be tighter than it looks. Two
        # columns of the same paper do NOT share baselines: measured offsets
        # of 2.887pt on one page and 1.0pt on another. A window scaled at
        # 0.3em gave a 10pt glyph 3.0pt of reach, and at 0.12em still 1.2pt --
        # in both cases enough for the LARGER glyphs of a small-caps word to
        # jump to the neighbouring column while the smaller ones stayed,
        # tearing the word in half at the font change:
        #
        #     not only does T          II. R
        #     IRAMISU introduce        ELATED WORK
        #
        # Small caps share the BASELINE of the word they belong to; only the
        # font and size differ. Scripts sit on their own baseline and are
        # rejoined afterwards by the fold. So this window only has to absorb
        # rounding noise, not typography.
        tol = 0.08 * max(g.size, 1.0)
        best, best_d = None, None
        for i, rk in enumerate(row_key):
            d = abs(rk - k)
            if d <= tol and (best_d is None or d < best_d):
                best, best_d = i, d
        if best is None:
            rows.append([g])
            row_key.append(k)
        else:
            rows[best].append(g)

    # Columns are separated BEFORE scripts are folded. Folding first lets a
    # row reach across the gutter -- the left column's text and the right
    # column's text share a baseline -- and once they are one row the column
    # split can no longer tell which glyph belongs where. Measured: a bullet
    # item came out as `We evaluate T` on one line and
    # `• IRAMISU on a set of deep learning and linear` on another.
    rows = _split_by_stream(rows)
    if rect is not None:
        rows = _split_at_columns(rows, _column_edge(rows, rect))

    # Fold a SCRIPT row into the row it belongs to: clearly smaller, close by,
    # and overlapping it horizontally. Anything else is a text block in its
    # own right, however small -- a 9pt code listing beside 10.9pt prose.
    changed = True
    while changed:
        changed = False
        rows.sort(key=lambda r: -sum(key(x) for x in r) / len(r))
        for i, r in enumerate(rows):
            # A SCRIPT row is short. A whole line is not a script, however
            # much smaller it is than its neighbour: a listing set beside a
            # larger panel label `(a)` folded two complete code lines into
            # the label's row, interleaving them character by character as
            # `(a)45 /V/arTiil0i,ngj0a,ndi1p,arja1l;lelization.`
            # A script row is short.
            #
            # 695/696: the CONTENT STREAM says more than this. A definition's
            # superscripts and subscripts each gather into a row of their
            # own -- measured, superscripts at stream 1013..1044 and
            # subscripts at 1018..1047, both INSIDE the main line's
            # 922..1053, because the producer emitted base, superscript,
            # subscript, base, ... Folding on that containment DID reassemble
            # the expression, and measured WORSE on all fourteen corpus
            # documents (e.g. 84.4% -> 79.8%, crops 327 -> 403), because the
            # scripts then land in a row where attachment still goes by x and
            # the nearest glyph collects them: `\emptyset;_{P}a_{,}n_{A}d`.
            #
            # The fold is right and the ATTACHMENT is what must change first.
            # Not enabled until `_attach_scripts` can bind a script to the
            # base it was emitted beside.
            if len(r) > 6:
                continue
            s_size = max(x.size for x in r)
            s_key = sum(key(x) for x in r) / len(r)
            rx0 = min(x.rect[0] for x in r)
            rx1 = max(x.rect[2] for x in r)
            best, best_d = None, None
            for j, other in enumerate(rows):
                if i == j:
                    continue
                o_size = max(x.size for x in other)
                if s_size >= 0.85 * o_size:
                    continue                  # not a script: a block
                d = abs(sum(key(x) for x in other) / len(other) - s_key)
                if d > 0.75 * o_size:
                    continue
                ox0 = min(x.rect[0] for x in other)
                ox1 = max(x.rect[2] for x in other)
                if rx1 < ox0 - o_size or rx0 > ox1 + o_size:
                    continue                  # nowhere near it horizontally
                if best_d is None or d < best_d:
                    best, best_d = j, d
            if best is not None:
                rows[best].extend(r)
                del rows[i]
                changed = True
                break

    # An ACCENT joins the row of the glyph it was emitted beside.
    #
    # `\widetilde{O}` reaches the page as the accent at stream 2635 and the
    # `O` at 2636 -- adjacent in the stream, 2.5pt apart in baseline, which
    # is past the row window. So the accent lands in a row of its own and
    # the composition never happens: measured, 703 `tildewide`, 130
    # `hatwide` and their wider sizes on one paper, every one a crop.
    #
    # Geometry cannot fix this by widening the window, because 2.5pt is also
    # the distance to a script on the line above. The emission order can.
    # NOT CALLED. `_merge_stream_lines(rows, line_bands)` produces the
    # producer's own line structure and it is correct -- 91.pdf goes from 72
    # rows to 21, against 22 line returns in its stream. Enabling it measured:
    #
    #     display blocks    817 -> 98      (gold 421; now UNDER)
    #     crops             548 -> 1303
    #     maths projected   ~88% -> 62.4%
    #     script-attachment failures        1532
    #     within one of gold  32 -> 22
    #
    # Every metric except the row count got worse, because `_attach_scripts`
    # cannot handle a whole display line with all its scripts in one row --
    # which is exactly what 696 measured when it tried the same fold from the
    # other direction and reverted for the same reason.
    #
    # The rows are right and the pass that consumes them is not. Attachment
    # by stream adjacency has to come first; then this line is uncommented.
    rows = _rejoin_accents(rows)

    # Again AFTER the fold: folding a script row into its base can bridge two
    # runs the stream says were never together, putting the line numbers of
    # one listing line onto the next.
    rows = _split_by_stream(rows)
    return [sorted(r, key=lambda g: g.rect[0]) for r in rows]


def build(path: str, pages: Iterable[int] | None = None) -> list[PageNode]:
    """Build the document model. One GlyphNode per LTChar, no exceptions."""
    out: list[PageNode] = []
    links_by_page = _page_links(path, pages)
    stream_by_page = _stream_index(path, pages)
    # The producer's own line structure, where the stream states it.
    line_bands_by_page = _line_bands(path, pages)
    # Which fonts are monospace IN THIS DOCUMENT, measured from advance
    # widths. Names are unreliable: a publisher's subset can be called
    # anything, and this journal sets its listings in a proportional face.
    set_measured_monospace(measure_monospace(_advance_samples(path, pages)))
    for idx, layout in enumerate(extract_pages(path, page_numbers=pages)):
        pno = (list(pages)[idx] + 1) if pages is not None else idx + 1
        items: list = []
        for e in layout:
            _walk(e, items)

        glyphs: list[GlyphNode] = []
        rules: list[RuleNode] = []
        strokes: list[Rect] = []
        fills: list[FillNode] = []
        invisible = 0
        for n, o in enumerate(items):
            if isinstance(o, LTChar):
                fam = family_of(o.fontname)
                if o.invisible:
                    invisible += 1
                # A font with NO /Encoding gets StandardEncoding names from
                # pdfminer, and the fork reports them as if they were the
                # font's own. In a symbol font they are certainly wrong:
                # TeX-matha10 cid 112 came through as `p` and RENDERS as
                # `(`, so `\pi^{*}(\omega_{0})` was read as
                # `\pi^{*}p\omega_{0}q`. The CID is right; only the name is
                # wrong. Before the fork there was no name and the span
                # deferred, which was correct -- so the fork turned an
                # abstention into a confident wrong answer.
                gname = o.glyphname
                verified = tex_slot(o.fontname, o.cid)
                if verified:
                    gname = verified
                # 779 -- AND ASK THE PACKAGE'S OWN DECLARATION FILE.
                #
                # `texmap.MATHABX` is `mathabx.dcl` read out, 573 (font,
                # slot) -> name pairs, and it was consulted only by
                # `texpackages` -- to decide which packages a PREAMBLE needs.
                # Nothing ever asked it what a CID means, so the two
                # documents it was built from still lost their mathematics:
                # 31 of the corpus's 228 crops, all `unmapped-glyph`, all in
                # wzlxjtu-001 and -002, the AAAI templates that load it.
                #
                # It runs after `tex_slot` because that table was verified by
                # RENDERING each slot at 500dpi, which outranks a
                # declaration file; and it abstains where the file is silent
                # rather than guessing the macro from the name.
                if not verified:
                    _mx = texmap.mathabx_tex(
                        texmap.mathabx_slot(o.fontname, o.cid))
                    if _mx is not None:
                        gname = _mx
                elif untrusted_name(o.fontname, gname):
                    gname = None
                if not gname:
                    # A subsetted CM font can arrive with no names at all, and
                    # the CID still carries the identity -- the CM encodings
                    # are fixed. See `texmap.CM_ENCODING`, built from the 102
                    # documents that DO name these glyphs (391 pairs, none
                    # ambiguous). Without it a page re-rendered through
                    # MathPix deferred 24 of its 36 maths spans on `\partial`,
                    # `\prime` and `-`.
                    gname = texmap.cm_glyphname(o.fontname, o.cid)
                if not gname and texmap.symbol_pua_latex(
                        o.get_text(), o.fontname) is not None:
                    # 787 — THE IDENTITY WAS IN THE ToUnicode ALL ALONG. A
                    # subsetted Symbol font arrives with no glyph names at
                    # all, so the PUA codepoint the ToUnicode gives is the
                    # only thing that says which glyph this is — and it says
                    # it exactly, because that codepoint IS 0xF000 plus the
                    # font's own byte. Same shape as `cm_glyphname` above:
                    # recover the name the subsetting threw away, from
                    # evidence the font itself supplies, gated on the font.
                    #
                    # Without this the table added to texmap was unreachable:
                    # `project` keys on the glyph NAME, and there was none.
                    gname = o.get_text()
                glyphs.append(
                    GlyphNode(
                        id=f"p{pno}g{n}", page=pno,
                        rect=_sane_rect(o.bbox, o.matrix[5], o.size),
                        text=o.get_text(), cid=o.cid, glyphname=gname,
                        fontname=o.fontname, family=fam, size=o.size,
                        tex=project(fam, gname, o.cid, o.fontname), matrix=o.matrix,
                        # 778 -- A FLIPPED MATRIX IS NOT A ROTATION.
                        #
                        # Rotation lives in the matrix's b and c. A matrix
                        # (1, 0, 0, -1, x, y) has neither: it reflects the
                        # glyph's own y axis, which is what a producer that
                        # works in screen coordinates emits, and the text
                        # still reads left to right. pdfminer calls it
                        # not-upright, and this reader sends anything
                        # not-upright to the ROTATED pipeline -- where it is
                        # treated as a stamp or a margin note and kept out of
                        # the flow entirely.
                        #
                        # 2002.06055 draws its blackboard letters that way.
                        # The `\fieldc` of `(\Hilb, \cotimes, \fieldc)`
                        # became a one-glyph rotated line of its own and the
                        # reading came out `(\mathrm{Hilb}, \hat{\otimes},
                        # )` -- a symbol dropped between a comma and a
                        # bracket with nothing to show it had gone.
                        #
                        # A real 90-degree stamp has b and c NON-zero
                        # (0, 1, -1, 0) and is still refused, which is what
                        # keeps `arXiv:0805.0311v3` out of the prose.
                        upright=bool(o.upright) or (abs(o.matrix[1]) < 1e-6
                                                    and abs(o.matrix[2]) < 1e-6),
                        color=to_rgb(getattr(
                            getattr(o, "graphicstate", None), "ncolor", None)),
                        stream=stream_by_page.get(pno, {}).get(
                            (round(o.matrix[4], 1), round(o.matrix[5], 1),
                             o.get_text()), -1),
                    )
                )
            else:
                x0, y0, x1, y1 = o.bbox
                h, w = y1 - y0, x1 - x0
                if isinstance(o, LTImage) and not (
                        (h <= 2.0 and w > 2.0) or (w <= 2.0 and h > 2.0)):
                    continue          # a real image, not a rule
                strokes.append(o.bbox)
                if getattr(o, "fill", False):
                    col = to_rgb(getattr(o, "non_stroking_color", None))
                    if col is not None and col != (1.0, 1.0, 1.0):
                        fills.append(FillNode(rect=o.bbox, color=col))
                # a rule is a filled bar: long and thin in one direction
                if _is_plain_rule(o.bbox):
                    rules.append(RuleNode(id=f"p{pno}r{n}", page=pno, rect=o.bbox))

        page_size = _dominant_size(glyphs)

        # 778 -- A GLYPH CANNOT ADVANCE 8.16pt WHILE BEING 0.12pt TALL.
        #
        # 2002.06055 draws its blackboard letters from a font pdfminer cannot
        # resolve at all -- `fontname` comes back as the literal string
        # "unknown" -- with a FLIPPED text matrix, (1, 0, 0, -1, x, y). From
        # that pdfminer computes `size` 0.120 and a box 0.16pt tall, while the
        # advance is 8.160 and the origin sits exactly on the line's baseline.
        #
        # The box is what line grouping clusters on, so the letter was placed
        # in no line at all and the author's `(\Hilb, \cotimes, \fieldc)`
        # came out `(\mathrm{Hilb}, \hat{\otimes}, )` -- a symbol dropped
        # silently between a comma and a bracket, which is the failure this
        # project treats as worse than a crop.
        #
        # The contradiction is INSIDE THE GLYPH and needs no page context to
        # see: nothing advances sixty-eight times its own height. What the
        # page supplies is the replacement size, and the matrix supplies the
        # baseline it is drawn on -- both of which were right all along.
        if page_size > 0:
            for _g in glyphs:
                if _g.size >= 0.2 * page_size:
                    continue
                _adv = _g.rect[2] - _g.rect[0]
                if _adv < 0.2 * page_size:
                    continue          # a genuinely tiny glyph: leave it
                _base = _g.matrix[5]
                _g.size = page_size
                _g.rect = (_g.rect[0], _base, _g.rect[2], _base + page_size)
        for r in rules:
            r.role = _rule_role(r, glyphs, page_size, rules)

        # Sideways text must be separated BEFORE grouping. A rotated glyph's
        # text-space origin runs along the page's y axis, so its `baseline`
        # is not comparable with an upright glyph's and baseline clustering
        # scatters it through the body text. An arXiv stamp reading
        # "arXiv:0805.0311v3 [math.GM] 28 Sep 2014" turns up as `M4102peS82]`
        # and `ma[3v1130` wedged into the title.
        upright_glyphs = [g for g in glyphs if g.upright]
        rotated_glyphs = [g for g in glyphs if not g.upright]

        # A diagram is a REGION, not a line of text. Its glyphs are removed
        # from the text flow so the arrow stamps stop scattering through the
        # prose; the rectangle is projected as a crop instead.
        diagrams = _diagram_regions(upright_glyphs, strokes)
        if diagrams:
            def _rule_in_diagram(r: RuleNode) -> bool:
                cx = 0.5 * (r.rect[0] + r.rect[2])
                cy = 0.5 * (r.rect[1] + r.rect[3])
                return any(x0 <= cx <= x1 and y0 <= cy <= y1
                           for x0, y0, x1, y1 in diagrams)
            # a bar inside a figure is part of the drawing, not a fraction
            rules = [r for r in rules if not _rule_in_diagram(r)]
            def _in_diagram(g):
                cx = 0.5 * (g.rect[0] + g.rect[2])
                cy = 0.5 * (g.rect[1] + g.rect[3])
                return any(x0 <= cx <= x1 and y0 <= cy <= y1
                           for x0, y0, x1, y1 in diagrams)
            upright_glyphs = [g for g in upright_glyphs if not _in_diagram(g)]

        page = PageNode(
            page=pno, rect=layout.bbox, diagrams=diagrams,
            links=links_by_page.get(pno, []),
            fills=fills,
            invisible=bool(glyphs) and invisible == len(glyphs),
        )
        # A column layout must not have its rows read across the gutter; the
        # split happens inside the grouper, before scripts are folded.
        upright_glyphs = _merge_operator_names(upright_glyphs)
        upright_glyphs = _merge_enclosures(upright_glyphs)
        upright_glyphs = _merge_extenders(upright_glyphs)
        groups = _group_lines(upright_glyphs, rect=layout.bbox,
                              line_bands=line_bands_by_page.get(pno))
        groups = _split_local_columns(groups, layout.bbox)
        rotated_groups = _group_rotated(rotated_glyphs)
        span_pt = _dominant_size(upright_glyphs or glyphs)

        def _near_rows(rule: RuleNode):
            """The row just above and just below a bar, within its x-range.

            Restricted to rows within two line-heights: a row anywhere else on
            the page is also "above" the bar, and accepting those merged most
            of the page into one line.
            """
            mid = 0.5 * (rule.rect[1] + rule.rect[3])
            up = dn = None
            up_d = dn_d = 2.0 * span_pt
            for i, grp in enumerate(groups):
                inside = [g for g in grp
                          if g.rect[0] >= rule.rect[0] - 2
                          and g.rect[2] <= rule.rect[2] + 2]
                if not inside:
                    continue
                base = sum(g.baseline for g in inside) / len(inside)
                d = abs(base - mid)
                if d > 2.0 * span_pt:
                    continue
                if base > mid and d < up_d:
                    up, up_d = i, d
                elif base < mid and d < dn_d:
                    dn, dn_d = i, d
            return up, dn

        # A fraction spans two baselines BY CONSTRUCTION, so baseline grouping
        # puts its numerator and denominator in different rows. The bar is
        # explicit evidence that those two rows are one line, so it merges
        # them -- otherwise numerator and denominator never meet and no `\frac`
        # can ever be built.
        rule_line: dict[int, int] = {}
        for r in rules:
            if r.role != "fraction":
                continue
            up, dn = _near_rows(r)
            if up is None or dn is None or up == dn:
                continue
            groups[up] = groups[up] + groups[dn]
            groups[dn] = []
            rule_line[id(r)] = up

            # The fraction now has its two halves, but it still has to rejoin
            # the expression it sits INSIDE. The host row has no glyph under
            # the bar -- the fraction occupies that column -- so the search
            # above cannot find it, and a display came out as an orphan line
            # `1 12 2` with `(1,0) |-> (1 (x) 1 + i (x) i)` stranded beside it.
            host = None
            host_d = 2.0 * span_pt
            mid = 0.5 * (r.rect[1] + r.rect[3])
            for i, grp in enumerate(groups):
                if not grp or i == up:
                    continue
                near = [g for g in grp
                        if r.rect[0] - 2.5 * span_pt <= g.rect[2]
                        and g.rect[0] <= r.rect[2] + 2.5 * span_pt]
                if not near:
                    continue
                base = sum(g.baseline for g in near) / len(near)
                d = abs(base - mid)
                if d < host_d:
                    host, host_d = i, d
            if host is not None:
                groups[up] = groups[up] + groups[host]
                groups[host] = []
        # 730 — REJOIN A ROW SPLIT BY A RAISED ELEMENT.
        #
        # Measured on wzlxjtu-006, `L=\prod_{i=0}^3 e^{\phi^i K^i}`:
        #
        #     g4  base=627.61  x=[286.8,328.0]  the raised operator
        #     g5  base=620.26  x=[263.1,283.4]  'L='
        #     g6  base=620.26  x=[304.0,540.0]  'e(1)'
        #
        # g5 and g6 share a baseline EXACTLY -- they are one line -- and the
        # grouper separated them because the `\prod` stands between them on
        # its own raised baseline, leaving a 20.6pt hole that reads like a
        # column gutter. Nothing downstream can recover from that: the main
        # row of the display is in two pieces before any structure pass runs.
        #
        # The rejoin is only made when something STANDS IN THE HOLE at a
        # nearby baseline. Two columns of prose also share baselines and sit
        # either side of a gap -- what they do not have is a raised glyph
        # occupying it. That is the difference, and it is the evidence used.
        #: 781q — THE SAME BASELINE, COMPUTED 85,921 TIMES FOR TWO PAGES.
        #:
        #: The rejoin below is a fixed point over a TRIPLE loop -- every
        #: group against every other, and for each pair every third group
        #: as a possible filler -- so `_bl` is asked for the same group
        #: O(n^3) times per sweep, and each answer walks all its glyphs.
        #: Profiled on a 1,175-page handbook set in 7,962 font subsets:
        #: `_dominant_baseline` 85,921 calls, 10.99s of 21s for FOUR pages,
        #: and 3,162,978 reads of `GlyphNode.baseline` underneath it.
        #:
        #: A group's baseline cannot change while nothing merges, so it is
        #: remembered for the sweep and forgotten the moment one does.
        #:
        #: KEYED BY INDEX, NOT BY `id()`. The first version keyed on the
        #: list's identity and moved the corpus by one crop (228 -> 229):
        #: a merge frees one list and builds another, and CPython may hand
        #: the freed id straight to the new one, so a remembered answer
        #: could be served for a DIFFERENT group. An index is stable for
        #: the sweep and only ever reassigned by the merge that clears the
        #: memo. With that, the corpus is unmoved -- which is the only
        #: evidence that "the same function, called less" is true.
        _bl_memo: dict = {}

        def _bl(grp):
            r"""The row's OWN baseline: the one its full-size glyphs sit on.

            The mean over every glyph is not that. wzlxjtu-006's second
            display holds

                base 526.06  'i 2 2sigma 1 8 -6sigma [ 4sigma cosh x5'
                base 521.62  'V(sigma,phi)=-ge+me(-32ge'

            which is ONE row: the five `\cosh` are 12pt and sit on 521.62 with
            the `V`, and 526.06 is a mean dragged up by 8pt scripts and by the
            fraction rows the bar merge pulled in. Comparing means put the two
            halves 4.44pt apart and no rejoin fired, so the row was emitted as
            a display block of scripts and an INLINE span holding its own
            beginning -- `$V (\sigma, \phi ) = -g e + me \biggl( - 32ge$`.
            """
            # FULL-SIZE glyphs only. `_dominant_baseline` takes the mode over
            # every glyph, and in a band that is mostly scripts the mode IS
            # the script line: the band above holds nine 8pt script glyphs
            # against eight 12pt ones, so it reported 527.40 where its own
            # `\cosh`es sit at 522.50 with the `V`, and the two halves stayed
            # 4.90pt apart against a 1.80pt tolerance.
            big = max(g.size for g in grp)
            full = [g for g in grp if g.size >= 0.95 * big]
            return _dominant_baseline(full or grp)

        def _bl_at(i):
            """`_bl(groups[i])`, remembered for the sweep."""
            hit = _bl_memo.get(i)
            if hit is None:
                _bl_memo[i] = hit = _bl(groups[i])
            return hit

        _changed = True
        while _changed:
            _changed = False
            for _i in range(len(groups)):
                if not groups[_i]:
                    continue
                for _j in range(len(groups)):
                    if _i == _j or not groups[_j] or not groups[_i]:
                        continue
                    a, b = groups[_i], groups[_j]
                    if abs(_bl_at(_i) - _bl_at(_j)) > 0.15 * span_pt:
                        continue
                    ax0 = min(g.rect[0] for g in a)
                    ax1 = max(g.rect[2] for g in a)
                    bx0 = min(g.rect[0] for g in b)
                    bx1 = max(g.rect[2] for g in b)
                    # negative when the two INTERLEAVE in x
                    gap = max(bx0 - ax1, ax0 - bx1)
                    if gap > 5.0 * span_pt:
                        continue
                    filler = False
                    for _k in range(len(groups)):
                        if _k in (_i, _j) or not groups[_k]:
                            continue
                        # The filler must REACH INTO the gap, not begin in
                        # it. Testing where it starts missed every script
                        # band, because a superscript begins back over the
                        # term it belongs to: wzlxjtu-096 sets
                        # `\mathfrak{D}^{\mathfrak{J}_B,(1,0;AB^{-1})}
                        # T_{\mathfrak{J}_D}(z)` with
                        #
                        #   D and its subscript   x=[245.6, 266.0]
                        #   the superscript       x=[255.6, 311.4]
                        #   T(z),                 x=[311.9, 348.7]
                        #
                        # -- one row, whose two full-size halves sit 46pt
                        # apart with the superscript spanning the space
                        # between them. The superscript starts at 255.6,
                        # inside the left half, so "begins in the gap" found
                        # nothing and the row was printed as two.
                        kx0 = min(g.rect[0] for g in groups[_k])
                        kx1 = max(g.rect[2] for g in groups[_k])
                        if not (kx1 > ax1 and kx0 < bx0):
                            continue
                        if abs(_bl_at(_k) - _bl_at(_i)) <= 2.5 * span_pt:
                            filler = True
                            break
                    # A filler is needed only when something STANDS IN the
                    # gap -- the raised-operator case this was written for.
                    # Two halves of a row that are merely adjacent have no
                    # filler between them, and they do not need one: sharing
                    # the row's own baseline, both carrying mathematics, and
                    # separated by less than a quad is already decisive.
                    # Prose columns share baselines too, but they are text and
                    # the gutter between them is far wider than that.
                    # Overlapping in x and sharing the row's own baseline is
                    # not adjacency at all -- it is the same row, written
                    # twice by the grouper. wzlxjtu-006's second display puts
                    # the superscripts of `V(\sigma,\phi^i) = -g^2e^{2\sigma}`
                    # directly ABOVE it, so the two bands interleave and an
                    # adjacency test can never see them as one.
                    if gap > 0 and not filler:
                        if gap > 3.0 * span_pt:
                            continue
                        if not (any(g.is_math for g in a)
                                and any(g.is_math for g in b)):
                            continue
                    groups[_i] = a + b
                    groups[_j] = []
                    # Both indices now hold different groups, and any other
                    # entry was computed against the pre-merge arrangement.
                    _bl_memo.clear()
                    _changed = True

        # 730 — STACKED LIMITS, by the same argument as the fraction bar.
        #
        # `structure.py` states as a limit that it models "no stacked limits
        # above/below big operators". The reason it could not is not that the
        # rule is hard -- `_attach_scripts` already treats a bigop as a main
        # glyph and hangs scripts on it -- but that the limits never REACH it.
        # Baseline grouping puts the row above and the row below a `\prod` in
        # rows of their own, exactly as it does a fraction's numerator, and a
        # fraction is rescued only because its bar is explicit evidence that
        # the rows are one line. An operator has no bar.
        #
        # The evidence it has instead is its own geometry: TeX centres a limit
        # on the operator's axis and sets it at script size. A row that sits
        # WHOLLY inside the operator's column, within two line-heights, and in
        # smaller type, is a limit. A text line passing above fails all three.
        #
        # Measured on wzlxjtu-006: `L=\prod_{i=0}^3 e^{\phi^i K^i}` arrived as
        # four blocks -- `L =`, `\prod_{\phi^i K^i}`, `i=0`, `e` -- with the
        # upper limit `3` outside the display altogether.
        for _gi in range(len(groups)):
            if not groups[_gi]:
                continue
            for _b in [g for g in groups[_gi] if g.tex.kind == "bigop"]:
                bx0, bx1 = _b.rect[0], _b.rect[2]
                bw = max(bx1 - bx0, 1.0)
                for _j in range(len(groups)):
                    other = groups[_j]
                    if _j == _gi or not other:
                        continue
                    # 740 -- CENTRED ON THE OPERATOR, NOT CONTAINED BY IT.
                    #
                    # TeX centres a limit on its operator and lets it be as
                    # wide as it needs to be. Containment therefore fails
                    # exactly when the limit is the interesting one:
                    # wzlxjtu-030 sets
                    #
                    #     \sum_{u=1,2,3}^{s+t-|s-t|-1}
                    #
                    # whose operator is 14.4pt wide and whose limits are 27.5
                    # and 47.0 -- and all three centres are 421.6 TO THE
                    # TENTH OF A POINT. The upper limit was refused, stayed a
                    # band of its own, and then CAPTURED the operator in the
                    # furniture pass below, so the whole `\sum` was carried
                    # out of its equation and emitted as a second row.
                    #
                    # The containment test is kept as the other way in: a
                    # limit narrower than its operator satisfies it and need
                    # not be centred to the same tolerance.
                    ocx = 0.5 * (min(g.rect[0] for g in other)
                                 + max(g.rect[2] for g in other))
                    centred = abs(ocx - 0.5 * (bx0 + bx1)) <= 0.5 * bw
                    if not centred and not all(
                            bx0 - 0.75 * bw
                            <= 0.5 * (g.rect[0] + g.rect[2])
                            <= bx1 + 0.75 * bw for g in other):
                        continue
                    # The vertical window is scaled to the OPERATOR, and it
                    # is deliberately generous, because the two tests either
                    # side of it carry the weight: a row wholly inside the
                    # operator's narrow column AND set smaller than it is a
                    # limit, and a line of text is neither.
                    #
                    # Measured on wzlxjtu-006: `\prod` baseline 631.6, lower
                    # limit baseline 606.4 -- 25.2pt, or 2.1 times the 12pt
                    # operator. A window of 2.0 line-heights (24.0) rejected
                    # it by 1.2pt while admitting the upper limit, which is
                    # the asymmetry a big operator has by construction: it is
                    # raised to the maths axis, so its lower limit is further
                    # from its baseline than its upper one. The glyph BOX
                    # cannot be used instead -- pdfminer reports [628.0,
                    # 643.6] for that `\prod`, only 3.6pt of depth below the
                    # baseline, which is not where the operator is drawn.
                    base = sum(g.baseline for g in other) / len(other)
                    _win = 2.5 * max(_b.size, span_pt)
                    if abs(base - _b.baseline) > _win:
                        continue
                    # A limit is set SMALLER than its operator. Without this a
                    # display line that happened to sit under a `\sum` -- a
                    # second equation of the same width -- would be swallowed.
                    if max(g.size for g in other) >= 0.95 * _b.size:
                        continue
                    groups[_gi] = groups[_gi] + other
                    groups[_j] = []

        # 730 — and the operator itself must REJOIN THE ROW IT STANDS IN.
        #
        # It is raised to the maths axis, so the grouper gives it a band of
        # its own; with its limits now gathered onto it, that band holds the
        # whole `\prod_{i=0}^{3}` and nothing it multiplies. The row it
        # belongs to is the one whose x-range it stands inside -- the same
        # argument the fraction pass makes when it rejoins a bar's host.
        for _i in range(len(groups)):
            if not groups[_i]:
                continue
            # A RADICAL SIGN is the same furniture as a big operator here:
            # tall, raised, and given a band of its own by baseline grouping.
            # Measured on wzlxjtu-020, `\sqrt{\gamma}`: the sign occupies
            # x=[151.6,161.6] alone and its vinculum runs [161.6,168.3], so
            # the bar overruns the band's extent by 0.7pt and is assigned to
            # a different row entirely -- the sign and its own bar never meet.
            # Big DELIMITERS are the same furniture again, and they travel
            # with the radical: wzlxjtu-020 sets `\delta(\sqrt{\gamma}
            # L_{ren})` as two bands --
            #
            #   base 480.8   parenleftbig@146  radical@152  parenrightbig@189
            #   base 470.9   delta@139  gamma@162  L@168  r@177  e@180  n@184
            #
            # -- everything tall on one, everything it encloses on the other.
            # `_attach_scripts` already groups "bigop" and "delimiter"
            # together for exactly this reason; the band merge must too, or a
            # band of pure furniture never rejoins the row it is furniture FOR.
            def _furniture(g):
                return (g.tex.kind in ("bigop", "delimiter")
                        or (g.glyphname or "").startswith("radical"))

            ops = [g for g in groups[_i] if _furniture(g)]
            if not ops:
                continue
            # a band that is ONLY that furniture and its limits, nothing else
            if any(not _furniture(g) and g.size >= 0.95 * max(o.size for o in ops)
                   for g in groups[_i]):
                continue
            ox0 = min(g.rect[0] for g in ops)
            osz = max(g.size for g in ops)
            host, host_d = None, 2.5 * span_pt
            for _j in range(len(groups)):
                if _j == _i or not groups[_j]:
                    continue
                # 740 -- A LIMIT ROW IS NOT A HOST.
                #
                # The host is chosen by NEAREST BASELINE, and an operator's
                # own limit is nearer to it than the row it stands in:
                # wzlxjtu-030's `\sum` sits at 447.5, its upper limit at
                # 451.3 and its equation at 438.0, so the operator was
                # rejoined to its own superscript -- 3.8pt away against 9.5
                # -- and the pair left the equation together.
                #
                # A limit is set at SCRIPT SIZE; a row has full-size glyphs
                # in it. That is the same test the stacked-limit merge above
                # uses to tell a limit from a second equation.
                if max(g.size for g in groups[_j]) < 0.95 * osz:
                    continue
                jx0 = min(g.rect[0] for g in groups[_j])
                jx1 = max(g.rect[2] for g in groups[_j])
                if not (jx0 - 2.0 * span_pt <= ox0 <= jx1 + 2.0 * span_pt):
                    continue
                d = abs(_bl(groups[_j]) - _bl(groups[_i]))
                if d < host_d:
                    host, host_d = _j, d
            if host is not None:
                groups[host] = groups[host] + groups[_i]
                groups[_i] = []

        # 731 — A RADICAL SIGN FOLLOWS ITS VINCULUM.
        #
        # The sign is raised like any tall furniture, so grouping can leave it
        # on the row ABOVE the one it belongs to. On wzlxjtu-020 that put the
        # sign of the root on base 463.4 into the row at 470.9, where it has
        # no bar -- and an unpaired radical defers the whole span, so a row
        # that had assembled correctly was thrown away for a glyph that was
        # never its own.
        #
        # The pairing is unambiguous: TeX draws the vinculum starting exactly
        # at the sign's right edge (161.6 to 161.6, measured). Follow it.
        for _i in range(len(groups)):
            if not groups[_i]:
                continue
            for _g in list(groups[_i]):
                if not (_g.glyphname or "").startswith("radical"):
                    continue
                gsize = _g.size or span_pt
                bar = None
                for r in rules:
                    if abs(r.rect[0] - _g.rect[2]) > 0.6 * gsize:
                        continue
                    rmid = 0.5 * (r.rect[1] + r.rect[3])
                    if _g.rect[1] - gsize <= rmid <= _g.rect[3] + gsize:
                        bar = r
                        break
                if bar is None:
                    continue
                bmid = 0.5 * (bar.rect[1] + bar.rect[3])
                dest = None
                for _j in range(len(groups)):
                    if _j == _i or not groups[_j]:
                        continue
                    if any(g.baseline < bmid
                           and bar.rect[0] - 1 <= 0.5 * (g.rect[0] + g.rect[2])
                           <= bar.rect[2] + 1 for g in groups[_j]):
                        dest = _j
                        break
                if dest is not None:
                    groups[_i] = [g for g in groups[_i] if g is not _g]
                    groups[dest] = groups[dest] + [_g]

        # 733 — A BAND OF PURE SCRIPTS BELONGS TO THE BAND ITS BASES ARE IN,
        # AND THE STREAM IS WHAT SAYS WHICH BAND THAT IS.
        #
        # Baseline clustering puts every raised glyph of a display on one
        # band, because they DO share a baseline -- the superscripts of a row
        # are all raised by the same amount. wzlxjtu-010's fifth equation,
        # `f'=2(G_0S_0+G_3S_3)`, `e^{-2f}=4(...)-4(S_0^2+S_3^2)`, arrives as
        #
        #     band A   ' -2f 2 2 2                   every superscript
        #     band B   f = 2(G S + G S ) e = 4(...)  every base
        #
        # and `_attach_scripts` is handed one or the other, never both. No
        # rule about coordinates can undo this: the scripts really are on a
        # line of their own, and the page says nothing about which base each
        # belongs to. It is a property of the finished page, not of the
        # document, and it is where the glyph coordinates stop being evidence.
        #
        # The CONTENT STREAM still has it. TeX emits a base immediately
        # followed by its own scripts -- `N two zero` for `N_0^2`, `M I A B`
        # for `M^I_{AB}` -- so the glyph most recently emitted BEFORE a script
        # is its base, and the band holding that glyph is the band the script
        # belongs to. Measured over the corpus, every glyph carries an index.
        #
        # Voted rather than decided per glyph: one band of scripts serves one
        # row, so the destination is the row most of its bases are in.
        _idx = sorted(((g.stream, _j) for _j, grp in enumerate(groups)
                       for g in grp if g.stream >= 0))
        # PER GLYPH by default since 736. It was "unanimous" -- place a band
        # only when every glyph of it names the same destination row -- because
        # splitting a band per glyph measured worse. That reason is gone: it
        # measured worse by CREATING LEADING SCRIPTS, a row beginning with a
        # script whose base had moved elsewhere, and that refused the whole
        # display until 735 gave it the `{}` base LaTeX already has for it.
        #
        # Unanimity also cannot place the common case. wzlxjtu-005's fourth
        # display sets three rows and ONE raised band across them:
        #
        #   base 289.67  13 glyphs, all 8pt   I I r i mu B I i s e mu B I B
        #   base 284.12  23 glyphs            row 2
        #   base 283.94  17 glyphs            row 3
        #
        # The band serves two rows, so the stream names two destinations and
        # unanimity placed none of it -- every superscript in the display
        # silently gone, `\lambda^I_A` read as `\lambda_A`. A dropped symbol
        # is worse than a refusal because nothing marks it.
        _mode = os.environ.get("PDF2MMD_SCRIPTBAND", "perglyph")
        if _idx and _mode != "off":
            import bisect as _bisect
            _keys = [s for s, _ in _idx]
            for _i in range(len(groups)):
                grp = groups[_i]
                if not grp or not all(g.stream >= 0 for g in grp):
                    continue
                if not _off_row_band(grp, rules, span_pt):
                    continue                  # not a band of scripts
                # PER GLYPH, not per band. Voting a whole band to one
                # destination was tried and over-merged: a single band of
                # raised glyphs serves every row of a display, so sending it
                # all to the row most of it belonged to dragged the other
                # rows' scripts along. Measured: 315 blocks against the
                # author's 421, and crops up from 452 to 591. The stream
                # names a base for EACH script, so each one is placed on its
                # own evidence and a band can be split between rows.
                moved = []
                for g in grp:
                    k = _bisect.bisect_left(_keys, g.stream) - 1
                    while k >= 0 and _idx[k][1] == _i:
                        k -= 1
                    if k < 0:
                        continue
                    dest = _idx[k][1]
                    if dest == _i or not groups[dest]:
                        continue
                    # a script sits beside its base, not a page away
                    db = (sum(x.baseline for x in groups[dest])
                          / len(groups[dest]))
                    if abs(db - g.baseline) > 2.0 * span_pt:
                        continue
                    moved.append((dest, g))
                if not moved:
                    continue
                # UNANIMOUS: fire only where the stream is not ambiguous --
                # every glyph of the band names the same base row, and none
                # of them failed to name one. A band that serves two rows is
                # left alone rather than split on a majority, because a
                # misplaced script is a wrong reading and a left-alone band
                # is the crop it already was.
                if _mode == "unanimous":
                    if len(moved) != len(grp):
                        continue
                    if len({d for d, _ in moved}) != 1:
                        continue
                gone = {id(g) for _, g in moved}
                for dest, g in moved:
                    groups[dest] = groups[dest] + [g]
                groups[_i] = [g for g in grp if id(g) not in gone]

        # 744 -- A GLYPH SANDWICHED IN THE STREAM BELONGS TO ITS NEIGHBOURS.
        #
        # The pass above rescues a band that is ENTIRELY scripts. It cannot
        # help a script that was absorbed into a full-size row, because it
        # skips any group holding full-size glyphs -- and that is the case
        # that produces a WRONG READING rather than a missing one.
        #
        # wzlxjtu-009's `M` rows:
        #
        #     stream 1698  'e'  base 152.72   row M_3
        #     stream 1699  'sigma'  base 157.66   row M_0   <- wrong
        #     stream 1700  'sin'  base 152.72   row M_3
        #     stream 1703  'phi'  base 152.72   row M_3
        #     stream 1704  '3'  base 157.66   row M_0       <- wrong
        #     stream 1708  '('  base 152.72   row M_3
        #
        # Those two are the superscripts of `e^{\sigma}` and `\phi^3` on the
        # LOWER row. They sit 4.94pt above it and 12.5pt below the row above,
        # so they are nearer to where they belong -- and went to the other
        # one anyway. The reading came out
        #
        #     M_0 = 2m e^{-3\sigma} \cos \phi_{\sigma}^{3} \sinh \phi_{3}^{0}
        #     M_3 = -2ig e \sin \phi
        #
        # two invented subscripts on one row and two superscripts missing
        # from the next. Nothing marks either.
        #
        # The stream is unambiguous where position is not: each stray sits
        # BETWEEN two glyphs of the row it belongs to. Both neighbours must
        # agree -- one would be an adjacency, two is a sandwich -- and the
        # glyph must be script-size, so this moves scripts and never prose.
        if _idx:
            import bisect as _bisect
            # Index carries the BASELINE too, because a stream neighbour is
            # not always a neighbour on the page: TeX emits an equation's
            # NUMBER after its body, so the glyph following `\phi` in the
            # stream can be the `(` of a tag 163pt up the page. Those are
            # skipped when looking for the sandwich -- the neighbour has to
            # be on the same band to say anything about this glyph.
            _nb = sorted((g.stream, _j, g.baseline)
                         for _j, grp in enumerate(groups)
                         for g in grp if g.stream >= 0)
            _sk = [s for s, _, _ in _nb]
            _moves = []

            def _side(k, step, base):
                k += step
                while 0 <= k < len(_nb):
                    if abs(_nb[k][2] - base) <= 2.0 * span_pt:
                        return _nb[k][1]
                    k += step
                return None

            for _i, grp in enumerate(groups):
                if not grp:
                    continue
                for g in grp:
                    if g.stream < 0 or g.size >= 0.95 * span_pt:
                        continue
                    k = _bisect.bisect_left(_sk, g.stream)
                    if k >= len(_nb) or _nb[k][0] != g.stream:
                        continue
                    before = _side(k, -1, g.baseline)
                    after = _side(k, +1, g.baseline)
                    if before is None or before != after or before == _i:
                        continue
                    if not groups[before]:
                        continue
                    db = (sum(x.baseline for x in groups[before])
                          / len(groups[before]))
                    if abs(db - g.baseline) > 2.0 * span_pt:
                        continue
                    _moves.append((before, _i, g))
            if _moves:
                _gone = {id(g) for _, _, g in _moves}
                for dest, _, g in _moves:
                    groups[dest] = groups[dest] + [g]
                for _i in {src for _, src, _ in _moves}:
                    groups[_i] = [g for g in groups[_i] if id(g) not in _gone]

        keep = [i for i, g in enumerate(groups) if g]
        remap = {old: new for new, old in enumerate(keep)}
        groups = [groups[i] for i in keep]
        rule_line = {k: remap[v] for k, v in rule_line.items() if v in remap}

        for idx, group in enumerate(groups):
            group, dropped = merge_fragments(group)
            gx0 = min(g.rect[0] for g in group)
            gy0 = min(g.rect[1] for g in group)
            gx1 = max(g.rect[2] for g in group)
            gy1 = max(g.rect[3] for g in group)
            # Each rule belongs to ONE line: the one it was merged into, or --
            # for a non-fraction rule -- the line whose box encloses it.
            # A line's BOX includes ascenders and descenders, so a bar
            # belonging to the line below falls inside it. Measured: the
            # overline of a `\bar{Z}` one line down was attached here and
            # then landed in the x-range of `(Y,Z)`, which deferred a span
            # that had no accent at all. Baseline distance decides instead.
            base = _dominant_baseline(group)
            mine = []
            for r in rules:
                if id(r) in rule_line:
                    if rule_line[id(r)] == idx:
                        mine.append(r)
                    continue
                mid = 0.5 * (r.rect[1] + r.rect[3])
                # A VINCULUM BELONGS TO ITS RADICAL, at any height.
                #
                # The baseline window below is 0.8 em, which fits an overline
                # on running text. A `\sqrt`'s bar sits as high as its
                # radicand is tall: wzlxjtu-014's `W = \sqrt{S_0^2 + S_3^2}`
                # puts it 14.8pt above a row baseline of 664.20, so the line
                # was handed NO rules at all and the radical deferred as an
                # unmapped glyph, taking the equation with it.
                #
                # Widening the window generally was tried before and cost two
                # display blocks. This needs no window: TeX starts the bar
                # exactly at the sign's right edge -- 296.4 to 296.4, measured
                # -- and nothing else in a row does that.
                #
                # 751 -- AND IT MUST BE ITS OWN RADICAL'S. x alone identifies
                # the bar only while one radical on the page starts there.
                # wzlxjtu-024 sets `\sqrt{2}` in equation 5 and again in
                # equation 6, at x=302.79 and x=301.64 -- close enough that
                # each equation's bar abutted BOTH signs, so equation 5's
                # line was handed a rule from y=158.13, ninety points below
                # it, and equation 6's was handed one from y=275.19.
                # Unaccounted rules on both: `fraction+overline+unmapped`,
                # and both equations became crops.
                #
                # TeX draws the vinculum at the TOP of the sign, inside its
                # box. That is the test `_rule_role` already applies to the
                # same decision, and applying it here too costs nothing that
                # the x test was buying -- the sign is still what names the
                # bar, it just has to be a sign that is actually there.
                if any((g.glyphname or "").startswith("radical")
                       and abs(r.rect[0] - g.rect[2]) <= 0.6 * max(g.size, 1.0)
                       and g.rect[1] - 1 <= mid <= g.rect[3] + 1
                       for g in group):
                    mine.append(r)
                    continue
                # 763 -- AN OVERLINE SITS ON TOP OF THE BOX IT COVERS, and
                # that is higher than 0.8 em above the baseline.
                #
                # wzlxjtu-031's second display is
                # `A=\sum..A_m^sV_m^s \qquad \overline{A}=\sum..` and both
                # bars went missing: TeX draws `\overline` above the HEIGHT
                # of what it covers plus three rule thicknesses, which for a
                # 10pt `A` is 10.13pt -- against a window of 8.0. The line
                # was handed no rule, the accent was never built, and the
                # two halves of the equation came out identical.
                #
                # Not a wider window. The bar of an overline is drawn to the
                # WIDTH OF THE BOX, so `\overline{A}` puts a rule at exactly
                # 177.50..184.97 over an `A` at exactly 177.50..184.97, a
                # tenth of a point above its top. Nothing else in a row is
                # laid out like that: a fraction bar sits on the maths axis,
                # a quarter em above the baseline and nowhere near the top of
                # anything, and this asks `_rule_role` to have said overline
                # first.
                if _covers_as_overline(r, mid, group):
                    mine.append(r)
                    continue
                # A bar BELOW the baseline cannot belong to this line: an
                # overline goes above what it covers. Two such rules from the
                # line below were being attached here and deferred a span
                # that carried no accent.
                if mid < base - 0.15 * span_pt:
                    continue
                # Widening this window to the line's own extent was tried
                # as the explanation for the merge failure -- a merged
                # display line is two or three times a text line, so its
                # fraction bar can sit outside `0.8 * span_pt` of the
                # baseline. Measured with the merge ON: projection stayed at
                # 62.4% and script-attachment failures stayed at 666. It was
                # a plausible cause and it is not the one. Reverted; with
                # the merge OFF it also cost 2 display blocks.
                if (r.rect[0] >= gx0 - 6 and r.rect[2] <= gx1 + 6
                        and abs(mid - base) <= 0.8 * span_pt):
                    mine.append(r)
            is_math = any(g.is_math for g in group) or bool(mine)
            # 741 -- A MERGED BAND IS IN MERGE ORDER, WHICH IS NO ORDER.
            #
            # Every band merge here concatenates: `groups[host] + groups[_i]`.
            # The result is whatever order the passes happened to run in, and
            # it reaches `to_tex` as the sequence of the line. wzlxjtu-092's
            # denominator row runs stream 438..484 and then JUMPS BACK to
            # 471..483 -- the script band was appended after the delimiter
            # band, so every big delimiter ended up adjacent to another big
            # delimiter and the output carried `\bigl( \bigr)\bigl( \bigr)`
            # with the contents gone.
            #
            # Restored to the order THE PDF DREW THEM IN, which is the order
            # TeX emitted them, which is reading order. Not x: a superscript
            # is drawn where it belongs in the expression and sits above the
            # base that precedes it, and sorting by position is what loses
            # that. The stream index is the evidence; x is the fallback for a
            # page where some glyph lacks one.
            if all(getattr(g, "stream", None) is not None for g in group):
                group = sorted(group, key=lambda g: g.stream)
            page.lines.append(
                LineNode(
                    id=f"p{pno}l{len(page.lines)}", page=pno,
                    rect=(gx0, gy0, gx1, gy1),
                    type="formula" if is_math else "text",
                    glyphs=group, rules=mine, merged=dropped,
                )
            )
        for group in rotated_groups:
            gx0 = min(g.rect[0] for g in group)
            gy0 = min(g.rect[1] for g in group)
            gx1 = max(g.rect[2] for g in group)
            gy1 = max(g.rect[3] for g in group)
            page.lines.append(
                LineNode(
                    id=f"p{pno}r{len(page.lines)}", page=pno,
                    rect=(gx0, gy0, gx1, gy1),
                    type="text", glyphs=group, rules=[], rotated=True,
                )
            )
        # Reading order by BAND. A page is not simply two columns: a
        # full-width element -- a wide figure, its caption, a section heading
        # spanning both columns -- ENDS the two-column region above it and
        # starts a new one below.
        #
        # Sorting by (column, y) over the whole page ignores that, so a figure
        # high in the right column of a lower band was emitted after every
        # line of the left column. Measured: Figure 7's caption arrived two
        # paragraphs late, exactly the height of the figure.
        #
        # Within a band: the whole left column, then the whole right column.
        # Full-width rows are emitted where they sit, closing one band and
        # opening the next.
        # No dependency on a detected column EDGE. `_col` classifies by width
        # and centre, and the band ordering is right for a single-column page
        # too. Requiring an edge meant a page whose left-edge modes were
        # confused -- a figure with its own panels -- skipped banding
        # altogether and fell back to y-order, interleaving the panels line
        # by line. Measured: the band code was never entered on that page.
        # Classify by WIDTH and CENTRE, not by a precise boundary. The edge
        # is an estimate: measured at 295 on a page whose left column runs to
        # 302, which made every left-column line look full-width and closed a
        # band on each one. A column line is narrow and sits on one side; a
        # full-width line is simply wide.
        lefts = [ln.rect[0] for ln in page.lines if ln.glyphs]
        rights = [ln.rect[2] for ln in page.lines if ln.glyphs]
        text_w = (max(rights) - min(lefts)) if lefts else 1.0
        centre = 0.5 * (min(lefts) + max(rights)) if lefts else 0.0

        def _col(ln: LineNode) -> int:
            if (ln.rect[2] - ln.rect[0]) > 0.7 * text_w:
                return 2                  # full width
            return 0 if 0.5 * (ln.rect[0] + ln.rect[2]) < centre else 1

        ordered: list[LineNode] = []
        band: list[LineNode] = []

        def _flush_band() -> None:
            band.sort(key=_in_band)
            ordered.extend(band)
            band.clear()

        # Within a band, order by the CONTENT STREAM where it is available.
        # The producer emitted the page in the order it wanted it read, and a
        # figure with its own internal panels -- scheduling commands beside
        # the code they generate -- is emitted panel by panel. Sorting those
        # by (column, y) interleaves them line by line:
        #
        #     11 bx[i1][j1][c]=
        #     6 by.tile(i, j, 32, 32, i0, j0, i1, j1);
        #     13 + in[i][j+2][c])/3
        #
        # Geometry falls back in where the stream index is missing.
        def _in_band(ln: LineNode):
            return (ln.stream if ln.stream >= 0 else 1 << 30,
                    -ln.rect[3], ln.rect[0])

        for ln in sorted(page.lines, key=lambda ln: (-ln.rect[3], ln.rect[0])):
            if _col(ln) == 2:
                _flush_band()
                ordered.append(ln)
            else:
                band.append(ln)
        _flush_band()
        page.lines = ordered
        # The listing grid is measured HERE, on the finished lines, so that
        # every projection reads one measurement instead of making its own.
        # The frames come first: a listing's rectangle is the one it is
        # drawn inside, where the author drew one.
        page.frames = listings.frames(rules, span_pt)
        page.listings = listings.accumulate(page)
        out.append(page)
    return out


# ----------------------------------------------------------------------- U6
def span_gaps(span) -> list[dict]:
    """Gaps inside a span that carry INFORMATION, as measured data.

    A LaTeX space emits no glyph: `\\quad` and `\\!` exist in the PDF only
    as an advance of the current point, so a reader that reports glyphs
    reports nothing at all about them. Measured on a compiled table of all
    thirteen forms: `\\!` is -0.167 em, `\\,` +0.167, `\\;` +0.278,
    `\\quad` +1.0, `\\qquad` +2.0.

    Which COMMAND produced a given width cannot be recovered -- TeX's own
    atom spacing and an align environment produce the same widths -- so this
    reports the MEASUREMENT and leaves the reading to a consumer that knows
    more. Ordinary inter-glyph gaps are omitted; what remains is a gap that
    is negative, or wide enough that nothing automatic explains it.

    Each entry: the index of the glyph the gap follows, the gap in em, and
    the two glyphs it sits between.
    """
    out: list[dict] = []
    glyphs = sorted(span.glyphs, key=lambda g: g.rect[0])
    for i, (a, b) in enumerate(zip(glyphs, glyphs[1:])):
        size = max(a.size, b.size, 1.0)
        em = (b.rect[0] - a.rect[2]) / size
        cls = space_class(em)
        # A gap TeX's own table produces is REPORTED, not skipped. It is the
        # evidence for the pair of atom classes that produced it -- Baker,
        # Sexton & Sorge (DAS 2010) use exactly this to tell a calligraphic
        # `R` used as a RELATION from one used as a letter. Measured, 81.3%
        # of all gaps on one paper land on the table.
        if cls in (1, 2, 3):
            pass
        elif -0.05 < em < 0.45:          # ordinary spacing; nothing to say
            continue
        out.append({
            "after": i,
            "em": round(em, 3),
            "pt": round(b.rect[0] - a.rect[2], 2),
            "left": a.text,
            "right": b.text,
            "kind": "negative" if em < 0 else "wide",
            "tex_class": space_class(em),
        })
    return out


def line_font_size(line: "LineNode") -> float:
    """The line's dominant type size, as MathPix reports per line."""
    return _dominant_size(line.glyphs) if line.glyphs else 0.0


def _contour(rect: Rect, page: "PageNode", k: float) -> list[list[int]]:
    """MathPix's four-corner contour, clockwise from the top left."""
    x0 = round(rect[0] * k)
    x1 = round(rect[2] * k)
    y0 = round((page.rect[3] - rect[3]) * k)
    y1 = round((page.rect[3] - rect[1]) * k)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _px_region(rect: Rect, page: PageNode, k: float) -> dict:
    """A PDF-point rect (y up) as a pixel region (y down from top-left)."""
    return {
        "top_left_x": round(rect[0] * k),
        "top_left_y": round((page.rect[3] - rect[3]) * k),
        "width": max(1, round((rect[2] - rect[0]) * k)),
        "height": max(1, round((rect[3] - rect[1]) * k)),
    }


def to_lines_json(pages: list[PageNode],
                  px_per_pt: float = PX_PER_PT,
                  doc_id: str = "pdfdrill") -> dict:
    """MathPix-shaped geometry, projected from the model.

    Coordinates are PIXELS at `px_per_pt`, top-left origin, exactly as MathPix
    writes them -- not PDF points. A consumer must be able to take a region
    from here, put it straight into a crop URL, and get that region back.
    """
    k = px_per_pt
    # THE LINE TYPE, from the one classifier. `LineNode.type` is "text" or
    # "formula" — two values, and pdfdrill's twenty docmodel modules key off
    # SIXTEEN, so a two-type stream can only ever produce paragraphs. The
    # classifier lives in `project_mmd` because that is where its inputs are
    # (the document font profile, each page's margins, the listing grid);
    # imported late because that module builds on the node types defined here.
    # A failure here must not cost the geometry, which is the part that is
    # always right: fall back to the node's own type.
    try:
        from project_mmd import classify_lines
        _types = classify_lines(pages)
    except Exception:                                    # noqa: BLE001
        _types = {}

    def _line_type(p, i, ln) -> tuple:
        return _types.get((p.page, i)) or (ln.type, {})

    out = {
        "pages": [
            {
                # MathPix's own page keys first, so a consumer written
                # against their export reads ours unchanged.
                "image_id": f"{doc_id}-{p.page:02d}",
                "page": p.page,
                "languages_detected": [],
                "page_width": round((p.rect[2] - p.rect[0]) * k),
                "page_height": round((p.rect[3] - p.rect[1]) * k),
                "px_per_pt": round(k, 6),
                "source": "pdfminer-docmodel",
                "diagrams": [_px_region(d, p, k) for d in p.diagrams],
                "fills": [
                    {"region": _px_region(fl.rect, p, k),
                     "color": list(fl.color) if fl.color else None}
                    for fl in p.fills
                ],
                "links": [
                    {"region": _px_region(l.rect, p, k),
                     "uri": l.uri, "dest": l.dest, "citekey": l.citekey}
                    for l in p.links
                ],
                "lines": [
                    {
                        # MathPix line keys, then ours. `cnt` is their
                        # four-corner contour; for an axis-aligned line it is
                        # the region's corners, which is what they emit for
                        # printed text too.
                        "id": ln.id,
                        "type": _line_type(p, i, ln)[0],
                        "line": i + 1,
                        "column": 0,
                        "font_size": round(line_font_size(ln)),
                        "is_printed": True,
                        "is_handwritten": False,
                        "conversion_output": False,
                        "confidence": 1.0 if all(
                            sp.kind == "text" or span_latex(sp) is not None
                            for sp in ln.spans) else 0.0,
                        "confidence_rate": 1.0,
                        "cnt": _contour(ln.rect, p, k),
                        "gaps": [gp for sp in ln.spans
                                 for gp in span_gaps(sp)],
                        "region": {
                            "top_left_x": round(ln.rect[0] * k),
                            "top_left_y": round((p.rect[3] - ln.rect[3]) * k),
                            "width": max(1, round((ln.rect[2] - ln.rect[0]) * k)),
                            "height": max(1, round((ln.rect[3] - ln.rect[1]) * k)),
                        },
                        "text": (" ".join(span_text(sp) for sp in ln.spans)),
                        "complete": all(
                            sp.kind == "text" or span_latex(sp) is not None
                            for sp in ln.spans
                        ),
                        "rules": [
                            {"role": r.role,
                             "region": _px_region(r.rect, p, k)}
                            for r in ln.rules
                        ],
                        "deferred_glyphs": [
                            {"id": g.id, "region": _px_region(g.rect, p, k),
                             "font": g.fontname, "glyphname": g.glyphname}
                            for g in ln.glyphs if g.tex.latex is None
                        ],
                        # What the type brought with it — a heading's LEVEL, a
                        # listing's LANGUAGE. Carried beside the type rather
                        # than encoded into it, so a reader that ignores them
                        # still reads the type.
                        **_line_type(p, i, ln)[1],
                        # the source line index, so a container added
                        # afterwards can name its children by id
                        "_i": i,
                    }
                    for i, ln in enumerate(p.lines)
                ],
            }
            for p in pages
        ]
    }
    _add_column_containers(out, pages, k)
    _add_table_containers(out, pages, k)
    _split_runin_headings(out, pages, k)
    return out


def _split_runin_headings(out: dict, pages: list["PageNode"], k: float) -> None:
    r"""Make a run-in heading its own line, in front of the prose it introduces.

    814 — `\paragraph{Analysis: Finance Benchmark}` sets its title bold at BODY
    SIZE and lets the text run on from it after a 1 em space, so the heading and
    the paragraph share one baseline and therefore one LineNode. Emitted whole,
    the heading is the first three words of a paragraph — which is what it was,
    in the docmodel and in every projection.

    `project_mmd.runin_heading` measured where it ends; this makes that two line
    records. The heading's rectangle stops at the last bold glyph and the prose's
    starts at the first plain one, so the split is visible in the inspect view
    and a crop of either is right. Both keep the line's vertical extent, because
    they do share a baseline.

    LAST, after the container passes, so a container that already lists the
    original line gains the heading beside it rather than losing it.
    """
    for page_rec, p in zip(out["pages"], pages):
        recs = page_rec["lines"]
        by_i = {r.get("_i"): r for r in recs if r.get("_i") is not None}
        made: list = []
        for i, ln in enumerate(p.lines):
            rec = by_i.get(i)
            if rec is None:
                continue
            n = rec.pop("runin_split", None)
            level = rec.pop("runin_level", None)
            if not n or n >= len(ln.glyphs):
                continue
            head_gl, rest_gl = ln.glyphs[:n], ln.glyphs[n:]
            # The word gap comes from the WHOLE line. Derived from the bold
            # prefix alone — seven glyphs — the threshold lands above the real
            # word space and `Base LLM` comes out `BaseLLM`. The line is one
            # typographic unit; both halves are measured against it.
            wg = _word_gap(ln.glyphs)
            x0 = min(g.rect[0] for g in head_gl)
            x1 = max(g.rect[2] for g in head_gl)
            rx0 = min(g.rect[0] for g in rest_gl)
            top_y = round((p.rect[3] - ln.rect[3]) * k)
            height = max(1, round((ln.rect[3] - ln.rect[1]) * k))
            head = dict(rec)
            head["id"] = f"{rec['id']}h"
            head["type"] = "section_header"
            if level:
                head["level"] = level
            head["text"] = _run_text(head_gl, wg).strip()
            head["region"] = {"top_left_x": round(x0 * k), "top_left_y": top_y,
                              "width": max(1, round((x1 - x0) * k)),
                              "height": height}
            head["cnt"] = _contour((x0, ln.rect[1], x1, ln.rect[3]), p, k)
            # The heading is not the prose: neither carries the other's pieces.
            for key in ("gaps", "rules", "deferred_glyphs"):
                head.pop(key, None)
            rec["text"] = _run_text(rest_gl, wg).strip()
            rec["region"] = {"top_left_x": round(rx0 * k), "top_left_y": top_y,
                             "width": max(1, round((ln.rect[2] - rx0) * k)),
                             "height": height}
            rec["cnt"] = _contour((rx0, ln.rect[1], ln.rect[2], ln.rect[3]), p, k)
            made.append((rec, head))
        for rec, head in made:
            recs.insert(recs.index(rec), head)
            # A container listing the prose line must list the heading too, or
            # the heading falls out of the reading order the container states.
            for other in recs:
                kids = other.get("children_ids")
                if kids and rec["id"] in kids and head["id"] not in kids:
                    kids.insert(kids.index(rec["id"]), head["id"])
            if rec.get("parent_id"):
                head["parent_id"] = rec["parent_id"]


def _add_table_containers(out: dict, pages: list["PageNode"], k: float) -> None:
    """A `table` container per ruled table, with its rows as children and its
    caption named.

    MathPix ships a `table` whose children are its cells; we do not measure
    cells yet, so ours holds ROWS — the lines inside the rectangle. That is the
    logical first step the user asked for: a correct rectangle and the caption
    that belongs to it, before any attempt at `tabular`.

    `caption_id` rather than nesting the caption as a child, because a caption
    is printed ABOVE the table in most styles and BELOW in others, and a tree
    that makes it a child has to pick one. Naming it leaves the order on the
    page where it belongs.
    """
    from project_mmd import table_regions
    for page_rec, p in zip(out["pages"], pages):
        try:
            regions = table_regions(p)
        except Exception:                                # noqa: BLE001
            continue
        if not regions:
            continue
        recs = page_rec["lines"]
        by_index = {}
        for r in recs:
            if r.get("_i") is not None:
                by_index[r["_i"]] = r
        containers = []
        for n, t in enumerate(regions):
            x0, y0, x1, y1 = t["rect"]
            kids = [by_index[i]["id"] for i in t["lines"] if i in by_index]
            cap = by_index.get(t["caption_index"])
            tid = f"{page_rec.get('image_id') or p.page}-tab{n}"
            for i in t["lines"]:
                if i in by_index:
                    by_index[i].setdefault("parent_id", tid)
            containers.append({
                "id": tid, "type": "table", "line": 0, "font_size": 0,
                "is_printed": True, "is_handwritten": False,
                "conversion_output": False, "confidence": 1.0,
                "confidence_rate": 1.0,
                "cnt": _contour((x0, y0, x1, y1), p, k),
                "region": {
                    "top_left_x": round(x0 * k),
                    "top_left_y": round((p.rect[3] - y1) * k),
                    "width": max(1, round((x1 - x0) * k)),
                    "height": max(1, round((y1 - y0) * k)),
                },
                "text": "", "children_ids": kids,
                "caption_id": cap["id"] if cap else None,
                "caption_number": t["caption"]["number"],
            })
        page_rec["lines"] = containers + recs


def _add_column_containers(out: dict, pages: list["PageNode"], k: float) -> None:
    """Give the flat line list the one level of nesting it was missing.

    MathPix nests almost everything one step under a `column`: 528 of 1269
    lines on 1909.00741 are `column -> text`. That nesting is not decoration —
    it is the reading order of a two-column paper, stated rather than left for
    each consumer to guess from x-coordinates. We emitted 0 `parent_id` and 0
    `children_ids` against their 1244 and 121, so every reader downstream had
    to rediscover the columns or get the order wrong.

    A container is a REAL measurement, not a label: its rectangle is the union
    of the lines it holds, so a reader can draw it and check it. It carries no
    text and `conversion_output: False`, which is exactly how MathPix ships one
    — a consumer that walks lines for prose skips it without being taught to.

    Only ONE level, and only columns. list_item -> text and table -> cell are
    the next two MathPix has; neither is measured here yet, and a container
    invented without a measurement behind it is a structure the document does
    not have.
    """
    from project_mmd import column_membership
    for page_rec, p in zip(out["pages"], pages):
        try:
            member = column_membership(p)
        except Exception:                                # noqa: BLE001
            continue
        if not member:
            continue
        recs = page_rec["lines"]
        by_col: dict = {}
        for i, col in member.items():
            if 0 <= i < len(recs):
                by_col.setdefault(col, []).append(i)
        containers = []
        for col in sorted(by_col):
            idxs = by_col[col]
            rects = [p.lines[i].rect for i in idxs if p.lines[i].glyphs]
            if not rects:
                continue
            x0 = min(r[0] for r in rects); y0 = min(r[1] for r in rects)
            x1 = max(r[2] for r in rects); y1 = max(r[3] for r in rects)
            cid = f"{page_rec.get('image_id') or p.page}-col{col}"
            for i in idxs:
                recs[i]["parent_id"] = cid
            containers.append({
                "id": cid,
                "type": "column",
                "column": col,
                "line": 0,
                "font_size": 0,
                "is_printed": True,
                "is_handwritten": False,
                "conversion_output": False,
                "confidence": 1.0,
                "confidence_rate": 1.0,
                "cnt": _contour((x0, y0, x1, y1), p, k),
                "region": {
                    "top_left_x": round(x0 * k),
                    "top_left_y": round((p.rect[3] - y1) * k),
                    "width": max(1, round((x1 - x0) * k)),
                    "height": max(1, round((y1 - y0) * k)),
                },
                "text": "",
                "children_ids": [recs[i]["id"] for i in idxs],
            })
        # Containers FIRST, as MathPix orders them: a reader building a tree in
        # one pass meets the parent before the children it names.
        page_rec["lines"] = containers + recs


# ----------------------------------------------------------------------- U7
def _word_gap(glyphs: list["GlyphNode"]) -> float:
    """The gap width that separates words on THIS run.

    A fixed fraction of the type size does not survive justification. Measured
    on one justified line at 12pt: gaps within words ran 0.07-0.87 and gaps
    between words 2.04-4.92, while the fixed threshold of 0.22em was 2.64 --
    sitting inside the word cluster, so `any quaternion` came out
    `anyquaternion`. The split is plainly bimodal, so find it.
    """
    size = max((g.size for g in glyphs), default=10.0)
    # Keep EVERY gap, including the near-zero ones between letters. Dropping
    # them destroys the bimodality this depends on: with only the word gaps
    # left, the widest jump is found somewhere inside that cluster and the
    # threshold lands above a real word space -- one line came out as
    # `oneofthemaingoalsofthesenotes`.
    gaps = sorted(max(0.0, b.rect[0] - a.rect[2])
                  for a, b in zip(glyphs, glyphs[1:]))
    if len(gaps) < 4:
        return 0.22 * size
    # The split must have a POPULATION above it, not just one gap. A single
    # outlier -- the space around an inline summation sign, measured at 15.2pt
    # where the word spaces were 2.7-3.3 -- otherwise defines the boundary,
    # the threshold clamps to its ceiling, and the whole line runs together:
    # `certainkindsof"polynomials,"linearcombinations`.
    need = max(2, int(0.10 * len(gaps)))
    best, at = 0.0, None
    for i in range(len(gaps) - 1):
        if len(gaps) - (i + 1) < need:
            break                      # too few gaps left above this split
        a, b = gaps[i], gaps[i + 1]
        if b - a > best:
            best, at = b - a, 0.5 * (a + b)
    if at is None or best < 0.05 * size:
        return 0.22 * size
    return min(max(at, 0.08 * size), 0.30 * size)


def _run_text(glyphs: list[GlyphNode], word_gap: float = 0.0) -> str:
    """Text of a glyph run, with word breaks reconstructed from geometry.

    TeX and many other producers position words rather than emitting space
    glyphs, so concatenating `get_text()` runs every word together. A gap
    wider than a fraction of the glyph size is a word break.
    """
    out: list[str] = []
    prev: GlyphNode | None = None
    threshold = word_gap or _word_gap(glyphs)
    for g in glyphs:
        if prev is not None:
            gap = g.rect[0] - prev.rect[2]
            if gap > threshold and not out[-1].endswith(" "):
                out.append(" ")
        out.append(g.text)
        prev = g
    return "".join(out)


def plain(line: LineNode) -> str:
    return _run_text(line.glyphs)


def to_latex(line: LineNode) -> str | None:
    """LaTeX for a FLAT formula line, else None.

    Returning None is the correct answer for anything needing a layout tree.
    A caller must not substitute the plain text: that text is the glyph
    sequence in x-order, which for a formula with scripts is wrong.
    """
    if not line.flat:
        return None
    return " ".join(g.tex.latex for g in line.glyphs if g.tex.latex)


def span_reason(sp: Span) -> str:
    """WHICH PASS refused, not what the span happens to contain.

    This used to report the span's CONTENTS: any rule's role, plus
    `unmapped-glyph` if any glyph failed to project. A span holding a
    fraction therefore reported `fraction` even when the fraction was the
    one part that worked -- measured on the PDF2LaTeX dataset, the largest
    crop class was labelled `fraction` while `_split_fractions` had built
    the fraction correctly and `_attach_scripts` had refused the
    twenty-three other glyphs of the span.

    Every count in 709 rested on this string. It now names the pass that
    actually returned None, established by running them.
    """
    from structure import _attach_scripts, _split_fractions

    # RUN THE MERGES FIRST. This checked the RAW glyphs, so a span holding an
    # accent reported `accent-not-composed` whether or not the accent had
    # composed -- `glyph_latex` returns None for an accent by design, which is
    # what step 1 looks for. wzlxjtu-033 reported 13 of its 15 crops that way
    # while `_merge_accents` was consuming every one of its `\bar{z}`
    # (20 glyphs in, 15 out) and the refusal was somewhere else entirely.
    #
    # The docstring above promises the pass that ACTUALLY returned None,
    # established by running them. Step 1 was the one place that did not.
    from structure import (_merge_accents, _merge_mapsto, _merge_negations,
                           _merge_operator_runs)
    ordered = sorted(sp.glyphs, key=lambda g: g.rect[0])
    try:
        probe = _merge_operator_runs(_merge_accents(_merge_negations(
            _merge_mapsto(list(ordered))), 0))
    except Exception:
        probe = ordered
    unmapped = [g for g in probe if glyph_latex(g) is None]

    # 1a. an ACCENT is not an unmapped glyph. It has its LaTeX and is waiting
    #     to be composed with a base; `glyph_latex` returns None for it by
    #     design. Reporting it as unmapped sent 23 `circumflex` to the
    #     "add it to the table" pile when it was already in the table.
    # 752 -- A RADICAL SIGN IS NOT AN UNMAPPED GLYPH.
    #
    # `radicalbig` projects to `\sqrt` perfectly well; `glyph_latex` returns
    # None for it because a radical needs COMPOSITION with its vinculum, the
    # same as an accent needs its base. The kind is "rule" and this list did
    # not have it, so eleven of them over the corpus -- `radicalBig` 5,
    # `radicalbig` 4, `radicalBigg` 2 -- were reported as MISSING FROM THE
    # GLYPH TABLE. That is a wrong diagnosis pointing at the wrong file, and
    # it is the third time this list has been short: 15 accents were
    # mislabelled the same way before "accent" was added to it.
    pending = [g for g in unmapped if g.tex.kind in ("accent", "overlay",
                                                     "fragment", "rule")]
    truly = [g for g in unmapped if g not in pending]
    if truly:
        names = sorted({(g.glyphname or g.text or "?") for g in truly})
        return "unmapped-glyph:" + ",".join(names[:3])
    if pending:
        kinds = sorted({g.tex.kind for g in pending})
        names = sorted({(g.glyphname or "?") for g in pending})
        # every "rule" glyph is a radical sign; say so rather than "rule".
        label = "radical" if kinds[0] == "rule" else kinds[0]
        return f"{label}-not-composed:" + ",".join(names[:3])

    # 2. a rule no pass models
    unmodelled = sorted({r.role for r in sp.rules
                         if r.role not in ("fraction", "separator",
                                           "underscore", "overline")})
    if unmodelled:
        return "unmodelled-rule:" + "+".join(unmodelled)

    # 3. the fraction pass
    try:
        fracs, rest = _split_fractions(ordered, sp.rules)
    except Exception:
        return "fraction-split-error"
    bars = [r for r in sp.rules if r.role == "fraction"]
    if bars and not fracs:
        return "fraction-unresolved"
    for f in fracs:
        from structure import to_tex
        if to_tex(f.num, []) is None or to_tex(f.den, []) is None:
            return "fraction-part-unprojectable"

    # 4. the script pass, on what the fractions left behind
    if rest and _attach_scripts(rest) is None:
        return "script-attachment"
    if _attach_scripts(ordered) is None:
        return "script-attachment"

    # 5. everything the individual passes accept, and the whole still failed
    return "assembly"


def span_latex(sp: Span) -> str | None:
    """LaTeX for a maths span, or None to defer.

    Tries the structure pass first (fractions and scripts); falls back to the
    flat path when the span has no vertical structure to recover. Imported
    late because `structure` builds on the node types defined here.
    """
    if sp.kind != "math" or not sp.glyphs:
        return None
    from structure import span_to_tex

    tex = span_to_tex(sp)
    if tex:
        return tex
    if sp.flat:
        out = " ".join(x for x in (glyph_latex(g) for g in sp.glyphs) if x)
        return out or None
    # An EMPTY string is not a projection. Returning "" produced `$` + `` +
    # `$` = a bare `$$`, which pairs with a real display delimiter and makes
    # the renderer swallow the prose between them as mathematics.
    return None


def span_text(sp: Span) -> str:
    """Projection of one span: prose, `$maths$`, or an explicit deferral."""
    if sp.kind == "text":
        return _run_text(sp.glyphs)
    tex = span_latex(sp)
    if tex is not None:
        return f"${tex}$"
    return (f"<!-- DEFERRED {sp.id} rect={[round(v, 1) for v in sp.rect]} "
            f"reason={span_reason(sp)} -->")


def to_markdown(pages: list[PageNode]) -> str:
    """Markdown with LaTeX injected, and explicit markers where it is not."""
    out: list[str] = []
    for p in pages:
        if p.invisible:
            out.append(f"<!-- page {p.page}: OCR layer (Tr 3); not projected -->")
            continue
        out.append(f"<!-- page {p.page} -->")
        for ln in p.lines:
            out.append(" ".join(span_text(sp) for sp in ln.spans))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    rng = range(int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else None
    model = build(path, rng)
    print(json.dumps(to_lines_json(model), indent=1)[:2000])
