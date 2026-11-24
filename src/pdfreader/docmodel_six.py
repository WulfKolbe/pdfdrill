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
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Iterable, NamedTuple

import logging

from pdfminer.high_level import extract_pages
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.layout import LTChar, LTCurve, LTImage, LTLine, LTRect

from pdfreader import listings
from pdfreader import texmap
from pdfreader.texmap import (TexToken, family_of, greek_latex, is_drawing, space_class,
                    tex_slot, untrusted_name, names_untrusted,
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

#: 889 — RELATION SYMBOLS LIVE IN THE ROMAN FONT, and that is where three
#: separate bug reports came from.
#:
#: TeX's `\mathcode` puts a relation in FAMILY 0, the roman font: `=` is
#: "303D (class 3 = relation, family 0, slot 3D), so a display's `=` arrives
#: as CMR10 at body size — identical, by font and size, to prose. `is_math`
#: asked only "is this glyph in a maths family", so every relation in every
#: display was classified as text, and a run of upright letters AROUND one
#: went with it.
#:
#: Three reproducers, all the same shape, found by psred reading the same
#: documents:
#:
#:     sigma26-075 EQ0033   `I =`, `II = 2`, `III =`   the fundamental forms
#:     sigma26-073 EQ0945   `)=`, `):=`
#:     1709.07941  EQ0256   `+ (1`
#:
#: `\mathrm{II} = 2\sin\phi\,dx\,dy` is upright letters followed by `=`, which
#: is exactly what running text looks like to a font test. psred gets all
#: three right; we dropped the names, the relations and `\mathrm{d}` while
#: keeping the maths-font glyphs beside them.
#:
#: THIS IS THE SAME ARGUMENT THE GREEK RULE ALREADY MAKES one line below in
#: `is_math`: "TeX puts uppercase Greek in the ROMAN font, so going by font
#: alone left `\Gamma^{+}` and `\Phi` sitting in prose spans." Relations are
#: the second family of characters with that property, and the larger one.
#:
#: DELIBERATELY NARROW. Only characters that essentially never appear in
#: running English prose are listed. `(`, `)`, `[`, `]`, `:`, `;`, `,`, `.`,
#: `!`, `?`, `/` and the digits are ALSO family-0 maths characters and are
#: excluded, because they are ordinary punctuation and making them
#: unconditionally mathematical would turn prose into equations — the failure
#: pointing the other way, and a worse one. `-` needs no entry: TeX's minus is
#: family 2 (CMSY) and is already a maths family.
MATH_RELATIONS = frozenset(
    "=<>≠≤≥≈≡∼≅∝"      # = < > ≠ ≤ ≥ ≈ ≡ ∼ ≅ ∝
    "∈∉⊂⊃⊆⊇"                     # ∈ ∉ ⊂ ⊃ ⊆ ⊇
    "→↦⇒⇔←⟶⟼"               # → ↦ ⇒ ⇔ ← ⟶ ⟼
    "±∓×÷∗⋅"                     # ± ∓ × ÷ ∗ ⋅
    # `+` is family 0 too (\mathcode`+ = "202B, class 2 binary, family 0),
    # and it is the third reproducer: 1709.07941 EQ0256 lost `+ (1`, and
    # sigma26-075 EQ0033 still lost the `+` before its last `\mathrm{d}y^2`
    # with only the relations in. A `+` in running English prose is rarer
    # than an `=`; the ones that exist (`C++`, `A+`) are glued to a word,
    # and `textish` already forces a glued symbol to text.
    "+"
)

#: TeX's CLASS 2 (binary operators) among the above, kept separate because the
#: left-hand-side rule must NOT key on them.
#:
#: `\mathcode` distinguishes them: `=` is class 3 (relation), `+` is class 2
#: (binary). A definition's left-hand side is followed by a RELATION — `II =`
#: — and absorbing an upright run before a BINARY is a different and weaker
#: claim: `n + p` with an upright `n` is the case 775 deliberately kept as
#: prose, and `test_an_upright_letter_is_not_swept_in_by_this_rule` caught the
#: over-reach immediately. Both classes stay maths for `is_math` (both are
#: family 0, and the dropped `+` of EQ0256 is why), but only class 3 licenses
#: sweeping a neighbouring upright name into the mathematics.
MATH_BINARIES = frozenset("+±∓×÷∗⋅")

#: The glyph NAMES of the same characters, for a font whose encoding does not
#: give a usable Unicode value. R2 exposed the name for exactly this reason: a
#: subset font can report the wrong character and still name the glyph right.
MATH_RELATION_NAMES = frozenset({
    "equal", "less", "greater", "lessequal", "greaterequal", "notequal",
    "approxequal", "equivalence", "similar", "congruent", "proportional",
    "element", "notelement", "propersubset", "propersuperset",
    "reflexsubset", "reflexsuperset", "arrowright", "arrowleft",
    "arrowdblright", "arrowdblleft", "arrowdblboth", "mapsto",
    "plusminus", "minusplus", "multiply", "divide", "asteriskmath",
    "periodcentered", "plus",
})

#: The glyph names of the class-2 binaries, so `_is_relation` can exclude them
#: by name as well as by character.
_BINARY_NAMES = frozenset({"plus", "plusminus", "minusplus", "multiply",
                           "divide", "asteriskmath", "periodcentered"})


def _is_relation(g) -> bool:
    r"""Is this glyph a class-3 RELATION, as TeX's `\mathcode` means it?

    889 — the predicate the left-hand-side rule keys on. A relation licenses
    sweeping a short upright name into the mathematics beside it (`II =`); a
    class-2 BINARY does not (`n + p` with an upright `n` stays prose, which is
    what 775 established and what the guard test enforces).
    """
    if g is None:
        return False
    t = (getattr(g, "text", "") or "").strip()
    n = str(getattr(g, "glyphname", "") or "").strip().lower()
    if t in MATH_BINARIES or n in _BINARY_NAMES:
        return False
    return t in MATH_RELATIONS or n in MATH_RELATION_NAMES


def _needs_a_right_operand(g) -> bool:
    r"""Can this glyph NOT end a well-formed expression?

    B1 — a relation or a binary operator always has something to its right:
    `$x<$` and `$a+$` are malformed, so whatever follows is the operand. This
    is the union of TeX's class 3 and class 2, where `_is_relation` is class 3
    alone — a binary licenses no left-hand-side sweep (775, `n + p` stays
    prose) but it does demand an operand.

    `bar` is in neither set, which is what keeps `|x|` from claiming the digit
    beside it: a closing delimiter ENDS an expression.
    """
    if g is None:
        return False
    t = (getattr(g, "text", "") or "").strip()
    n = str(getattr(g, "glyphname", "") or "").strip().lower()
    return t in MATH_RELATIONS or n in MATH_RELATION_NAMES


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
    #: 893 — THE GLYPH'S MEASURED INK, or None when it could not be measured.
    #:
    #: `rect` is pdfminer's box, which is the FONT's box: every glyph of a
    #: font reports the same height, so `x` and `g` are equally tall and a
    #: `\bigl(` from CMEX reaches 8 pt into the line above. `inkboxes` reads
    #: the embedded Type 1/CFF program and returns the outline's real extent.
    #:
    #: A SECOND FIELD, never a replacement for `rect`. Twenty modules read
    #: `rect`, Type 3 and TrueType are not covered so `ink` is legitimately
    #: absent, and a plausible wrong box is the one failure that cannot be
    #: detected downstream (`inkboxes`' own contract). So readers that want
    #: the true extent ask for it and get `None` when there is none.
    ink: Rect | None = None

    @property
    def is_math(self) -> bool:
        # A Greek letter is mathematics whatever font carries it: TeX puts
        # uppercase Greek in the ROMAN font, so going by font alone left
        # `\Gamma^{+}` and `\Phi` sitting in prose spans.
        return (self.family in MATH_FAMILIES
                or greek_latex(self.glyphname) is not None
                # 889 — and a RELATION, wherever it is set. See MATH_RELATIONS.
                or (self.text or "").strip() in MATH_RELATIONS
                or str(self.glyphname or "").strip().lower()
                in MATH_RELATION_NAMES)

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


#: T-0154 — THE LATIN f AND s LIGATURES, AND THE LETTERS THEY STAND FOR.
#:
#: A typeface sets `fi`, `ff`, `fl`, `ffi`, `ffl` as ONE glyph, and pdfminer
#: returns that glyph's text as the Unicode ligature character. Kept verbatim
#: it misspells every word it appears in — `Artiﬁcial`, `deﬁnition`,
#: `Schefﬂer`, `eﬃcient` — against every reference that spells the letters
#: out: the PDF's own text layer, MathPix, the author's LaTeX.
#:
#: MEASURED over the 24 board-14 extracts at d98fa365: 223 of these
#: characters on 13 of the 24 pages (fi 172, fl 20, ff 19, ffi 12).
#:
#: `texmap._TEXT_MATHS` already decomposes them on the MATHS path, by glyph
#: NAME, because "its ligatures stand for two letters". The prose path reads
#: `glyph.text` and never passed through it.
#:
#: Only these seven. U+FB07 onwards is not Latin, and `ß`, `æ` and `œ` are
#: letters of their own alphabets, not ligatures to be taken apart.
_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
}


def _spell_glyph(text: str, glyphname: "str | None", cid: int = -1) -> str:
    r"""A glyph's text, with a ligature CHARACTER or a composite NAME spelled
    out in the letters it stands for, and a Cyrillic name on a Latin code
    read as the Latin letter.

    Three rules, and the character one runs first because it is the one the
    fonts state properly.

    1. A LIGATURE CHARACTER. `_spell_ligature`, from d1e73fe2: pdfminer
       returns U+FB01 for an `fi` glyph and keeping it misspells every word
       it stands in.

    2. A COMPOSITE NAME WHOSE TEXT IS SHORT. Linux Libertine sets the
       small-cap `Qu` of "Equity" as one glyph named `q.sc_u.sc`, and the
       font's ToUnicode maps it to a single `q` — so 1805.01788 p3 reads
       `Eqity` four times against `Equity` six. A dropped letter is a GLYPH
       finding, not a style one.

    3. A CYRILLIC LETTER ON A LATIN LETTER'S CODE. 1805.01788 sets `log` in
       LinLibertine italic, and the subset names the `g` glyph
       `afii10069.ital` -- the AFII name for Cyrillic `de`, whose italic is
       drawn like a Latin g. pdfminer trusts the NAME, so the reading said
       `loд`: a wrong character, and worse, one `glyph_latex` cannot emit
       (its letter path requires `isascii`), so the whole maths span deferred
       and the fraction it sat in was never built. The FONT'S OWN CODE says
       103, which is `g`, and the ink is a `g`.

       MEASURED, because the obvious general rule is wrong: across the ten
       documents of the inspect set, 620 glyphs decode to a non-Latin
       character sitting on a printable ASCII code, and nearly all are
       CORRECT -- TeX's quotes (`'` -> U+2019), CMSY's `p` -> U+221A,
       `2` -> U+2208. Preferring the code would have broken every one. Only
       FOUR decode to CYRILLIC, all four this same `д` on cid 103 in
       LinLibertineI on 1805.01788, every one of them a Latin g.

       So the rule is Cyrillic-only. It is still a rule about evidence, not
       about this font: a Cyrillic glyph NAME on a code that a Latin encoding
       already spells is a naming artefact of the subset. A genuinely
       Cyrillic document encodes its text at the Cyrillic code points, where
       this does not fire -- but one that put `afii10069` at code 103 through
       a /Differences array would be read as `g`, and that is the risk.

    ONLY WHERE THE TEXT IS SHORTER THAN THE PARTS. MEASURED over the 24
    board-14 extracts, every underscore-named glyph: `f_i` 29 -> 'fi',
    `f_f` 21 -> 'ff', `f_l` 6 -> 'fl', `t_t` 2 -> 'tt' — all correct
    already — and `q.sc_u.sc` 2 -> 'q', the only short one. So 58 of the 60
    composite glyphs on the whole set are untouched, and a rule that rewrote
    every `X_Y` name from its parts would be a no-op for them and a risk for
    any name whose parts are not plain letters.

    AND EVERY PART MUST REDUCE TO ONE LETTER after its `.suffix` is dropped.
    A part that does not — `dotlessi`, `ff`, a name never seen here — makes
    the whole name abstain, because inventing characters is worse than the
    one that is missing. One glyph keeps one box either way.
    """
    text = _spell_ligature(text or "")
    if (len(text) == 1 and 0x400 <= ord(text) <= 0x4FF
            and 33 <= cid <= 126 and chr(cid).isalpha()):
        return chr(cid)                   # rule 3, above
    if not glyphname or "_" not in glyphname:
        return text
    parts = glyphname.split("_")
    if len(text) >= len(parts):
        return text
    letters = []
    for part in parts:
        base = part.split(".")[0]
        if len(base) != 1 or not base.isalpha():
            return text                   # not a letter: spell nothing
        letters.append(base)
    return "".join(letters)


def _spell_ligature(text: str) -> str:
    """`text` with every Latin f/s ligature replaced by its letters.

    ONE GLYPH KEEPS ONE BOX. The letters share the box the type was set in,
    which is what the page contains; no glyph is invented and no `rect` is
    split. A caller that wants a box per letter cannot have one here, and
    would be measuring something the PDF does not state.
    """
    if not text:
        return text
    for lig, letters in _LIGATURES.items():
        if lig in text:
            text = text.replace(lig, letters)
    return text


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
    # 889 — AN OPERATOR NAME IS NOT A WORD, and counting it as one is what
    # disqualified a whole class of display.
    #
    # `\cos` and `\sin` are set upright in CMR, three letters running
    # together — indistinguishable from prose by the test below, and they
    # pushed `_longest` to 3 on sigma26-075's fundamental-forms display. That
    # failed `_mostly_math`, which disabled every absorption rule on the line,
    # which is why `\mathrm{I}`, `\mathrm{II}`, `\mathrm{III}` stayed prose
    # even after relations became mathematical. psred named this cause
    # ("operator names like sin/tanh taken as prose in displays") before I
    # measured it; the span dump confirms it — `I`, `II`, `III` and one `+`
    # were the only text spans on a line that is entirely an equation.
    #
    # `texmap.OPERATOR_NAMES` is the authority and it is taken from LaTeX's
    # own `amsopn.sty`, not remembered: 38 names, `arccos` through `Pr`. A run
    # spelling one of them is a function, so it does not count toward the
    # word test. The test still catches real prose, which does not consist of
    # `\log`, `\det` and `\tanh`.
    from pdfreader.texmap import OPERATOR_NAMES as _OPS
    _OPSET = frozenset(n.lower() for n in _OPS)

    def _is_rel(g) -> bool:
        """A class-3 RELATION, not a class-2 binary. See MATH_BINARIES."""
        if g is None:
            return False
        t = (g.text or "").strip()
        n = str(g.glyphname or "").strip().lower()
        if t in MATH_BINARIES or n in _BINARY_NAMES:
            return False
        return t in MATH_RELATIONS or n in MATH_RELATION_NAMES

    # Collect the letter runs FIRST, then judge them. The single-pass version
    # could not ask what FOLLOWS a run, and what follows is the evidence that
    # settles it.
    _runs_txt: list = []
    _cur: list = []
    _prev = None
    for _idx, _g in enumerate(ordered):
        _alpha = (not _g.is_math) and _g.text.strip().isalpha()
        if _alpha and _prev is not None and (
                _g.rect[0] - _prev.rect[2] < 0.3 * max(dom, 1.0)):
            _cur.append(_g)
        elif _alpha:
            if _cur:
                _runs_txt.append((_cur, ordered[_idx - 1] if _idx else None))
            _cur = [_g]
        else:
            if _cur:
                _runs_txt.append((_cur, _g))
            _cur = []
        _prev = _g if _alpha else None
    if _cur:
        _runs_txt.append((_cur, None))

    _longest = 0
    for _run, _after in _runs_txt:
        _txt = "".join(g.text.strip() for g in _run)
        # An OPERATOR NAME is a function, not a word — `texmap.OPERATOR_NAMES`
        # is taken from LaTeX's own amsopn.sty, 38 names.
        if _txt.lower() in _OPSET:
            continue
        # A NAME FOLLOWED BY A RELATION is a left-hand side, not a word. This
        # is the rule that `III` needed: the fundamental forms are `I`, `II`,
        # `III`, and `III` is three letters running together, so the very name
        # the absorption rule exists to rescue was what disqualified its line.
        # No English sentence puts a word immediately before an `=`.
        if _is_rel(_after):
            continue
        _longest = max(_longest, len(_run))
    _n_math = sum(1 for g in ordered if g.is_math)
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
    from pdfreader.structure import _NEGATED
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

    # 891 — A STACKED LIMIT IS PART OF ITS OPERATOR, AND IT NEVER TOUCHES IT.
    #
    # `_tight` -- the gate every absorption below passes through -- requires
    # that two runs MEET ON THE PAGE, because a CMEX radical whose baseline is
    # on this line draws its ink 30pt lower and so stole the `on` of `only`.
    # A big operator's LOWER LIMIT has exactly that shape and is correct: TeX
    # sets it below the operator's box, clear of it, by construction. The rule
    # that protects prose from a radical therefore refuses every lower limit.
    #
    # Measured on 1805.01788 p3, `DCG@k(r) = \sum_{i=1}^{k}\frac{...}{...}`:
    #
    #     summationdisplay  x 437.2..449.0  y  99.96..111.61  base 102.65
    #     k   upper limit   x 440.8..444.6  y 102.75..110.03  base 104.44
    #     i = 1             x 437.6..448.5  y  81.24.. 88.52  base  82.93
    #
    # The upper limit overlaps the operator's box and was absorbed. The lower
    # limit is 11.4pt clear of it and stayed TEXT, so the row read
    # `$\sum^{k}$ i=1 $\frac{...}$` -- the condition outside the mathematics,
    # in a page's worth of displays that all have this shape.
    #
    # NOTHING DOWNSTREAM NEEDED CHANGING. `structure.to_tex` on those same
    # glyphs AS ONE GROUP already answers `\sum_{i=1}^{k}`, and on the page's
    # other display `\sum_{i=1}^{n}|A_i - R_i| = ...` likewise. The span
    # boundary was the whole defect, which is why this is a rule about what
    # counts as mathematics and not a rule about limits.
    #
    # The evidence is the triple the band merge at 730/740 already uses to
    # tell a limit from a second equation: SCRIPT SIZE, CENTRED ON THE
    # OPERATOR'S COLUMN, and a baseline window scaled to the operator. A
    # prose word fails the first; a neighbouring term fails the second.
    # INTEGRALS ARE NOT IN THE CLASS and that is measured, not assumed --
    # `\int` is `\nolimits` even in display, 2 under against 21 beside over
    # the 102 documents, so `_LARGE_OP_STEMS` leaves it out.
    for _op in ordered:
        if _op.tex.kind != "bigop":
            continue
        # The variant suffix is `may_take_limits`' own business now -- see
        # `texmap._operator_basename`. It was stripped here for one commit,
        # because `summationdisplay.1` is what txfonts names every `\sum` on
        # 1805.01788 and the two tables are keyed by the base name.
        if not texmap.may_take_limits(_op.tex.latex, _op.glyphname):
            continue
        _ox0, _ox1 = _op.rect[0], _op.rect[2]
        _ow = max(_ox1 - _ox0, 1.0)
        _win = 2.5 * max(_op.size, dom)
        for _lim in ordered:
            if _lim is _op:
                continue
            if _lim.size >= 0.95 * _op.size:
                continue                  # a limit is set at script size
            _c = 0.5 * (_lim.rect[0] + _lim.rect[2])
            if not _ox0 - 0.75 * _ow <= _c <= _ox1 + 0.75 * _ow:
                continue
            if abs(_lim.baseline - _op.baseline) > _win:
                continue
            mathish.add(id(_lim))

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
                # B1 — A RELATION'S RIGHT OPERAND, when prose follows it.
                #
                # Absorption required maths on BOTH sides, so a digit that
                # ENDS an expression was never taken. Three occurrences on
                # the board's two worst prose pages (state 75):
                #
                #   lib:4859edad9294 p1287 L25  "... if $x <$ 0, and for a"
                #   lib:6d90e8d27b8b p174  L7   "$x(1) =$ 1 liefert $c =$ 1,"
                #
                # and the same line of 4859 shows it is NOT the digit's font,
                # which was the standing hypothesis: `... $x \geq 0, |x| =
                # -x$ if $x <$ 0, ...` — both zeros are family `text-cm`,
                # glyphname `zero`, size 12.0, and both relations are
                # recognised (`greaterequal` from CMSY, `less` from CMMI,
                # where TeX keeps `<` and `>`). What differs is only what
                # follows: maths after the first, prose after the second.
                #
                # NOR CAN SPACING DECIDE IT. Measured on that line, word gap
                # 2.20: `≥`->`0` 4.08 and `<`->`0` 4.08 are identical, and an
                # ordinary prose word gap is 4.35 — 6% wider. `_tight`
                # demands under 0.35 of the word gap, so it is no help here.
                #
                # The evidence is the mathematics: a relation or binary
                # CANNOT end an expression, so the neutral run to its right
                # is its operand. One side is enough when the left side ends
                # open.
                if (not absorb and left_any and neutral
                        and _needs_a_right_operand(runs[i - 1][-1])):
                    absorb = True
                    take_left, take_right = True, False
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
                # 889 — A NAME FOLLOWED BY A RELATION IS A LEFT-HAND SIDE.
                #
                # `_solo` requires an ITALIC single letter, so the upright
                # multi-letter names TeX sets with `\mathrm` could never be
                # absorbed: sigma26-075's fundamental forms are `\mathrm{I}`,
                # `\mathrm{II}`, `\mathrm{III}` in CMR10 at body size, flush
                # left where a section number sits. Making relations
                # mathematical (MATH_RELATIONS) recovered the `=` signs on
                # this document's 9 affected displays but not the names in
                # front of them: `I` is at the head of the line with nothing
                # mathematical to its LEFT, and adjacency on one side was not
                # enough for an upright run.
                #
                # The RELATION is the evidence. `II =` opening a display is a
                # definition's left-hand side; no English sentence puts a
                # one-to-three letter word immediately before an `=`. So the
                # right neighbour being a relation licenses the absorption
                # where italics would otherwise have to.
                #
                # Still narrow: the line must be a display, the run must be
                # 1-3 letters (so `and`, `for`, `with` cannot reach it — `and`
                # is three letters but is never followed by `=`), and the
                # relation must be the IMMEDIATE neighbour.
                # `i` indexes RUNS, not glyphs: the right neighbour is the
                # first glyph of the next RUN. Indexing `ordered` with a run
                # index found an unrelated glyph and the rule silently never
                # fired on the document it was written for.
                _nxt = runs[i + 1][0] if i + 1 < len(runs) else None
                _lhs = (_mostly_math and 1 <= len(run) <= 3
                        and all(g.text.strip().isalpha() for g in run)
                        and _is_relation(_nxt))
                # 890 — AND THE RIGHT-HAND SIDE. `dA + A \wedge \star A = 0`
                # came out `… = ` with the `0` gone: a digit is not alphabetic
                # so `_lhs` could not reach it, `_solo` wants an italic
                # letter, and the plain absorption wants mathematics on BOTH
                # sides — which `0` does not have, because an equation number
                # `(7)` sits to its right. So the whole right-hand side of a
                # relation was dropped while the relation itself survived,
                # which is the worst of the three states: the row reads as an
                # equation asserting nothing.
                #
                # Mirror of `_lhs` with the evidence on the other side, and
                # alphaNUMERIC because a right-hand side is usually a number.
                _prv = runs[i - 1][-1] if i else None
                _rhs = (_mostly_math and 1 <= len(run) <= 3
                        and all(g.text.strip().isalnum() for g in run)
                        and _is_relation(_prv))
                _l_ok = left_any and _solid(i - 1) and (left or _solo or _lhs
                                                          or _rhs)
                _r_ok = right_any and _solid(i + 1) and (right or _solo or _lhs
                                                         or _rhs)
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

    # A RUN BOUNDARY MUST NOT FALL INSIDE A FRACTION BAR.
    #
    # A span claims a rule only when the rule lies ENTIRELY within it (see the
    # note on `mine` below), so a bar cut across two runs is claimed by
    # NEITHER, and the fraction is then lost without a word. Measured on
    # 1805.01788 p3, whose DCG display came out
    #
    #     DCG@k $(r$ $) =$ $\sum^{k}$ i=1 2r ${}^{(i}$ ${}^{)} -$ 1loд2 $(i$ $+ 1)$
    #
    # -- every character present, the structure gone. The line carried the bar
    # and not one of its eleven spans did.
    #
    # The whole-line guard above refuses this line because it is 43% letters
    # (`DCG`, `log` and the variables), which is ordinary for a display. That
    # guard protects prose from being swallowed and is left alone: the bar's
    # OWN EXTENT is what needs protecting, not the line. Its x-range is what
    # the typesetter drew -- the same evidence `_split_fractions` partitions by
    # and the same one `split_terms` already refuses to cut a term on -- so the
    # runs it straddles are joined, and exactly one run holds it.
    for _r in line.rules:
        if _r.role != "fraction":
            continue
        hit = [i for i, run in enumerate(runs)
               if min(g.rect[0] for g in run) <= _r.rect[2] + 1
               and max(g.rect[2] for g in run) >= _r.rect[0] - 1]
        if len(hit) < 2:
            continue                      # already whole, or not on this line
        lo, hi = hit[0], hit[-1]
        #: THE ORDER THE PDF DREW THEM IN, not x. A fraction's two halves
        #: share a column, so x-order interleaves them -- the very defect the
        #: whole-line branch above is written against. `to_tex` separates them
        #: by the bar and does not care about the order; the FALLBACK does,
        #: and it is what a reader sees when `to_tex` refuses. Sorted by x,
        #: this line fell back to `$lo2дr2(i()i −+ 11)$`.
        _merged = [g for run in runs[lo:hi + 1] for g in run]
        runs[lo] = (sorted(_merged, key=lambda g: g.stream)
                    if all(getattr(g, "stream", -1) >= 0 for g in _merged)
                    else sorted(_merged, key=lambda g: g.rect[0]))
        for _i in range(lo + 1, hi + 1):
            runs[_i] = []
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
                <= rect[3] + 0.5 * dominant]
        # T-0156 — A RULE WITH INK ABOVE AND BELOW IT IS A FRACTION, WHATEVER
        # FONT THE INK IS IN.
        #
        # The claim above was computed only `if kind == "math"`, and `kind`
        # is decided by FONT FAMILY — so a fraction whose numerator and
        # denominator are set in a TEXT font was prose, and the bar lying
        # inside its own span was never handed to it.
        #
        # Measured on 1805.01788 p3, reference
        # `\frac{a_{i1}}{r_{i1}}=\frac{a_{i2}}{r_{i2}}`:
        #
        #     the LINE carried 2 rules, the two bars
        #     span 0 spanned x 136.2..147.1 and the bar at 136.5..147.6 was
        #       INSIDE it, yet the span held 0 rules
        #     every glyph was family `text`, so kind was `text`
        #     `to_tex` returned None and the span was flattened to x-order,
        #       numerator and denominator zipped: `arii11`
        #
        # `_split_fractions` was never at fault: given those rules it returns
        # the two Fracs. It was never reached.
        #
        # And the flattening closed a loop with the display test: `ai1ri1`
        # reads as a six-letter WORD, which is why `is_display` refused that
        # same line as prose. The flattening made the line look like prose,
        # which kept it from the pass that would have unflattened it.
        #
        # The promotion is NARROW: a rule claimed by this span must have the
        # span's own ink both ABOVE and BELOW it. A rule with ink on one side
        # only is an underline, a table border or a strike — not a fraction —
        # and the span stays prose with no rules, exactly as before.
        if kind != "math" and mine:
            mid = [0.5 * (r.rect[1] + r.rect[3]) for r in mine]
            above = any(g.rect[1] > m for g in run for m in mid)
            below = any(g.rect[3] < m for g in run for m in mid)
            if above and below:
                kind = "math"
        if kind != "math":
            mine = []
        out.append(Span(id=f"{line.id}s{n}", kind=kind, rect=rect,
                        glyphs=run, rules=mine, line_size=dominant,
                        word_gap=wg))
    return _prose_is_not_maths(out)


def _prose_is_not_maths(spans: "list[Span]") -> "list[Span]":
    r"""A span that is nothing but upright letters from a TEXT font is prose.

    The absorption rules above pull a short letter run into a neighbouring
    maths span, which is right for a variable and wrong for a word. Measured
    on lib:c57ac038ae5f p293, where the line opens "are orthogonal" and the
    rest of it is an equation: the first span came out `math` holding
    `a r e o`, and the remaining `rthogonal.` stayed text, so the reading
    emitted

        $\mathrm{are} \mathrm{o}$ rthogonal. Indeed, by (13.10), ...

    which splits a word across two spans, leaves unbalanced maths behind it
    ("Missing $ inserted" on two lines of that page), and cost 56 unpaired
    glyphs on that one line.

    The test is the GLYPHS, not the rendered string: every glyph from a text
    family, every one alphabetic, and at least two of them. A span holding a
    digit, a symbol, a script, a rule or a glyph from a maths font is left
    exactly as it was, so a variable run, an operator name beside symbols and
    `\mathrm{d}x` are all untouched. Board-wide this re-types 16 of 1,403
    maths spans, on 6 of 24 pages.

    A single letter stays maths: `$\mathrm{T}$` for a transpose and `$x$` are
    both one letter, and nothing here can tell them apart.
    """
    for sp in spans:
        if sp.kind != "math" or sp.rules or len(sp.glyphs) < 2:
            continue
        # ONE SIZE, because a script is set smaller and a script is structure.
        # `\mathrm{Mod}_{\mathrm{Z}}^{\mathrm{cn}}` is upright letters
        # throughout, so without this it re-typed as text and came out
        # `ModcZn` -- the sub- and superscript flattened into the word. Prose
        # is one size; an expression with scripts is not.
        base = sp.glyphs[0].size
        if any(abs(g.size - base) > 0.1 for g in sp.glyphs):
            continue
        if all(g.family in ("text", "text-cm") and not g.is_math
               and len(g.text) == 1 and g.text.isalpha() for g in sp.glyphs):
            sp.kind = "text"
    # AND THE WORD HAS TO BE PUT BACK TOGETHER. Spans are joined with a space,
    # so re-typing alone turned `$\mathrm{are} \mathrm{o}$ rthogonal` into
    # `are o rthogonal` -- the maths gone and the word still broken. Two text
    # spans closer than a word space were one word before the split.
    out: "list[Span]" = []
    for sp in spans:
        if (out and sp.kind == "text" and out[-1].kind == "text"
                and sp.glyphs and out[-1].glyphs and not sp.rules
                and not out[-1].rules
                and sp.glyphs[0].rect[0] - out[-1].glyphs[-1].rect[2]
                < 0.3 * max(sp.line_size or 0.0, 1.0)):
            prev = out[-1]
            prev.glyphs = prev.glyphs + sp.glyphs
            prev.rect = (min(prev.rect[0], sp.rect[0]), min(prev.rect[1], sp.rect[1]),
                         max(prev.rect[2], sp.rect[2]), max(prev.rect[3], sp.rect[3]))
            continue
        out.append(sp)
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


#: The stems a `largesymbols` font uses for its operators. A name built on
#: one of these STATES its own size class (`...display` / `...text`) and is
#: trusted; a name that is not built on one carries no size information and
#: the glyph's mapped identity decides instead. See `_bigop_raise`.
_BIGOP_STEMS = ("integral", "summation", "product", "coproduct", "union",
                "intersection", "logicaland", "logicalor", "bigodot",
                "bigoplus", "bigotimes", "contintegral")

#: LaTeX -> ems, for a glyph whose NAME cannot say which size it is.
#: Only what has been measured: `\int` on lib:6d90e8d27b8b p174, where all
#: four integral positions sit exactly 1.36 em above their display's
#: baseline (517.87 over 504.79, 419.71 over 406.75, 332.95 over 319.87).
_BIGOP_RAISE_LATEX = {r"\int": 1.36}


def _bigop_raise(glyphname: str | None, latex: str | None = None,
                 family: str | None = None, fontname: str | None = None,
                 em_width: float = 0.0, cuts: "tuple" = ()) -> float:
    r"""Ems this operator is set above the baseline of the row it belongs to.

    T-0156 — THE NAME IS NOT THE IDENTITY, AND THIS TABLE WAS THE LAST PLACE
    STILL TREATING IT AS ONE. `texmap.project` already normalises both ways a
    glyph name lies, and this lookup repeated the raw-name test without them:

      * A WRONG NAME ENTIRELY. A subset with no ToUnicode is named after
        whatever a fallback encoding puts at each code: on lib:6d90e8d27b8b
        p174 the `esint` integrals are called `acute` and `circumflex`.
        `texmap` already overrides those from the cid, so the reader KNOWS
        the glyph is `\int` while this table still saw an accent and
        answered 0.00. Unraised, the integral keeps its maths-axis baseline
        and the row grouper puts it in the PROSE LINE ABOVE: p174's
        "...liefert:" lines came out holding `$\int \int$` with their own
        displays left integral-free. The failure 750 recorded for
        wzlxjtu-024, by a different route to the same place.

    So: a name built on a `largesymbols` stem STATES its size class and is
    trusted, suffix and all; a name that is not gets the raise its mapped
    LaTeX earns, and only inside a maths extension font, where an operator
    is display-cut by construction.
    """
    name = glyphname or ""
    if name in _BIGOP_RAISE:
        return _BIGOP_RAISE[name]
    # the rest of CMEX's display-size operators -- product, coproduct, the
    # big set operators -- are cut on the same design size as the summation.
    if name.endswith("display"):
        return 0.95
    if any(name.startswith(stem) for stem in _BIGOP_STEMS):
        return 0.0                    # the name says `text`: not raised
    # The name carries no size class. Ask the font's own table, where the
    # identity was established by rendering the outline -- `texmap` knows
    # cid 31 of an `esint` subset is the DISPLAY cut and cid 30 the text one,
    # which no name here could say.
    if family == "math-extension":
        from . import texmap as _tm
        got = _tm.esint_raise(fontname, em_width, cuts)
        if got is not None:
            return got
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
    for g in group:
        if not (-0.10 * g.size <= mid - g.rect[3] <= 0.40 * g.size):
            continue
        bw = rule.rect[2] - rule.rect[0]
        gw = g.rect[2] - g.rect[0]
        # AN ACCENT'S BAR IS NOT CONTAINED BY ITS BASE. Containment is right
        # for `\overline{A}`, which TeX draws to the width of the box it
        # covers, and wrong for `\bar{M}`, which is drawn to the width of the
        # ACCENT and overhangs. Measured on 2103.01507 p118: the bar runs
        # 222.83..233.63 over an `M` at 222.84..232.50, so it failed the old
        # test by 0.63pt -- and with it all 26 of that page's overlines were
        # found, classified `overline`, and then attached to no line at all.
        # Across the board's accent-bearing pages, 45 rules were classified
        # and 8 attached.
        #
        # Overlap instead of containment, with the bar's own width held near
        # the glyph's: a rule much longer than the glyph it sits over is a
        # table rule or a frame, not this glyph's accent.
        if bw > 1.6 * gw:
            continue
        ov = min(rule.rect[2], g.rect[2]) - max(rule.rect[0], g.rect[0])
        if ov >= 0.80 * min(bw, gw):
            return True
    return False


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
        if _off_row_by_rule(g, rules, span_pt):
            continue                     # a fraction part: off-row by rule
        return False                     # a term of the row itself
    return True


def _script_beside_its_base(g, dest: list, rules: list,
                            span_pt: float) -> bool:
    r"""Is `g` off the row of `dest` — a script beside its base, or a part the
    page's own fraction bar puts off the row?

    781 — THE MEASURE IS THE DESTINATION'S OWN SIZE, NOT THE PAGE'S.

    `_off_row_band` asks `g.size < 0.95 * span_pt`, and `span_pt` is the
    dominant size of the WHOLE PAGE, so every row of any block set smaller than
    the body reads as a band of scripts in its entirety. 780 caught that once,
    for a `\ttfamily\tiny` listing, with a monospace test — which answers only
    the case where the smaller block happens to be code.

    Measured on 2016icpr page 1 (body 10.0 pt, abstract 9.0 pt): all eight
    abstract lines passed the gate and 733 moved 51 of 51, 50 of 50, 47 of 47,
    51 of 51, 54 of 54, 55 of 55, 54 of 54 and 27 of 27 glyphs onto the row
    above. `page.lines` held four rows of two lines interleaved glyph by glyph,

        (CCALbs)troafcta—bTihnearpyroimblaegmeoisflwaeblel-lidnegﬁntheedcaonnd…

    which a word-level projection prints as `an exact solution to problem the
    exists`. The library's own reading of this paper carries it.

    A superscript is small BESIDE ITS BASE; the page's dominant size says
    nothing about it. 767's clause still admits a full-size numerator, because
    there the page drew the evidence itself.
    """
    dsize = _dominant_size(dest) if dest else span_pt
    if g.size < 0.95 * (dsize or span_pt):
        return True
    return _off_row_by_rule(g, rules, span_pt)


def _off_row_by_rule(g, rules: list, span_pt: float) -> bool:
    """767's clause on its own: a FULL-SIZE glyph the page's own fraction bar
    puts off the row. Its centre is in the bar's x-range and its baseline is
    not the bar's axis, which is what makes it a numerator or a denominator
    rather than a term of the row."""
    #: A BAR CLAIMS THE ROWS BESIDE IT, NOT THE WHOLE COLUMN. The distance
    #: from the bar's axis was bounded BELOW and not above, so a glyph 200 pt
    #: away counted as a numerator. On 2312.11532 p7 `_rule_role` calls the
    #: table's booktabs midrule and six 126.6 pt chart axes "fraction", and
    #: whole body rows in their x-range were moved into the stream-preceding
    #: row -- "...in ETM, which" + "also utilizes Word2Vec." as one line,
    #: ours 0.5290 against MathPix 0.0917, unpaired 773/758 (inkdrill-10).
    #: The upper bound is 1.5 em, the window `_near_rows` already uses for
    #: the rows a bar may join.
    cx = 0.5 * (g.rect[0] + g.rect[2])
    return any(r.role == "fraction"
               and r.rect[0] - 1 <= cx <= r.rect[2] + 1
               and 0.12 * span_pt
               < abs(g.baseline - 0.5 * (r.rect[1] + r.rect[3]))
               <= 1.5 * span_pt
               for r in rules)


#: T-0154 — the widest bar whose operands may be plain, non-mathematical
#: glyphs, in em. See `_rule_role` for the measurement this comes from: real
#: fractions over digits and upright letters reach 2.0 em, and the table and
#: footnote rules misread as fractions start at 6.2 em.
_PLAIN_OPERAND_EM = 4.0


def _rule_role(node: RuleNode, glyphs: list[GlyphNode],
               size: float = 10.0, others: "list[RuleNode]" = (),
               page_width: "float | None" = None) -> str:
    """Classify a rule by what sits above and below it.

    A fraction bar has glyphs on both sides; an overline or a radical vinculum
    has glyphs below only. This is geometry, not recognition, and it abstains
    by returning "unknown" rather than picking the likelier option.
    """
    x0, y0, x1, y1 = node.rect
    mid = 0.5 * (y0 + y1)

    # A TABLE RULE IS NOT A FRACTION BAR, and it is not a listing border
    # either -- 735's reach test passes for it, because a table's rows DO
    # span their rule end to end.
    #
    # Calling one `fraction` does not merely build a wrong `\frac`: it
    # destroys the page's line structure. `_off_row_by_rule` treats every
    # glyph whose centre lies in a fraction bar's x-range as being OFF its
    # row, so one full-width rule makes `_off_row_band` true for every row of
    # the page, and the script-band pass then moves each glyph to whatever row
    # the content stream emitted before it. Measured on 1511.08771 p2709: one
    # rule at x=[72,532], `fraction`; `_off_row_band` true for 50 of 50 rows;
    # 1,145 of the page's 2,526 glyphs moved; 52 rows collapsed into 26 lines
    # of 17.5pt, two printed table rows each; the ink judge paired 73 of 2,526
    # glyphs, 2.9% of the page.
    #
    # Measured over the board's 21 born-digital pages (drillgroup 716b4d1),
    # the 56 rules this function called `fraction`, by width:
    #
    #     of the PAGE width   in ems     what they are
    #     0.064 .. 0.089      2.8 ..  3.9    real fraction bars        (8)
    #     0.344, 0.380        15.1,  23.2    wide display fractions    (2)
    #     0.550 .. 0.773      42.2 .. 47.1   table rules               (4)
    #
    # BOTH conditions, because each alone is unsafe: a share of the page is
    # blind to type size, and an em count is blind to page size. 735's
    # contract bar (160.2pt in 12pt type, 13.35 em) clears neither, so it
    # stays a fraction. `page_width` is None wherever a caller has no page --
    # every existing unit test -- and then this test does not run at all.
    if page_width and (x1 - x0) >= 0.45 * page_width and (x1 - x0) >= 25.0 * size:
        return "table"

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
    # T-0154 — A FRACTION BAR'S OPERANDS ARE MATHEMATICS.
    #
    # Neither width test above reaches a table's row rule when the table is
    # narrower than half the page: 2312.11532 p7 prints Table 3 with a rule
    # 0.38 of the page wide at 26 em, so the page-share guard misses it, and
    # a table's row spans its rule end to end, so the reach test below passes
    # it. The two rows of the table were merged into one line 83 units tall,
    # `Codebook 106 money, ... Codebook 176 life, ...`, on a board page.
    #
    # So the evidence is not the width. It is what sits over and under the
    # bar. MEASURED over the 24 board-14 extracts, 140 rules classified
    # `fraction`, of which 50 carry no mathematical glyph on either side:
    #
    #     23.2 em  2312.11532 p7   'Codebook106money / Codebook176life'  table
    #     20.3 em  2311.09533v3    'Bay,Alaska[3].The / ExamplefromASQA' table
    #     18.5 em  RE4B-DE p559    'buggeroderDBIzu / 5DynamicBinary'    footnote
    #     13.7 em  2311.09533v3    'ascaptured...The / datawascaptured'  table
    #     11.7 em  0864 p4         '10aaaab / 11bcccc'                   table
    #     11.7 em  0864 p4         '5a5a5a / 6aaaab'                     table
    #      7.2 em  2311.09533v3    'WithTTAprior / ,a7.8strike-slip'     table
    #      7.2 em  2311.09533v3    'to...priorunsup / tencewasconfirmed' table
    #      6.2 em  lib:69bc5c71b881 'https://iddp.is/ / urOlafFridleifss' footnote
    #     ----------------------------------------------------------- gap
    #      2.0 em  lib:3c16fac66fdd 'qge„ / 4m'
    #      1.5 em  lib:3c16fac66fdd '@ / @xj'      a partial derivative
    #      1.2 em  1805.01788       'ai1 / ri1'
    #      0.5 em  and below        '1 / 2', '1 / e', '3 / 4'
    #       ...    41 in all, every one under 2.1 em
    #
    # Above the gap: nine table and footnote rules. Below it: forty-one real
    # fractions whose operands are plain digits or upright letters, which
    # carry no maths font and therefore no `is_math`. Nothing lies between
    # 2.0 and 6.2 em, so every threshold in that range answers identically
    # and `_PLAIN_OPERAND_EM` is not tuned.
    #
    # ABOVE THAT BOUNDARY, MATHEMATICS ON BOTH SIDES. One side is not enough,
    # and the 4-to-12 em band is where that was measured. All nine rules the
    # board set calls `fraction` in it:
    #
    #     11.7 em  0864 p4          one      'X1X2X3X4Y / 11a11a'
    #     11.7 em  0864 p4          one      'ftheTwenty-Eighth / X1X2X3X4Y'
    #     11.7 em  0864 p4       neither     '5a5a5a / 6aaaab'
    #     11.7 em  0864 p4       neither     '10aaaab / 11bcccc'
    #      7.2 em  2311.09533v3  neither x2   table rules
    #      6.2 em  lib:69bc5c71 neither      footnote rule
    #      5.1 em  1805.01788      both      'DCG@k(ρ∗) / DCG@k(ρ)'   GENUINE
    #      4.1 em  1805.01788      both      '2rli−1 / loд2(j+1)'     GENUINE
    #
    # Both genuine fractions carry mathematics on BOTH sides; both
    # maths-on-one-side cases are 0864 p4's own table rules, one side being
    # the running head and the other the table's `X1 X2 X3 X4 Y` header set
    # in maths italic. So the same boundary serves both halves of the test,
    # and the earlier 12 em special case is gone: it had left those two
    # rules alone and that table half-merged.
    #
    # It also catches the six axis rules of Figure 3's plots on 2312 p7 —
    # `k=1` above, `100 200 300` below, 12.7 em, one maths glyph above and
    # none beneath. The set's one genuine wide display fraction keeps its
    # role: lib:3fe71b4ef018 p328, 15.1 em, nine maths glyphs above, five
    # below.
    _above_math = any(g.is_math for g in glyphs
                      if (x0 - 1 <= 0.5 * (g.rect[0] + g.rect[2]) <= x1 + 1)
                      and 0 < g.baseline - mid < window)
    _below_math = any(g.is_math for g in glyphs
                      if (x0 - 1 <= 0.5 * (g.rect[0] + g.rect[2]) <= x1 + 1)
                      and -window < g.baseline - mid < 0)
    if ((x1 - x0) / max(size, 1.0) > _PLAIN_OPERAND_EM
            and not (_above_math and _below_math)):
        return "separator"

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
                    #: T-0154 — AND A BIG DELIMITER IS NOT A TEXT LINE EITHER.
                    #:
                    #: A tall bracket is drawn RAISED — `bracketleftbig` sits
                    #: at baseline 106.9 in a row whose baseline is 98.9 — so
                    #: its baseline lands near a NUMERATOR's by coincidence.
                    #: On lib:c57ac038ae5f p293 the `\bigr]` closing the
                    #: previous term's column vector sits at baseline 79.11,
                    #: within this test's 0.1 em of the numerator's 78.15 and
                    #: 4.5 em from the bar, so it counted as a line running
                    #: across: the bar became an `overline`, `\frac{1}{2}`
                    #: was never built and `\alpha_1`'s VALUE WAS LOST
                    #: ENTIRELY — `α1 = ,` against MathPix's
                    #: `\alpha_{1}=\frac{1}{2}`.
                    #:
                    #: Same reasoning as the script test above: a running text
                    #: line is not set in script type, and it is not set in
                    #: extensible delimiters either.
                    if (g.family == "math-extension"
                            or (g.tex is not None
                                and g.tex.kind == "delimiter")):
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

    def _fits_the_bar(baselines: list[float]) -> bool:
        r"""Is the ink on this baseline the thing the rule is DRAWN TO?

        T-0162 — the under-rule branch. `\underline` and `\overline` are both
        drawn to the width of their argument, so the argument's extent and the
        rule's extent are the same measurement. This asks exactly that: the
        ink must not overflow the bar by more than a quarter em on either
        side, and must cover at least 0.45 of it.

        NOT `_sits_under`, which sums the FULL WIDTH of every glyph whose
        CENTRE falls in the bar's x-range. That sum can exceed the bar's width
        without the ink fitting it at all: a 80 pt word centred over a 4.7 pt
        rule passes, which is precisely the short-table-rule case this branch
        must not claim. `_sits_under` needed the sum because
        `\overline{e_1 e_2 e_3}` covers six narrow glyphs and no single one is
        near the bar's width — and a union extent would serve that case too,
        so `_sits_under` is probably better off written this way. It is NOT
        changed here: 107 rules on the board are `overline` today and that is
        a separate measurement, not a tidy-up to ride along with this.
        """
        if not baselines:
            return False
        want = max(set(baselines), key=baselines.count)
        near = [g for g in glyphs
                if abs(g.baseline - want) <= 0.1 * max(size, 1.0)
                and x0 - 1 <= 0.5 * (g.rect[0] + g.rect[2]) <= x1 + 1]
        if not near:
            return False
        ex0 = min(g.rect[0] for g in near)
        ex1 = max(g.rect[2] for g in near)
        slack = 0.25 * max(size, 1.0)
        if ex0 < x0 - slack or ex1 > x1 + slack:
            return False
        return (ex1 - ex0) >= 0.45 * max(x1 - x0, 0.1)

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
    #: T-0162 — INK ABOVE AND NOTHING BELOW HAD NO BRANCH AT ALL, so every
    #: `\underline` in the corpus came back `unknown`, and an unaccounted rule
    #: defers the whole span.
    #:
    #: MEASURED AND CHECKED AGAINST THE AUTHOR (standing rule, 2026-11-23).
    #: arxiv.gr-qc_0212041 p1 draws three such rules, each 4.7 pt wide and
    #: 0.48 pt thick, each exactly spanning a CMMI10 `e` 1.33 pt above it —
    #: and the author's own source (CG.tex from the e-print) holds exactly
    #: three `\underline`, every one `\underline{e}`.
    #:
    #: IT CANNOT BE WRITTEN WITH `above`. `_is_own_row` counts what else sits
    #: on the numerator's baseline outside the bar, to catch a text line
    #: running across — and an underlined letter IS part of a running line:
    #: `=`, `d` and `x` share the baseline of all three on that page, so
    #: `above` is False for every one. Containment is the test that fits, the
    #: same evidence the overline uses.
    #:
    #: `\underrightarrow` IS NOT HERE, and an earlier note had the two queued
    #: as one defect. The same author writes it 43 times and TeX builds it
    #: from GLYPHS — a `minus` and an `arrowright` from CMSY10 on one
    #: baseline, overlapping — so no rule is drawn and no branch here could
    #: emit one. That is a glyph-composition task.
    #: AND IT HAS TO HAVE BEEN DRAWN AS A LINE. Found by checking the four
    #: rules this branch newly claimed on the board set, none of which is a
    #: `\underline` and three of which have NO THICKNESS AT ALL:
    #:
    #:   2311.09533v3 p1  33.6pt 3.09em h=0.00  above 'BAaGyR,AElEawsk/oaT.'
    #:                                          — two interleaved rows of
    #:                                          NimbusRom, i.e. a link or
    #:                                          frame rule under a byline
    #:   lib:b21e554b9232 6.5pt 0.60em h=0.00  above 'te', mid-word (x2)
    #:   lib:5a5c76391c9c 12.2pt 1.22em h=0.66  above CambriaMath `L_c(`
    #:
    #: The three verified cases — 0212041's `\underline{e}`, against the
    #: author's own source — are 0.48pt thick. A rule with zero thickness was
    #: not drawn as a line, and this reader already knows that shape: the
    #: underscore branch above says `took_*` "reaches the model as a 3.14pt
    #: ZERO-HEIGHT rule at the baseline". No threshold: either it has
    #: thickness or it does not.
    #:
    #: The fourth, at 0.66pt, still passes and is NOT verified — no author
    #: source exists for that document. It is on a page the board does not
    #: judge, so no board number moves either way, and it is recorded here
    #: rather than argued away.
    if (y1 - y0) > 0 and _fits_the_bar(above_b) and not below_b:
        return "underline"
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


def _row_straddles_bar(grp: list, rule: "RuleNode", span_pt: float) -> bool:
    r"""True when this row ALREADY holds both halves of `rule`'s fraction.

    `_group_lines`' script fold sometimes puts a numerator and a denominator
    in one row before the bar merge runs. The bar then joins that finished
    fraction to whatever sits nearest above it, and on lib:c57ac038ae5f p293
    that is a complete sentence: "By (13.5) we have Q(xk + apk) = ... where
    rk :=b-Axk.SincepTk Apk >= 0..." -- two text rows run together with the
    second's spaces lost. It is caught because the host row's own
    superscripts fall inside the bar's x-range.

    A row with glyphs on BOTH sides of the bar, inside its x-range and within
    the two line-heights `_near_rows` already uses, is the whole fraction. A
    real two-row fraction has each half on one side only and still merges.
    """
    mid = 0.5 * (rule.rect[1] + rule.rect[3])
    above = below = False
    for g in grp:
        if g.rect[0] < rule.rect[0] - 2 or g.rect[2] > rule.rect[2] + 2:
            continue
        if abs(g.baseline - mid) > 2.0 * span_pt:
            continue
        if g.baseline > mid:
            above = True
        elif g.baseline < mid:
            below = True
    return above and below


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


def _region_holding(rect, regions) -> "int | None":
    """The index of the region whose box holds this rect's centre, or None."""
    cx = 0.5 * (rect[0] + rect[2])
    cy = 0.5 * (rect[1] + rect[3])
    for i, (x0, y0, x1, y1) in enumerate(regions):
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return i
    return None


def _without_edge_band(regions, em: float = 0.0) -> list:
    r"""`regions`, each shrunk at its LEFT and BOTTOM edge by the band.

    A region is left alone where shrinking it would empty it. The regions
    themselves are never replaced: they are the crop rectangles and the page
    keeps them; this is the box the glyph FILTER asks about.
    """
    band = _DIAGRAM_EDGE_EM * (em or _DIAGRAM_EM)
    out = []
    for x0, y0, x1, y1 in regions:
        nx0, ny0 = x0 + band, y0 + band
        out.append((nx0, ny0, x1, y1) if (nx0 < x1 and ny0 < y1)
                   else (x0, y0, x1, y1))
    return out


def _spans_two_regions(glyphs, regions) -> bool:
    r"""Is this line made ENTIRELY of figure glyphs, from two or more figures?

    The band admits a figure's edge text and the row grouper then reads
    across the page: three charts side by side put their axis labels on one
    baseline, so 2312.11532 p7 gained `'100 100'`, `'(b 100'` and
    `'k=1 k=1 k=1'`, each from two or three different figures. Such a line is
    REFUSED rather than merged — a local decision that needs no per-region
    grouping.

    ENTIRELY, because a line of prose that happens to pass a figure is
    somebody else's and must not be dropped.
    """
    live = [g for g in (glyphs or []) if (g.text or "").strip()]
    if not live:
        return False
    tags = [_region_holding(g.rect, regions) for g in live]
    if any(t is None for t in tags):
        return False
    return len(set(tags)) >= 2


#: T-0154 — the band at a figure region's left and bottom edge, in em, where
#: an axis and its labels live. MEASURED over the 24 board-14 extracts: of
#: the 688 glyphs inside a detected region, 235 sit within 3 em of a left or
#: bottom edge and 453 in the middle, which is the ink the filter exists for.
#: On 0864 p4 a 3 em band returns exactly the ten y-axis tick labels and
#: nothing else.
_DIAGRAM_EDGE_EM = 3.0

#: The em the band is counted in. The figure text measured here is 7 pt
#: against a 10 pt body, and a region carries no type size of its own.
_DIAGRAM_EM = 7.0


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
    # A PAGE CAN HAVE MARKS AND NO MEASURABLE TEXT SIZE: a full-page figure
    # made entirely of drawing-font glyphs and strokes leaves `_dominant_size`
    # with nothing to take a mode of, and it returns 0. `gap` is then 0 and the
    # grid key below divides by it — 22 documents in the corpus pass died
    # there, the largest class of the 47.
    #
    # The join distance has to come from somewhere, so it comes from the marks
    # themselves: the median mark height, which is the only scale the page
    # actually states. A page whose marks have no height either is a page with
    # nothing to cluster.
    if gap <= 0:
        heights = sorted(r[3] - r[1] for r in marks if r[3] > r[1])
        if not heights:
            return []
        gap = 3.0 * heights[len(heights) // 2]
    if gap <= 0:
        return []

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
        from pdfreader import psstream
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
        vertical = abs(b) > abs(a)
        if vertical:                              # advances along y
            run.sort(key=lambda g: g.matrix[5], reverse=b < 0)
        else:                                     # advances along x
            run.sort(key=lambda g: g.matrix[4], reverse=a < 0)
        out.extend(_split_rotated_run(run, vertical))
    return out


def _split_rotated_run(run: list["GlyphNode"],
                       vertical: bool) -> list[list["GlyphNode"]]:
    r"""Cut a sideways run where a gap says one label has ended.

    T-0156 — THE MISSING HALF OF A RULE THE HORIZONTAL SIDE ALREADY HAS.
    `_group_rotated` keys a run on the coordinate PERPENDICULAR to the
    writing direction, so every rotated glyph sharing a rounded x lands in
    ONE run however far apart it is along the writing axis — and nothing
    then split it. Horizontal rows are split at a wide gap (see
    `_column_edge`, which takes a gap of 1.5 type sizes as separating two
    blocks on one row); sideways runs were not.

    What it cost, on board 0864 p4 — the board's worst `ours` row at 0.0656,
    nearly twice the next:

        our page 2        242 lines, 135 of them `rotated_text`
        MathPix's          83 lines
        the reading held  `monspc`, `PUSPUS`, `rndOO`, `rrd(O,O)`

    Those are Figure 3's axis and legend labels run together — two or three
    distinct labels per line. The judge's unpaired glyphs are the same
    characters on BOTH sides (14 E, 7 Y, 7 U, 7 S … identical distributions),
    so nothing was lost: the text was read and placed wrong, and 50% of the
    226 unpaired sat in five lines.

    THE THRESHOLD IS NOT NEW AND NOT FROM THIS PAGE. It is `_column_edge`'s
    1.5 type sizes, the same rule applied along the other axis. Measured in
    ems of each run's own size, the three merged runs separate on it:

        'monspc'    0.39 0.25 [2.41] 0.19 0.25
        'PUSPUS'    0.93 1.09 [5.54] 0.93 1.08
        'rrd(O,O)'  0.43 0.43 0.64 0.61 [4.89] 0.72 [4.48]

    within-label gaps 0.19-1.09, between-label 2.41-5.54. An arXiv stamp,
    the other thing this function exists for, has word gaps far below it and
    stays one run.
    """
    if len(run) < 2:
        return [run]
    size = max((g.size for g in run), default=10.0)
    lo, hi = (1, 3) if vertical else (0, 2)
    out, cur = [], [run[0]]
    for prev, g in zip(run, run[1:]):
        # the clear distance between the two glyphs along the writing axis,
        # whichever way round they are
        gap = max(g.rect[lo] - prev.rect[hi], prev.rect[lo] - g.rect[hi])
        if gap >= 1.5 * size:
            out.append(cur)
            cur = [g]
        else:
            cur.append(g)
    out.append(cur)
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
    # THE BUCKET LABEL IS NOT A COORDINATE, so keep the x that made it.
    # `int(x // 12) * 12` rounds DOWN to a 12 pt grid: 2009tiplabeling's right
    # column starts at 311.97 and is filed under 300. Reading the label back
    # as a position is an error of up to 12 pt, and a gutter is 12 pt wide.
    pos: dict[int, list[float]] = {}
    for r in rows:
        if len(r) <= 8:
            continue
        x0 = min(g.rect[0] for g in r)
        k = int(x0 // 12) * 12
        edges[k] = edges.get(k, 0) + 1
        pos.setdefault(k, []).append(x0)
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
            pos.setdefault(k2, []).append(at)
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
    # A second mode, well to the right of the first and past the middle,
    # carrying a real share of the rows.
    #
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
    # A SECOND COLUMN IS THE WIDTH OF THE FIRST, and that is what picks it out
    # of the modes that clear the guards. The rule was "the FIRST mode past
    # 0.9 * mid", and a display equation indented in the LEFT column clears
    # every guard: measured on 2009tiplabeling page 1 (text 49..563, gutter at
    # 313) the answer came back 278.2, seven rows were cut in the wrong place,
    # and 10 of 88 finished lines still carried both columns' glyphs at one
    # baseline. Across the fifteen CCL readings that was 2,165 of 9,688 body
    # lines, 22.3%, and it is what the owner's Claude.ai chat reported as the
    # columns being mixed up.
    #
    # Two columns of a paper are the same width by construction, so the second
    # starts near the middle of the text MEASURE (not of the page: a wide
    # margin moves the one and not the other). Among the candidates that pass,
    # take the one nearest to that.
    span0 = min((min(g.rect[0] for g in r) for r in rows if r), default=rect[0])
    span1 = max((max(g.rect[2] for g in r) for r in rows if r), default=rect[2])
    target = first + 0.5 * (span1 - span0)
    # AND IT CARRIES A COMPARABLE SHARE OF THE ROWS. `n >= 2` let three rows of
    # an indented equation stand in for a column: measured on a synthetic
    # one-column page (text 85..510, an equation at 280), the old rule invented
    # a gutter at 271.2 and 748 records what that costs in the real corpus —
    # equation 4's denominator cut into `\frac{p_{0\mid0}}{- p}`. The code's
    # own note says a real page's two columns carry 43 rows and 43; half the
    # first column's own mode is the weakest form of that statement.
    need = max(2, 0.5 * edges.get(first, 0))
    cands = [k for k, n in ordered
             if k > first + 0.25 * (rect[2] - rect[0]) and k > mid * 0.9
             and n >= need]
    if cands:
        k = min(cands, key=lambda k: abs(k - target))
        gl = [g for r in rows if r for g in r]
        size = _dominant_size(gl) if gl else 10.0
        size = size or 10.0
        # THE EDGE IS THE MIDDLE OF THE GUTTER, AND THE GUTTER IS MEASURED.
        #
        # What stood here subtracted half a body size from `k` — and `k` is a
        # 12 pt bucket LABEL. Measured on 2009tiplabeling page 1: the right
        # column starts at 311.97, which buckets to 300, and the answer came
        # back 300 - 5 = 295.0 while the LEFT column's text ends at 300.02. The
        # cut point sat four points inside the left column, so no row could be
        # split there: every body row has contiguous glyphs across 295 (`t`
        # [287.8,290.6] `h`[290.6,295.6] `e`[295.6,300.0] in "...part of the
        # foreground..."), the gap walk in `_split_at_columns` found no gap
        # bracketing the edge on 11 of 13 straddling rows, and 15 of 88 lines
        # finished carrying both columns. The splitter was never the fault.
        #
        # So resolve the label back to the column's own start, find where the
        # column to its left actually ends, and cut between them. On that page
        # the band is empty from 302 to 310 by glyph occupancy, and this puts
        # the edge at 306.0.
        start = min(pos.get(k) or [float(k)])
        # Rows wholly left of that start are the left column; a row that
        # crosses the gutter (a full-width table, or a row still merged at
        # this stage) is not evidence of where the column ends.
        ends = [max(g.rect[2] for g in r) for r in rows
                if r and max(g.rect[2] for g in r) <= start]
        # A GUTTER IS A FEW POINTS WIDE. Where every left-column row is still
        # merged, the widest row left of the start is some short figure label
        # and the midpoint would land deep inside the text; take the margin
        # instead. Three body sizes is the bound: 2009tiplabeling's gutter is
        # 11.95 pt against a 10 pt body.
        if ends and start - max(ends) <= 3.0 * size:
            return 0.5 * (max(ends) + start)
        return start - 0.5 * size
        # A SMALL margin left of the second column, not the midpoint to
        # the first column's widest line. The midpoint is computed from
        # rows that may still be fragments at this stage, and it landed
        # at x=121 on a page whose columns divide at 312 -- cutting a
        # bullet item in half after `We evaluate T`.
        #
        # THE BODY'S SIZE, NOT THE PAGE'S LARGEST. `max` over every glyph on
        # the page is the TITLE's size, and half of a 19.6 pt title is 9.8 pt
        # of margin where the gutter is 5: measured on 2009tiplabeling page 1
        # the mode is 300, the left column's text ends at 295, and the cut
        # landed at 290.2 -- four points INSIDE the left column, so its last
        # glyphs were handed to the right column and 9 of 88 lines still held
        # both. The dominant size is the body text, which is what a gutter is
        # measured in.
    return None


class _PanelBarriers(NamedTuple):
    r"""The gutters between side-by-side figure panels, WITH their band.

    T-0156 — THE BAND IS PART OF THE BARRIER, and this type exists because
    three consumers in a row forgot it. A barrier is evidence about the
    strip of page the panels occupy and about nothing else:

        the cross-panel detector  ignored Y -> flagged 60 prose lines
        `_split_at_panel_gutters` ignored Y -> cut `on the sign convention.`
                                               mid-word
        the script-absorption veto ignored Y -> detached
                                  `\psi|_{K_{H} \times\{0\}}` from its base,
                                  with chars +0, so every count passed
        the rejoin sweep           ignored Y -> latent, found while writing
                                               this type

    Each was fixed in the commit after the one before, because the band was
    something a caller had to remember rather than something the barrier
    carried. So `crosses` does the whole test and there is no way to ask
    about the x without the y.
    """

    xs: tuple
    y0: float
    y1: float

    def crosses(self, x_lo: float, x_hi: float,
                y_lo: float, y_hi: float, *, reach: float) -> bool:
        """Does a gutter lie between `x_lo` and `x_hi`, for ink whose y
        range overlaps the band? No gutters, or ink out of band, is False —
        the barrier simply has nothing to say there.

        A Y RANGE, NOT A BASELINE, and the difference is measured. Routing
        the row split through a baseline point dropped 2312.11532 p7's
        subfigure captions back into one line: the caption's baseline sits
        2.4 pt BELOW the band while its rect reaches into it, so a point
        test excluded exactly the row the rule exists to cut. A caller with
        one glyph passes its own box; a caller with a row passes the row's.
        """
        if not self.xs:
            return False
        lo, hi = (y_lo, y_hi) if y_lo <= y_hi else (y_hi, y_lo)
        if hi < self.y0 - reach or lo > self.y1 + reach:
            return False
        a, z = (x_lo, x_hi) if x_lo <= x_hi else (x_hi, x_lo)
        return any(a <= x <= z for x in self.xs)


def _panel_barriers(diagrams: list[Rect]) -> "_PanelBarriers":
    r"""The x of each gutter BETWEEN two horizontally adjacent figure
    panels, and the band those panels occupy.

    One definition for every consumer — the row split, the rejoin sweep and
    the script-absorption veto — because a barrier one of them honours and
    another ignores is no barrier at all: measured, the sweep put
    2312.11532 p7's three subfigure captions back into one line after the
    split had separated them, and the absorption pass then put the legend
    digits back one digit at a time.

    Panels that overlap in x are stacked rather than side by side and yield
    no barrier.
    """
    rects = list(diagrams or [])
    spans = sorted((r[0], r[2]) for r in rects)
    xs = tuple((a1 + b0) / 2.0 for (_, a1), (b0, _) in zip(spans, spans[1:])
               if b0 > a1)
    if not xs:
        return _PanelBarriers((), 0.0, 0.0)
    return _PanelBarriers(xs, min(r[1] for r in rects),
                          max(r[3] for r in rects))


def _split_at_panel_gutters(rows: list[list["GlyphNode"]],
                            diagrams: list[Rect]) -> list[list["GlyphNode"]]:
    r"""Cut a row that reads across the gutter BETWEEN two figure panels.

    T-0156 — THE BOARD'S WORST `ours` ROW, AND NOT A MISSING THRESHOLD.
    2312.11532 p7 at judge 0.0454 has clean prose and 26 unpaired glyphs,
    every one of them on two lines:

        L6    0.050.25                                      6 unpaired on A
        L55   (d)NYT-NPMI.100(e)NYT-Diversity.30000(f)...  10 A + 10 B

    L6 loses the page's `k=3` and `k=1`; L55 carries the legend digits at
    x 1348..2093 where the page has them at 1735..3004 — THE SAME
    CHARACTERS IN THE WRONG PLACE. Three charts side by side put their tick
    labels, legends and subfigure captions on one baseline each, and the row
    grouper reads straight across:

        '0.15 1.0 0.15'                      panels 0,1
        '0.1 0.1'                            panels 0,1
        '0.05 k=3 k=3 0.05 k=3'              panels 0,1,2   <- L6
        '(d) NYT-NPMI. $100 200$ 300(e) ...' panels 0,1,2   <- L55

    THE GAP RULE IS NOT THE PROBLEM, which is why nothing here is a new
    number. Measured in each row's own type size, the gaps at the panel
    boundaries are 15.2, 20.1, 20.7, 43.1 em against `_column_edge`'s 1.5 —
    ten to thirty times over. What was missing is a BARRIER saying the gap
    is a figure boundary and not word spacing.

    WHY THE THREE EXISTING MECHANISMS DO NOT COVER IT, each checked before
    this was written:

      * `_spans_two_regions` already refuses a line drawn from two figures,
        and its docstring names this very page. It requires the line to be
        made ENTIRELY of glyphs INSIDE a region, and a chart's tick labels
        and caption are drawn just OUTSIDE the plot rectangle: of the four
        rows above, three have NO glyph in any region and the fourth has 8
        outside. Correct for what it does, blind to this.
      * `_column_edge` yields ONE page-level boundary, where the second
        column starts. Three panels need two, and it ignores any row of 8
        glyphs or fewer, which `'0.1 0.1'` is.
      * `_split_local_columns` INFERS a gutter from 3+ wide rows banded by
        vertical adjacency. The figure band holds four rows at four
        different baselines, so the bands are too small and it returns
        early.

    So the barrier comes from the page's own figure geometry — the diagram
    rectangles already detected and already kept on the page — and the
    threshold stays `_column_edge`'s 1.5 type sizes. A row is cut where a
    gap of at least 1.5 sizes CONTAINS the midpoint of a gutter between two
    horizontally adjacent panels. Both conditions are needed: the gap alone
    splits ordinary word spacing inside a wide caption, and the barrier
    alone splits a caption that legitimately runs under all three panels.
    """
    if not diagrams or len(diagrams) < 2:
        return rows
    # The gutters between horizontally adjacent panels, as barrier x's. Two
    # panels that overlap in x (stacked, not side by side) give no barrier.
    bars = _panel_barriers(diagrams)
    if not bars.xs:
        return rows
    # AND THE BARRIER REACHES ONLY AS FAR AS THE FIGURES THEMSELVES.
    # A gutter is evidence about the band the panels occupy and about
    # nothing else on the page. Without a vertical test, prose that merely
    # crosses a barrier x is cut: on arxiv.2609.23822 `on the sign
    # convention.` became `on the sign conventi` + `on.` (the tail then
    # typed as maths) and the regrouping cost `e^{n-1}` its exponent.
    #
    # THE REACH IS 2.0 OF THE ROW'S OWN TYPE SIZE, AND IT IS THE ONLY NEW
    # NUMBER IN T-0156. Everything else here reuses `_column_edge`'s 1.5.
    # 1.5 was tried and is WRONG: measured on the rows the splitter itself
    # receives,
    #
    #     2312.11532 p2  caption '(d) NYT-NPMI...(f) NYT-TQ.'
    #                    14.0 pt below the panels, row size  9.0 = 1.56 sizes  CUT
    #     2609.23822     prose 'on the sign convention.'
    #                    28.2 pt below the panels, row size 12.0 = 2.36 sizes  KEPT
    #
    # the window is (1.56, 2.36) and 1.5 falls BELOW it, excluding the
    # caption it exists to cut — by 0.6 pt. 2.0 sits near the middle, with
    # 29% of margin on the caption and 15% on the prose; `1.5 x the page's
    # dominant size` also fits the window but leaves only 7% on the caption
    # side, so it was rejected.
    #
    # THE WINDOW RESTS ON TWO ROWS, which is thin evidence for a constant
    # and is stated here so the next reader does not take it for more. Its
    # check is the held-out sample: 220 library pages drawn at interior
    # pages (seed 20261123), 217 of them carrying no adjacent panels at
    # all, 2 changed and 0 worse. A third row that falls inside (1.56,
    # 2.36) would narrow the window and may move this number; that is a
    # measurement to take, not a reason to widen the reach now.
    #
    # HOW 1.5 CAME TO LOOK RIGHT: I measured the caption's offset as 1.8 pt
    # on the FINAL merged row, whose box is inflated by legend digits drawn
    # higher up the page, instead of on the row this function is handed.
    # Measuring the output rather than the input is what let the number be
    # wrong by a factor of eight.
    #
    # Per ROW, because a caption is set in the figure's type size and the
    # prose below it is not. The failure modes are asymmetric — too tight
    # misses a merge, too loose breaks prose — so where the window is this
    # narrow, erring tight is the safe side.
    # A FIRST VERSION REACHED A FULL PANEL HEIGHT (58.3 pt here) and cut
    # that prose line by 4.7 pt.
    out: list[list[GlyphNode]] = []
    for row in rows:
        if len(row) < 2:
            out.append(row)
            continue
        ordered = sorted(row, key=lambda g: g.rect[0])
        size = max((g.size for g in ordered), default=10.0)
        parts, cur = [], [ordered[0]]
        for prev, g in zip(ordered, ordered[1:]):
            gap = g.rect[0] - prev.rect[2]
            # ONE call, so the band cannot be left out (`_PanelBarriers`).
            if gap >= 1.5 * size and bars.crosses(
                    prev.rect[2], g.rect[0],
                    min(x.rect[1] for x in ordered),
                    max(x.rect[3] for x in ordered),
                    reach=2.0 * size):
                parts.append(cur)
                cur = [g]
            else:
                cur.append(g)
        parts.append(cur)
        # A row that did not cross a barrier is returned UNTOUCHED, in its
        # original order, so this function is a no-op wherever it does not
        # fire.
        out.extend(parts if len(parts) > 1 else [row])
    return out


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


def _bar_by_its_spacing(glyphs: list["GlyphNode"]) -> None:
    r"""A vertical bar is a DELIMITER unless the page gave it a relation's space.

    `texmap` maps CMSY's `bar` to `\mid`, which is a class-3 relation and sets
    a thick space on each side. The page usually prints `|x|=x`, flush: on
    lib:4859edad9294 p1287 the reading emitted `$\mid x\mid = x$`, every glyph
    after the first bar shifted, and 28 of that line's glyphs failed to pair
    with the page -- while the pairs that did form had zero glyph findings.

    The ink says which it is. Measured over the board's 24 pages, 122 bar
    glyphs with a neighbour on each side, as the smaller gap in ems:

        p0 .. p75   -0.404 .. 0.003     flush: a delimiter
        p90, p100    0.278,   0.518     spaced: a relation
        above 0.15 em                   17 of 122

    So 0.15 em, in the empty middle. A bar at the end of a line, or with no
    neighbour on one side, keeps the mapping it had -- there is nothing to
    measure and `\mid` is the safer of the two.
    """
    ordered = sorted(glyphs, key=lambda g: (round(g.baseline * 4), g.rect[0]))
    for i, g in enumerate(ordered):
        if (g.glyphname or "") != "bar" or g.tex.latex != r"\mid":
            continue
        left = ordered[i - 1] if i else None
        right = ordered[i + 1] if i + 1 < len(ordered) else None
        if left is None or right is None:
            continue
        if abs(left.baseline - g.baseline) > 0.1 or abs(right.baseline - g.baseline) > 0.1:
            continue
        em = max(g.size, 1.0)
        gap = min((g.rect[0] - left.rect[2]) / em, (right.rect[0] - g.rect[2]) / em)
        if gap < 0.15:
            g.tex = g.tex._replace(latex="|", kind="delimiter")


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
    from pdfreader.texmap import operator_name
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
        # THE SAME QUESTION ON THE LEFT. The run-must-END-here guard below
        # refuses `supp`, and said why: an upright roman letter glued to a
        # name at a tight gap makes the whole thing a WORD. This walk
        # advances one glyph at a time, so it also arrives at the `l` of
        # `muslim`, where `lim` spells a name and nothing follows it --
        # and 2312.11532 p7 came back as `$\mathrm{mus}\lim,$ turkish`
        # (T-0154, seen on the board's own `glyphlines` route). `supp` was
        # refused and `ppsup` was not, by the identical argument.
        prv = ordered[i - 1] if i else None
        if (prv is not None
                and prv.family in ("text", "text-cm")
                and len(prv.text) == 1 and prv.text.isalpha()
                and abs(prv.size - ordered[i].size) <= 0.1
                and abs(prv.baseline - ordered[i].baseline) <= 0.1
                and ordered[i].rect[0] - prv.rect[2]
                <= 0.12 * ordered[i].size):
            out.append(ordered[i])
            i += 1
            continue
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
    from pdfreader.texmap import OVERLAY_PAIRS
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


#: A TEXT ACCENT'S GLYPH NAME, AND THE COMBINING MARK THAT COMPOSES IT.
#: Adobe glyph names on the left, Unicode combining marks on the right. Only
#: marks that compose with a Latin letter into a precomposed character are
#: listed: `unicodedata` decides whether a given pair has one, and a pair that
#: has none is left as it was rather than written as two characters that look
#: like one.
_TEXT_ACCENT_MARK = {
    "dieresis": "̈", "acute": "́", "grave": "̀",
    "circumflex": "̂", "tilde": "̃", "caron": "̌",
    "macron": "̄", "breve": "̆", "ring": "̊",
    "ringabove": "̊", "dotaccent": "̇", "cedilla": "̧",
    "hungarumlaut": "̋", "ogonek": "̨",
}


def _compose_text_accents(rows: list[list["GlyphNode"]]) -> list[list["GlyphNode"]]:
    r"""An accent over a letter is ONE character, in prose.

    TeX sets `Saarbr\"ucken` as the accent first, at an offset, and the base
    letter after it one point to the left:

        39  r         x=370.94
        40  dieresis  x=375.92   tex.latex='\ddot'
        41  u         x=374.92

    `\ddot` is a MATHS accent, so the dieresis opened a maths span and took
    the rest of the word with it -- pdfdrill read 0864's affiliation line as
    `... Saarbr $\mathrm{ucken},$ Germany`, and pdf2mmd2, from the same
    glyphs, cut the line in two at the accent instead. Measured on 0864: 42 of
    69 unpaired open-page lines are an accent or end at one.

    `structure._merge_accents` already composes a MATHS accent, but a prose
    word never reaches the maths structure pass. So the pair is composed here,
    into the character the page actually shows, before spans are decided.

    THE BASE IS THE NEXT GLYPH IN THE ROW, and only if it sits under the
    accent: TeX positions the accent over its base, so their boxes overlap. A
    letter further along the line is somebody else's.
    """
    out = []
    for row in rows:
        if not any((getattr(g, "glyphname", "") or "") in _TEXT_ACCENT_MARK
                   and (getattr(g, "family", "") or "").startswith("text")
                   for g in row):
            out.append(row)
            continue
        new: list = []
        skip = -1
        for i, g in enumerate(row):
            if i == skip:
                continue
            mark = _TEXT_ACCENT_MARK.get(getattr(g, "glyphname", "") or "")
            fam = getattr(g, "family", "") or ""
            if not mark or not fam.startswith("text") or i + 1 >= len(row):
                new.append(g)
                continue
            base = row[i + 1]
            bt = base.text or ""
            #: One letter, under the accent. The boxes overlap because TeX
            #: centres the accent on its base; a glyph that merely follows on
            #: the line is not a base.
            if (len(bt) != 1 or not bt.isalpha()
                    or base.rect[0] > g.rect[2] or base.rect[2] < g.rect[0]):
                new.append(g)
                continue
            composed = unicodedata.normalize("NFC", bt + mark)
            if len(composed) != 1:
                new.append(g)          # no precomposed character exists
                continue
            #: AND ITS LaTeX, or a MATHS span loses the accent.
            #:
            #: This used to set `text` alone. A prose span is written from
            #: `text` and was right; a maths span is written from
            #: `tex.latex`, which still said `x`. MEASURED on
            #: lib:6d90e8d27b8b p174, whose derivatives are dotted: pdfminer
            #: gives 22 `˙` glyphs, this pass composes them into `ẋ` x18 and
            #: `ċ` x4, their `tex.latex` stayed `x` and `c`, and the reading
            #: held 0 `\dot` against MathPix's 22 `\dot{x}`. The composition
            #: was working and its result never reached the reading.
            #:
            #: The accent glyph already carries the command (`_TEXT_ACCENT`
            #: gives `dotaccent` the token `\dot`), so the composed token is
            #: that command applied to the base's own LaTeX, and nothing is
            #: invented. Where the accent has no command, the base's token
            #: is kept rather than a guess made.
            _acc_cmd = (g.tex.latex or "").strip()
            _base_tex = (base.tex.latex or bt)
            _tex = (TexToken("%s{%s}" % (_acc_cmd, _base_tex), "atom",
                             base.tex.package, base.tex.confidence)
                    if _acc_cmd.startswith("\\") else base.tex)
            new.append(replace(
                base, text=composed, tex=_tex,
                rect=(min(g.rect[0], base.rect[0]), min(g.rect[1], base.rect[1]),
                      max(g.rect[2], base.rect[2]), max(g.rect[3], base.rect[3]))))
            skip = i + 1
        out.append(new)
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

    THE CUT IS A GAP, NOT A PARTITION. This used to sort each row into
    `rect[2] <= edge` and `rect[0] >= edge` and measure between the two lists,
    which fails twice over. A glyph OVERLAPPING the edge — pdfminer's rect is
    the font's box, so a tall delimiter or an italic descender reaches past the
    gutter without ink being there — belonged to neither list, and the split
    was refused for the whole row; partitioning by the glyph's centre instead
    put the overlapping glyph in one list while the other list still began
    before it ended, so the measured gap came out 0.00. Measured on
    2009tiplabeling page 1 with the edge correct at 295.0: 13 rows straddled
    the gutter, ten of them reported `gap = 0.00`, and the split fixed one.

    So the row is walked in x and the widest gap BETWEEN CONSECUTIVE GLYPHS
    that spans the edge is the candidate. That gap is real white space by
    construction, the two halves are contiguous in x, and every glyph lands on
    exactly one side.

    (`g not in left` was also wrong on its own terms: `GlyphNode` is a
    dataclass, so `in` compares by VALUE, and two glyphs with the same rect and
    text — a repeated digit in a table row — are equal.)

    A row is split only where that gap is a GUTTER rather than a word space, so
    a full-width title or caption whose text runs straight across is left
    whole. Without that, a table row in the left column and a listing line in
    the right arrive as one row and are sorted together by x:
    `GPU code generation Yes No Yes Yes Yes 45 Computation bx(i, j, c)`.
    """
    if edge is None:
        return rows
    out: list[list[GlyphNode]] = []
    for row in rows:
        row = sorted(row, key=lambda g: g.rect[0])
        if len(row) < 2:
            out.append(row)
            continue
        # the widest inter-glyph gap that spans the edge
        best_gap, best_i = -1.0, None
        for i in range(len(row) - 1):
            a, b = row[i], row[i + 1]
            if a.rect[2] <= edge + 0.5 <= b.rect[0] + 0.5:
                g = b.rect[0] - a.rect[2]
                if g > best_gap:
                    best_gap, best_i = g, i + 1
        if best_i is None:
            out.append(row)
            continue
        # A GUTTER IS THE ROW'S OWN WIDEST GAP, BY A CLEAR MARGIN — not a gap
        # over some absolute width. The bar was `0.8 * max(g.size for g in
        # row)`: 7.7 pt for a 9.6 pt body row and more for any row carrying a
        # big delimiter, while 2009tiplabeling's gutter is about 5 pt. No
        # constant can do this job in either direction, because full
        # justification stretches a word space past 6 pt — a bar low enough to
        # admit the gutter admits a stretched space in a full-width title and
        # cuts it (`Fig. 6: A heatma` / `p comparing the normalized
        # execution`). What separates them is the gap's width AGAINST THE OTHER
        # GAPS IN THE SAME ROW: running text has word spaces that are all much
        # of a muchness; a row spanning a gutter has one gap that is plainly
        # not a word space.
        inner = sorted(x for x in (row[i + 1].rect[0] - row[i].rect[2]
                                   for i in range(len(row) - 1)) if x > 0.2)
        typical = inner[len(inner) // 2] if inner else 0.0
        size = _dominant_size(row) or 10.0
        if best_gap >= 0.45 * size and (typical <= 0.0
                                        or best_gap >= 1.6 * typical):
            out.append(row[:best_i])
            out.append(row[best_i:])
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

    # The em-widths of the big-operator cuts these glyphs are drawn from.
    # A `largesymbols` font keeps a DISPLAY and a TEXT cut of one symbol and
    # only the width separates them (see `texmap.esint_raise`); collected
    # once here rather than per glyph.
    _cuts = tuple(sorted({
        round((g.rect[2] - g.rect[0]) / g.size, 3)
        for g in glyphs
        if g.tex.kind == "bigop" and g.family == "math-extension"
        and g.rect and g.size}))

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
            _w = ((g.rect[2] - g.rect[0]) / g.size) if (g.rect and g.size) else 0.0
            return g.baseline - _bigop_raise(
                g.glyphname, g.tex.latex, g.family,
                g.fontname, _w, _cuts) * g.size
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

    #: T-0154 — A THIRD FOLD STOOD HERE AND IS GONE. `_fold_fraction_operands`
    #: joined a fraction's operand rows to the row its bar sits in, added for
    #: p293's `\alpha_1 = \frac{1}{2}` whose value was lost entirely. MEASURED
    #: afterwards over all 30 board pages: with it disabled the projection is
    #: IDENTICAL, p293's `\alpha_1 = \frac{1}{2}` included — though it did fire,
    #: merging 24 rows across 6 pages, 6 of them on p293 itself. The merge at
    #: `_near_rows` below already joins those same rows for every `fraction`
    #: rule, so this was a stricter spelling of a job already done. α1 was
    #: recovered by the `_rule_role` delimiter exclusion, which made that bar a
    #: `fraction` in the first place; the fold rode along and took the credit.
    #: Three folds have now stood in this spot and none of them survived.

    # AFTER the script fold above: folding a script row into its base can
    # bridge two runs the stream says were never together, putting the line
    # numbers of one listing line onto the next.
    rows = _split_by_stream(rows)
    return [sorted(r, key=lambda g: g.rect[0]) for r in rows]


#: (path, pages_read, reason) when the last `build()` stopped early, else None.
#: Read by `cmd_equations` so a truncated document says so in its report.
LAST_READ_ERROR: "tuple | None" = None
#: The traceback behind `LAST_READ_ERROR`, for diagnosing where a read stopped.
LAST_READ_TRACEBACK: "str | None" = None


def _cropboxes(path: str) -> dict:
    r"""Every page's CropBox, by page number, 1-based.

    THE FRAME IS THE CROPBOX, because that is what anyone renders.
    pdfminer's `LTPage.bbox` is the MediaBox, and on lib:d68e0271bd4d p334 the
    two differ by a scale AND an origin -- MediaBox 0 0 595 842, CropBox
    43 87 473 747. The reading declared a 595 x 842 page and placed every
    region at MediaBox-absolute coordinates while Ghostscript and MathPix both
    produce 430 x 660, so no glyph could pair with its own ink: that page was
    the board's worst ours row at residual 1.4311 against MathPix's 0.0391, and
    nothing in either picture said why.

    `PDFPage.cropbox` states it. Reading the page dictionaries is cheap -- no
    content stream is interpreted -- and a failure here leaves the MediaBox in
    place rather than losing the document.
    """
    out: dict = {}
    try:
        from pdfminer.pdfpage import PDFPage
        with open(path, "rb") as fh:
            for i, pg in enumerate(PDFPage.get_pages(fh), 1):
                box = getattr(pg, "cropbox", None)
                if box and len(box) == 4:
                    out[i] = (float(box[0]), float(box[1]),
                              float(box[2]), float(box[3]))
    except Exception:
        return {}
    return out


def build(path: str, pages: Iterable[int] | None = None, *,
          ink: "bool | None" = None) -> list[PageNode]:
    """Build the document model. One GlyphNode per LTChar, no exceptions.

    `ink=True` also measures each glyph's real outline extent and sets
    `GlyphNode.ink` (893). None follows `INK_REGIONS` / `PDFDRILL_INK_REGIONS`.
    """
    out: list[PageNode] = []
    links_by_page = _page_links(path, pages)
    stream_by_page = _stream_index(path, pages)
    # The producer's own line structure, where the stream states it.
    line_bands_by_page = _line_bands(path, pages)
    # Which fonts are monospace IN THIS DOCUMENT, measured from advance
    # widths. Names are unreliable: a publisher's subset can be called
    # anything, and this journal sets its listings in a proportional face.
    set_measured_monospace(measure_monospace(_advance_samples(path, pages)))
    # ONE BAD PAGE MUST NOT COST THE DOCUMENT.
    #
    # `extract_pages` is a generator, so an exception raised inside it ends the
    # iteration: everything already read is discarded and the caller gets
    # nothing. Two pdfminer defects do exactly that, and they are pdfminer's,
    # not ours — a corrupt LZW stream (`lzw.py:61`, IndexError) and a TrueType
    # cmap subtable format pdfminer does not implement (`pdffont.py:798`,
    # AssertionError('Unhandled', 14)). Between them they cost 10 documents of
    # the corpus pass, each losing every page for the sake of one.
    #
    # Patching pdfminer is the wrong answer: the vendored fork is additive by
    # construction and adding error handling to it would change behaviour for
    # every caller. So the loop keeps what it has. A document that dies on
    # page 400 now yields 399 pages and says so, instead of yielding nothing.
    # A document that dies on page 1 still yields nothing — honestly.
    read_error = None
    _crop = _cropboxes(path)
    _pages_iter = extract_pages(path, page_numbers=pages)
    while True:
        try:
            idx_layout = next(_pages_iter, None)
        except Exception as e:                               # noqa: BLE001
            # The TRACEBACK is kept, not just the message. A partial read says
            # what stopped it; without where, the next person has to
            # re-provoke the failure to find out — which for a 1,200-page book
            # is twenty minutes before the question can even be asked.
            import traceback as _tb
            read_error = f"{type(e).__name__}: {e}"
            globals()["LAST_READ_TRACEBACK"] = _tb.format_exc()
            break
        if idx_layout is None:
            break
        idx, layout = len(out), idx_layout
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
                # A GLYPH NAME IS TEXT, AND A FONT CAN HAND US BYTES.
                # pdfminer's Type 1 header parser stores what the font program
                # states with `cast(str, name)` — a cast, not a conversion, so
                # a program whose names arrive as bytes propagates them all the
                # way here. Every downstream consumer then does string work on
                # them: `texmap.codepoint_of` matched a str regex against bytes
                # and raised, costing 8 documents in the corpus pass, the
                # Bronshtein handbook among them.
                #
                # Normalised ONCE, here, where names enter the model — not in
                # `codepoint_of`, which is one of a dozen readers of this field.
                # latin-1 cannot fail and preserves the byte values, which is
                # right for PostScript names: they are ASCII in practice and
                # the point is to stop a type error, not to invent an encoding.
                if isinstance(gname, (bytes, bytearray)):
                    gname = bytes(gname).decode("latin-1", "replace")
                glyphs.append(
                    GlyphNode(
                        id=f"p{pno}g{n}", page=pno,
                        rect=_sane_rect(o.bbox, o.matrix[5], o.size),
                        text=_spell_glyph(o.get_text(), gname, o.cid),
                        cid=o.cid, glyphname=gname,
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
            r.role = _rule_role(r, glyphs, page_size, rules,
                                page_width=(layout.bbox[2] - layout.bbox[0]
                                            if layout.bbox is not None else None))

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
            # T-0154 — ...EXCEPT AT THE REGION'S EDGE, WHERE ITS AXIS IS.
            #
            # This filter is right about a figure's INK and wrong about its
            # axis labels and legend, which are text a reading must carry.
            # MEASURED over the 24 board-14 extracts: it removes 680 glyphs
            # that carry text, on 4 pages (2312 p7 364, lib:5a5c76391c9c p4
            # 264, 0864 p4 38, lib:c57ac038ae5f p293 14). On 0864 p4 the 34
            # it takes are exactly the y-axis tick labels of its three
            # charts, character for character the judge's lost set —
            # `5` x14, `0` x8, `1` x5, `.` x5, `2` x2.
            #
            # So the test runs against each region SHRUNK by a band, and a
            # glyph in that band survives. The regions themselves are
            # unchanged: they are the crop rectangles and the page keeps them.
            _inner = _without_edge_band(diagrams)
            upright_glyphs = [g for g in upright_glyphs
                              if _region_holding(g.rect, _inner) is None]

        # The CropBox when the document states one, else pdfminer's MediaBox
        # bbox. A CropBox equal to the MediaBox changes nothing.
        _box = _crop.get(pno)
        page = PageNode(
            page=pno, rect=(_box if _box else layout.bbox), diagrams=diagrams,
            links=links_by_page.get(pno, []),
            fills=fills,
            invisible=bool(glyphs) and invisible == len(glyphs),
        )
        # A column layout must not have its rows read across the gutter; the
        # split happens inside the grouper, before scripts are folded.
        upright_glyphs = _merge_operator_names(upright_glyphs)
        upright_glyphs = _merge_enclosures(upright_glyphs)
        upright_glyphs = _merge_extenders(upright_glyphs)
        _bar_by_its_spacing(upright_glyphs)
        groups = _group_lines(upright_glyphs, rect=layout.bbox,
                              line_bands=line_bands_by_page.get(pno))
        groups = _split_local_columns(groups, layout.bbox)
        # The page's own figure geometry is a barrier: three charts side by
        # side must not have their labels read across (T-0156).
        groups = _split_at_panel_gutters(groups, diagrams)
        # THE GUTTER IS EVIDENCE, AND IT OUTRANKS EVERY MERGE BELOW.
        #
        # `_group_lines` separates the columns and hands back rows that each
        # belong to ONE column. The band sweep further down then put twelve of
        # them back together on 2009tiplabeling page 1 -- the left column's
        # [49.0..300.0] concatenated with the right column's [312.0..563.0] --
        # because the two share a baseline (two columns of one paper have the
        # same leading by construction) and their 12 pt separation clears a
        # bar of `3.0 * span_pt`, 30 pt here. Its own comment asserted the
        # opposite: "Prose columns share baselines too, but they are text and
        # the gutter between them is far wider than that." It is not; a
        # two-column IEEE paper's gutter is about one em.
        #
        # Measured: `_group_lines` returned 113 rows with 2 straddling, and
        # `page.lines` came out with 14 of 89 straddling. That is the whole of
        # what the owner's Claude.ai chat read as the columns being mixed --
        # `...introduction of the Union- / improve neighborhood exploration`.
        #
        # So keep the edge and let every merge below consult it. None of them
        # is entitled to join two groups that the column detector put on
        # opposite sides of a gutter.
        _gutter = (_column_edge(groups, layout.bbox)
                   if layout.bbox is not None else None)
        # AND THE FIGURE PANELS' OWN GUTTERS ARE THE SAME KIND OF EVIDENCE.
        # `_split_at_panel_gutters` cuts a row at one of these; without the
        # veto below, the rejoin sweep closed the cut again, because its
        # reach is 5 of the PAGE's dominant size — 50 pt here — and a panel
        # gutter is narrower than that. Measured on 2312.11532 p7: three
        # crossings, `'100200300' + '100200300'` twice and `'k=3' + '0.05'`
        # once, which put the three subfigure captions back into one line
        # and left L55 — 20 of the page's 26 unpaired glyphs — exactly as
        # it was before the split.
        _bars = _panel_barriers(diagrams)
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
            #: A ROW THAT ALREADY STRADDLES THE BAR IS A FINISHED FRACTION.
            #: Merging it joins two complete text rows -- lib:c57ac038ae5f
            #: p293 L4 and L22, found by inkdrill-10.
            if (_row_straddles_bar(groups[up], r, span_pt)
                    or _row_straddles_bar(groups[dn], r, span_pt)):
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
                    # Opposite sides of the page's own gutter: not one row.
                    if _gutter is not None and (ax1 <= _gutter <= bx0
                                                or bx1 <= _gutter <= ax0):
                        continue
                    # Opposite sides of a FIGURE PANEL's gutter: likewise.
                    # BOTH baselines must be in the band. This veto had NO
                    # band test until `_PanelBarriers` was written — latent,
                    # and it would have blocked a legitimate rejoin anywhere
                    # on a page that merely HAS side-by-side panels. Found
                    # only because the type makes the omission impossible to
                    # express.
                    _ry0 = min(min(x.rect[1] for x in a),
                               min(x.rect[1] for x in b))
                    _ry1 = max(max(x.rect[3] for x in a),
                               max(x.rect[3] for x in b))
                    if (_bars.crosses(ax1, bx0, _ry0, _ry1,
                                      reach=2.0 * span_pt)
                            or _bars.crosses(bx1, ax0, _ry0, _ry1,
                                             reach=2.0 * span_pt)):
                        continue
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
                    # 781 — A SCRIPT IS SMALL AGAINST THE ROW IT WOULD JOIN,
                    # NOT AGAINST THE PAGE.
                    #
                    # `_off_row_band` asks `g.size < 0.95 * span_pt`, and
                    # `span_pt` is the dominant size of the WHOLE PAGE. A block
                    # set smaller than the body therefore reads as a band of
                    # scripts in its entirety — which is 780's defect over
                    # again, that one caught by a monospace test because the
                    # block happened to be code.
                    #
                    # Measured on 2016icpr page 1 (body 10.0 pt, abstract
                    # 9.0 pt): all eight abstract lines passed the gate, 51 of
                    # 51 glyphs of each were moved onto the line above, and the
                    # abstract came out as four rows of two lines interleaved
                    # glyph by glyph —
                    #
                    #   (CCALbs)troafcta—bTihnearpyroimblaegmeoisflwaeblel-lid…
                    #
                    # which a word-level projection then prints as
                    # `an exact solution to problem the exists`. The library's
                    # own reading of this paper has it, so it is not new.
                    #
                    # The destination's own size is the measure that matters: a
                    # superscript is small BESIDE ITS BASE. 767's fraction
                    # clause still admits a full-size numerator, because there
                    # the page drew the evidence itself.
                    if not _script_beside_its_base(g, groups[dest],
                                                   rules, span_pt):
                        continue
                    # a script sits beside its base, not a page away
                    db = (sum(x.baseline for x in groups[dest])
                          / len(groups[dest]))
                    if abs(db - g.baseline) > 2.0 * span_pt:
                        continue
                    # AND NOT ACROSS A FIGURE PANEL'S GUTTER (T-0156).
                    #
                    # A chart's legend digits are SMALLER than the subfigure
                    # caption beside them, so this pass reads them as scripts
                    # and gives them to a base in the next panel's caption.
                    # On 2312.11532 p7 that undid the panel split one digit
                    # at a time — `(d)NYT-NPMI.` + `100` + `0` + `0` + `2` …
                    # until the caption held `(d) NYT-NPMI. 100 200 300`,
                    # whose own legend belongs to panel (e). The split itself
                    # had emitted `(d)NYT-NPMI.` clean; this is what put it
                    # back, and it is also why those digits came out typed as
                    # MATHS (`$100 200$`) — a script is maths by construction.
                    #
                    # The symptom reported was two line boxes overlapping by
                    # 363 px (x 393..1308 against 945..1877, same row), and
                    # recomputing each piece's region from its own glyphs
                    # would have shrunk the boxes while LEAVING the wrong
                    # glyphs inside them. The region was never the cause.
                    # ...AND ONLY INSIDE THE FIGURE BAND. A barrier is
                    # evidence about the panels' own strip of the page and
                    # nothing else, exactly as in `_split_at_panel_gutters`.
                    # Without the band this veto blocks ORDINARY scripts
                    # whose base happens to lie across a barrier x: measured
                    # on arxiv.1907.11795 p39, `\psi|_{K_{H} \times\{0\}}`
                    # lost its subscript to a display of its own, and on
                    # arxiv.2609.23822 p11 `$Q^{a-2} = Q^{0} = \{[v^{1,0}],
                    # [v^{0,1}]\}$` became `$Q = Q^{0} = \{[v], [v]\}$`
                    # with `$a-2$ $1,0$ $0,1$` stranded beside it. Neither
                    # page lost a character, and both lost the structure,
                    # which is the worse failure: the text reads right and
                    # the mathematics is wrong.
                    #
                    # THIRD TIME FOR THIS ONE OMISSION, which is why the
                    # band now lives in `_PanelBarriers` and not here: the
                    # cross-panel detector ignored Y and flagged 60 prose
                    # lines; the split ignored Y and cut a prose line
                    # mid-word; this veto ignored Y and detached scripts.
                    _dx0 = min(x.rect[0] for x in groups[dest])
                    _dx1 = max(x.rect[2] for x in groups[dest])
                    if _bars.crosses(min(_dx0, g.rect[0]),
                                     max(_dx1, g.rect[2]),
                                     g.rect[1], g.rect[3],
                                     reach=2.0 * max(g.size, span_pt)):
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
            #: An accent and the letter under it are ONE character, and this
            #: is the first point where they are adjacent in the order TeX
            #: emitted them -- which is what the pass needs, since TeX draws
            #: the accent first and the base one point to its left. Before
            #: this, `\ddot` opened a maths span and took the rest of the word
            #: with it: `Saarbr $\mathrm{ucken},$ Germany`.
            group = _compose_text_accents([group])[0]
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
        # T-0154 — A LINE IS NOT MADE FROM TWO FIGURES.
        #
        # The band above admits a figure's edge text, and the row grouper
        # then reads across the page: three charts side by side put their
        # axis labels on one baseline, so 2312 p7 gained `'100 100'`,
        # `'(b 100'` and `'k=1 k=1 k=1'` — one line from two or three
        # different figures. Such a line is REFUSED rather than merged,
        # which is a local decision and needs no per-region grouping.
        #
        # Only a line made ENTIRELY of figure glyphs is a candidate: a line
        # of prose that happens to pass a figure is somebody else's.
        if diagrams:
            page.lines = [ln for ln in page.lines
                          if not _spans_two_regions(ln.glyphs, diagrams)]

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
    # A PARTIAL READ MUST NOT LOOK LIKE A COMPLETE ONE. If nothing was read
    # the failure is the honest answer and is raised as before; if something
    # was, the pages are returned AND the reason is recorded, so the caller
    # reports "read N pages, then …" rather than presenting a truncated
    # document as the document.
    if read_error:
        if not out:
            raise RuntimeError(read_error)
        globals()["LAST_READ_ERROR"] = (path, len(out), read_error)
    else:
        globals()["LAST_READ_ERROR"] = None
    # 893 — MEASURE THE INK, when asked. Last, so a failure here costs the
    # measurement and never the document: every glyph keeps pdfminer's box and
    # `glyph_box` falls back to it, which is what every region meant before
    # this existed.
    if INK_REGIONS if ink is None else ink:
        LAST_INK_REPORT.clear()
        for p in out:
            try:
                attach_ink(path, p)
            except Exception as e:                           # noqa: BLE001
                LAST_INK_REPORT[p.page] = {
                    "measured": 0, "glyphs": sum(len(l.glyphs) for l in p.lines),
                    "why": f"{type(e).__name__}: {e}"}
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
    x0 = round((rect[0] - page.rect[0]) * k)
    x1 = round((rect[2] - page.rect[0]) * k)
    y0 = round((page.rect[3] - rect[3]) * k)
    y1 = round((page.rect[3] - rect[1]) * k)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


#: 893 — whether `build()` measures ink. OFF by default and that is a cost
#: decision, not a confidence one: `inkboxes.ink_boxes` re-runs pdfminer over
#: the page. `PDFDRILL_INK_REGIONS=1` or `build(..., ink=True)` turns it on.
#:
#: THE COST IS +35%, NOT DOUBLE. This said "measuring doubles the read. A
#: corpus pass is ~6 h; silently making it ~12 h is the operator's call",
#: which was an estimate and is pessimistic. MEASURED over the 24 judged born
#: pages of board75, installed entry point, `glyphlines --force` each way:
#:
#:     no ink   170.4 s total   7.10 s/page
#:     ink      230.0 s total   9.58 s/page     x1.35
#:
#: So a ~6 h corpus pass becomes about 8 h, not 12 — the re-run shares parse
#: cost the estimate assumed it duplicated. T-0161 owns the decision, and now
#: it owns a number instead of an adjective.
INK_REGIONS = os.environ.get("PDFDRILL_INK_REGIONS", "") not in ("", "0")

#: Set by `attach_ink` so a consumer can tell a page measured from ink from a
#: page that fell back. {page number: {"measured": n, "glyphs": n, "why": …}}
LAST_INK_REPORT: dict = {}


def attach_ink(path: str, page: "PageNode") -> dict:
    r"""Set `GlyphNode.ink` on every glyph of `page` that can be measured.

    893 — THE JOIN IS ON EVIDENCE, NOT ON ORDER. psred left this exact
    assumption open ("assumes pdfminer and inkboxes list overlaid glyphs in
    the same order; unverified"), and an order-based join is undetectable when
    it slips: every glyph gets A box, just the wrong one, and a region drawn
    from it looks plausible.

    `inkboxes` returns pdfminer's OWN bbox for each record, so that bbox is
    the key — it is positional, so it identifies the glyph INSTANCE rather
    than the character, and a mismatch shows up as an unmatched record rather
    than as a silently shifted box. Font and size join too, because two glyphs
    can share a box when one is drawn over another (which is how TeX sets
    `\cong`).

    Returns the per-page report rather than printing: how many glyphs were
    measured, how many were not, and why not.
    """
    from pdfreader import inkboxes as _ib

    def _key(box, font, size):
        return (round(box[0], 2), round(box[1], 2), round(box[2], 2),
                round(box[3], 2), (font or "").split("+")[-1], round(size, 2))

    try:
        recs = _ib.ink_boxes(path, page.page)
    except Exception as e:                                   # noqa: BLE001
        rep = {"measured": 0, "glyphs": 0, "why": f"{type(e).__name__}: {e}"}
        LAST_INK_REPORT[page.page] = rep
        return rep

    # EXACTLY ONE RECORD, OR NONE. Two glyphs can share a pdfminer box, a
    # font and a size — that is precisely how TeX draws `\cong` (a `\sim`
    # then an `=` under it) and `\widehat{x}` (the accent then the letter).
    # A dict that keeps the last one would hand BOTH glyphs the same box, and
    # one of them would be wrong while looking measured. So the map holds
    # every candidate and an ambiguous key yields no ink at all, counted
    # under its own name: a glyph the join could not resolve is not the same
    # fact as a glyph the font could not measure.
    cand: dict = {}
    for r in recs:
        if r.get("ink"):
            cand.setdefault(
                _key(r["pdfminer"], r.get("font"), r.get("size") or 0.0),
                []).append(tuple(r["ink"]))
    n = hit = ambiguous = nokey = 0
    for ln in page.lines:
        for g in ln.glyphs:
            n += 1
            got = cand.get(_key(g.rect, g.fontname, g.size))
            if not got:
                nokey += 1
            elif len(got) > 1 and len(set(got)) > 1:
                ambiguous += 1
            else:
                g.ink = got[0]
                hit += 1
    rep = {"measured": hit, "glyphs": n,
           "unmeasured": n - hit,
           "no_matching_record": nokey,
           "ambiguous_join": ambiguous,
           "records": len(recs), "with_ink": len(cand),
           "why": None if hit else "no record matched"}
    LAST_INK_REPORT[page.page] = rep
    return rep


def glyph_box(g: "GlyphNode") -> Rect:
    """The glyph's MEASURED ink where it exists, its font box otherwise.

    893 — the one place that decision is made, so a region, a crop and a mark
    cannot disagree about which box they meant. `inkboxes` returns None for an
    uncovered font rather than guessing, and the fallback is the font box
    because that is what every region meant before this existed.
    """
    return g.ink if getattr(g, "ink", None) else g.rect


def _px_region(rect: Rect, page: PageNode, k: float) -> dict:
    """A PDF-point rect (y up) as a pixel region (y down from top-left).

    x subtracts `page.rect[0]`; y already counts down from `page.rect[3]`, so
    it needs nothing once that rect is the CropBox.
    """
    return {
        "top_left_x": round((rect[0] - page.rect[0]) * k),
        "top_left_y": round((page.rect[3] - rect[3]) * k),
        "width": max(1, round((rect[2] - rect[0]) * k)),
        "height": max(1, round((rect[3] - rect[1]) * k)),
    }


#: 844 — our line types in MathPix's export vocabulary. See `_mp_type`.
_MP_TYPE = {
    "math": "text",            # ours is PROSE carrying inline maths
    "equation": "math",        # ours is DISPLAY maths; theirs is called `math`
    "caption": "figure_label",  # they have no `caption`; `figure_label` is the
                               # type the host rule and the transclusion
                               # exclusion already know (line_types.py)
    "formula": "text",         # a maths-font glyph run, not a display equation
}


def _column_reading_order(pages: list[PageNode]) -> list[PageNode]:
    """A fully columnised page's lines in READING order, not stream order.

    `_add_column_containers` states the columns as containers, and its own
    docstring says why: the nesting IS the reading order of a two-column paper,
    "stated rather than left for each consumer to guess from x-coordinates".
    But the flat `lines` list stayed in the order the content stream emits, and
    every consumer that walks it -- a markdown projection, the ink judge, a CER
    against the page's text layer -- reads the columns interleaved.

    Measured on the board's two-column page lib:69bc5c71b881 p16 (91 lines, all
    91 assigned to one of 2 columns). Left/right of each line in list order:

        ours      LLRRLLLLLLLLRRRRRRRLLLLRRLLLL...
        MathPix   LLLLLLLLLLLLLLLLLLLLLLLL...RRRR...

    The content stream emits two lines of the left column, two of the right,
    and so on, and we followed it. Order-free the two readings of that page are
    nearly identical -- 8 words missing, 18 extra of 714 -- yet our CER against
    the page's own text layer is 0.3169 against MathPix's 0.0151. The whole gap
    is the order.

    ONLY when every line of the page belongs to a column, and there are at
    least two. A page with full-width lines between column blocks (a title, a
    section heading spanning both) needs those lines placed in bands, and a
    band rule invented without a measurement behind it would move text that is
    currently in the right place. Such a page keeps the order it has.
    """
    from dataclasses import replace
    try:
        from pdfreader.project_mmd import column_membership
    except Exception:                                    # noqa: BLE001
        return pages
    out = []
    for p in pages:
        try:
            member = column_membership(p)
        except Exception:                                # noqa: BLE001
            out.append(p)
            continue
        if (not member or len(member) != len(p.lines)
                or len(set(member.values())) < 2):
            out.append(p)
            continue
        order = sorted(range(len(p.lines)),
                       key=lambda i: (member[i], -p.lines[i].rect[3],
                                      p.lines[i].rect[0]))
        out.append(p if order == list(range(len(p.lines)))
                   else replace(p, lines=[p.lines[i] for i in order]))
    return out


def to_lines_json(pages: list[PageNode],
                  px_per_pt: float = PX_PER_PT,
                  doc_id: str = "pdfdrill") -> dict:
    """MathPix-shaped geometry, projected from the model.

    Coordinates are PIXELS at `px_per_pt`, top-left origin, exactly as MathPix
    writes them -- not PDF points. A consumer must be able to take a region
    from here, put it straight into a crop URL, and get that region back.
    """
    k = px_per_pt
    # Reading order BEFORE anything else reads the lines: `classify_lines` and
    # every container pass key off the position of a line in `p.lines`, so the
    # order has to be settled first or the two disagree.
    pages = _column_reading_order(pages)
    # THE LINE TYPE, from the one classifier. `LineNode.type` is "text" or
    # "formula" — two values, and pdfdrill's twenty docmodel modules key off
    # SIXTEEN, so a two-type stream can only ever produce paragraphs. The
    # classifier lives in `project_mmd` because that is where its inputs are
    # (the document font profile, each page's margins, the listing grid);
    # imported late because that module builds on the node types defined here.
    # A failure here must not cost the geometry, which is the part that is
    # always right: fall back to the node's own type.
    try:
        from pdfreader.project_mmd import classify_lines
        _types = classify_lines(pages)
    except Exception:                                    # noqa: BLE001
        _types = {}

    def _line_type(p, i, ln) -> tuple:
        return _types.get((p.page, i)) or (ln.type, {})

    def _mp_type(t: str) -> str:
        r"""Our internal line type, in MATHPIX's export vocabulary.

        844 — THE EXPORT SPEAKS MATHPIX, THE READER KEEPS ITS OWN WORDS. A
        `lines.json` is MathPix's format; every consumer in `src/docmodel/` was
        written against their 31 types and `docmodel/line_types.py` is built out
        of them. Two of ours collided with theirs by NAME while meaning the
        opposite, which is worse than a type they have never seen:

          ours `math`      = PROSE carrying inline maths
          MathPix `math`   = DISPLAY maths, `\[ … \]`
          ours `equation`  = display maths (MathPix emits no `equation` at all)

        So `inlinectx.load_spans` skips `type == "math"` as display maths and
        threw away the host line of nearly every inline formula we produced,
        while mining our real display maths as if it were prose. The error ran
        in both directions. Measured by inkdrill over 20 sigma26 documents:
        29,172 of 36,813 inline spans (79.2%) invisible; the one document with a
        MathPix reading lost 0 of 565. Measured here on arXiv 1102.1889: the
        glyph lane produced 961 Equations against the author LaTeX's 83, and the
        first five are the paper's ABSTRACT and prose sentences — "Abstract. In
        this paper we introduce the $\mathrm{o}\log,$ …" filed as display maths.
        `paragraph.py` excludes `math` AND `equation` from prose, so those lines
        were lost as paragraphs too.

        `formula` maps to `text`, not `math`: it is the raw pre-classification
        type for a glyph run in a maths font, and the 166 that survive
        `_line_type` are things like "Josef $\mathrm{Ba}\ker$ , Alan Sexton and
        $\mathrm{Vol}\ker$ Sorge" — an author line misread, not an equation.
        `text` also preserves today's behaviour exactly, since `paragraph.py`
        never excluded `formula`.

        `rotated_text` is DELIBERATELY NOT renamed although MathPix has no such
        type. It is the arXiv stamp down the left margin, `paragraph.py` excludes
        it by that name, and its comment there says why: "An arXiv stamp down the
        left margin is not a sentence in section 1." Calling it `text` would
        make it one.
        """
        return _MP_TYPE.get(t, t)

    out = {
        # 846 — PROVENANCE BELONGS TO THE DOCUMENT, NOT TO EACH OF ITS PAGES.
        # inkdrill found the consequence: `cmd_ocr`'s backup guard reads
        # `lj.get("source")` at the TOP level, we wrote it only per page, so
        # every reading of ours looked like MathPix to it — and it would file a
        # pdf2mmd reading as `<stem>.lines.mathpix.bak.json`, permanently,
        # because `if not bak.exists()` then refuses to correct it. A real
        # MathPix reading displaced later could not be backed up: the slot taken,
        # by the wrong reader, under MathPix's name.
        #
        # `_lines_json_source` happened to work anyway — it regexes the first
        # 8 KB and page 1's key falls inside that — but that is key ordering, not
        # a contract. Stating it at the top makes both readers right by
        # construction. The per-page key stays: a merged reading can carry pages
        # from two readers, and that is the only place that can say so.
        "source": "pdfminer-docmodel",
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
                        "type": _mp_type(_line_type(p, i, ln)[0]),
                        "line": i + 1,
                        "column": 0,
                        # 844 — MATHPIX'S UNIT. Theirs is 250-dpi page pixels
                        # (29 where we said 9, ratio == px_per_pt); every other
                        # geometry key here is already scaled by `k` and this
                        # one was not, so the SAME NAME meant a different
                        # thing. Safe to change: `type_contract` records that
                        # font_size is "consumed by RANK within a document,
                        # never by value" (header.levels_by_font_size), and the
                        # pixel scale is the granularity that module was built
                        # for — point-rounding merged headings it can now rank.
                        "font_size": round(line_font_size(ln) * k),
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
                            "top_left_x": round((ln.rect[0] - p.rect[0]) * k),
                            "top_left_y": round((p.rect[3] - ln.rect[3]) * k),
                            "width": max(1, round((ln.rect[2] - ln.rect[0]) * k)),
                            "height": max(1, round((ln.rect[3] - ln.rect[1]) * k)),
                        },
                        "text": _as_display(
                            " ".join(span_reading_text(sp) for sp in ln.spans),
                            _mp_type(_line_type(p, i, ln)[0])),
                        # 844 — MathPix puts `text_display` on EVERY line and
                        # `inlinectx.load_spans` reads `text_display or text`
                        # (676 review B3). We emitted none, so a consumer that
                        # trusts the field got None. Ours already carries its
                        # `$…$` spans in `text`, so the two are the same string
                        # — emitting it is what makes that true rather than
                        # something a reader has to know.
                        "text_display": _as_display(
                            " ".join(span_reading_text(sp) for sp in ln.spans),
                            _mp_type(_line_type(p, i, ln)[0])),
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
    _split_equation_numbers(out, pages, k)
    _split_qed_symbols(out, pages, k)
    _mark_generated_text(out)
    return out


#: The glyph a proof ends with, by GLYPH NAME rather than by rendered
#: character. On sigma26-075 every one of the 20 is `squaresolid` carrying
#: U+25A0; a name is available here because the vendored pdfminer exposes it
#: (R2), and a name survives a font whose encoding gives the character wrong.
_QED_GLYPHS = frozenset({"squaresolid", "square", "blacksquare", "qedsymbol",
                         "openbox", "filledbox", "blacksquarelarge"})
_QED_CHARS = frozenset("■□∎◻◼⬛⬜")


def _is_qed(g) -> bool:
    """Is this glyph a proof-ending box?"""
    nm = str(getattr(g, "glyphname", None) or "").strip().lower()
    return nm in _QED_GLYPHS or (g.text or "") in _QED_CHARS


def _split_qed_symbols(out: dict, pages: list["PageNode"], k: float) -> None:
    r"""Make the box that ends a proof its own line, as MathPix does.

    882 Phase 1 — MathPix emits 19 `qed_symbol` lines on sigma26-075 and we
    emitted none, because the box reaches us in two shapes and neither was
    typed:

        a line of its own          p4,  29 px wide at the right margin
        the last token of prose    p5,  "… and linearity. $\blacksquare$"

    The second is the majority and is why this is a SPLIT rather than a
    retype: MathPix's reading has the box on a line by itself in both cases,
    so a consumer written against their export looks for a `qed_symbol` line
    and finds our proof's last sentence instead.

    DETECTED BY GLYPH NAME, NOT BY THE RENDERED CHARACTER OR THE LaTeX. All 20
    on this document are `squaresolid`; the name comes from the vendored
    pdfminer (R2) and survives a font whose encoding reports the character
    wrongly. Matching on our own `$\blacksquare$` projection would be matching
    on our own output, which is the oracle error `_document_entry` already
    warns about one layer up.

    TWO DELIBERATE DIVERGENCES FROM THE REFERENCE, both recorded rather than
    smoothed over:

    1. MathPix writes `text: ""` and puts the symbol only in `text_display`.
       We write it in both. An empty `text` is a LOSS, and the type already
       says what the line is — emulating the loss would make our export
       agree with the reference by discarding the same information, which is
       not the kind of compatibility worth having (880's rule).
    2. MathPix renders it `\square`, hollow. The glyph is named `squaresolid`
       and carries U+25A0, so we render `\blacksquare`. One of us is wrong
       about the fill and the evidence here says it is not us. Written down
       because a measured disagreement with the reference is a finding, and
       matching the reference would delete it.

    AFTER the equation-number split, for the same reason that one runs last: a
    container that already lists the host line gains the box beside it rather
    than losing it.
    """
    for page_rec, p in zip(out["pages"], pages):
        recs = page_rec["lines"]
        by_i = {r.get("_i"): r for r in recs if r.get("_i") is not None}
        made: list = []
        for i, ln in enumerate(p.lines):
            rec = by_i.get(i)
            if rec is None or ln.rotated or not ln.glyphs:
                continue
            ink = [g for g in ln.glyphs if (g.text or "").strip()]
            if not ink:
                continue
            tail = [g for g in ink if _is_qed(g)]
            if not tail:
                continue
            # Only a TRAILING box ends a proof. A box used as an operator mid
            # line is not a QED mark, and nothing here should claim it is.
            if not _is_qed(ink[-1]):
                continue
            box = [g for g in ink if _is_qed(g) and g.rect[0] >= ink[-1].rect[0]]
            body = [g for g in ink if id(g) not in {id(b) for b in box}]
            text = "$\\blacksquare$"
            if not body:
                # Already alone on its line: retype in place. There is nothing
                # to split and an empty host would be worse than the type.
                rec["type"] = "qed_symbol"
                rec["text"] = text
                rec["text_display"] = text
                continue
            bx0 = min(g.rect[0] for g in box)
            bx1 = max(g.rect[2] for g in box)
            hostx1 = max(g.rect[2] for g in body)
            qed = dict(rec)
            qed["id"] = f"{rec['id']}q"
            qed["type"] = "qed_symbol"
            qed["text"] = text
            qed["text_display"] = text
            qed["region"] = {"top_left_x": round(bx0 * k),
                             "top_left_y": rec["region"]["top_left_y"],
                             "width": max(1, round((bx1 - bx0) * k)),
                             "height": rec["region"]["height"]}
            qed["cnt"] = _contour((bx0, ln.rect[1], bx1, ln.rect[3]), p, k)
            for key in ("gaps", "rules", "deferred_glyphs", "children_ids",
                        "_i", "generated", "latex"):
                qed.pop(key, None)
            # The prose stops where its own ink stops, so a crop of either is
            # right — the same correction the equation-number split makes.
            rec["region"]["width"] = max(1, round((hostx1 - ln.rect[0]) * k))
            rec["cnt"] = _contour((ln.rect[0], ln.rect[1], hostx1, ln.rect[3]),
                                  p, k)
            made.append((rec, qed))
        for host, qed in made:
            recs.insert(recs.index(host) + 1, qed)
        for n, r in enumerate(recs, 1):
            r["line"] = n


def _mark_generated_text(out: dict) -> None:
    r"""880 — mark text the TYPESETTER produced, beside the type MathPix uses.

    A `generated` field, not a type: the type belongs to MathPix's vocabulary
    and every consumer in `src/docmodel/` keys off it, so a type they have
    never seen is a line they drop. Being better than the reference must not
    mean being incompatible with it.

    MathPix flattens a bibliography into prose — 298 lines across the four
    readings this library holds, all `text`, plus a dot-leader line typed
    `math`. Our own reader does the same thing independently. This says which
    lines were produced by a counter rather than written, so a consumer need
    not re-derive it from the prose.
    """
    from pdfreader import generated_text as _gt
    # THE SECTION A LINE SITS IN IS EVIDENCE. A glossary entry and a symbol
    # table entry have no shape of their own — they are short lines, like any
    # other short line. What identifies them is the heading above them, and
    # LaTeX "only organises the counters": the author supplied the entries and
    # the package produced the order and the numbering. So the scope runs from
    # a generating heading to the next heading of any kind.
    #
    # Scope ENDS at the next section_header, never at a page break: a
    # bibliography crosses pages and a TOC usually does.
    scope = None
    for page_rec in out.get("pages") or []:
        for rec in page_rec.get("lines") or []:
            if rec.get("type") == "section_header":
                scope = _gt.section_generator(
                    texmap.unwrap_emphasis(rec.get("text") or ""))
                if scope:
                    rec["generated_scope"] = scope
                    rec["latex"] = _gt.GENERATOR_LATEX.get(scope)
                continue
            if rec.get("type") == "equation_number":
                g = "equation_number"
            else:
                # T-0156 — WITHOUT THE FACE WRAPPERS. `rec["text"]`
                # now carries them for the judge, and this test reads
                # the START of the line: `\textbf{1.` is not a
                # counter shape, so 76 of 0864 p4's list items came
                # back as `text` and its model lost them all.
                g = _gt.generated_by(
                    texmap.unwrap_emphasis(rec.get("text") or ""),
                                     line_type=rec.get("type") or "") or scope
            if not g:
                continue
            rec["generated"] = g
            # THE LaTeX IS THE COMMAND, NOT THE EXPANSION. Re-typeset and
            # LaTeX rebuilds these from the counters; emitting the expanded
            # text as source would freeze this build's page numbers into the
            # document, wrong the first time anything above them changed
            # length. The text field keeps what this build produced.
            cmd = _gt.GENERATOR_LATEX.get(g)
            if cmd:
                rec["latex"] = cmd
            # 882 Phase 1 — AND THE TYPE, WHERE MATHPIX HAS A WORD FOR IT.
            #
            # Measured on sigma26-075: MathPix emits 55 `list_item`, 15 of
            # them carrying their own text, and those 15 are BOTH kinds —
            # `(ii) Clearly, \(\det I = XY/\sin^2\phi\) …` and
            # `[4] Bianchi L., Lezioni di geometria differenziale …`. So a
            # bibliography entry is a `list_item` in their vocabulary, which
            # is the same judgement 880 arrived at from the other side: the
            # counter is the generated thing and `\bibitem` is an `\item`
            # whose label a package wrote.
            #
            # We mark 57 bib_entry and 12 list_label on this document and
            # exported every one as `text`, so a consumer written against
            # MathPix looked for a list and found prose. `type_contract` says
            # `list_item` is read by `list_items` and breaks a paragraph —
            # exactly what these lines should do, and what `text` prevented.
            # (out/245: `list_item` went unread in 882 documents. Emitting it
            # as `text` is the same loss from the writing end.)
            #
            # Only from `text`. A line the classifier established as a
            # heading, a caption, a footnote or an equation number is not
            # relabelled by a counter shape — the order-of-certainty rule
            # `classify_lines` states, applied here.
            if g in ("list_label", "bib_entry") and rec.get("type") == "text":
                rec["type"] = "list_item"


def _split_equation_numbers(out: dict, pages: list["PageNode"], k: float) -> None:
    r"""Make an equation's number its own line, after the display it labels.

    879 Phase 1 — A TYPE THE VOCABULARY DECLARED AND THE READER COULD NEVER
    PRODUCE. `LINE_TYPES` has listed `equation_number` all along and
    `classify_lines` assigns it ZERO times, because `absorb_equation_numbers`
    joins the number's line to its display before classification ever sees it.
    That absorption is right and stays: 739 measured what happens without it —
    two numbered displays fused into one `aligned`, and the numbers surviving
    as loose prose that `to_markdown` dropped and `to_latex` printed twice.

    But MathPix emits the number as its OWN line, 40 of them on sigma26-075,
    and the export speaks MathPix while the reader keeps its own words — the
    rule `_mp_type` already states for `math`/`equation`. So the model keeps
    the number absorbed and the EXPORT splits it out again.

    The glyphs are still there and still identifiable: `equation_number` reads
    them back by the same three conditions that found them in the first place
    — parenthesised, ending at the column's right margin, behind a wide gap.
    Nothing is guessed and nothing new is measured.

    LAST, after the run-in split, for the same reason that one runs last: a
    container that lists the original line gains the number beside it rather
    than losing it.
    """
    from pdfreader import project_mmd as _mmd
    for page_rec, p in zip(out["pages"], pages):
        recs = page_rec["lines"]
        by_i = {r.get("_i"): r for r in recs if r.get("_i") is not None}
        made: list = []
        for i, ln in enumerate(p.lines):
            rec = by_i.get(i)
            if rec is None or ln.rotated or not ln.glyphs:
                continue
            try:
                tag = _mmd.equation_number(ln, _mmd.column_of(p, ln)[1])
            except Exception:                                # noqa: BLE001
                continue
            if not tag:
                continue
            body = [g for g in ln.glyphs
                    if g.text.strip() and id(g) not in set(map(id, tag))]
            if not body:
                # A line that is NOTHING but a number is already its own line;
                # splitting it would leave an empty host.
                continue
            tx0 = min(g.rect[0] for g in tag)
            tx1 = max(g.rect[2] for g in tag)
            bx1 = max(g.rect[2] for g in body)
            top_y = rec["region"]["top_left_y"]
            height = rec["region"]["height"]
            num = dict(rec)
            num["id"] = f"{rec['id']}n"
            num["type"] = "equation_number"
            num["text"] = "".join(g.text for g in
                                  sorted(tag, key=lambda g: g.rect[0])).strip()
            num["text_display"] = num["text"]
            num["region"] = {"top_left_x": round(tx0 * k), "top_left_y": top_y,
                             "width": max(1, round((tx1 - tx0) * k)),
                             "height": height}
            num["cnt"] = _contour((tx0, ln.rect[1], tx1, ln.rect[3]), p, k)
            # The number is not the equation: neither carries the other's
            # pieces, and a `deferred_glyphs` list on a label is meaningless.
            for key in ("gaps", "rules", "deferred_glyphs", "children_ids",
                        "_i"):
                num.pop(key, None)
            # …AND IT STOPS CARRYING THE NUMBER'S TEXT.
            #
            # T-0156. This split gave the number its own record, its own
            # region at the margin and its own `cnt` — and left it in the
            # HOST's text as well, so every number was emitted TWICE. On the
            # board's own judged readings: lib_c57ac038ae5f p293, 6 numbers as
            # their own line and the same 6 inside a math line; lib_3fe71b4ef018
            # p328, 8 and 8. The judge renders what is written, so it set each
            # number at the margin AND beside the formula, which is where the
            # unpaired "(" and the stray digit in the region came from.
            #
            # Trimmed from the glyphs the split already identified, not by a
            # pattern over the text: `tag` is what `mmd.equation_number`
            # returned — parenthesised, at the column's right margin, behind a
            # wide gap — so the characters removed here are exactly the ones
            # that moved.
            _tagtext = num["text"]
            for _key in ("text", "text_display"):
                _t = rec.get(_key) or ""
                _at = _t.rfind(_tagtext)
                if _at >= 0:
                    rec[_key] = (_t[:_at] + _t[_at + len(_tagtext):]).rstrip()
            # …and the display stops where its own ink stops.
            rec["region"]["width"] = max(
                1, round((bx1 - ln.rect[0]) * k))
            rec["cnt"] = _contour((ln.rect[0], ln.rect[1], bx1, ln.rect[3]),
                                  p, k)
            made.append((rec, num))
        for host, num in made:
            at = recs.index(host)
            recs.insert(at + 1, num)
        for n, r in enumerate(recs, 1):
            r["line"] = n


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
    from pdfreader.project_mmd import table_regions
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
                # 844 — a container IS a line, so it carries `text_display`
                # like every other one. "MathPix has it on every line" is the
                # reason `load_spans` may read `text_display or text` without
                # checking, and 13-19 container lines per document were the
                # exception that made that false.
                "text": "", "text_display": "", "children_ids": kids,
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
    from pdfreader.project_mmd import column_membership
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
                "text_display": "",                      # 844, as above
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


#: What a glyph with no identity is written as. An explicit unknown, counted
#: in the line's `deferred_glyphs`, rather than a placeholder that reads as
#: the four letters `cid` plus a number nobody put on the page.
UNKNOWN_GLYPH_CHAR = "\ufffd"


def _glyph_text(g: GlyphNode) -> str:
    r"""One glyph as text, never as pdfminer's `(cid:N)` placeholder.

    A font with no ToUnicode map makes `get_text()` return `(cid:205)`, and
    writing that into a reading puts nine characters on the page that are not
    there: 61 of them over 9 of the board's 24 born-digital pages, against
    MathPix's none. Measured on 1805.01788 p3, where all 21 are `\sum`.

    The identity is recovered where the font states it -- `texmap.project`
    now answers a variant name like `summationtext.1` from its base -- and
    what remains unidentified is written as one explicit unknown character,
    which the line's `deferred_glyphs` already names glyph by glyph.
    """
    t = g.text or ""
    #: A MATHS GLYPH IS WHAT THE FONT DRAWS, NOT WHAT ITS ENCODING CALLS IT.
    #:
    #: TeX-matha12 hands pdfminer StandardEncoding names -- `p` `q` `r` `s`
    #: `braceleft` -- while the font draws `(` `)` `[` `]` and a brace that
    #: must be escaped. `build` already corrects the identity through
    #: `tex_slot`, so the glyph carries both, and returning `g.text` threw the
    #: correction away: 67 glyphs disagree on lib:c9daf79960c3 p68 and the page
    #: would not compile, "Missing }".
    #:
    #: Only a MATHS family. For a text glyph `g.text` stays the answer: the
    #: name-keyed tables abstain on perfectly readable text -- a CID-keyed
    #: Libertinus page states no glyph names at all and reads correctly through
    #: `g.text` -- and preferring the field there would put a raw character
    #: where `greek_latex` would have given a command.
    #: IT RECOVERS AN IDENTITY; IT MUST NOT SPEND ONE. Where `g.text` is
    #: already a CORRECT non-ASCII character there is nothing misnamed, and
    #: the field can only be equal or worse: `_UNI_LATEX[0x2212]` is `"-"`, so
    #: a U+2212 MINUS read as an ASCII hyphen. Board 0864 p4's judged page
    #: differs from the pre-b7996491 reader in exactly two leaf lines, both
    #: this, and it cost the page 7 pairings -- 3929 -> 3922, residual 0.1659
    #: -> 0.1676, the one row of the ninth state's seven that pdfdrill caused.
    #:
    #: `g.text` is correct only where the FONT names its slots. A misnamed
    #: slot's fallback is usually ASCII (`f` for `{`, `;` for `,`, `0` for a
    #: prime) but not always: TeX-matha12 reports `“` for `=` and `Ñ`
    #: for `\rightarrow`, so that font is asked by name, not by character.
    #: Measured, 2026-11-18, one judge, three-page extracts:
    #:
    #:     0864 p4            0.1676 -> 0.1659   (the regression, gone)
    #:     1511.08771 p2709   0.0209 -> 0.0186   (flagged 12 -> 6; its primes
    #:                                            are U+2032, not `0`)
    #:     lib:c9daf79960c3   0.0147 unchanged   (26 TeX-matha corrections
    #:                                            kept by the font test)
    fam = getattr(g, "family", "") or ""
    if fam.startswith(("math", "maths", "ams")) and g.tex and g.tex.latex:
        if (names_untrusted(getattr(g, "fontname", ""))
                or t.isascii() or not g.tex.latex.isascii()):
            return g.tex.latex
        return t
    #: pdfminer's placeholder for a glyph whose font states no Unicode for it
    #: is the literal string `(cid:<number>)`. A string test, not a regex:
    #: this module imports `re` nowhere at the top level.
    if not (t.startswith("(cid:") and t.endswith(")") and t[5:-1].isdigit()):
        return t
    return g.tex.latex or UNKNOWN_GLYPH_CHAR


def _needs_maths(t: str) -> bool:
    """Is this token LaTeX that only works inside maths mode?"""
    return t.startswith(chr(92)) and t[1:2].isalpha() and t not in _TEXT_COMMANDS


#: Commands that are legal in text mode, so they are not wrapped.
_TEXT_COMMANDS = frozenset({chr(92) + n for n in
                            ("textbf", "textit", "emph", "texttt", "textsc",
                             "ldots", "dots", "%", "&", "_", "#", "$")})


def _run_text(glyphs: list[GlyphNode], word_gap: float = 0.0,
              maths_mode: bool = False) -> str:
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
        t = _glyph_text(g)
        # A MATHS COMMAND IN A TEXT RUN NEEDS ITS MATHS MODE. The operator
        # merge marks the collapsed glyph `math-symbol` and the span around it
        # can still be text, so `\lg` landed outside `$...$` and pdflatex
        # answered "Missing $ inserted" -- 13 of the board's 14 lines that do
        # not compile, including every one on lib:c57ac038ae5f p293, whose
        # display was typed as prose and carries `\bigl[` in text mode.
        if not maths_mode and _needs_maths(t):
            t = "$" + t + "$"
        # A COMMAND MUST END. `_merge_operator_names` collapses the upright
        # letters of `\lg` into one glyph whose text IS the command, and the
        # letters that follow it are a separate run -- so concatenating them
        # spelled `\lgcRn`, an undefined control sequence that breaks the line
        # and corrupts the word. Measured on lib:c9daf79960c3 p68: `functor
        # G : CA\lgcRn Ñ ...`, one of 6 lines on that page the judge could not
        # set, which cost 307 of its 1,703 glyphs.
        if (out and t[:1].isalpha() and out[-1].startswith(chr(92))
                and out[-1][-1:].isalpha()):
            out.append(" ")
        out.append(t)
        prev = g
    return "".join(out)


def plain(line: LineNode) -> str:
    return _run_text(line.glyphs)


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
    from pdfreader.structure import _attach_scripts, _split_fractions

    # RUN THE MERGES FIRST. This checked the RAW glyphs, so a span holding an
    # accent reported `accent-not-composed` whether or not the accent had
    # composed -- `glyph_latex` returns None for an accent by design, which is
    # what step 1 looks for. wzlxjtu-033 reported 13 of its 15 crops that way
    # while `_merge_accents` was consuming every one of its `\bar{z}`
    # (20 glyphs in, 15 out) and the refusal was somewhere else entirely.
    #
    # The docstring above promises the pass that ACTUALLY returned None,
    # established by running them. Step 1 was the one place that did not.
    from pdfreader.structure import (_merge_accents, _merge_mapsto, _merge_negations,
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
    #: T-0162 — `underline` JOINED THIS SET WITH ITS PASS, not before it.
    #: Classifying the three rules on 0212041 p1 as `underline` instead of
    #: `unknown` changed only the WORD the span deferred on
    #: ("unmodelled-rule:underline"), and a role no pass consumes is worse
    #: than an honest `unknown` — it reads as handled. `_merge_underlines`
    #: emits the `\underline{...}`, and that is what earns the entry here.
    unmodelled = sorted({r.role for r in sp.rules
                         if r.role not in ("fraction", "separator",
                                           "underscore", "overline",
                                           "underline")})
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
        from pdfreader.structure import to_tex
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
    from pdfreader.structure import span_to_tex

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


#: Line types the classifier establishes as a DISPLAY equation.
_DISPLAY_TYPES = {"math", "equation"}


def _as_display(text: str, line_type: str) -> str:
    r"""A display equation written `\[...\]`, or `text` unchanged.

    T-0154/T-0156. Every maths span is written `$...$` — inline maths —
    whatever the line's type, so a line the classifier established as a
    DISPLAY equation reached the reading in text style. A `\frac` is then set
    small with its bar low, where the page sets it large with the bar high.

    MEASURED on lib:6d90e8d27b8b p174, from the judge's rule findings: four
    fraction bars the ink draws at y=1987 our LaTeX draws at 1970 (x2) and
    2001 (x2) — 17 above and 14 below — so each counts twice, once missing
    and once invented. The same on L3 (ink 638, ours 633) and L5 (959/943).
    The CONTENT is not in question: our line and MathPix's are the same
    equation with the same fractions in the same order, and only the
    delimiters differ.

    SCOPE over the 24 board-14 extracts: 128 of 131 lines typed `math` or
    `equation` are written inline — p293 20, 0864 p4 18, p174 18, p154 16,
    p118 13, and six more pages.

    ONLY WHEN THE WHOLE LINE IS ONE MATHS SPAN. A sentence with maths in it
    is not a display equation, and wrapping it would set its words in maths
    mode; such a line keeps its `$...$` spans.
    """
    if line_type not in _DISPLAY_TYPES:
        return text
    body = (text or "").strip()
    if len(body) < 3 or not body.startswith("$") or not body.endswith("$"):
        return text
    inner = body[1:-1]
    if "$" in inner:
        return text                      # several spans: a sentence, not a display
    #: AND IT MUST HOLD SOMETHING READABLE. Board state 34: four lines of
    #: 1805.01788 p3 whose whole body is the replacement character were
    #: wrapped as displays, and pdflatex answered "Missing $ inserted" on
    #: each — `not_compiled` 0 -> 4. Inline, the same body compiled. A line
    #: the reader could not read is not an equation to set in display style;
    #: it keeps the delimiters it had, and its `complete: false` and
    #: `deferred_glyphs` already say what happened to it.
    if not inner.replace("\ufffd", "").strip():
        return text
    return "\\[\n%s\n\\]" % inner


def span_reading_text(sp: Span) -> str:
    """One span as the READING's text: prose, `$maths$`, or the characters the
    page carries when the maths cannot be typed.

    `span_text` is a PROJECTION FOR PEOPLE, and an untypeable maths span there
    becomes `<!-- DEFERRED ... -->`, which tells a reader where to look. In a
    lines.json `text` field the same string is a defect, because every consumer
    of `text` reads it as the line's text: the ink judge TYPESETS it, so a line
    of prose grows a run of visible angle brackets and flags every glyph, and a
    CER against the page's own text layer is charged for the whole comment.
    Measured on two board pages (board 010a31b, judge inkdrill 504cf59):

        lib:c9daf79960c3 p68   CER 0.7521 with the markers, 0.1511 without
                               (MathPix on the same page: 0.1799)
        1805.01788 p3          CER 0.2866 with, 0.0472 without
                               (MathPix: 0.0621)

    Both pages read BETTER than the paid lane once the markers are out of
    `text`, so the markers were the whole measured gap.

    Nothing is lost by keeping them out of the reading: the same line record
    already carries `deferred_glyphs` -- every glyph with no LaTeX, with its
    region, font and glyph name -- plus `complete: false` and
    `confidence: 0.0`. The characters are what the page shows, which is what a
    reading is for; `to_markdown` keeps the explicit marker.
    """
    if sp.kind == "text":
        # T-0156 — AND THE FACE THE PAGE SET IT IN. The reading's `text`
        # already carries LaTeX for maths (`$...$` below), and the judge sets
        # each line from THIS field (`judge.py:1269`), taking only the font
        # family from the page — so a wrapper that reaches only the `.tex`
        # projection cannot move `style_rate`. Same rule as the projection:
        # every face in the span must agree (`texmap.emphasis_for`).
        _live = [g for g in sp.glyphs if (g.text or "").strip()]
        return texmap.wrap_emphasis(
            _run_text(sp.glyphs),
            {g.fontname for g in _live},
            [g.glyphname for g in _live],
            any((g.text or "").islower() and ".sc" not in (g.glyphname or "")
                for g in _live))
    tex = span_latex(sp)
    if tex is not None:
        return f"${tex}$"
    # The characters of a span that could not be typed, in ONE maths group.
    #
    # Not a text run: a maths command among them then lands in text mode and
    # pdflatex answers "Missing $ inserted" -- 13 of the board's 14 lines that
    # would not compile. Not one group per command either: `\bigl[` must be
    # matched by `\bigr]` INSIDE the same group, so wrapping each token on its
    # own turned `3\bigl[-11/2\bigr]` into `3$\bigl[$-11/2$\bigr]$` and broke
    # the pair. One group round the whole span keeps every pair together, and a
    # character the renderer cannot set in maths mode is dropped and counted by
    # the judge rather than failing the line (inkdrill db1e766).
    #
    # Safe because a span of pure prose is no longer a maths span at all:
    # `_prose_is_not_maths` re-types it before this is ever reached.
    #: T-0154 — AND A ROW THAT REFUSES IS STILL SEVERAL TERMS. Measured on
    #: lib:c57ac038ae5f p293 rows 27 and 28: `to_tex` refuses both rows, yet
    #: assembles the `\alpha_0` term ALONE as `\alpha_{0} = \frac{1}{2} ,`
    #: — correct, subscript and fraction. One whole-row refusal was flattening
    #: all eight terms to their characters, losing `t_0`'s subscript,
    #: `\alpha_0`'s fraction and `-4^{-1}`'s exponent together. 1 of 8 terms
    #: assembles on its own, so this is necessary and not sufficient; the rest
    #: need the Above/Below relation (see the multi-baseline design).
    #:
    #: INSIDE THE ONE GROUP, for the reason the comment above gives: a term's
    #: own `\bigl[` ... `\bigr]` stays in the same group as its match. A term
    #: that still refuses is flattened exactly as the whole span was, so no
    #: glyph is dropped and the character count cannot fall.
    from pdfreader.structure import split_terms, to_tex

    pieces: list[str] = []
    terms = split_terms(sp.glyphs, sp.rules)
    if len(terms) > 1:
        for term in terms:
            tx0 = min(g.rect[0] for g in term)
            tx1 = max(g.rect[2] for g in term)
            mine = [r for r in (sp.rules or [])
                    if tx0 - 1 <= r.rect[0] and r.rect[2] <= tx1 + 1]
            one = to_tex(list(term), mine)
            pieces.append(one if one else _run_text(term, maths_mode=True))
    body = (" ".join(x for x in pieces if x) if any(pieces)
            else _run_text(sp.glyphs, maths_mode=True))
    return ("$" + body + "$") if body.strip() else body


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
