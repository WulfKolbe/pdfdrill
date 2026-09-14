r"""What the PDF itself says is on the page, glyph by glyph.

A MathPix reading is one opinion about some ink. For a born-digital document
there is a SECOND, INDEPENDENT opinion available for free, and it is the
typesetter's own: the page's text layer, plus the font `/Encoding` that names
every glyph the text layer cannot map to Unicode. This module reads that.

WHY IT EXISTS
-------------
679. Nineteen of 44,633 published equation/formula rows cannot be typeset at
all, and eight of those are a MathPix GLYPH DECOMPOSITION: the recogniser met
a symbol it could not name and emitted CJK radicals or ideographic
DESCRIPTION characters (⿰ ⿱ ⿺ ⿻ — whose only purpose is to describe how a
character is composed) in its place. Asking a language model to guess the
intended symbol works, but it guesses; the PDF knows.

Measured on the three rows of mielke-geometrodynamics, against MathPix:

    row      MathPix wrote              the PDF's glyphs say
    EQ0857   \mathbf{匕}                 Ł  (Times-Roman /Lslash, code 173)
    EQ0472   \stackrel{十}{\Omega}       + (a literal plus)
    FO0431   \jmath  AND  」            /floorright BOTH TIMES — one symbol,
                                        two different wrong guesses

FO0431's own surrounding prose, from the same text layer, reads "covariant
Lie derivative ... on M with respect to an arbitrary vector field": the
document names its own symbol.

TWO SOURCES, AND THE SECOND IS THE USEFUL ONE
---------------------------------------------
A glyph with a `/ToUnicode` entry arrives as a character and needs nothing.
A glyph WITHOUT one arrives as the literal string `(cid:N)` — and that is not
a failure, it is the signal: it marks exactly the glyphs where the producer
supplied no Unicode and an OCR therefore had to invent. For those, the font's
`/Encoding /Differences` still names the glyph, and TeX's names are
self-describing: `floorright` is ⌋, `lscript` is ℓ, `parenleftbigg` is `\bigg(`,
`similarequal` is ≅, `negationslash` is the `\not` overlay.

Measured over the 20 published documents: 604 distinct glyph names, of which
267 are outside the Adobe Glyph List — i.e. 267 names that arrive as
`(cid:N)` and would otherwise be lost. They are overwhelmingly the Computer
Modern / MathTime / AMS conventions, not arbitrary strings.

WHAT THIS IS NOT
----------------
Not a transcriber. It reports evidence — characters, glyph names, fonts,
sizes, positions — and never assembles LaTeX. Turning a census into a reading
is a separate judgement, made with this in hand.

LIMITS, NAMED
-------------
* A SCANNED page has no text layer and no fonts; the census is empty and says
  so. That is where ink measurement is the only evidence.
* A symbolic font declaring a text encoding (`WinAnsi`) with no `/ToUnicode`
  yields PLAUSIBLE BUT WRONG characters rather than `(cid:N)`, which is worse
  than silence. `mielke`'s 15 `Adv*` fonts are this shape (15 of 230, absent
  from every page measured here). `suspect_fonts()` names them so a caller can
  distrust their characters while still trusting their glyph NAMES.
* Coordinates come in as MathPix's 250-dpi CropBox pixels (654) because that
  is what the model stores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

#: MathPix renders every page at 250 dpi of the CropBox (654), and PDF user
#: space is 72 dpi. One scale, stated once.
MATHPIX_DPI = 250.0
_PT_PER_PX = 72.0 / MATHPIX_DPI

#: poppler/pdfminer render an unmapped glyph as this literal string.
CID = re.compile(r"^\(cid:(\d+)\)$")

#: A font that declares a TEXT encoding and supplies no `/ToUnicode` while
#: actually holding symbols. Its characters cannot be trusted; its glyph
#: names still can.
_SUSPECT_NAME = re.compile(r"Adv(TT|P|SPRING|GTIMES|MSBM)", re.I)


@dataclass(frozen=True)
class Glyph:
    """One glyph as the PDF describes it."""
    char: str                      # the decoded character, or "(cid:N)"
    name: Optional[str]            # the /Differences glyph name, when unmapped
    font: str
    size: float
    x: float
    line: int                      # rounded `top`, so a caller can group rows
    #: 688 fix — the glyph's right edge. Added because `overprints()` compared
    #: START positions within 2.5 pt and so could not tell a glyph drawn
    #: THROUGH another from one drawn BESIDE it. Measured cost: of 30 detected
    #: overprints, at least three were a division solidus or a prime standing
    #: next to a narrow glyph — `(a^\dagger+a)/\sqrt{2}` is division, not a
    #: cancelled root. Defaults to `x` so an older caller still constructs.
    x1: float = 0.0

    @property
    def token(self) -> str:
        """What to show a reader: the glyph name wins, because a name is
        specific where a character is absent."""
        return ("/" + self.name) if self.name else self.char

    @property
    def unmapped(self) -> bool:
        return bool(CID.match(self.char))


def _lit(x):
    """A PSLiteral's name, or the value unchanged."""
    return getattr(x, "name", x)


def font_differences(pdf_path) -> dict:
    """{BaseFont: {code: glyph name}} for every font carrying /Differences.

    Walks the xref rather than the page tree: a font dictionary is reachable
    from several pages and this is read once per document.
    """
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdftypes import resolve1

    out: dict = {}
    with open(pdf_path, "rb") as fh:
        doc = PDFDocument(PDFParser(fh))
        for xref in doc.xrefs:
            for objid in xref.get_objids():
                try:
                    obj = resolve1(doc.getobj(objid))
                except Exception:
                    continue                      # a damaged object is not fatal
                if not isinstance(obj, dict) or _lit(obj.get("Type")) != "Font":
                    continue
                enc = resolve1(obj.get("Encoding"))
                diffs = resolve1(enc.get("Differences")) if isinstance(enc, dict) else None
                if not isinstance(diffs, list):
                    continue
                table, code = {}, 0
                for item in diffs:
                    item = resolve1(item)
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        code = int(item)
                    else:
                        nm = _lit(item)
                        if isinstance(nm, str):
                            table[code] = nm
                        code += 1
                if table:
                    out.setdefault(str(_lit(obj.get("BaseFont")) or ""), {}).update(table)
    return out


def suspect_fonts(names) -> list:
    """Those font names whose CHARACTERS should not be trusted (see LIMITS)."""
    return sorted({n for n in names if _SUSPECT_NAME.search(n or "")})


def region_to_points(region: dict) -> tuple:
    """MathPix 250-dpi CropBox pixels -> (x0, y0, x1, y1) in PDF points."""
    x, y = float(region["top_left_x"]), float(region["top_left_y"])
    w, h = float(region["width"]), float(region["height"])
    return (x * _PT_PER_PX, y * _PT_PER_PX,
            (x + w) * _PT_PER_PX, (y + h) * _PT_PER_PX)


def census(page, region: dict, differences: dict, *, pad: float = 4.0) -> list:
    """Every Glyph inside `region`, in reading order.

    `page` is a pdfplumber page; `differences` is `font_differences()`'s
    result. `pad` widens the box by a few points because a MathPix region is
    a tight box around ink and a glyph's declared origin can sit just outside
    it.
    """
    x0, y0, x1, y1 = region_to_points(region)
    out = []
    for c in page.chars:
        if not (x0 - pad <= c["x0"] <= x1 + pad and y0 - pad <= c["top"] <= y1 + pad):
            continue
        char, name = c["text"], None
        m = CID.match(char)
        if m:
            name = (differences.get(c["fontname"]) or {}).get(int(m.group(1)))
        out.append(Glyph(char=char, name=name, font=c["fontname"],
                         size=float(c["size"]), x=float(c["x0"]),
                         line=int(round(c["top"])), x1=float(c["x1"])))
    out.sort(key=lambda g: (g.line, g.x))
    return out


#: Glyphs that are drawn THROUGH another glyph rather than beside it: the
#: Feynman/cancel slash and its named cousins. A plain "/" is the one that
#: matters most and is the one a named-glyph check cannot see, because it maps
#: to Unicode perfectly well.
OVERPRINT_MARKS = ("/", "\u2044", "\u2215")
OVERPRINT_NAMES = ("negationslash", "arrownortheast", "arrowsoutheast")


def overprints(glyphs, *, min_overlap: float = 0.5) -> list:
    r"""[(mark, base, overlap fraction)] where one glyph is drawn THROUGH another.

    688 — A SLASH THROUGH A LETTER IS ONE SYMBOL, AND MATHPIX DROPS BOTH HALVES.
    `1510.06699_EQ0241` prints `\cancel{J}` as two overprinted glyphs:

        'J'  x 207.84-213.36  top 470.73  CMMI10
        '/'  x 208.56-213.54  top 469.77  CMMI10

    a 0.7 pt offset, i.e. the same place. MathPix emitted neither the J nor the
    slash, and — because the J anchored the numerator — produced
    `rac{...}{}` and `rac{}{...}`, two fractions each missing a half. The
    row renders and no gate sees it.

    The same book composes `⇐`+`⇒` into `⟺` this way and MathPix reads THAT
    correctly, so overprinting as such is handled; it is the rare composition
    that is dropped.

    WHY A NAMED-GLYPH CHECK CANNOT FIND THIS. `missing_glyphs` only looks at
    glyphs the font had to NAME because Unicode could not map them. A plain
    "/" maps perfectly, arrives as a character, and is therefore invisible to
    it. Geometry is the only evidence: two glyphs at one position are one
    symbol.

    `min_overlap` is a fraction of the NARROWER glyph's width, so a wide
    delimiter beside a thin letter is not mistaken for an overprint. Same
    baseline band is required (within one glyph height), because a superscript
    sits above rather than through.
    """
    out = []
    for i, a in enumerate(glyphs):
        for b in glyphs:
            if a is b:
                continue
            a_is_mark = a.char in OVERPRINT_MARKS or a.name in OVERPRINT_NAMES
            if not a_is_mark:
                continue
            if b.char in OVERPRINT_MARKS or b.name in OVERPRINT_NAMES:
                continue
            if abs(a.line - b.line) > 6:          # not the same baseline band
                continue
            aw = getattr(a, "width", None)
            # Glyph carries x only; width is not stored, so overlap is judged
            # on start positions, which for a 5-10pt glyph is sufficient and
            # is what the EQ0241 measurement used.
            # OVERLAP OF EXTENTS, not proximity of origins. A mark drawn
            # through a glyph covers most of it; a mark drawn beside one
            # touches at an edge.
            aw, bw = (a.x1 or a.x) - a.x, (b.x1 or b.x) - b.x
            if aw <= 0 or bw <= 0:                     # no width recorded
                if abs(a.x - b.x) <= 2.5:
                    out.append((a, b, round(abs(a.x - b.x), 2)))
                continue
            lo, hi = max(a.x, b.x), min(a.x1, b.x1)
            if hi - lo >= min_overlap * min(aw, bw):
                out.append((a, b, round(abs(a.x - b.x), 2)))
    return out


def as_line(glyphs) -> str:
    """The census as one readable line — what a prompt or a report shows."""
    return " ".join(g.token for g in glyphs)


def unmapped_names(glyphs) -> list:
    """The distinct glyph names the PDF had to supply because Unicode did not."""
    return sorted({g.name for g in glyphs if g.name})


def contradicts(latex: str, glyphs, *, own_region: bool,
                minimum: int = 3) -> "str | None":
    r"""A one-line reason when `latex` cannot be a reading of `glyphs`.

    NOT a transcription check — LaTeX and glyphs are different alphabets and
    a faithful reading legitimately adds `\frac`, `^`, `_` and braces that no
    glyph carries. This asks only the question a wrong answer fails loudly:
    do the glyphs the PDF actually places on the page APPEAR in the proposed
    reading at all?

    679 — this exists because the ink gate accepted a proposal that replaced
    mielke-geometrodynamics_EQ0378's mathematics with a sentence of English
    prose about the Pontryagin index, on the strength of the ink distance
    falling 106 -> 10. Ink distance measures how MUCH ink a rendering makes,
    not whether it is the same ink; a short wrong line beats a long damaged
    one. The letters and digits the PDF puts in that region are not in that
    sentence, and this would have said so.

    `own_region` IS REQUIRED AND IS NOT A CONVENIENCE. The test is only valid
    when `glyphs` came from the object's OWN region. An inline Formula has no
    region of its own, so a caller reaches for its HOST LINE's — and a host
    line is a whole line of prose. Measured on
    mielke-geometrodynamics_FO0431: its host-line census holds 92 glyphs, 84
    of them literal, because the line reads "covariant Lie derivative on M
    with respect to an arbitrary vector field" around the formula. Judged
    against that, MathPix's perfectly reasonable 8-character reading is
    "missing" 49 of 84 glyphs — a false refusal, and a confident one.

    So this declines rather than guesses when the region is not the object's,
    and the parameter is positional-by-keyword and has no default so that
    declining is a decision a caller makes on purpose.

    `minimum` is the floor below which the test declines to judge: a region
    holding one or two glyphs carries no evidence worth refusing on.
    """
    if not own_region:
        return None
    # ASCII alphanumerics ONLY, and this restriction is load-bearing. LaTeX
    # spells Greek and most symbols as COMMANDS, not characters: a page whose
    # glyphs are α β ϑ Π Σ is faithfully read as `\alpha \beta \vartheta
    # \Pi \Sigma`, in which not one of those characters appears. Requiring
    # the character rejects the correct reading.
    #
    # Measured on mielke EQ0378, which is why this is not a guess: over its
    # real 72-glyph census the first version called 26 of 33 "literal" glyphs
    # missing from the PROSE that had been wrongly accepted — correct — and
    # also rejected MathPix's own legitimate reading, because α β ϑ Π Σ ∼ ±
    # were counted as literals it lacked. A check that refuses the right
    # answer is worse than no check.
    #
    # ASCII letters and digits are the population LaTeX does spell literally,
    # so they are the only ones a reading is required to contain. Everything
    # else is evidence for a reader, not a test.
    literal = [g.char for g in glyphs
               if not g.unmapped and len(g.char) == 1
               and g.char.isascii() and g.char.isalnum()]
    if len(literal) < minimum:
        return None
    missing = [ch for ch in literal if ch not in latex]
    if len(missing) > len(literal) / 2:
        return ("%d of %d literal glyph(s) the PDF places in this region are "
                "absent from the reading (%s)"
                % (len(missing), len(literal),
                   "".join(sorted(set(missing))[:12])))
    return None


def missing_glyphs(latex: str, glyphs, *, own_region: bool) -> dict:
    r"""{glyph name: how many times the page has it but the reading does not}.

    682 — COUNTING, WHICH MEMBERSHIP COULD NEVER DO. `contradicts()` asks
    "is this glyph in the reading"; a reading that contains one π where the
    page has two passes it, and so does a reading that ignores an overprinted
    slash entirely. Both are real, both were found by a reader and not by a
    check:

      EQ0974  the page has π twice, MathPix read it once. pix2tex read it
              twice and is right.
      EQ0472  the page has an `/arrownortheast` overprinted on an `R`
              (the R's box sits entirely inside the glyph's); MathPix dropped
              it and the reading renders perfectly without it.
      EQ0293  the page has `/floorright` four times, the reading has
              `\rfloor` zero times and `\downharpoonleft` four times.

    Measured over mielke alone: 24 rows, 43 missing `\rfloor` — 30 of them
    misread as `\downharpoonleft` and 13 dropped. Not one of those rows fails
    any other gate, because every one of them TYPESETS.

    Only NAMED glyphs are counted, and only those `NAME_TOKENS` can turn into
    LaTeX. A delimiter-size name (`/bracketleftbigg` is `\bigg[`, which a
    reading legitimately writes `\left[`) would otherwise swamp the signal:
    a first, naive version of this reported 832 rows, whose top entries were
    all correct readings.
    """
    if not own_region:
        return {}
    import collections
    want = collections.Counter(g.name for g in glyphs
                               if g.name and g.name in NAME_TOKENS)
    out = {}
    for name, n in want.items():
        have = max(latex.count(tok) for tok in NAME_TOKENS[name])
        if have < n:
            out[name] = n - have
    return out


# ---------------------------------------------------------------------------
# 681 — the census as an ACCEPTANCE route, not only a refusal
# ---------------------------------------------------------------------------

#: Census glyph name -> the LaTeX token(s) that legitimately write it. Seeded
#: ONLY by what the rows in hand actually need: `/floorright` and `/Lslash`
#: for mielke's three, plus the two obvious mirrors. 267 names in this corpus
#: are outside the Adobe Glyph List; a table built ahead of demand would be
#: inventory rather than evidence, and every entry here has to be justified by
#: a row it unblocks.
NAME_TOKENS: dict = {
    "floorright":  (r"\rfloor",),
    "floorleft":   (r"\lfloor",),
    "ceilingright": (r"\rceil",),
    "ceilingleft": (r"\lceil",),
    "Lslash":      (r"\mathrm{Ł}", r"\L", "Ł"),
    "lscript":     (r"\ell",),
    # 682 fix — MEASURED, after this entry shipped wrong. It said `\cong`,
    # from memory. `similarequal` is ≃ (U+2243), which is `\simeq`; ≅ is a
    # different symbol. Checked against the corpus rather than argued: across
    # the 25 mielke rows whose page carries `/similarequal`, MathPix writes
    # `\simeq` 29 times and `\cong` never. The wrong entry generated 29 false
    # "missing glyph" reports against readings that were already correct —
    # in a table whose whole justification is that a lookup cannot
    # hallucinate. Every entry here must come from a row, not from recall.
    "similarequal": (r"\simeq",),
}


def _tokens(latex: str) -> list:
    r"""`latex` split into LaTeX tokens: a command (`\rfloor`) or one char."""
    out, i, n = [], 0, len(latex or "")
    while i < n:
        ch = latex[i]
        if ch == "\\" and i + 1 < n:
            j = i + 1
            if latex[j].isalpha():
                while j < n and latex[j].isalpha():
                    j += 1
            else:
                j += 1
            out.append(latex[i:j]); i = j
        else:
            out.append(ch); i += 1
    return out


#: LaTeX MARKUP: a reading composes these, a page never draws them. They are
#: exempt from BOTH of `justifies`' rules — from "is this token on the page",
#: because no page places a brace as a character, and from the narrowness
#: count, because `\cancel{X}` introduces `\cancel`, `{` and `}` and would
#: otherwise exhaust a three-token budget before changing anything at all.
#:
#: 688 — both exemptions were found by rows the route wrongly refused.
#: cardona-qft-methods_EQ0048 was refused for its braces alone;
#: mielke-geometrodynamics_EQ0474 for "4 distinct tokens" of which three were
#: markup; lyche-numerical-linear-algebra_EQ0855 for a literal NEWLINE.
STRUCTURE = frozenset({
    "{", "}", "$", "&", "^", "_", "\\", " ", "\n", "\t",
    r"\left", r"\right", r"\,", r"\;", r"\!", r"\:", r"\ ",
    r"\quad", r"\qquad", r"\big", r"\Big", r"\bigg", r"\Bigg",
})


def justifies(original: str, proposed: str, glyphs, *,
              max_new: int = 3) -> "tuple[bool, str]":
    r"""(ok, reason) — does the PDF's own census justify this exact repair?

    681. A THIRD ACCEPTANCE ROUTE, beside the ink gate and the author's
    e-print. It exists because the ink gate cannot be trusted to judge a
    reading: it accepted a sentence of English prose over an equation on a
    -96 ink delta, and 17 of 30 recorded refinements carry that same shape.
    Sending a repair whose right answer is already KNOWN through a gate that
    cannot tell right from wrong would stamp `verified_by: "ink"` on something
    the ink never established.

    For a glyph-decomposition defect the right answer IS known, and by a
    stronger authority than ink: the typesetter's own `/Encoding`. mielke's
    `匕` is `/Lslash`, its `」` and `\jmath` are both `/floorright`, its `十`
    is a literal `+`. This route accepts exactly that kind of repair and
    NOTHING WIDER, by two rules:

      1. EVERY TOKEN THE REPAIR INTRODUCES MUST BE JUSTIFIED BY THE CENSUS —
         either a literal character the census places in that region, or a
         LaTeX command that `NAME_TOKENS` ties to a glyph name the census
         reports. A token the page cannot be shown to contain is not a
         transcription, it is an invention.
      2. AT MOST `max_new` TOKENS MAY BE INTRODUCED AT ALL. This is what
         makes the route unable to accept a rewrite: MiniMax's own proposals
         for these rows fixed the symbol correctly and then appended a
         neighbouring equation, and that tail is dozens of tokens. A
         substitution is small by nature.

    Deliberately NOT checked here: whether the result renders. That is
    `validate_one`'s job and it runs first. This answers one question only —
    is the change the page's own evidence for it.
    """
    if not (proposed or "").strip():
        return False, "empty proposal"
    before, after = _tokens(original), _tokens(proposed)
    import collections
    removed = collections.Counter(before) - collections.Counter(after)
    added = collections.Counter(after) - collections.Counter(before)
    if not added and not removed:
        return False, "no change proposed"
    # 682 — DISTINCT tokens, not multiplicity, plus a balance test. mielke
    # EQ0293 reads the SAME glyph wrong four times: `/floorright` x4 on the
    # page, `\downharpoonleft` x4 in the reading. Repairing it introduces
    # `\rfloor` four times — one distinct token — and counting multiplicity
    # refused that legitimate substitution while a rewrite introducing three
    # different tokens passed. What distinguishes a substitution is that it
    # puts back what it takes away: n of X for n of Y.
    # content only: markup is not a change to the mathematics (STRUCTURE)
    add_c = {t: n for t, n in added.items() if t.strip() and t not in STRUCTURE}
    rem_c = {t: n for t, n in removed.items() if t.strip() and t not in STRUCTURE}
    if len(add_c) > max_new:
        return False, ("%d distinct content token(s) introduced, at most %d may "
                       "be — a census repair is a substitution, not a rewrite "
                       "(%s)" % (len(add_c), max_new, " ".join(sorted(add_c))[:60]))
    if sum(add_c.values()) > sum(rem_c.values()) + max_new:
        return False, ("introduces %d content token(s) against %d removed — a "
                       "substitution puts back what it takes away"
                       % (sum(add_c.values()), sum(rem_c.values())))

    literals = {g.char for g in glyphs if not g.unmapped}
    named = {g.name for g in glyphs if g.name}
    allowed = set()
    for nm in named:
        allowed.update(NAME_TOKENS.get(nm, ()))
    # 688 — AN OVERPRINT LICENSES A SLASH COMMAND. Two glyphs at one position
    # are one symbol, and no single glyph corresponds to the macro that writes
    # it: 1510.06699_EQ0241 prints a J at x 207.84 and a solidus at x 208.56,
    # and the reading for that is `\cancel{J}`. Without this the route refused
    # a repair that was correct, census-consistent and complete — measured on
    # that row, where MiniMax merged two malformed fractions and placed the
    # slashed J exactly right.
    #
    # `\cancel` only: `cancel` is in the report preamble (report_tex.py:811)
    # and `slashed` is not, so `\slashed` passes `display_safe` — which does
    # not check that a command exists — and then fails at xelatex. A token this
    # route licenses must be one the build can typeset.
    ops = overprints(glyphs)
    if ops:
        allowed.update((r"\cancel", r"\not"))
        # 688 — a NEGATION SLASH OVER A RELATION IS THE NEGATED RELATION, and
        # that is a different reading from "the relation, cancelled".
        # gilmore-lie-groups_EQ0012 prints `/negationslash` over `=` in
        # `(23)(12) = (123)`, where the mathematics is plainly "not equal";
        # `\cancel{=}` is visually faithful and semantically wrong. The
        # conventional macro is licensed for exactly the relations TeX has one
        # for, and nothing wider.
        REL = {"=": r"\neq", r"\in": r"\notin",
               r"\subset": r"\not\subset", r"\subseteq": r"\nsubseteq",
               r"\mid": r"\nmid", r"\leq": r"\nleq", r"\geq": r"\ngeq",
               r"\equiv": r"\nequiv", r"\parallel": r"\nparallel",
               r"\sim": r"\nsim"}
        for mark, base, _dd in ops:
            if mark.name == "negationslash" or mark.char == "/":
                tok = REL.get(base.char)
                if tok:
                    allowed.add(tok)

    # 688 — LATEX MARKUP IS NOT A GLYPH, and requiring the page to "place" it
    # refuses correct repairs. Wrapping a symbol as \cancel{D} necessarily
    # introduces `{` and `}`, which no page places as characters. Measured on
    # cardona-qft-methods_EQ0048: the repair rendered, was census-consistent,
    # left nothing missing and had no empty argument, and was refused solely
    # for its braces. 1510.06699_EQ0241 passed only by accident — its broken
    # \frac left spare braces that cancelled out the ones the repair added.
    #
    # These tokens are structure: a reading composes them, a page never draws
    # them. Same distinction as the Greek rule in `contradicts` — LaTeX spells
    # some things as commands and some as syntax, and neither is a glyph.
    unjustified = []
    for tok in added:
        if tok in STRUCTURE or not tok.strip():
            continue
        if tok in literals or tok in allowed:
            continue
        # a one-character token the census places, ignoring case-only noise
        if len(tok) == 1 and tok in literals:
            continue
        unjustified.append(tok)
    if unjustified:
        return False, ("the census does not place %s on this page; it names "
                       "%s and places %s"
                       % (" ".join(sorted(unjustified))[:40],
                          ", ".join("/" + n for n in sorted(named)) or "no "
                          "unmapped glyph",
                          "".join(sorted(c for c in literals
                                         if len(c) == 1))[:40]))
    return True, ("every introduced token is on the page: %s"
                  % " ".join(sorted(added)))
