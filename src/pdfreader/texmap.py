"""texmap — project a (font family, glyph name) onto a LaTeX token.

Built from the measured inventory of four born-digital maths documents:
280 distinct (family, glyphname) pairs over 64,094 maths glyph instances.
Nothing here is invented from TeX folklore that the corpus did not contain.

WHY THE FAMILY IS PART OF THE KEY
    The glyph name alone is not the identity. `C` is `C` in CMMI, `\\mathbb{C}`
    in MSBM, `\\mathcal{C}` in RSFS and `\\mathfrak{C}` in EUFM — same name,
    four different LaTeX tokens. The embedded font's family is what selects
    the alphabet, which is why the name channel had to carry the font too.

WHAT A TOKEN IS NOT
    Three kinds of maths cannot be projected from a glyph at all, and the
    table says so rather than guessing:

    FRAGMENT   an extensible delimiter is drawn as several glyphs stacked
               (`bracketlefttp` / `bracketleftex` / `bracketleftbt`). No one
               of them is a LaTeX token; the group is one `\\left[`. These
               must be merged by geometry before projection.
    RULE       `\\frac`, `\\sqrt`, `\\overline` have NO glyph for the bar.
               It is a filled rule, which pdfminer reports as an LTLine of
               zero height. `radicalbig` is only the radical SIGN; its
               vinculum is a separate rule. Recovering these needs the rule
               rectangles, not the glyph stream.
    UNKNOWN    not in the table. The caller must keep the blob/outline and
               defer, never emit a plausible-looking guess.

CONFIDENCE
    "corpus"    the mapping is standard and the glyph occurs in the corpus
    "unverified" plausible but NOT checked against a font's own encoding
                 table; treated as unknown by `project` unless explicitly
                 allowed, so it can never silently enter output.
"""
from __future__ import annotations

import re

_CM_SUBSET = re.compile(r"^[A-Z]{6}\+")
_CM_BASE = re.compile(r"\d+$")
from typing import NamedTuple


# TeX/Type1 maths font families. The family says which ALPHABET a glyph name
# is to be read in: `a` in CMMI is a maths variable, `a` in CMR is a letter.
FAMILY_RULES = [
    (re.compile(r"CM(MI|MIB)\d*", re.I), "math-italic"),      # Computer Modern math italic
    (re.compile(r"CM(SY|BSY)\d*", re.I), "math-symbol"),      # CM symbols
    (re.compile(r"CMEX\d*", re.I), "math-extension"),         # CM extension (big ops/delims)
    (re.compile(r"MSAM\d*|MSBM\d*", re.I), "ams-symbol"),     # AMS symbols A/B
    (re.compile(r"EUFM\d*|EUFB\d*", re.I), "fraktur"),
    (re.compile(r"EUSM\d*|EUSB\d*", re.I), "script"),
    (re.compile(r"MTMIB|MTMI", re.I), "math-italic"),         # MathTime italic
    (re.compile(r"MTSY|MTSYN|MTSYB", re.I), "math-symbol"),   # MathTime symbols
    (re.compile(r"BLEX|BLSY|MTEX", re.I), "math-extension"),  # Belleek/MathTime ext
    (re.compile(r"RSFS\d*", re.I), "script"),
    # LATIN MODERN: Computer Modern's successor, and what every
    # lualatex/xelatex document ships. Its maths fonts were falling through
    # to "text", so none of their glyph names were projected -- measured, 81
    # of the small crops in one corpus pass were LM `prime`, `element`,
    # `lscript` and `asteriskmath`, every one of which the table already
    # knows under its Computer Modern name.
    # MnSymbol: a complete maths family (MnSymbol5..7 are its optical
    # sizes). Unknown here, it fell through to "text" and nothing projected
    # -- measured, 3721 failures on one 476-page paper, 3239 of them the
    # single glyph `minute`, which RENDERS as a prime (`f'`).
    # `TeX-matha`/`TeX-mathx` are the AMS symbol and extension fonts under a
    # distiller's own naming. Classified as TEXT they emitted their
    # StandardEncoding fallback characters literally -- `\pi^{*}p\omega q`
    # for `\pi^{*}(\omega_{0})`.
    (re.compile(r"TeX-math[ab]\d*", re.I), "math-symbol"),
    (re.compile(r"TeX-mathx\d*", re.I), "math-extension"),
    (re.compile(r"TeX-mathit\d*", re.I), "math-italic"),
    (re.compile(r"MnSymbol\w*\d*", re.I), "math-symbol"),
    (re.compile(r"LMMathItalic\d*", re.I), "math-italic"),
    (re.compile(r"LMMathSymbols\d*", re.I), "math-symbol"),
    (re.compile(r"LMMathExtension\d*", re.I), "math-extension"),
    (re.compile(r"LMSans(Quotation|Demi)?\d*|LMRoman\w*\d*", re.I),
     "text-cm"),
    # TXFONTS / PXFONTS: the Times- and Palatino-based maths families, and
    # what a `\usepackage{txfonts}` document emits. Unknown here they fell
    # through to "text", so glyphs that the table already knows by name --
    # `prime`, `multiply`, `element`, `latticetop` -- were never looked up:
    # measured on 2601.07372, 16 deferrals from `txsys` and `txsym` alone,
    # every one of them a name the maths tables carry.
    #
    # The suffix letter varies by role and by optical size (`txsy`, `txsys`,
    # `txsym`, `txsyc`), so the match is on the STEM plus anything.
    (re.compile(r"(tx|px)(b)?mi\w*", re.I), "math-italic"),
    (re.compile(r"(tx|px)(b)?sy\w*", re.I), "math-symbol"),
    (re.compile(r"(tx|px)(b)?ex\w*", re.I), "math-extension"),
    # The `<Family>Math<Role>` naming that modern OpenType-era maths packages
    # use -- `XCharterMathMI` is XCharter's maths italic and was read as text.
    # Kept AFTER the explicit rules above so a known family still wins.
    # 828 — `\w` DOES NOT MATCH A HYPHEN, and a TeX font family is as likely
    # to write `Fourier-Math-Extension` as `XCharterMathEX`. Cahiers GUTenberg
    # 51 (Fourier-GUTenberg, Utopia + Fourier) ships three of them —
    # Fourier-Math-Symbols, Fourier-Math-Letters, Fourier-Math-Extension — and
    # every one fell through to "text", so the document's whole maths font
    # layer was read with the text tables: `integraldisplay` (a display
    # integral) projects to `\int` under math-extension and to nothing under
    # text, and came out as `(cid:110)`.
    #
    # The separator is optional and may be `-`, `_` or a space; `Letters` is
    # Fourier's name for what other families call `Italic`.
    (re.compile(r"[\w-]*Math[-_ ]?(Italic|MI|Letters?)[\w-]*", re.I), "math-italic"),
    (re.compile(r"[\w-]*Math[-_ ]?(Symbols?|SY)[\w-]*", re.I), "math-symbol"),
    (re.compile(r"[\w-]*Math[-_ ]?(Extension|EX)[\w-]*", re.I), "math-extension"),
    # DOUBLESTROKE (`dsfont`): a whole font whose every glyph is
    # blackboard-bold, digits included. Unknown here it fell through to
    # "text", so `dsrom12`'s `one` -- which is the IDENTITY MATRIX, the
    # double-struck 1 -- projected as an ordinary `1` and the symbol stopped
    # being itself. Eight of them in wzlxjtu-026 alone, against a gold that
    # writes `\mathds{1}` eight times.
    #
    # It is NOT `\mathbb`: amssymb's blackboard alphabet is msbm's, which
    # carries A-Z and no digits, so `\mathbb{1}` -- which is what MathPix
    # emits here -- has nothing to set. The font names its own package.
    (re.compile(r"dsrom\d*|doublestroke\w*", re.I), "doublestroke"),
    (re.compile(r"CMR\d*|CMBX\d*|CMTI\d*|CMSL\d*|CMTT\d*", re.I), "text-cm"),
]


# Italic in TeX font names is `TI` (text italic), `MI` (math italic) or `SL`
# (slanted) -- never the substring "it". Testing `endswith("it")` matched
# nothing: `CMTI10` ends in "ti". The error made every Computer Modern italic
# look upright, so variables were treated as operator names.
#: 776 -- THE SUBSTITUTE FONTS SPELL IT SHORT.
#:
#: `is_italic` decides whether a text-font letter on a display line is a
#: VARIABLE (775), so a name it does not recognise costs every variable in
#: that document. Surveyed over 7,376 distinct font names in the library, it
#: refused 29 genuinely italic ones -- and the top two are not rare:
#:
#:     NimbusRomNo9L-ReguItal     483 documents
#:     NimbusRomNo9L-MediItal     121
#:     NimbusRomNo9L-Regu-Slant_167 35   StandardSymL-Slant_167  33
#:     NimbusSanL-ReguItal / NimbusMonL-ReguObli   16 each
#:
#: URW's Nimbus faces are what Ghostscript and pdftex substitute with, so
#: they turn up in anything not shipping its own fonts. `ReguItal` carries
#: neither the word "italic" nor a hyphen before "Ital", which is what the
#: old pattern needed. `Slant_167` is a slanted instance and is italic for
#: every purpose here.
#:
#: Checked for the opposite error: no upright name in those 7,376 matches.
#: `LMMathItalic10-Regular` does, and should -- `-Regular` is its WEIGHT.
_ITALIC_NAME = re.compile(
    r"italic|oblique|"
    r"\bcm(ti|mi|sl|bxti|bxsl|mib|itt)\d*|"
    r"-(it|ital|italic|oblique)\b|"
    r"ital\w*$|obli\w*$|slant",
    re.I,
)


# Fonts whose glyphs are DRAWING, not text. Xy-pic builds a commutative
# diagram by stamping a dash glyph repeatedly along a line and capping it with
# an arrow-tip glyph; LaTeX's picture environment does the same with line10 and
# lasy. There are no path operators in the PDF at all -- the "strokes" are
# glyphs -- so a text pipeline scatters them through the prose as `****\ */`.
_DRAWING_NAME = re.compile(
    r"^xy(dash|atip|btip|mark|circ|dash|line|bsql|rown)|^xy[a-z]*-|"
    r"^(line|linew|lcircle|lcirclew)\d*$|"
    r"^lasy[b]?\d*$|"
    r"^(msam|msbm)$",          # bare, without a size: rare drawing variants
    re.I,
)


# TeX sets UPPERCASE Greek in the roman text font, not the maths font: in OT1
# `\Gamma` is cmr slot 0x00. So a `Gamma` glyph arrives from CMR12 with family
# "text-cm", and a classifier that goes by font alone calls it prose. It is
# mathematics -- the font is an encoding accident of OT1.
_UPPER_GREEK = {
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
    "Phi", "Psi", "Omega",
}


def greek_latex(glyphname: str | None) -> str | None:
    """The LaTeX command for a Greek letter glyph name, whatever font it
    was set in. Returns None for anything else."""
    if not glyphname:
        return None
    if glyphname in _UPPER_GREEK:
        return "\\" + glyphname
    if glyphname in _GREEK:
        return "\\" + glyphname
    return _VARIANTS.get(glyphname)


def is_drawing(fontname: str) -> bool:
    """True if this font draws diagram parts rather than setting text."""
    return bool(_DRAWING_NAME.search(fontname.split("+")[-1]))


# Typewriter faces. A line set in one is VERBATIM: its `<` and `>` come from
# the maths font because OT1 has no angle brackets, and projecting them as
# mathematics turns `<omtext xml:id="foo">` into `$<$ omtext xml:id="foo" $>$`.
_MONO_NAME = re.compile(
    r"\bcm(tt|sltt|itt|tex|vtt)\d*|"
    # 781 -- SFTT is TeX's OWN typewriter in T1 (cm-super), and the measured
    # route cannot see it on a short document: `measure_monospace` needs 100
    # advances and 10 distinct letters before it will call a font monospace,
    # and a four-line listing has forty glyphs. Three of the first twelve
    # gold listings read back as prose for exactly this reason. The name is
    # admissible here because the measurement CONFIRMS it wherever there is
    # enough of it: lst-278, 21,928 advances in SFTT0800, 51 letters,
    # advance/size 0.531 on 100.0% of them.
    r"\bsftt\d*|"
    r"courier|consol|monaco|menlo|inconsolata|nimbusmon|"
    # 781n -- MEASURED OVER 18,685 REAL /BaseFont NAMES, from the 6,101
    # PDFs of the IUST object corpus (arXiv 1812.09961). The old rule
    # anchored `mono` at the END of the name, which caught
    # `LiberationMono` and `DejaVuSansMono` and missed
    # `Monospace821BT-Roman` -- 98 occurrences, the single commonest
    # typewriter name in that sample -- along with `DroidSansMono-Slant`
    # and every `LMTypewriter*`, which is what `lmodern` makes \ttfamily.
    #
    # Two exclusions, and the corpus sized both: `monotype` is a FOUNDRY
    # (MonotypeCorsiva, a script face; 4 names, 5 occurrences) and
    # `monoprop` is Latin Modern Mono PROPORTIONAL, which is not fixed
    # pitch despite the name. Everything else matching `mono` in that
    # sample -- 50 distinct names, ~790 occurrences -- is genuinely
    # monospace: Bera, DejaVu, Droid, Fira, Free, Liberation, Luxi,
    # Monospac821, PrimaSansMono, TheSansMono and every LMMono.
    r"mono(?!type|prop)|typewriter|-tt\b",
    re.I,
)


# Fonts MEASURED to be monospace in the document being read. Names carry no
# reliable signal: `lmt-regular` is Latin Modern Typewriter and `t1-uni-regular`
# is proportional, and nothing in either name says so.
_MEASURED_MONO: set[str] = set()


def measure_monospace(samples) -> set[str]:
    """Which fonts are monospace, from their ADVANCE WIDTHS.

    A monospace face advances by the same amount for every glyph. Measured on
    one journal page:

        lmt-regular         91% of glyphs share one advance ratio -> monospace
        t1-uni-regular      25% -- proportional, despite setting the listings
        CharisSIL           12% -- ordinary body text
        LMRoman10-Regular  100% -- but all 517 glyphs are SPACES

    That last row is why diversity is required as well -- and it has to be
    LETTERS, not characters. Measured across two documents:

        lmt-regular   21 distinct, 20 letters, 0.920 uniform -> monospace
        CMR8          17 distinct,  4 letters, 0.930 uniform -> digits and
                      symbols, uniform by accident

    Uniformity alone cannot tell those apart; the alphabet can.

    `samples` yields (fontname, advance, size, text).
    """
    ratios: dict[str, list[float]] = {}
    chars: dict[str, set[str]] = {}
    for name, adv, size, text in samples:
        if size <= 0 or not text.strip():
            continue
        key = name.split("+")[-1]
        ratios.setdefault(key, []).append(round(adv / size, 3))
        chars.setdefault(key, set()).add(text)
    out: set[str] = set()
    for key, vals in ratios.items():
        letters = {c for c in chars.get(key, ()) if c.isalpha()}
        if len(vals) < 100 or len(letters) < 10:
            continue
        top = max(set(vals), key=vals.count)
        if vals.count(top) >= 0.9 * len(vals):
            out.add(key)
    return out


def set_measured_monospace(names) -> None:
    """Install the measured set for the document being read."""
    _MEASURED_MONO.clear()
    _MEASURED_MONO.update(names)


def is_monospace(fontname: str) -> bool:
    """True if this font is a typewriter face.

    Measurement first, name second: the name is a hint that happens to be
    right for TeX's own families and wrong for anything subset by a
    publisher's toolchain.
    """
    base = fontname.split("+")[-1]
    if base in _MEASURED_MONO:
        return True
    return bool(_MONO_NAME.search(base))


def is_italic(fontname: str) -> bool:
    """True if this font is an italic or slanted face."""
    return bool(_ITALIC_NAME.search(fontname.split("+")[-1]))


#: 781e -- moved here from `project_mmd`, where `structure` and `listings`
#: both had to reach into a projector to ask a question about a FONT. The
#: family tests belong together; the regex is unchanged.
_BOLD_NAME = re.compile(
    r"bold|"                          # Times-Bold, Arial,Bold, ...
    r"\bcm(bx|b|ssbx|bxti|bxsl)\d*|"  # Computer Modern bold family
    r"\bcmssdc\d*|"                   # CM sans demi condensed
    r"-(bd|bold|semibold|black|heavy)\b|"
    # 814 — URW NAMED TIMES' BOLD "MEDIUM". `\textbf` under `times`/`mathptmx`
    # resolves to `ptmb`, which embeds as `NimbusRomNo9L-Medi` — and that is
    # pdfLaTeX's default Times substitute, so it is the commonest bold face in
    # the corpus: 480 readings in 380 documents, every one of them invisible to
    # this test. Measured over 393 documents using the family, 376 carry BOTH
    # `-Regu` and `-Medi`, which settles which weight `Medi` is; only 4 have
    # `Medi` alone. Scoped to NimbusRomNo9L on purpose — `NimbusSanL` and
    # `NimbusMonL` spell their bold `-Bold`, so a blanket `medium` rule would
    # also catch `NunitoExtraLight-Medium` and `Flama-Ultralight`, which are
    # not bold at all. Same failure class as the CMBX note above.
    r"\bnimbusromno9l-medi|"
    # A truncated `-Bold`, as some producers write it (`NimbusSan-Bol`).
    r"-bol\b|"
    r"(^|[^a-z])(bd|blk)\d*$",
    re.I,
)


def is_bold(fontname: str) -> bool:
    """True if this font is a bold face."""
    return bool(_BOLD_NAME.search(fontname.split("+")[-1]))


def family_of(fontname: str) -> str:
    base = fontname.split("+")[-1]
    for rx, label in FAMILY_RULES:
        if rx.search(base):
            return label
    return "text"

class TexToken(NamedTuple):
    latex: str | None   # None when nothing can be emitted for this glyph alone
    kind: str           # atom | delimiter | bigop | accent | fragment | unknown
    package: str | None  # LaTeX package required, if any
    confidence: str     # corpus | unverified | none


UNKNOWN = TexToken(None, "unknown", None, "none")

# --- Greek and named letters shared by the maths alphabets -----------------
_GREEK = {
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau",
    "upsilon", "phi", "chi", "psi", "omega",
}
# TeX's "variant" glyph names, where the name carries the \var prefix
_VARIANTS = {
    "epsilon1": r"\varepsilon",
    "theta1": r"\vartheta",
    "rho1": r"\varrho",
    "phi1": r"\varphi",
    "sigma1": r"\varsigma",
}

# --- math-italic (CMMI / MTMI): variables, Greek, a few named symbols ------
_MATH_ITALIC = {
    "lscript": r"\ell", "star": r"\star", "partialdiff": r"\partial",
    # cmmi10 carries the musical symbols at 0x5B-0x5D
    "flat": r"\flat", "natural": r"\natural", "sharp": r"\sharp",
    "weierstrass": r"\wp", "arrowrightleft": r"\rightleftharpoons",
    "vector": r"\vec", "period": ".", "comma": ",", "slash": "/",
    "less": "<", "greater": ">", "parenleft": "(", "parenright": ")",
}

# --- math-symbol (CMSY / MTSYN) -------------------------------------------
_MATH_SYMBOL = {
    "minus": "-", "plus": "+", "equal": "=", "colon": ":", "semicolon": ";",
    "exclam": "!", "bar": r"\mid", "bardbl": r"\|",
    "asteriskmath": r"\ast", "periodcentered": r"\cdot", "multiply": r"\times",
    "plusminus": r"\pm", "minusplus": r"\mp", "prime": r"\prime",
    "logicaland": r"\wedge", "logicalor": r"\vee",
    "intersection": r"\cap", "union": r"\cup",
    "element": r"\in", "owner": r"\ni", "emptyset": r"\emptyset",
    "propersubset": r"\subset", "propersuperset": r"\supset",
    "reflexsubset": r"\subseteq",
    "lessequal": r"\leq", "greaterequal": r"\geq",
    "lessmuch": r"\ll", "greatermuch": r"\gg",
    "similar": r"\sim", "similarequal": r"\simeq", "approxequal": r"\approx",
    "equivalence": r"\equiv", "proportional": r"\propto",
    "precedes": r"\prec", "perpendicular": r"\perp",
    "infinity": r"\infty", "nabla": r"\nabla", "radical": r"\surd",
    # cmsy10 slot 0x3E. In a linear-algebra text this is the TRANSPOSE,
    # `A^{\top}`: 3738 occurrences in one 1962-page book.
    "latticetop": r"\top",
    # cmsy10 slot 0x0E: function composition, `f \circ g`. Confirmed against a
    # rendered page showing `f o i` where the source has a composition.
    "openbullet": r"\circ",
    "follows": r"\succ", "followsequal": r"\succeq",
    "precedesequal": r"\preceq",
    "heart": r"\heartsuit", "spade": r"\spadesuit", "club": r"\clubsuit",
    "diamondsuit": r"\diamondsuit",
    "existential": r"\exists", "universal": r"\forall",
    "flat": r"\flat", "sharp": r"\sharp", "natural": r"\natural",
    "triangleleft": r"\triangleleft", "triangleright": r"\triangleright",
    "backslash": r"\backslash", "aleph": r"\aleph", "wreathproduct": r"\wr",
    "triangle": r"\triangle", "diamond": r"\diamond",
    "diamondmath": r"\diamond", "bullet": r"\bullet",
    "circlemultiply": r"\otimes", "circleplus": r"\oplus",
    "circledot": r"\odot", "dagger": r"\dagger",
    "arrowright": r"\rightarrow", "arrowleft": r"\leftarrow",
    "arrowup": r"\uparrow", "arrowdown": r"\downarrow",
    "arrowboth": r"\leftrightarrow", "arrowbothv": r"\updownarrow",
    "arrowdblright": r"\Rightarrow", "arrowdblleft": r"\Leftarrow",
    "arrowdblboth": r"\Leftrightarrow",
    "arrownortheast": r"\nearrow", "arrownorthwest": r"\nwarrow",
    "arrowsoutheast": r"\searrow", "arrowsouthwest": r"\swarrow",
    "turnstileright": r"\vdash",
    "Ifractur": r"\Im", "Rfractur": r"\Re",
    "angbracketleft": r"\langle", "angbracketright": r"\rangle",
    # 828 — the SAME GLYPH under Adobe's name. Computer Modern calls it
    # `angbracketleft`; Fourier, Utopia and every Type 1 that follows the
    # Adobe glyph list call it `angleleft`. Cahiers GUTenberg 51 is a paper
    # about XML and MathML, so ⟨tag⟩ notation is on nearly every page: 77 of
    # its 93 deferrals were these two names, and each one defers the whole
    # maths span it sits in.
    "angleleft": r"\langle", "angleright": r"\rangle",
    "braceleft": r"\{", "braceright": r"\}",
    "bracketleft": "[", "bracketright": "]",
    "floorright": r"\rfloor", "floorleft": r"\lfloor",
    "ceilingright": r"\rceil", "ceilingleft": r"\lceil",
    "mapsto": r"\mapsto", "arrowhookright": r"\hookrightarrow",
    "arrowhookleft": r"\hookleftarrow",
    "reflexsuperset": r"\supseteq", "section": r"\S",
    "dagger": r"\dagger", "daggerdbl": r"\ddagger",
    # accents, which apply to a following/covered argument
    "circumflex": r"\hat", "tilde": r"\tilde", "bar_accent": r"\bar",
    "caron": r"\check", "macron": r"\bar", "dieresis": r"\ddot",
    # Measured on the PDF2LaTeX dataset: `ring` alone was 30 of 448 crops,
    # mapped for a TEXT family and not for a maths one, though a maths font
    # supplies it just as readily.
    "ring": r"\mathring", "breve": r"\breve", "acute": r"\acute",
    "grave": r"\grave", "dotaccent": r"\dot",
}
_SYMBOL_ACCENTS = {"circumflex", "tilde", "caron", "macron", "dieresis",
                   "ring", "breve", "acute", "grave", "dotaccent"}

# 777 -- THE UNICODE SPELLING OF THE SAME ACCENT.
#
# A font that names its glyphs after Unicode calls a combining accent
# `<name>cmb` -- U+0302 COMBINING CIRCUMFLEX ACCENT is `circumflexcmb`.
# MnSymbol does, and page 31 of 2002.06055 sets the author's
# `\newcommand{\cotimes}{\widehat{\otimes}}` as `circlemultiply` with a
# `circumflexcmb` over it. Unmapped, the accent could not compose, the span
# carried an unaccounted glyph, and the whole line -- a numbered item in a
# list of monoidal categories -- came out as an IMAGE CROP:
#
#     $\bullet (\mathrm{Hilb},$ ![unmapped-glyph:circumflexcmb](…jpg)
#
# Every accent in the table above has this twin and none of them was
# listed, so the aliases are DERIVED rather than retyped: a tenth entry
# added above would otherwise need remembering here.
_MATH_SYMBOL.update({name + "cmb": _MATH_SYMBOL[name]
                     for name in _SYMBOL_ACCENTS if name in _MATH_SYMBOL})
_SYMBOL_ACCENTS |= {name + "cmb" for name in tuple(_SYMBOL_ACCENTS)}
# Occurs in the corpus but NOT verified against a font encoding table.
# `circlecopyrt` was refused as unverified. RENDERED at 600dpi from a journal
# front page it is unmistakable: the ring of a copyright sign, with a
# separate `c` from the TEXT font drawn INSIDE it --
#
#     circlecopyrt  CMSY7  x=[177.6, 185.6]
#     c             CMR7   x=[179.8, 183.4]
#
# so `\copyright` in Computer Modern is a composition of two glyphs, not one,
# and refusing the ring dropped the symbol entirely: `2025. (cid:2)c The
# Author(s)`.
_SYMBOL_UNVERIFIED: set = set()

# --- ams-symbol (MSAM / MSBM) ---------------------------------------------
# Ordinary punctuation and operators as a font names them. Needed because a
# fraktur or script font emits its own brackets: measured, `parenleft`,
# `parenright` and `equal` from EUFM10 were 984 of one paper's failures.
# Text-font glyphs a maths formula uses. `dotlessi` is not a typographic
# curiosity: `\hat{\imath}` is set as a CIRCUMFLEX over a DOTLESS I, two
# glyphs, and both were unmapped -- 64 and 27 of one paper's failures. The
# `ff` ligature is one glyph for two letters.
_TEXT_MATHS = {
    "dotlessi": r"\imath", "dotlessj": r"\jmath",
    "ff": "ff", "fi": "fi", "fl": "fl", "ffi": "ffi", "ffl": "ffl",
    "quoteright": "'", "quoteleft": "`", "emdash": "---", "endash": "--",
    "hyphen": "-", "germandbls": "ss",
}

_TEXT_PUNCT = {
    "parenleft": "(", "parenright": ")",
    "bracketleft": "[", "bracketright": "]",
    "braceleft": r"\{", "braceright": r"\}",
    "equal": "=", "plus": "+", "minus": "-", "slash": "/",
    "backslash": r"\backslash", "bar": r"\mid", "colon": ":",
    "semicolon": ";", "comma": ",", "period": ".", "exclam": "!",
    "question": "?", "at": "@", "percent": r"\%", "numbersign": r"\#",
    "dollar": r"\$", "ampersand": r"\&", "underscore": r"\_",
    "asterisk": "*", "less": "<", "greater": ">",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}

_AMS = {
    # MnSymbol's name for the prime, verified by rendering `f'` at 500dpi
    # from a 476-page paper where it failed 3239 times.
    "minute": r"\prime", "second": r"\prime\prime",
    "blackcircle": r"\bullet", "ratio": ":", "whitecircle": r"\circ",
    "notequal": r"\neq", "notelement": r"\notin",
    "harpoonupright": r"\upharpoonright", "harpoonupleft": r"\upharpoonleft",
    "harpoondownright": r"\downharpoonright",
    "harpoondownleft": r"\downharpoonleft",
    # 771 -- THE HORIZONTAL PAIR, and the font names it by its BARBS while
    # LaTeX names it by its arrowheads, so the two read backwards from each
    # other. Settled by rendering, not by the name: 1609.05293 page 11 sets
    # `Cost(Q^{left} <op> Q^{right})` from GDXIPD+MSAM10 cid 10, glyph
    # `harpoonleftright`, and at 12x the top bar carries a RIGHT arrowhead
    # over a bottom bar carrying a LEFT one. Right over left is
    # `\rightleftharpoons`. MathPix reads that document correctly; we
    # emitted `(cid:10)` and deferred the span.
    "harpoonleftright": r"\rightleftharpoons",
    "harpoonrightleft": r"\leftrightharpoons",
    "arrowparrrightleft": r"\rightleftarrows",
    "arrowparrleftright": r"\leftrightarrows",
    "whitediamond": r"\diamond", "blackdiamond": r"\blacklozenge",
    "whitesquare": r"\square", "blacktriangle": r"\blacktriangle",
    "whitetriangle": r"\triangle", "whitestar": r"\star",
    "third": r"\prime\prime\prime",
    # Found by a corpus pass over small crops: the commonest AMS glyph names
    # the table did not carry. `defines` was identified by RENDERING it at
    # 500dpi out of a real page -- it is a triangle over an equals sign,
    # `\triangleq` -- rather than inferred from the name.
    "defines": r"\triangleq",
    "lessorsimilar": r"\lesssim", "greaterorsimilar": r"\gtrsim",
    "lessorequalslant": r"\leqslant", "greaterorequalslant": r"\geqslant",
    "squaresolid": r"\blacksquare", "squareimage": r"\sqsubset",
    "squareoriginal": r"\sqsupset",
    "subsetsqequal": r"\sqsubseteq", "supersetsqequal": r"\sqsupseteq",
    "trianglesolid": r"\blacktriangle", "circlesolid": r"\bullet",
    "lessmuch": r"\lll", "greatermuch": r"\ggg",
    "curlyless": r"\prec", "curlygreater": r"\succ",
    "planckover2pi": r"\hbar", "planckover2pi1": r"\hbar",
    "square": r"\square", "angle": r"\angle",
    "emptyset": r"\varnothing", "approxequal": r"\approx",
    "circleasterisk": r"\circledast",
    # MSAM slanted order relations
    "lessorequalslant": r"\leqslant", "greaterorequalslant": r"\geqslant", "triangleleft": r"\vartriangleleft",
    "triangleright": r"\vartriangleright",
}
# `notbar` is NOT an overlay: measured with real width and a gap on both sides,
# so it is a standalone binary relation (very likely "does not divide"). Which
# relation exactly is not verified against the font's encoding, so it abstains.
_AMS_UNVERIFIED = {"anticlockwise", "epsiloninv", "triangleinv", "notbar",
                   "upslope", "downslope",
                   # MSAM corner marks: used for angle marks and end-of-proof
                   # boxes; which command they are is not verified.
                   "rightanglese", "rightanglesw", "rightanglene",
                   "rightanglenw"}

# --- math-extension (CMEX / BLEX) -----------------------------------------
# The large operators of cmex10 ("largesymbols"). Each exists in two sizes and
# the glyph name carries which: `circleplusdisplay` and `circleplustext` are
# both `\bigoplus`, set larger in display style. Keying on the BASE name and
# stripping the size suffix covers the whole family at once -- enumerating
# them one at a time is how `circleplusdisplay` came to be missing while
# `circlemultiplydisplay` was present.
#
# Cross-checked against fontmath.ltx, which declares them by slot:
#   \bigodot "4A   \bigoplus "4C   \bigotimes "4E
#   \sum "50  \prod "51  \intop "52  \bigcup "53  \bigcap "54
#   \biguplus "55  \bigwedge "56  \bigvee "57  \coprod "60
_BIGOP_BASE = {
    "summation": r"\sum",
    "product": r"\prod",
    "coproduct": r"\coprod",
    "integral": r"\int",
    "contintegral": r"\oint",
    "union": r"\bigcup",
    "intersection": r"\bigcap",
    "unionmulti": r"\biguplus",
    "unionsq": r"\bigsqcup",
    "logicaland": r"\bigwedge",
    "logicalor": r"\bigvee",
    "circleplus": r"\bigoplus",
    "circlemultiply": r"\bigotimes",
    "circledot": r"\bigodot",
}


def _bigop(name: str) -> tuple[str, str] | None:
    """(latex, style) for a large-operator glyph name, or None."""
    for suffix, style in (("display", "display"), ("text", "text")):
        if name.endswith(suffix):
            base = _BIGOP_BASE.get(name[: -len(suffix)])
            if base:
                return base, style
    return None
_DELIM_SHAPE = {
    "paren": ("(", ")"), "bracket": ("[", "]"),
    "floor": (r"\lfloor", r"\rfloor"), "ceiling": (r"\lceil", r"\rceil"),
    "brace": (r"\{", r"\}"), "angbracket": (r"\langle", r"\rangle"),
    "slash": ("/", "/"),
}
_SIZE_CMD = {"big": r"\big", "Big": r"\Big", "bigg": r"\bigg", "Bigg": r"\Bigg"}
# Pieces of a built-up delimiter: never a token on their own.
_FRAGMENT_SUFFIX = ("tp", "bt", "ex", "mid")
# cmex10 carries each wide accent in three sizes. Only the base `hatwide` was
# listed, so `hatwider` and `hatwidest` -- 10 occurrences in one book -- fell
# through as unknown and deferred whole spans.
_WIDE_ACCENT = {
    "tildewide": r"\widetilde", "tildewider": r"\widetilde",
    "tildewidest": r"\widetilde",
    "hatwide": r"\widehat", "hatwider": r"\widehat",
    "hatwidest": r"\widehat",
}


def _math_italic(name: str) -> TexToken:
    # The dotless letters live in the MATHS italic font, not the text one:
    # `\hat{\imath}` is a circumflex over CMMI's `dotlessi`. 85 failures on
    # one paper were these two glyphs.
    if name in _TEXT_MATHS:
        return TexToken(_TEXT_MATHS[name], "atom", None, "corpus")
    if len(name) == 1 and name.isalpha():
        return TexToken(name, "atom", None, "corpus")
    if name in _VARIANTS:
        return TexToken(_VARIANTS[name], "atom", None, "corpus")
    if name in _GREEK:
        cmd = "\\" + name
        return TexToken(cmd, "atom", None, "corpus")
    if name.lower() in _GREEK and name[0].isupper():
        return TexToken("\\" + name, "atom", None, "corpus")
    if name in _MATH_ITALIC:
        latex = _MATH_ITALIC[name]
        kind = "accent" if name == "vector" else "atom"
        return TexToken(latex, kind, None, "corpus")
    return UNKNOWN


# `negationslash` has ZERO ADVANCE WIDTH: its ink extends outside its box and
# lies over a neighbour, so the box says nothing about which symbol it negates.
# Measured on a Computer Modern number-theory book, it appears immediately
# after an `equal` in some places and immediately before one in others, so the
# attachment side is not decidable from geometry alone here. `\not` PRECEDES
# its symbol in LaTeX, so guessing wrong turns `\neq` into `=\not` -- valid
# LaTeX, different mathematics. It is therefore a kind of its own with NO
# latex: a span containing one defers until composition is implemented.
_OVERLAY = {"negationslash": None, "circlecopyrt": None}

# An overlay composed with what it ENCLOSES or CROSSES. The key is the
# overlay's glyph name and the inner glyph's text.
OVERLAY_PAIRS = {
    ("circlecopyrt", "c"): "©",
    ("circlecopyrt", "R"): "®",
    ("circlecopyrt", "a"): "@",
}


_VARIANT_SUFFIX = re.compile(r"\.(alt\d*|var\d*|sc|ss\d*|oldstyle|fitted)$")


def _math_symbol(name: str) -> TexToken:
    # A font names a second design of the same character with a suffix:
    # `parenright.alt1` beside `parenright`, `uni2032.var` beside `uni2032`.
    # The suffix is a DESIGN choice, not a different character, and 1464
    # brackets on one paper were refused for carrying one.
    name = _VARIANT_SUFFIX.sub("", name)
    if name in _SYMBOL_UNVERIFIED:
        return TexToken(None, "unknown", None, "unverified")
    if name in _OVERLAY:
        return TexToken(None, "overlay", None, "corpus")
    if len(name) == 1 and name.isalpha() and name.isupper():
        # In CMSY the Latin capitals ARE the calligraphic alphabet.
        return TexToken(rf"\mathcal{{{name}}}", "atom", None, "corpus")
    if name in _SYMBOL_ACCENTS:
        return TexToken(_MATH_SYMBOL[name], "accent", None, "corpus")
    if name in _MATH_SYMBOL:
        return TexToken(_MATH_SYMBOL[name], "atom", None, "corpus")
    # A vendor's symbol font carries AMS names too: MathTime's MTSYN holds
    # `subsetsqequal` and `macron` alongside the CMSY set, and refusing them
    # here sent a symbol the table already knows to a crop.
    if name in _AMS:
        return TexToken(_AMS[name], "atom", None, "corpus")
    # A maths font supplies its own BRACKETS and operators: measured, 12333
    # parentheses from MnSymbol10 on one paper, refused by a reader that had
    # them in the plain table.
    if name in _TEXT_PUNCT:
        return TexToken(_TEXT_PUNCT[name], "atom", None, "corpus")
    return UNKNOWN


_TEXT_ACCENT = {
    "circumflex": r"\hat", "caron": r"\check", "tilde": r"\tilde",
    "acute": r"\acute", "grave": r"\grave", "breve": r"\breve",
    "dieresis": r"\ddot", "dotaccent": r"\dot", "ring": r"\mathring",
    "macron": r"\bar",
}


#: Every glyph of a doublestroke font is the double-struck form of one
#: ordinary character, so the projection is the character plus `\mathds`.
#: The digits are named, the letters are not.
_DOUBLESTROKE_CHAR = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


#: Computer Modern BOLD EXTENDED, the font `\bf` selects. `CMB10` is the
#: unextended bold roman; both are used the same way.
_BOLD_CM = re.compile(r"CM(BX|B)\d*$", re.I)


def _bold_math_glyph(name: str, fontname: str | None) -> "TexToken | None":
    r"""A letter of the BOLD TEXT FONT, used as a maths symbol.

    747 -- a document that writes its vectors and matrices `\bf{t}`, `\bf{F}`,
    `\bf{\Sigma}` sets them from CMBX, which classifies as `text-cm`; and a
    plain letter from a text font has no maths projection, so it came back
    UNKNOWN and took its whole span with it. Measured over the corpus: 582
    such glyphs inside MATH spans, in 12 documents -- `F` 116 times, `n` 79,
    `t` 54, `Sigma` 43.

    wzlxjtu-074 is the clear case. Four of its six equations were lost to
    `\hat{\bf{F}}_n`, and the reason reported was `unmapped-glyph`, not the
    accent: the accent composes, the bold `F` under it does not exist.

    Safe to decide here without knowing the span: prose is emitted from the
    glyph's TEXT (`_run_text`), never from this token, which only a maths
    span reads.

    `\mathbf` and not `\boldsymbol`: it is what the author wrote (`\bf`), it
    needs no package, and it sets uppercase Greek correctly -- checked by
    compiling `$\mathbf{\Sigma}$`, which is clean.
    """
    if not name or not fontname:
        return None
    if not _BOLD_CM.match(_CM_SUBSET.sub("", fontname)):
        return None
    if len(name) == 1 and (name.isalpha() or name.isdigit()):
        return TexToken(rf"\mathbf{{{name}}}", "atom", None, "corpus")
    if name in _UPPER_GREEK:
        up = "\\" + name
        # only the CAPITALS: those are the Greek a roman font carries, and
        # `\mathbf` over a lowercase Greek would be asking the operators
        # font for a letter it does not have.
        return TexToken(rf"\mathbf{{{up}}}", "atom", None, "corpus")
    return None


def _text_glyph(name: str) -> TexToken:
    """A text font's contribution to a formula.

    A text face supplies the ACCENT and the dotless letter that a composed
    maths accent is built from, and its ligatures stand for two letters.
    """
    if name in _TEXT_ACCENT:
        return TexToken(_TEXT_ACCENT[name], "accent", None, "corpus")
    if name in _TEXT_MATHS:
        return TexToken(_TEXT_MATHS[name], "atom", None, "corpus")
    if name in _TEXT_PUNCT:
        return TexToken(_TEXT_PUNCT[name], "atom", None, "corpus")
    return UNKNOWN


def _math_extension(name: str) -> TexToken:
    big = _bigop(name)
    if big:
        return TexToken(big[0], "bigop", None, "corpus")
    if name in _WIDE_ACCENT:
        return TexToken(_WIDE_ACCENT[name], "accent", None, "corpus")
    if name.startswith("radical"):
        # The radical SIGN only. Its vinculum is a rule, so the extent of the
        # argument is not knowable from this glyph.
        return TexToken(r"\sqrt", "rule", None, "corpus")
    if name in ("vextendsingle", "vextenddouble", "arrowvertex",
                "arrowbt", "arrowtp"):
        # pieces of a built-up extensible arrow or bar: one LaTeX token is
        # spread over several glyphs, so none of them projects alone
        return TexToken(None, "fragment", None, "corpus")
    if name.startswith("bracehtip"):
        return TexToken(None, "fragment", None, "corpus")
    for shape, (opener, closer) in _DELIM_SHAPE.items():
        if not name.startswith(shape):
            continue
        rest = name[len(shape):]
        for side, glyph in (("left", opener), ("right", closer)):
            if not rest.startswith(side):
                # `braceex` and `slashbig` carry no side
                continue
            suffix = rest[len(side):]
            if suffix in _FRAGMENT_SUFFIX:
                return TexToken(None, "fragment", None, "corpus")
            if suffix in _SIZE_CMD:
                cmd = _SIZE_CMD[suffix] + ("l" if side == "left" else "r")
                return TexToken(cmd + glyph, "delimiter", None, "corpus")
        # A sided-less delimiter such as `slashbig`: `/` is an ordinary
        # symbol, not a fence, so it takes the plain size command with no
        # l/r variant. `\bigl/` would be a syntax error.
        if rest in _SIZE_CMD:
            return TexToken(_SIZE_CMD[rest] + opener, "delimiter", None, "corpus")
        if rest in _FRAGMENT_SUFFIX or rest == "ex":
            return TexToken(None, "fragment", None, "corpus")
    return UNKNOWN


# --- mathabx (matha / mathb / mathx), by CID ---------------------------------
#
# `\\usepackage{mathabx}` REPLACES many standard maths symbols with its own
# fonts, and those fonts reach the reader with no usable glyph names -- the
# name pdfminer reports is a Latin fallback (`matha` slot 0xA5 comes back as
# `ecaron`, the glyph is `\\geq`). Two documents in the corpus load it, and
# they are the two whose mathematics was unreadable: wzlxjtu-001 and -002,
# identical AAAI templates.
#
# TAKEN FROM THE PACKAGE, not inferred. `mathabx.dcl` declares every symbol
# with its font and slot -- `\\DeclareMathSymbol`, `\\DeclareMathDelimiter`,
# `\\DeclareMathAccent`, `\\DeclareMathRadical` -- and this is that file read
# out: 573 (font, slot) -> name pairs. Checked against the corpus: slot 0xA4
# is `leq` and 0xA5 is `geq`, which is what the surrounding formula
# (`\\ell(\\theta_i^*) - l(\\theta^*) \\ge c(1)`) says those glyphs are.
#
# It does NOT cover everything: matha slots 112 and 113 appear 73 times each
# and `mathabx.dcl` declares neither, so 229 of the 402 mathabx glyphs in
# those two documents are still nameless.
MATHABX = {
    "matha": {2: 'times', 3: 'div', 4: 'cdotp', 5: 'circ', 6: 'ast', 7: 'coasterisk', 8: 'pm', 9: 'mp', 10: 'ltimes', 11: 'rtimes', 12: 'diamond', 13: 'bullet', 14: 'star', 15: 'varstar', 17: 'equiv', 18: 'sim', 19: 'approx', 20: 'simeq', 21: 'cong', 22: 'asymp', 23: 'divides', 24: 'neq', 25: 'notequiv', 26: 'nsim', 27: 'napprox', 28: 'nsimeq', 29: 'ncong', 30: 'notasymp', 31: 'notdivides', 32: 'neg', 33: 'll', 34: 'gg', 35: 'hash', 36: 'vdash', 37: 'dashv', 38: 'nvdash', 39: 'ndashv', 40: 'vDash', 41: 'Dashv', 42: 'nvDash', 43: 'nDashv', 44: 'Vdash', 45: 'dashV', 46: 'nVdash', 47: 'ndashV', 48: 'degree', 49: 'prime', 50: 'second', 51: 'third', 52: 'fourth', 53: 'flat', 54: 'natural', 55: 'sharp', 56: 'infty', 57: 'propto', 58: 'dagger', 59: 'ddagger', 60: 'ssum', 61: 'sprod', 62: 'amalg', 63: 'sqrt', 64: 'forall', 65: 'complement', 66: 'partial', 67: 'partialslash', 68: 'exists', 69: 'nexists', 70: 'Finv', 71: 'Game', 72: 'emptyset', 73: 'diameter', 74: 'top', 75: 'bot', 76: 'nottop', 77: 'notbot', 78: 'curlywedge', 79: 'curlyvee', 80: 'in', 81: 'owns', 82: 'notin', 83: 'notowner', 84: 'varnotin', 85: 'varnotowner', 86: 'barin', 87: 'ownsbar', 88: 'cap', 89: 'cup', 90: 'uplus', 91: 'sqcap', 92: 'sqcup', 93: 'squplus', 94: 'wedge', 95: 'vee', 96: 'oplus', 97: 'ominus', 98: 'otimes', 99: 'odiv', 100: 'odot', 101: 'ocirc', 102: 'oasterisk', 103: 'ocoasterisk', 104: 'oleft', 105: 'oright', 106: 'otop', 107: 'obot', 108: 'ovoid', 109: 'oslash', 110: 'obackslash', 111: 'otriangleup', 116: 'lbrace', 117: 'rbrace', 118: 'ldbrack', 119: 'rdbrack', 120: 'langle', 121: 'rangle', 122: 'backslash', 124: 'mid', 125: 'Vert', 126: 'vvvert', 127: 'notsign', 128: 'subset', 129: 'supset', 130: 'nsubset', 131: 'nsupset', 132: 'subseteq', 133: 'supseteq', 134: 'nsubseteq', 135: 'nsupseteq', 136: 'subsetneq', 137: 'supsetneq', 138: 'varsubsetneq', 139: 'varsupsetneq', 140: 'subseteqq', 141: 'supseteqq', 142: 'nsubseteqq', 143: 'nsupseteqq', 144: 'subsetneqq', 145: 'supsetneqq', 146: 'varsubsetneqq', 147: 'varsupsetneqq', 148: 'Subset', 149: 'Supset', 150: 'nSubset', 151: 'nSupset', 152: 'triangleleft', 153: 'triangleright', 154: 'ntriangleleft', 155: 'ntriangleright', 156: 'trianglelefteq', 157: 'trianglerighteq', 158: 'ntrianglelefteq', 159: 'ntrianglerighteq', 162: 'nless', 163: 'ngtr', 164: 'leq', 165: 'geq', 166: 'nleq', 167: 'ngeq', 168: 'varleq', 169: 'vargeq', 170: 'nvarleq', 171: 'nvargeq', 172: 'lneq', 173: 'gneq', 174: 'leqq', 175: 'geqq', 176: 'nleqq', 177: 'ngeqq', 178: 'lneqq', 179: 'gneqq', 180: 'lvertneqq', 181: 'gvertneqq', 182: 'eqslantless', 183: 'eqslantgtr', 184: 'neqslantless', 185: 'neqslantgtr', 186: 'lessgtr', 187: 'gtrless', 188: 'lesseqgtr', 189: 'gtreqless', 190: 'lesseqqgtr', 191: 'gtreqqless', 192: 'lesssim', 193: 'gtrsim', 194: 'nlesssim', 195: 'ngtrsim', 196: 'lnsim', 197: 'gnsim', 198: 'lessapprox', 199: 'gtrapprox', 200: 'nlessapprox', 201: 'ngtrapprox', 202: 'lnapprox', 203: 'gnapprox', 204: 'lessdot', 205: 'gtrdot', 206: 'lll', 207: 'ggg', 208: 'leftarrow', 209: 'rightarrow', 210: 'uparrow', 211: 'downarrow', 212: 'nwarrow', 213: 'nearrow', 214: 'swarrow', 215: 'searrow', 216: 'leftrightarrow', 217: 'updownarrow', 218: 'nleftarrow', 219: 'nrightarrow', 220: 'nleftrightarrow', 221: 'relbar', 222: 'mapstochar', 223: 'mapsfromchar', 224: 'leftharpoonup', 225: 'rightharpoonup', 226: 'leftharpoondown', 227: 'rightharpoondown', 228: 'upharpoonleft', 229: 'downharpoonleft', 230: 'upharpoonright', 231: 'downharpoonright', 232: 'leftrightharpoons', 233: 'rightleftharpoons', 234: 'updownharpoons', 235: 'downupharpoons', 240: 'Leftarrow', 241: 'Rightarrow', 242: 'Uparrow', 243: 'Downarrow', 244: 'Leftrightarrow', 245: 'Updownarrow', 246: 'nLeftarrow', 247: 'nRightarrow', 248: 'nLeftrightarrow', 249: 'Relbar', 250: 'Mapstochar', 251: 'Mapsfromchar'},
    "mathb": {0: 'dotplus', 1: 'dotdiv', 2: 'dottimes', 3: 'divdot', 4: 'udot', 5: 'square', 6: 'Asterisk', 7: 'coAsterisk', 8: 'circplus', 9: 'pluscirc', 10: 'convolution', 11: 'divideontimes', 12: 'blackdiamond', 13: 'sqbullet', 14: 'bigstar', 15: 'bigvarstar', 16: 'topdoteq', 17: 'botdoteq', 18: 'dotseq', 19: 'risingdotseq', 20: 'fallingdotseq', 21: 'coloneq', 22: 'eqcolon', 23: 'bumpedeq', 24: 'eqbumped', 25: 'Bumpedeq', 26: 'circeq', 27: 'eqcirc', 28: 'triangleq', 29: 'corresponds', 32: 'between', 33: 'smile', 34: 'frown', 35: 'varhash', 36: 'leftthreetimes', 37: 'rightthreetimes', 38: 'pitchfork', 39: 'bowtie', 40: 'VDash', 41: 'DashV', 42: 'nVDash', 43: 'nDashV', 44: 'Vvdash', 45: 'dashVv', 46: 'nVvash', 47: 'ndashVv', 54: 'therefore', 55: 'because', 56: 'ring', 57: 'dot', 58: 'ddot', 59: 'dddot', 60: 'ddddot', 61: 'angle', 62: 'measuredangle', 63: 'sphericalangle', 64: 'Sun', 65: 'Mercury', 66: 'Venus', 67: 'Earth', 68: 'Mars', 69: 'Jupiter', 70: 'Saturn', 71: 'Uranus', 72: 'Neptune', 73: 'Pluto', 74: 'varEarth', 75: 'leftmoon', 76: 'rightmoon', 77: 'fullmoon', 78: 'newmoon', 79: 'rip', 80: 'Aries', 81: 'Taurus', 82: 'Gemini', 83: 'Cancer', 84: 'Leo', 85: 'Virgo', 86: 'Libra', 87: 'Scorpio', 88: 'Sagittarius', 89: 'Capricornus', 90: 'doublebarwedge', 91: 'veedoublebar', 92: 'doublecap', 93: 'doublecup', 94: 'sqdoublecap', 95: 'sqdoublecup', 96: 'boxplus', 97: 'boxminus', 98: 'boxtimes', 99: 'boxdiv', 100: 'boxdot', 101: 'boxcirc', 102: 'boxasterisk', 103: 'boxcoasterisk', 104: 'boxleft', 105: 'boxright', 106: 'boxtop', 107: 'boxbot', 108: 'boxvoid', 109: 'boxslash', 110: 'boxbackslash', 111: 'boxtriangleup', 112: 'lgroup', 113: 'rgroup', 114: 'lceil', 115: 'rceil', 116: 'lfloor', 117: 'rfloor', 118: 'lcorners', 119: 'rcorners', 120: 'ulcorner', 121: 'urcorner', 122: 'llcorner', 123: 'lrcorner', 126: 'thickvert', 127: 'varnotsign', 128: 'sqsubset', 129: 'sqsupset', 130: 'nsqsubset', 131: 'nsqsupset', 132: 'sqsubseteq', 133: 'sqsupseteq', 134: 'nsqsubseteq', 135: 'nsqsupseteq', 136: 'sqsubsetneq', 137: 'sqsupsetneq', 138: 'varsqsubsetneq', 139: 'varsqsupsetneq', 140: 'sqsubseteqq', 141: 'sqsupseteqq', 142: 'nsqsubseteqq', 143: 'nsqsupseteqq', 144: 'sqsubsetneqq', 145: 'sqsupsetneqq', 146: 'varsqsubsetneqq', 147: 'varsqsupsetneqq', 148: 'sqSubset', 149: 'sqSupset', 150: 'nsqSubset', 151: 'nsqSupset', 152: 'smalltriangleup', 153: 'smalltriangledown', 154: 'smalltriangleleft', 155: 'smalltriangleright', 156: 'blacktriangleup', 157: 'blacktriangledown', 158: 'blacktriangleleft', 159: 'blacktriangleright', 160: 'prec', 161: 'succ', 162: 'nprec', 163: 'nsucc', 164: 'preccurlyeq', 165: 'succcurlyeq', 166: 'npreccurlyeq', 167: 'nsucccurlyeq', 168: 'preceq', 169: 'succeq', 170: 'npreceq', 171: 'nsucceq', 172: 'precneq', 173: 'succneq', 174: 'preceqq', 175: 'succeqq', 176: 'notpreceqq', 177: 'notsucceqq', 178: 'precneqq', 179: 'succneqq', 180: 'precvertneqq', 181: 'succvertneqq', 182: 'curlyeqprec', 183: 'curlyeqsucc', 184: 'ncurlyeqprec', 185: 'ncurlyeqsucc', 192: 'precsim', 193: 'succsim', 194: 'nprecsim', 195: 'nsuccsim', 196: 'precnsim', 197: 'succnsim', 198: 'precapprox', 199: 'succapprox', 200: 'nprecapprox', 201: 'nsuccapprox', 202: 'precnapprox', 203: 'succnapprox', 206: 'llcurly', 207: 'ggcurly', 208: 'leftleftarrows', 209: 'rightrightarrows', 210: 'upuparrows', 211: 'downdownarrows', 212: 'leftrightarrows', 213: 'rightleftarrows', 214: 'updownarrows', 215: 'downuparrows', 216: 'leftleftharpoons', 217: 'rightrightharpoons', 218: 'upupharpoons', 219: 'downdownharpoons', 220: 'leftbarharpoon', 221: 'rightbarharpoon', 222: 'barleftharpoon', 223: 'barrightharpoon', 224: 'leftrightharpoon', 225: 'rightleftharpoon', 226: 'rhook', 227: 'lhook', 228: 'diagup', 229: 'diagdown', 232: 'Lsh', 233: 'Rsh', 234: 'dlsh', 235: 'drsh', 236: 'looparrowleft', 237: 'looparrowright', 238: 'looparrowdownleft', 239: 'looparrowdownright', 240: 'curvearrowleft', 241: 'curvearrowright', 242: 'curvearrowleftright', 243: 'curvearrowbotleft', 244: 'curvearrowbotright', 245: 'curvearrowbotleftright', 246: 'circlearrowleft', 247: 'circlearrowright', 248: 'leftsquigarrow', 249: 'rightsquigarrow', 250: 'leftrightsquigarrow', 252: 'lefttorightarrow', 253: 'righttoleftarrow', 254: 'uptodownarrow', 255: 'downtouparrow'},
    "mathx": {5: 'lmoustache', 7: 'vert', 13: 'rmoustache', 15: 'Vert', 23: 'vvvert', 31: 'thickvert', 32: 'lbrace', 40: 'rbrace', 48: 'ldbrack', 55: 'lfilet', 56: 'rdbrack', 63: 'rfilet', 64: 'smallsum', 65: 'smallprod', 66: 'smallcoprod', 67: 'complement', 68: 'boldcomplement', 69: 'boldcup', 70: 'boldcap', 71: 'boldZ', 72: 'backslash', 74: 'bigboldZ', 80: 'lceil', 84: 'rceil', 88: 'lfloor', 92: 'rfloor', 96: 'sqrt', 97: 'sqrt', 104: 'braceld', 105: 'bracemd', 106: 'bracerd', 107: 'bracexd', 108: 'bracelu', 109: 'bracemu', 110: 'braceru', 111: 'bracexu', 112: 'widehat', 113: 'widecheck', 114: 'widetilde', 115: 'widebar', 116: 'widearrow', 117: 'wideparen', 118: 'lgroup', 119: 'rgroup', 144: 'bigplus', 145: 'bigtimes', 146: 'bigcomplementop', 147: 'bigtruc', 148: 'bigcurt', 149: 'biguplus', 150: 'bigsqcap', 151: 'bigsqcup', 152: 'bigsquplus', 153: 'bigwedge', 154: 'bigvee', 155: 'bigcurlywedge', 156: 'bigcurlyvee', 157: 'uparrow', 158: 'downarrow', 159: 'updownarrow', 173: 'Uparrow', 174: 'Downarrow', 175: 'Updownarrow', 176: 'sum', 177: 'prod', 178: 'coprod', 179: 'intop', 180: 'iintop', 181: 'iiintop', 182: 'ointop', 183: 'oiintop', 192: 'bigoplus', 193: 'bigominus', 194: 'bigotimes', 195: 'bigodiv', 196: 'bigodot', 197: 'bigocirc', 198: 'bigoasterisk', 199: 'bigocoasterisk', 200: 'bigoleft', 201: 'bigoright', 202: 'bigotop', 203: 'bigobot', 204: 'bigovoid', 205: 'bigoslash', 206: 'bigobackslash', 207: 'bigotriangleup', 208: 'bigboxplus', 209: 'bigboxminus', 210: 'bigboxtimes', 211: 'bigboxdiv', 212: 'bigboxdot', 213: 'bigboxcirc', 214: 'bigboxasterisk', 215: 'bigboxcoasterisk', 216: 'bigboxleft', 217: 'bigboxright', 218: 'bigboxtop', 219: 'bigboxbot', 220: 'bigboxvoid', 221: 'bigboxslash', 222: 'bigboxbackslash', 223: 'bigboxtriangleup'},
}

_MATHABX_FONT = re.compile(r"^(?:[A-Z]{6}\+)?TeX-(math[abx])\d+$")


def mathabx_name(fontname: str | None, cid: int) -> str | None:
    """The mathabx symbol name for a CID, from the package's own tables."""
    if not fontname or cid < 0:
        return None
    m = _MATHABX_FONT.match(fontname)
    return MATHABX.get(m.group(1), {}).get(cid) if m else None


# --- Computer Modern encodings, by CID ------------------------------------
#
# A subsetted CM font sometimes reaches the reader with NO glyph names at all.
# The identity is still there -- the CID -- because the CM encodings (OT1,
# OML, OMS, OMX) are fixed: CMSY slot 48 is `prime` in every CMSY ever cut.
#
# WHY THIS IS NEEDED, and it is not hypothetical. pdf2mmd's own output
# re-rendered through MathPix and read back gives, for a page it reads
# perfectly in the original:
#
#     CMSY10 cid=0  name=None text='-'   CMMI10 cid=64  name=None text='d'
#     CMSY10 cid=48 name=None text="'"   CMEX10 cid=113 name=None text='q'
#
# -- 24 of 36 maths spans deferred as `unmapped-glyph`, on `\partial`,
# `\prime`, `-` and `\radicalBig`. The FONT is classified correctly; only the
# name is missing.
#
# BUILT FROM THE CORPUS, not from memory. Every (family, cid) pair the 102
# documents resolve by name was collected -- 391 pairs across 8 families --
# and checked for disagreement: ZERO pairs carry two names. The encodings are
# what they are said to be, and this is that evidence written down.
CM_ENCODING = {
    "CMBX": {1: 'Delta', 6: 'Sigma', 8: 'Phi', 11: 'ff', 12: 'fi', 40: 'parenleft', 41: 'parenright', 44: 'comma', 45: 'hyphen', 46: 'period', 48: 'zero', 49: 'one', 50: 'two', 51: 'three', 52: 'four', 53: 'five', 55: 'seven', 56: 'eight', 58: 'colon', 63: 'question', 65: 'A', 66: 'B', 67: 'C', 68: 'D', 69: 'E', 70: 'F', 71: 'G', 72: 'H', 73: 'I', 75: 'K', 76: 'L', 77: 'M', 78: 'N', 79: 'O', 80: 'P', 81: 'Q', 82: 'R', 83: 'S', 84: 'T', 85: 'U', 86: 'V', 88: 'X', 89: 'Y', 90: 'Z', 94: 'circumflex', 97: 'a', 98: 'b', 99: 'c', 100: 'd', 101: 'e', 102: 'f', 103: 'g', 104: 'h', 105: 'i', 106: 'j', 107: 'k', 108: 'l', 109: 'm', 110: 'n', 111: 'o', 112: 'p', 113: 'q', 114: 'r', 115: 's', 116: 't', 117: 'u', 118: 'v', 119: 'w', 120: 'x', 121: 'y', 122: 'z'},
    "CMEX": {0: 'parenleftbig', 1: 'parenrightbig', 2: 'bracketleftbig', 3: 'bracketrightbig', 8: 'braceleftbig', 9: 'bracerightbig', 12: 'vextendsingle', 16: 'parenleftBig', 17: 'parenrightBig', 18: 'parenleftbigg', 19: 'parenrightbigg', 20: 'bracketleftbigg', 21: 'bracketrightbigg', 26: 'braceleftbigg', 32: 'parenleftBigg', 33: 'parenrightBigg', 34: 'bracketleftBigg', 35: 'bracketrightBigg', 48: 'parenlefttp', 49: 'parenrighttp', 50: 'bracketlefttp', 51: 'bracketrighttp', 52: 'bracketleftbt', 53: 'bracketrightbt', 54: 'bracketleftex', 55: 'bracketrightex', 64: 'parenleftbt', 65: 'parenrightbt', 73: 'contintegraldisplay', 80: 'summationtext', 81: 'producttext', 88: 'summationdisplay', 89: 'productdisplay', 90: 'integraldisplay', 101: 'tildewide', 104: 'bracketleftBig', 105: 'bracketrightBig', 112: 'radicalbig', 113: 'radicalBig', 114: 'radicalbigg', 115: 'radicalBigg', 122: 'bracehtipdownleft', 123: 'bracehtipdownright', 124: 'bracehtipupleft', 125: 'bracehtipupright'},
    "CMMI": {11: 'alpha', 12: 'beta', 13: 'gamma', 14: 'delta', 15: 'epsilon1', 16: 'zeta', 17: 'eta', 18: 'theta', 21: 'lambda', 22: 'mu', 23: 'nu', 24: 'xi', 25: 'pi', 26: 'rho', 27: 'sigma', 28: 'tau', 30: 'phi', 31: 'chi', 32: 'psi', 33: 'omega', 34: 'epsilon', 39: 'phi1', 58: 'period', 59: 'comma', 60: 'less', 61: 'slash', 62: 'greater', 63: 'star', 64: 'partialdiff', 65: 'A', 66: 'B', 67: 'C', 68: 'D', 69: 'E', 70: 'F', 71: 'G', 72: 'H', 73: 'I', 74: 'J', 75: 'K', 76: 'L', 77: 'M', 78: 'N', 79: 'O', 80: 'P', 81: 'Q', 82: 'R', 83: 'S', 84: 'T', 85: 'U', 86: 'V', 87: 'W', 88: 'X', 89: 'Y', 90: 'Z', 96: 'lscript', 97: 'a', 98: 'b', 99: 'c', 100: 'd', 101: 'e', 102: 'f', 103: 'g', 104: 'h', 105: 'i', 106: 'j', 107: 'k', 108: 'l', 109: 'm', 110: 'n', 111: 'o', 112: 'p', 113: 'q', 114: 'r', 115: 's', 116: 't', 117: 'u', 118: 'v', 119: 'w', 120: 'x', 121: 'y', 122: 'z'},
    "CMR": {0: 'Gamma', 1: 'Delta', 2: 'Theta', 3: 'Lambda', 5: 'Pi', 6: 'Sigma', 8: 'Phi', 10: 'Omega', 11: 'ff', 12: 'fi', 13: 'fl', 14: 'ffi', 19: 'acute', 22: 'macron', 33: 'exclam', 34: 'quotedblright', 35: 'numbersign', 39: 'quoteright', 40: 'parenleft', 41: 'parenright', 43: 'plus', 44: 'comma', 45: 'hyphen', 46: 'period', 47: 'slash', 48: 'zero', 49: 'one', 50: 'two', 51: 'three', 52: 'four', 53: 'five', 54: 'six', 55: 'seven', 56: 'eight', 57: 'nine', 58: 'colon', 59: 'semicolon', 61: 'equal', 65: 'A', 66: 'B', 67: 'C', 68: 'D', 69: 'E', 70: 'F', 71: 'G', 72: 'H', 73: 'I', 74: 'J', 75: 'K', 76: 'L', 77: 'M', 78: 'N', 79: 'O', 80: 'P', 81: 'Q', 82: 'R', 83: 'S', 84: 'T', 85: 'U', 86: 'V', 87: 'W', 89: 'Y', 90: 'Z', 91: 'bracketleft', 92: 'quotedblleft', 93: 'bracketright', 94: 'circumflex', 96: 'quoteleft', 97: 'a', 98: 'b', 99: 'c', 100: 'd', 101: 'e', 102: 'f', 103: 'g', 104: 'h', 105: 'i', 106: 'j', 107: 'k', 108: 'l', 109: 'm', 110: 'n', 111: 'o', 112: 'p', 113: 'q', 114: 'r', 115: 's', 116: 't', 117: 'u', 118: 'v', 119: 'w', 120: 'x', 121: 'y', 122: 'z', 123: 'endash', 126: 'tilde'},
    "CMSY": {0: 'minus', 1: 'periodcentered', 2: 'multiply', 3: 'asteriskmath', 6: 'plusminus', 7: 'minusplus', 8: 'circleplus', 10: 'circlemultiply', 12: 'circledot', 14: 'openbullet', 15: 'bullet', 17: 'equivalence', 18: 'reflexsubset', 20: 'lessequal', 21: 'greaterequal', 24: 'similar', 25: 'approxequal', 28: 'lessmuch', 33: 'arrowright', 36: 'arrowboth', 39: 'similarequal', 41: 'arrowdblright', 47: 'proportional', 48: 'prime', 49: 'infinity', 50: 'element', 54: 'negationslash', 56: 'universal', 62: 'latticetop', 67: 'C', 68: 'D', 69: 'E', 70: 'F', 72: 'H', 75: 'K', 76: 'L', 77: 'M', 78: 'N', 79: 'O', 80: 'P', 83: 'S', 87: 'W', 88: 'X', 90: 'Z', 91: 'union', 94: 'logicaland', 98: 'floorleft', 99: 'floorright', 102: 'braceleft', 103: 'braceright', 104: 'angbracketleft', 105: 'angbracketright', 106: 'bar', 107: 'bardbl', 110: 'backslash', 112: 'radical', 114: 'nabla', 121: 'dagger'},
    "CMTI": {12: 'fi', 44: 'comma', 45: 'hyphen', 46: 'period', 48: 'zero', 49: 'one', 65: 'A', 66: 'B', 69: 'E', 76: 'L', 80: 'P', 83: 'S', 84: 'T', 97: 'a', 98: 'b', 99: 'c', 100: 'd', 101: 'e', 102: 'f', 103: 'g', 104: 'h', 105: 'i', 106: 'j', 108: 'l', 109: 'm', 110: 'n', 111: 'o', 112: 'p', 114: 'r', 115: 's', 116: 't', 117: 'u', 119: 'w', 120: 'x', 121: 'y'},
    "CMTT": {101: 'e', 113: 'q', 116: 't'},
    "MSAM": {3: 'square'},
}


def cm_glyphname(fontname: str | None, cid: int) -> str | None:
    """The CM glyph name for a CID, when the font declared none."""
    if not fontname or cid < 0:
        return None
    base = _CM_BASE.sub("", _CM_SUBSET.sub("", fontname))
    return CM_ENCODING.get(base, {}).get(cid)


def project(family: str, glyphname: str | None,
            cid: int = -1, fontname: str | None = None) -> TexToken:
    """Map one glyph identity to a LaTeX token.

    Returns UNKNOWN rather than a guess whenever the identity is not stated,
    not in the table, or not verified. A caller must treat `latex is None` as
    "keep the blob" — never as "emit nothing and move on".
    """
    _sym = symbol_pua_latex(glyphname, fontname)
    if _sym is not None:
        return TexToken(_sym, "atom", None, "symbol-font")
    if glyphname and codepoint_of(glyphname) is not None:
        # 786 — THE FONT STATED THE CODEPOINT. `uni1D6FC` / `u1D719` is an
        # identity, not a guess, so it is answered before the per-family
        # tables (which are keyed by PostScript names and never hold these).
        # Checked first because a family table that happens to contain the
        # literal string would be answering a different question.
        _u = unicode_latex(glyphname)
        if _u is not None:
            return TexToken(_u, "atom", None, "unicode")
    if not glyphname:
        # One identity survives a missing glyph name: MSBM10's blackboard
        # capitals, which are keyed by CID. Everything else abstains, as
        # before -- a nameless glyph is not an identity.
        name = mathabx_name(fontname, cid)
        if name:
            return TexToken("\\" + name, "atom", "mathabx", "corpus")
        if family == "ams-symbol" and 65 <= cid <= 90:
            return TexToken(rf"\mathbb{{{chr(cid)}}}", "atom", "amssymb",
                            "corpus")
        return UNKNOWN
    if family == "math-italic":
        return _math_italic(glyphname)
    if family == "math-symbol":
        return _math_symbol(glyphname)
    if family == "math-extension":
        return _math_extension(glyphname)
    if family == "doublestroke":
        ch = _DOUBLESTROKE_CHAR.get(glyphname)
        if ch is None and len(glyphname) == 1 and glyphname.isalnum():
            ch = glyphname
        if ch:
            return TexToken(rf"\mathds{{{ch}}}", "atom", "dsfont", "corpus")
        return UNKNOWN
    if family in ("text", "text-cm"):
        bold = _bold_math_glyph(glyphname, fontname)
        if bold is not None:
            return bold
        return _text_glyph(glyphname)
    if family == "ams-symbol" and glyphname:
        # A wide accent is an accent whatever font it was found in: some
        # documents ship `hatwide` in a family this classifier reads as AMS.
        if glyphname in _WIDE_ACCENT:
            return TexToken(_WIDE_ACCENT[glyphname], "accent", None, "corpus")
        if glyphname in _AMS_UNVERIFIED:
            return TexToken(None, "unknown", None, "unverified")
        if glyphname in _AMS:
            return TexToken(_AMS[glyphname], "atom", "amssymb", "corpus")
        if len(glyphname) == 1 and glyphname.isupper():
            return TexToken(rf"\mathbb{{{glyphname}}}", "atom", "amssymb", "corpus")
        return UNKNOWN
    if family == "ams-symbol" and 65 <= cid <= 90:
        # MSBM10 CARRIES NO GLYPH NAMES AT ALL. Its `Encoding` is absent and
        # the fork resolves nothing from the font program, so every glyph
        # arrives with `glyphname=None` and the branch above cannot fire --
        # `\mathbb{H}` deferred as an unmapped glyph, taking its whole span
        # with it, five times in wzlxjtu-008 alone.
        #
        # The CID still says which letter it is: msbm10 sets the blackboard
        # capitals at the ASCII uppercase slots. Checked over the corpus
        # before relying on it -- 100 MSBM glyphs, every one with a cid in
        # 65..90 and text exactly chr(cid), and not one with a glyph name.
        return TexToken(rf"\mathbb{{{chr(cid)}}}", "atom", "amssymb", "corpus")
    # A fraktur or script font carries ORDINARY PUNCTUATION too: a formula
    # set in Euler emits its parentheses, its `=` and its `-` from EUFM10,
    # not from the maths font beside it. Refusing those deferred the whole
    # formula -- measured, 1200 failures on one paper, every one a bracket
    # or an operator the plain table already knows.
    if family in ("script", "fraktur"):
        if len(glyphname) == 1 and glyphname.isalpha():
            wrap = r"\mathcal" if family == "script" else r"\mathfrak"
            pkg = None if family == "script" else "amsfonts"
            return TexToken(rf"{wrap}{{{glyphname}}}", "atom", pkg, "corpus")
        if glyphname in _MATH_SYMBOL:
            return TexToken(_MATH_SYMBOL[glyphname], "atom", None, "corpus")
        if glyphname in _TEXT_PUNCT:
            return TexToken(_TEXT_PUNCT[glyphname], "atom", None, "corpus")
        return UNKNOWN
    return UNKNOWN

# --- Unicode-named glyphs -------------------------------------------------
#
# A publisher's maths font names its glyphs by CODEPOINT, not by the
# PostScript names TeX uses: STIXMath emits `u1D460`, `u1D6FF`, `uni2032`
# where Computer Modern emits `s`, `delta`, `prime`. Measured on three
# journal papers, those names were the single largest cause of deferral --
# 48 glyphs of one document's mathematics with nothing wrong with them
# except that the table did not speak their dialect.
#
# The Mathematical Alphanumeric Symbols block (U+1D400..U+1D7FF) encodes a
# LETTER together with a STYLE, so it decomposes: U+1D460 is an italic `s`,
# which is what a maths italic already means, and U+1D6FF is an italic
# `delta` -- i.e. `\delta`.

_UNI_NAME = re.compile(r"^u(?:ni)?([0-9A-Fa-f]{4,6})(?:\.\w+)?$")

# base codepoint -> (style, offset) for the alphanumeric block
_MATH_ALPHA = [
    (0x1D400, "bold", "A"), (0x1D434, "italic", "A"),
    (0x1D468, "bolditalic", "A"), (0x1D49C, "script", "A"),
    (0x1D504, "fraktur", "A"), (0x1D538, "double", "A"),
    (0x1D5A0, "sans", "A"), (0x1D670, "mono", "A"),
]

_GREEK_ITALIC = (0x1D6FC, 0x1D6FD, 0x1D6FE, 0x1D6FF)   # alpha..delta run


#: 787 — the published Adobe Symbol encoding, byte -> LaTeX. A PDF that uses
#: the Symbol font maps each glyph into the Private Use Area at 0xF000 + byte,
#: so U+F065 is byte 0x65 is `epsilon`.
#:
#: The ASSEMBLY PIECES ARE ABSENT ON PURPOSE. 0xE6..0xEF and 0xF3..0xFE are the
#: top/middle/bottom/extension fragments of tall parentheses, brackets, braces
#: and integrals; 0xBD/0xBE are arrow extensions and 0x60 is the radical
#: extension. None is a character. They belong to the assembly pass, and
#: emitting one puts a bracket shard in the middle of an equation — the same
#: judgement that keeps U+239C unmapped.
_SYMBOL_PUA = {
    0x20: " ", 0x21: "!", 0x22: r"\forall", 0x23: "#", 0x24: r"\exists",
    0x25: r"\%", 0x26: r"\&", 0x27: r"\ni", 0x28: "(", 0x29: ")",
    0x2A: r"\ast", 0x2B: "+", 0x2C: ",", 0x2D: "-", 0x2E: ".", 0x2F: "/",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4", 0x35: "5",
    0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x3A: ":", 0x3B: ";", 0x3C: "<", 0x3D: "=", 0x3E: ">", 0x3F: "?",
    0x40: r"\cong",
    0x41: r"\mathrm{A}", 0x42: r"\mathrm{B}", 0x43: r"\mathrm{X}",
    0x44: r"\Delta", 0x45: r"\mathrm{E}", 0x46: r"\Phi", 0x47: r"\Gamma",
    0x48: r"\mathrm{H}", 0x49: r"\mathrm{I}", 0x4A: r"\vartheta",
    0x4B: r"\mathrm{K}", 0x4C: r"\Lambda", 0x4D: r"\mathrm{M}",
    0x4E: r"\mathrm{N}", 0x4F: r"\mathrm{O}", 0x50: r"\Pi", 0x51: r"\Theta",
    0x52: r"\mathrm{P}", 0x53: r"\Sigma", 0x54: r"\mathrm{T}",
    0x55: r"\Upsilon", 0x56: r"\varsigma", 0x57: r"\Omega", 0x58: r"\Xi",
    0x59: r"\Psi", 0x5A: r"\mathrm{Z}",
    0x5B: "[", 0x5C: r"\therefore", 0x5D: "]", 0x5E: r"\perp", 0x5F: r"\_",
    0x61: r"\alpha", 0x62: r"\beta", 0x63: r"\chi", 0x64: r"\delta",
    0x65: r"\epsilon", 0x66: r"\phi", 0x67: r"\gamma", 0x68: r"\eta",
    0x69: r"\iota", 0x6A: r"\varphi", 0x6B: r"\kappa", 0x6C: r"\lambda",
    0x6D: r"\mu", 0x6E: r"\nu", 0x6F: "o", 0x70: r"\pi", 0x71: r"\theta",
    0x72: r"\rho", 0x73: r"\sigma", 0x74: r"\tau", 0x75: r"\upsilon",
    0x76: r"\varpi", 0x77: r"\omega", 0x78: r"\xi", 0x79: r"\psi",
    0x7A: r"\zeta",
    0x7B: r"\{", 0x7C: r"\mid", 0x7D: r"\}", 0x7E: r"\sim",
    0xA2: r"\prime", 0xA3: r"\leq", 0xA4: "/", 0xA5: r"\infty",
    0xAB: r"\leftrightarrow", 0xAC: r"\leftarrow", 0xAD: r"\uparrow",
    0xAE: r"\rightarrow", 0xAF: r"\downarrow",
    0xB0: r"^{\circ}", 0xB1: r"\pm", 0xB2: r"\prime\prime",
    0xB3: r"\geq", 0xB4: r"\times", 0xB5: r"\propto", 0xB6: r"\partial",
    0xB7: r"\cdot", 0xB8: r"\div", 0xB9: r"\neq", 0xBA: r"\equiv",
    0xBB: r"\approx", 0xBC: r"\ldots",
    0xC0: r"\aleph", 0xC1: r"\Im", 0xC2: r"\Re", 0xC3: r"\wp",
    0xC4: r"\otimes", 0xC5: r"\oplus", 0xC6: r"\emptyset",
    0xC7: r"\cap", 0xC8: r"\cup", 0xC9: r"\supset", 0xCA: r"\supseteq",
    0xCB: r"\not\subset", 0xCC: r"\subset", 0xCD: r"\subseteq",
    0xCE: r"\in", 0xCF: r"\notin",
    0xD0: r"\angle", 0xD1: r"\nabla", 0xD5: r"\prod", 0xD6: r"\surd",
    0xD7: r"\cdot", 0xD8: r"\neg", 0xD9: r"\wedge", 0xDA: r"\vee",
    0xDB: r"\Leftrightarrow", 0xDC: r"\Leftarrow", 0xDD: r"\Uparrow",
    0xDE: r"\Rightarrow", 0xDF: r"\Downarrow",
    0xE0: r"\lozenge", 0xE1: r"\langle", 0xE5: r"\sum",
    0xF1: r"\rangle", 0xF2: r"\int",
}

#: The font whose private slots mean the table above. Matched on the NAME,
#: because that is the only thing distinguishing these slots from any other
#: font's internal numbering. A subset prefix (`ABCDEE+Symbol`) is still Symbol.
_SYMBOL_FONT = re.compile(r"(?:^|\+)Symbol(?:MT|PS)?\b", re.I)


def symbol_pua_latex(glyphname: str, fontname: "str | None") -> "str | None":
    """LaTeX for a Symbol-font glyph the PDF hid in the Private Use Area."""
    if not fontname or not _SYMBOL_FONT.search(fontname):
        return None
    if not glyphname or len(glyphname) != 1:
        return None
    cp = ord(glyphname)
    if not (0xF000 <= cp <= 0xF0FF):
        return None
    return _SYMBOL_PUA.get(cp - 0xF000)


def codepoint_of(glyphname: str) -> int | None:
    """The Unicode codepoint a glyph name encodes, or None.

    Accepts `uXXXX`, `uniXXXX` and a variant suffix (`uni2032.var`), which is
    how a font distinguishes two designs of the same character.
    """
    m = _UNI_NAME.match(glyphname or "")
    return int(m.group(1), 16) if m else None


def _alphanumeric(cp: int) -> str | None:
    """LaTeX for a Mathematical Alphanumeric Symbols codepoint."""
    # Greek italic run: U+1D6FC is alpha, and the Greek names follow in order
    if 0x1D6FC <= cp <= 0x1D71B:
        greek = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
                 "theta", "iota", "kappa", "lambda", "mu", "nu", "xi",
                 "omicron", "pi", "rho", "varsigma", "sigma", "tau",
                 "upsilon", "phi", "chi", "psi", "omega"]
        idx = cp - 0x1D6FC
        if idx < len(greek):
            name = greek[idx]
            return " " if name == "omicron" else "\\" + name
        # 786 — the run does NOT end at omega. Seven variant letters close it,
        # and returning None for them deferred whole spans on a single glyph:
        # U+1D719 (phi symbol) alone accounted for 2 of 2405.08011v1's 9
        # deferrals. They are variants, so they take the \var... names where
        # LaTeX has one.
        tail = {0x1D715: "\\partial", 0x1D716: "\\epsilon",
                0x1D717: "\\vartheta", 0x1D718: "\\varkappa",
                0x1D719: "\\phi", 0x1D71A: "\\varrho",
                0x1D71B: "\\varpi"}
        return tail.get(cp)
    if 0x1D6A8 <= cp <= 0x1D6C0:                     # bold capital Greek
        caps = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta",
                "Theta", "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi",
                "Omicron", "Pi", "Rho", "vartheta", "Sigma", "Tau",
                "Upsilon", "Phi", "Chi", "Psi", "Omega"]
        idx = cp - 0x1D6A8
        if idx < len(caps):
            return "\\" + caps[idx]
        return None
    for base, style, first in _MATH_ALPHA:
        if base <= cp < base + 52:
            off = cp - base
            ch = chr(ord("A") + off) if off < 26 else chr(ord("a") + off - 26)
            if style == "italic":
                return ch                     # maths italic is the default
            if style == "bold":
                return rf"\mathbf{{{ch}}}"
            if style == "bolditalic":
                return rf"\boldsymbol{{{ch}}}"
            if style == "script":
                return rf"\mathcal{{{ch}}}"
            if style == "fraktur":
                return rf"\mathfrak{{{ch}}}"
            if style == "double":
                return rf"\mathbb{{{ch}}}"
            if style == "sans":
                return rf"\mathsf{{{ch}}}"
            if style == "mono":
                return rf"\mathtt{{{ch}}}"
    return None


# Codepoints outside the alphanumeric block that a maths font emits by name.
_UNI_LATEX = {
    0x2032: "\\prime", 0x2033: "\\prime\\prime", 0x2034: "\\prime\\prime\\prime",
    0x2192: "\\rightarrow", 0x2190: "\\leftarrow", 0x2194: "\\leftrightarrow",
    0x21D2: "\\Rightarrow", 0x21D0: "\\Leftarrow", 0x21D4: "\\Leftrightarrow",
    0x2208: "\\in", 0x2209: "\\notin", 0x2211: "\\sum", 0x220F: "\\prod",
    0x221A: "\\sqrt", 0x221E: "\\infty", 0x2229: "\\cap", 0x222A: "\\cup",
    0x222B: "\\int", 0x2248: "\\approx", 0x2260: "\\neq", 0x2261: "\\equiv",
    0x2264: "\\leq", 0x2265: "\\geq", 0x2282: "\\subset", 0x2286: "\\subseteq",
    0x2287: "\\supseteq", 0x2283: "\\supset", 0x22A2: "\\vdash",
    0x22A8: "\\models", 0x2205: "\\emptyset", 0x2200: "\\forall",
    0x2203: "\\exists", 0x00D7: "\\times", 0x00B1: "\\pm", 0x2217: "*",
    0x2218: "\\circ", 0x2219: "\\cdot", 0x22C5: "\\cdot", 0x2026: "\\ldots",
    0x22EF: "\\cdots", 0x2113: "\\ell", 0x2202: "\\partial", 0x2207: "\\nabla",
    0x00AC: "\\neg", 0x2227: "\\wedge", 0x2228: "\\vee", 0x2295: "\\oplus",
    0x2297: "\\otimes", 0x2212: "-", 0x2032: "\\prime",
    0x2013: "--", 0x2014: "---", 0x00A0: " ", 0x2009: "\\,",
}


# ZapfDingbats names its glyphs `a1`..`a191`, and no table shipped with
# pdfminer or fontTools covers them. Only entries VERIFIED by rendering the
# glyph out of a real document belong here -- an unresolved marker is a
# visible crop, a wrong one is a silent corruption.
_DINGBAT = {
    # Rendered at 400 dpi from a journal title page: a five-pointed outlined
    # star with stress lines, used as the article's footnote marker.
    "a36": "\u2729",
}


#: 786 — letterlike symbols that sit OUTSIDE the Mathematical Alphanumeric
#: blocks, so `_alphanumeric` cannot reach them and `chr(cp).isalnum()` is
#: false. ℎ is an italic h and nothing more; ℏ and ℘ have their own LaTeX.
_LETTERLIKE = {0x210E: "h", 0x210F: "\\hbar", 0x2118: "\\wp",
               # 786 — double-struck letters. A font that names its glyphs by
               # codepoint writes ℂ as `uni2102`; 482 occurrences of it and 214
               # of ℝ deferred their whole span in a 10-document sample.
               0x2102: "\\mathbb{C}", 0x210D: "\\mathbb{H}",
               0x2115: "\\mathbb{N}", 0x2119: "\\mathbb{P}",
               0x211A: "\\mathbb{Q}", 0x211D: "\\mathbb{R}",
               0x2124: "\\mathbb{Z}", 0x2113: "\\ell",
               0x2215: "/", 0x223C: "\\sim", 0x2212: "-"}

#: 786 — ASCII PUNCTUATION IS NOT ALPHANUMERIC, and that one word cost more
#: than every exotic symbol combined: `unicode_latex` ended with
#: `ch.isalnum() and cp < 0x2000`, so a font naming its comma `uni002C`
#: produced no LaTeX and deferred the entire maths span around it. In a
#: 10-document random sample that was 3,028 commas and 847 full stops — 57%
#: of all unmapped-glyph occurrences, against 338 for the whole Greek run.
#:
#: Only characters that are safe BARE in math mode are passed through; the
#: ones LaTeX reserves get their escaped form. `^`, `~` and `\` are absent
#: deliberately: as a literal glyph each needs a text-mode command, and
#: guessing which is how a superscript becomes a stray accent.
_MATH_SAFE = set(",.;:!?()[]/|*+-=<>@")
_ESCAPED = {"{": "\\{", "}": "\\}", "%": "\\%", "&": "\\&",
            "#": "\\#", "$": "\\$", "_": "\\_"}


def unicode_latex(glyphname: str) -> str | None:
    """LaTeX for a glyph named by its codepoint, or None."""
    if glyphname in _DINGBAT:
        return _DINGBAT[glyphname]
    cp = codepoint_of(glyphname)
    if cp is None:
        return None
    if cp in _UNI_LATEX:
        return _UNI_LATEX[cp]
    if cp in _LETTERLIKE:
        return _LETTERLIKE[cp]
    if cp < 0x80:
        ch_ = chr(cp)
        if ch_ in _ESCAPED:
            return _ESCAPED[ch_]
        if ch_ in _MATH_SAFE:
            return ch_
    got = _alphanumeric(cp)
    if got is not None:
        return got
    ch = chr(cp)
    if ch.isalnum() and cp < 0x2000:
        return ch
    return None


# --- maths spacing --------------------------------------------------------
#
# A LaTeX space emits NO GLYPH. Measured on a table of all thirteen forms
# compiled with pdflatex: every one is a pure advance of the current point,
# and the advances are QUANTISED in em, so the command that produced them is
# recoverable from geometry alone:
#
#     \!        -0.167      \enspace   +0.500
#     (none)     0.000       \quad      +1.000
#     \,        +0.167      \qquad     +2.000
#     \:        +0.222      \          +0.333
#     \;        +0.278      ~          +0.333
#
# 3mu is 1/6 em, 4mu is 2/9, 5mu is 5/18 -- the table is TeX's own, not a
# fitted one. Emitting a single generic space for all of them, which is what
# this projector did, loses `\!` (a NEGATIVE space, deliberate kerning) and
# cannot distinguish `$ab$` from `$a\quad b$`.
#
# `\ `, `~` and an ordinary text space all measure +0.333 and are not
# distinguishable here; the ordinary space is emitted for that band.

# ONLY the gaps TeX's own rules cannot produce.
#
# The first version mapped every band, and measured 48.8 spacing commands
# per 1000 tokens on a real paper -- far more explicit spacing than any
# author writes. The reason is that TeX inserts spacing AUTOMATICALLY by
# atom class: a binary operator takes a medium space either side, a relation
# a thick one. Those gaps measure 0.222 and 0.278 em and are
# indistinguishable from `\:` and `\;` by width alone. Emitting them as
# explicit commands would make a recompile add TeX's spacing again ON TOP.
#
# What survives is what automatic spacing never produces between ordinary
# atoms: a NEGATIVE gap (the author wrote `\!`), and a gap of an em or more
# (`\quad`, `\qquad`). Distinguishing `\,` from a binary operator's own
# medium space needs the atom classes, which this projector does not model.
# Narrowed AGAIN, by a second measurement. `\quad` and `\qquad` fired on
# the gaps an ALIGN environment leaves before its relation --
# `\vartheta^{\alpha}\quad= E_{i}^{\alpha}` -- which the author never
# wrote. Alignment, automatic atom spacing and explicit commands all produce
# the same widths, and width alone cannot separate them.
#
# What is left is what geometry CAN settle: whether the glyphs abut at all,
# and a negative gap, which nothing automatic produces.
_SPACE_BANDS = [
    (-0.08, r"\!"),
    (0.08, ""),           # the glyphs abut: `$ab$`, not `$a b$`
]


def math_space(gap_em: float) -> str:
    """The LaTeX spacing command a measured gap encodes.

    `gap_em` is the gap between two glyphs divided by the type size. Returns
    the empty string when the glyphs abut, so `$ab$` stays `$ab$`.
    """
    for edge, latex in _SPACE_BANDS:
        if gap_em < edge:
            return latex
    return " "


# --- TeX's spacing table, read backwards ----------------------------------
#
# TeX inserts space between two atoms as a function of their CLASSES, from a
# fixed 8x8 table (Knuth; LaTeX Companion p.525; reproduced as Table 1 in
# Baker, Sexton & Sorge, DAS 2010). Four values only:
#
#     0  no space        1  thin   3mu = 1/6 em
#     2  medium 4mu      3  thick  5mu = 5/18 em
#
# Read FORWARDS that is a nuisance: 694 measured that an author's `\:` and a
# binary operator's automatic 4mu are the same width, and concluded the atom
# classes were unrecoverable and the spacing therefore not projectable.
#
# Read BACKWARDS it is a signal. The space that TeX inserted IS the evidence
# for the class pair that produced it. Measured on one paper, 1887 gaps:
#
#     class 0  0.000 em   973 gaps   51.6%
#     class 1  0.167 em   158          8.4%
#     class 2  0.222 em    61          3.2%
#     class 3  0.278 em   341         18.1%
#                                     ----
#                                     81.3% of all gaps land on the table
#
# That is what lets a calligraphic `R` in `x R y` be identified as a RELATION
# rather than an ordinary letter: the author's own spacing says so.

_MU = 1.0 / 18.0                      # 18mu to the em

SPACE_CLASS = {0: 0.0, 1: 3 * _MU, 2: 4 * _MU, 3: 5 * _MU}

# Table 1: allowed spacing class for (left, right) atom classes. None means
# the pair cannot occur -- TeX converts one of the atoms to another type
# first. A value in parentheses in the printed table applies only outside
# scripts; that distinction is not modelled here.
ATOM_CLASSES = ("Ord", "Op", "Bin", "Rel", "Open", "Close", "Punct", "Inner")

_SPACING_TABLE = {
    "Ord":   {"Ord": 0, "Op": 1, "Bin": 2, "Rel": 3, "Open": 0, "Close": 0,
              "Punct": 0, "Inner": 1},
    "Op":    {"Ord": 1, "Op": 1, "Bin": None, "Rel": 3, "Open": 0,
              "Close": 0, "Punct": 0, "Inner": 1},
    "Bin":   {"Ord": 2, "Op": 2, "Bin": None, "Rel": None, "Open": 2,
              "Close": None, "Punct": None, "Inner": 2},
    "Rel":   {"Ord": 3, "Op": 3, "Bin": None, "Rel": 0, "Open": 3,
              "Close": 0, "Punct": 0, "Inner": 3},
    "Open":  {"Ord": 0, "Op": 0, "Bin": None, "Rel": 0, "Open": 0,
              "Close": 0, "Punct": 0, "Inner": 0},
    "Close": {"Ord": 0, "Op": 1, "Bin": 2, "Rel": 3, "Open": 0, "Close": 0,
              "Punct": 0, "Inner": 1},
    "Punct": {"Ord": 1, "Op": 1, "Bin": None, "Rel": 1, "Open": 1,
              "Close": 1, "Punct": 1, "Inner": 1},
    "Inner": {"Ord": 1, "Op": 1, "Bin": 2, "Rel": 3, "Open": 1, "Close": 0,
              "Punct": 1, "Inner": 1},
}


def space_class(gap_em: float, tol: float = 0.03) -> int | None:
    r"""Which of TeX's four spacing classes a measured gap is, or None.

    None means the gap is not one TeX's table produces -- an author's
    explicit `\quad`, an alignment, or a word space in text.
    """
    for cls, width in SPACE_CLASS.items():
        if abs(gap_em - width) <= tol:
            return cls
    return None


def class_pairs(space: int) -> list:
    """The (left, right) atom classes that produce this spacing class.

    The inverse is NOT unique -- a thick space is any of seven pairs -- but
    it is a strong constraint, and combined with the glyph identity, which a
    born-digital PDF gives exactly, it often determines the class.
    """
    return [(a, b) for a in ATOM_CLASSES for b in ATOM_CLASSES
            if _SPACING_TABLE[a][b] == space]


# --- fonts with no /Encoding ----------------------------------------------
#
# Most TeX maths fonts in a dvips/Distiller PDF carry NO /Encoding at all.
# pdfminer then falls back to StandardEncoding, and the fork's `glyphname`
# reports that fallback as if it were the font's own name:
#
#     TeX-matha10  cid 112 -> "p"             RENDERED: `(`
#     TeX-matha10  cid 113 -> "q"             RENDERED: `)`
#     TeX-matha10  cid 16  -> "quotedblleft"
#     TeX-matha10  cid 18  -> "quotedblbase"
#     TeX-matha10  cid 24  -> "perthousand"
#     TeX-matha10  cid  6  -> "ring"
#
# The CID is correct; only the NAME is wrong. Before the fork there was no
# name and the span deferred, which was the right outcome. The fork turned an
# abstention into a confident wrong answer -- `\pi^{*}(\omega_{0})` read as
# `\pi^{*}p\omega_{0}q` -- and a confident wrong answer is the one failure
# this project is built to avoid.
#
# These families are SYMBOL fonts: they contain no Latin alphabet and no text
# punctuation, so a StandardEncoding name in one of them is certainly the
# fallback and not the truth.
_NO_LATIN = re.compile(r"TeX-math[a-z]\d*|CMEX\d*|LMMathExtension\d*"
                       r"|MSAM\d*|MSBM\d*", re.I)

# StandardEncoding names that such a font can never legitimately carry.
_STANDARD_TEXT_NAMES = {
    "quoteleft", "quoteright", "quotedblleft", "quotedblright",
    "quotedblbase", "quotesinglbase", "perthousand", "ring", "grave",
    "acute", "dieresis", "cedilla", "germandbls", "ampersand", "at",
    "exclam", "question", "percent", "dollar", "numbersign",
}

# Slots VERIFIED by rendering the glyph out of a real document. Nothing goes
# in here on the strength of a table or a guess.
_TEX_SLOTS = {
    # Each rendered at 500dpi from its EXACT glyph box out of 1.pdf, side by
    # side, so there is no neighbouring glyph to misread:
    #     16 `=`   18 `~`   24 `!=`   80 `in`   82 `notin`
    ("TeX-matha", 16): "equal",
    ("TeX-matha", 18): "similar",
    ("TeX-matha", 24): "notequal",
    ("TeX-matha", 80): "element",
    ("TeX-matha", 82): "notelement",
    ("TeX-matha", 112): "parenleft",     # rendered: `\pi^{*}(\omega_{0})`
    ("TeX-matha", 113): "parenright",
}


def untrusted_name(fontname: str, glyphname: str | None) -> bool:
    """Is this glyph name the StandardEncoding fallback rather than the font's?

    True means ABSTAIN: the name cannot be relied on, so no LaTeX should be
    emitted for it and the span should defer with the region kept.
    """
    if not glyphname:
        return False
    base = fontname.split("+")[-1]
    if not _NO_LATIN.match(base):
        return False
    if len(glyphname) == 1 and glyphname.isalpha():
        return True
    return glyphname in _STANDARD_TEXT_NAMES


#: 779 -- WHAT `mathabx.dcl` CALLS A SLOT, AND WHAT LaTeX CALLS IT.
#:
#: `MATHABX` is `mathabx.dcl` read out -- 573 (font, slot) -> name pairs --
#: and until now it was consulted only by `texpackages`, to decide which
#: packages a preamble needs. Nothing asked it what a CID means, so the two
#: documents it was built from still lost their mathematics to
#: `unmapped-glyph`: 31 of the corpus's 228 crops, all in wzlxjtu-001 and
#: -002, the two AAAI templates that load the package.
#:
#: Its names are mathabx's MACRO names, not this table's glyph names, so a
#: second step is needed -- and it is a LOOKUP, not `"\\" + name`. Guessing
#: the macro would emit `\coasterisk` for slots nobody has verified; the
#: rule here is to abstain instead, so a name absent from this dict leaves
#: the glyph unmapped and the span defers exactly as it does today.
#:
#: These six are the ones those documents actually use. Each maps to THIS
#: table's own canonical glyph name rather than to LaTeX directly, so the
#: kind, the package registration and the dialect comparison all keep working
#: from one place. `leq`/`geq` are the pair the comment above already checked
#: against their surrounding formula.
_MATHABX_TEX = {
    "leq": "lessequal", "geq": "greaterequal",
    "vert": "bar", "Vert": "bardbl",
    "lbrace": "braceleft", "rbrace": "braceright",
}


def mathabx_slot(fontname: str, cid: int) -> str | None:
    """The `mathabx.dcl` name for a slot of one of its fonts, or None."""
    base = fontname.split("+")[-1].lower()
    for fam in ("matha", "mathb", "mathx"):
        if fam in base:
            return MATHABX.get(fam, {}).get(cid)
    return None


def mathabx_tex(name: str | None) -> str | None:
    """This table's glyph name for a `mathabx.dcl` name, or None to abstain."""
    return _MATHABX_TEX.get(name or "")


def tex_slot(fontname: str, cid: int) -> str | None:
    """The VERIFIED glyph name for a slot, or None."""
    base = fontname.split("+")[-1]
    for (fam, slot), name in _TEX_SLOTS.items():
        if slot == cid and base.lower().startswith(fam.lower()):
            return name
    return None


# --- log-like operator names ----------------------------------------------
#
# TeX sets `\sup`, `\min`, `\lim` and their kin in UPRIGHT ROMAN, so they
# reach the page as ordinary roman letters with no mark of being one token.
# Read letter by letter they become `\mathrm{m}\mathrm{in}`, and worse: a
# neighbouring glyph then attaches to one of the letters as a script, which
# is how `\sup` became `\mathrm{s}_{<}\mathrm{u}_{i}\mathrm{p}_{-}`.
#
# The list is TeX's own set of log-like functions (Knuth, Appendix B).
# Longest match first, so `limsup` is not read as `lim` followed by `sup`.
OPERATOR_NAMES = (
    "arccos", "arcsin", "arctan", "liminf", "limsup", "injlim", "projlim",
    "varliminf", "varlimsup", "varinjlim", "varprojlim",
    "cosh", "coth", "sinh", "tanh", "det", "dim", "exp", "gcd", "hom",
    "inf", "ker", "lim", "log", "max", "min", "sec", "sup", "arg", "cos",
    "cot", "csc", "deg", "sin", "tan", "ln", "lg", "Pr",
)

# --- LIMIT PLACEMENT, AS A TABLE -------------------------------------------
#
# Whether an operator sets its scripts BELOW/ABOVE or BESIDE is not visible on
# the page: `\\max_{x\\in A}` and `\\log_2` are both upright roman letter runs,
# and only the first centres its condition underneath. No geometry separates
# them, so the reader has to be told. This is that table, and it is taken
# from LaTeX rather than remembered.
#
# PROVENANCE. `amsopn.sty` declares each name as `\\qopname\\relax m{...}` or
# `\\qopname\\relax o{...}` -- m for MOVABLE LIMITS, o for ordinary. Extracted
# from the installed TeX tree (texmf-dist/tex/latex/amsmath/amsopn.sty):
#
#     m (12)  Pr det gcd inf injlim lim liminf limsup max min projlim sup
#     o (22)  arccos arcsin arctan arg cos cosh cot coth csc deg dim exp hom
#             ker lg ln log sec sin sinh tan tanh
#
# `\\varlimsup`, `\\varliminf`, `\\varinjlim`, `\\varprojlim` and `\\varlim` are
# built separately in the same file (from an overlined `lim`) and take limits
# like the family they belong to.
#
# NOTE, because it is the obvious mistake and it was made: `\\dim`, `\\hom`,
# `\\ker`, `\\deg` and `\\arg` LOOK like they belong with `\\max` and `\\min`
# -- they are short, upright, and take a subscript -- and amsopn declares all
# five `o`. Their scripts sit beside them. Treating them as limit operators
# makes the reader claim a neighbouring term's scripts.
LIMIT_OPERATORS = frozenset((
    "Pr", "det", "gcd", "inf", "injlim", "lim", "liminf", "limsup",
    "max", "min", "projlim", "sup",
    "varinjlim", "varliminf", "varlimsup", "varprojlim",
))
# `varlim` is NOT in that set: `\\varlim@` is amsopn's internal helper
# (`\\protected\\def\\varlim@#1#2`), not a command an author can write. There
# are exactly four `\\var*lim` operators. Scraping the file for
# `\\protected\\def\\(var[a-z]+)` picks the helper up because `\\b` matches at
# the `@`.
#
# KERNEL-ONLY CAVEAT, recorded because nothing here can detect it. Without
# `amsmath`, `latex.ltx` leaves `\\dim` and `\\ker` WITHOUT `\\nolimits`, so
# they take under-limits in display style; `amsopn` redefines both to `o`.
# A reader working from the PDF cannot see which was loaded. All 102 gold
# documents in this corpus load `amsmath`, and none of them writes `\\dim_`
# or `\\ker_`, so the question is not live here -- but a document that skips
# `amsmath` and subscripts a `\\dim` will be read with its script beside the
# operator when the page shows it underneath.

#: Sum-class operators, which take limits in display style AND change size.
#: These arrive as glyphs from the extensible font, so they are named by
#: GLYPH, not by control sequence. The `display`/`text` suffix is the size
#: TeX chose, which is itself the statement of which style the row is in:
#: `summationdisplay` carries its limits above and below, `summationtext`
#: beside it. Measured over the corpus, the extensible font yields exactly
#: `integraldisplay`, `summationdisplay`, `summationtext` and
#: `productdisplay`; the rest of the class is listed because it is the same
#: class, not because this corpus exercises it.
# INTEGRALS ARE NOT IN THIS LIST, and the corpus is why. Measured over the
# 102 documents, counting where each operator's scripts actually sit:
#
#     summationdisplay   140 under   59 beside
#     productdisplay      59 under   11 beside
#     integraldisplay      2 under   21 beside     <-- the odd one out
#
# which is right and the table was wrong: `\\int` is `\\nolimits` by default
# even in display style -- TeX sets its limits at the upper right, not above
# and below -- while `\\sum` and `\\prod` are `\\displaylimits`. Listing
# integrals here would have made the reader hunt for a condition underneath
# an operator that never has one.
_LARGE_OP_STEMS = (
    "summation", "product", "coproduct",
    "union", "intersection", "unionmulti", "squareunion",
    "logicaland", "logicalor", "circleplus", "circlemultiply", "circledot",
)
LARGE_OPERATORS_DISPLAY = frozenset(s + "display" for s in _LARGE_OP_STEMS)
LARGE_OPERATORS_TEXT = frozenset(s + "text" for s in _LARGE_OP_STEMS)


def may_take_limits(latex: str | None = None,
                    glyphname: str | None = None) -> bool:
    r"""COULD a script centred under this operator be one of its limits?

    Not the same question as `takes_limits`, which answers what LaTeX does by
    DEFAULT. Two things put limits under an operator that the default would
    have set beside it: `\limits` after any Op atom, and a display sub-formula
    set in text style. Measured on the corpus, `producttext` -- the text-size
    product -- carries limits above and below 31 times against 9 beside, e.g.
    `\prod` with `i=1` under it and `8` over it in wzlxjtu-078 and -084.

    So for the SUM CLASS the size variant is not evidence either way, and the
    geometry decides: a script that overhangs the operator horizontally is a
    limit, a script sitting to its right is not. A named operator is still
    judged by the table, because `\log_2` and `\max_{x}` are identical runs of
    upright letters and geometry cannot separate them.
    """
    if latex and latex.lstrip("\\") in LIMIT_OPERATORS:
        return True
    return bool(glyphname) and (glyphname in LARGE_OPERATORS_DISPLAY
                                or glyphname in LARGE_OPERATORS_TEXT)


def takes_limits(latex: str | None = None, glyphname: str | None = None) -> bool:
    """Does this operator set its scripts BELOW and ABOVE, not beside?

    Answers for both classes: a named operator by its control sequence, a
    sum-class operator by its glyph. A `...text` glyph is the SAME operator
    set in text style, where TeX puts the limits beside it -- so it is
    deliberately not in the display set.
    """
    if latex and latex.lstrip("\\") in LIMIT_OPERATORS:
        return True
    return bool(glyphname) and glyphname in LARGE_OPERATORS_DISPLAY


_BY_LENGTH = tuple(sorted(OPERATOR_NAMES, key=len, reverse=True))


def operator_name(text: str) -> str | None:
    r"""The LaTeX command for a run of roman letters, if it is one.

    Exact match only. A run spelling `sup` is `\sup`; a run spelling `supp`
    is not, and guessing would turn a variable name into an operator.
    """
    for name in _BY_LENGTH:
        if text == name:
            return "\\" + name
    return None


def operator_prefix(text: str) -> str | None:
    """The longest operator name this run STARTS with, or None."""
    for name in _BY_LENGTH:
        if text.startswith(name):
            return name
    return None
