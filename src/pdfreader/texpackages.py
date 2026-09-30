"""texpackages - which package defines each command we emit.

Mathpix produces LaTeX that does not always compile, because the training
data carried the symbol but not the package that defines it. We do not have
that problem: every symbol we emit was chosen from a known FONT, and the font
says which package a LaTeX author would have loaded to get it. MSAM/MSBM is
amssymb, EUFM is amsfonts, RSFS is mathrsfs, and so on.

So the preamble can be derived rather than guessed: scan the document for the
commands actually used and require exactly those packages. A document that
uses no fraktur does not load amsfonts.

Only commands that NEED a package appear here. Everything in plain TeX --
`\\alpha`, `\\sum`, `\\frac`, `\\left`, `\\widehat` -- is deliberately absent.
"""
from __future__ import annotations

import re

# command (without backslash) -> package that defines it
PACKAGE_OF: dict[str, str] = {}


def _add(package: str, *names: str) -> None:
    for n in names:
        PACKAGE_OF[n] = package


# --- mathabx: the matha/mathb/mathx symbol fonts ------------------------------
# Registered from `texmap.MATHABX`, which is `mathabx.dcl` read out. A symbol
# only this package defines needs it declared, or the projected LaTeX will not
# compile -- and `unknown_commands` would otherwise warn about every one.
def _add_mathabx():
    try:
        from texmap import MATHABX
    except Exception:
        return
    names = sorted({n for f in MATHABX for n in MATHABX[f].values()})
    # ONLY the symbols mathabx alone defines. Most of its table re-declares
    # ordinary maths -- `leq`, `geq`, `lbrace` -- from its own fonts, and
    # registering those would make every plain formula in the corpus claim to
    # need the package.
    own = [n for n in names
           if n not in PACKAGE_OF and unknown_commands("\\" + n + " x")]
    _add("mathabx", *own)


# --- characters the TEXT font cannot set --------------------------------------
#
# Prose does not go through `texmap`: a glyph the PDF's ToUnicode names is
# written into the `.tex` as itself, and compiles only if the text font has
# it. Latin Modern does not have Greek, and does not have most symbols, so
# the character is dropped with
#
#     Missing character: There is no α (U+03B1) in font [lmroman10-regular]
#
# which is a WARNING, not an error: the document still builds, one character
# short, and nothing in the output says so. Found only by compiling PDFs from
# outside the corpus -- three of eighteen lost a character this way.
#
# MEASURED, not guessed. Every non-ASCII character pdf2mmd has emitted over
# the 102-document corpus and the 18 outside documents -- 40 distinct -- was
# set on its own in the preamble this file derives. Thirty-six rendered;
# four did not: U+03B1, U+03B2, U+2729 and one Private Use codepoint.
#
# The table is therefore by CLASS, not by the four accidents: the whole Greek
# block, because a text font having two of its letters and not the rest is not
# a thing that happens, plus the symbols the corpus actually carries.
#
# `\newunicodechar` and not `\DeclareUnicodeCharacter`: the latter is inputenc,
# which is pdfLaTeX-only and does nothing under xelatex -- and the form MathPix
# emits for it, `\ifmmode\times\else{$\times$}\fi`, opens a maths environment
# inside one that is already open.

_GREEK_LOWER = [
    ("α", "alpha"), ("β", "beta"), ("γ", "gamma"),
    ("δ", "delta"), ("ε", "varepsilon"), ("ζ", "zeta"),
    ("η", "eta"), ("θ", "theta"), ("ι", "iota"),
    ("κ", "kappa"), ("λ", "lambda"), ("μ", "mu"),
    ("ν", "nu"), ("ξ", "xi"), ("π", "pi"), ("ρ", "rho"),
    ("σ", "sigma"), ("τ", "tau"), ("υ", "upsilon"),
    ("φ", "varphi"), ("χ", "chi"), ("ψ", "psi"),
    ("ω", "omega"),
    # the variant codepoints: Unicode splits the two shapes TeX splits, but
    # the other way round for epsilon and phi -- U+03B5 is the `\varepsilon`
    # shape and U+03F5 the `\epsilon` one.
    ("ς", "varsigma"), ("ϑ", "vartheta"), ("ϕ", "phi"),
    ("ϖ", "varpi"), ("ϱ", "varrho"), ("ϵ", "epsilon"),
]
#: only the eleven capitals TeX names; the others are Latin letters in shape
#: and in code, and `\Alpha` does not exist.
_GREEK_UPPER = [
    ("Γ", "Gamma"), ("Δ", "Delta"), ("Θ", "Theta"),
    ("Λ", "Lambda"), ("Ξ", "Xi"), ("Π", "Pi"),
    ("Σ", "Sigma"), ("Υ", "Upsilon"), ("Φ", "Phi"),
    ("Ψ", "Psi"), ("Ω", "Omega"),
]
#: Greek capitals that ARE a Latin capital. Declared so the reading survives
#: even though the shape is the Latin one -- dropping them silently is the
#: defect this table exists for.
_GREEK_UPPER_LATIN = [
    ("Α", "A"), ("Β", "B"), ("Ε", "E"), ("Ζ", "Z"),
    ("Η", "H"), ("Ι", "I"), ("Κ", "K"), ("Μ", "M"),
    ("Ν", "N"), ("Ο", "O"), ("Ρ", "P"), ("Τ", "T"),
    ("Χ", "X"),
]

TEXT_UNICODE: dict[str, str] = {}
for _c, _n in _GREEK_LOWER + _GREEK_UPPER:
    TEXT_UNICODE[_c] = "\\ensuremath{\\%s}" % _n
for _c, _n in _GREEK_UPPER_LATIN:
    TEXT_UNICODE[_c] = "\\ensuremath{\\mathrm{%s}}" % _n
#: `\varkappa` is amssymb's, so it is registered as needing it below.
TEXT_UNICODE["ϰ"] = "\\ensuremath{\\varkappa}"

TEXT_UNICODE.update({
    # the stars: a footnote marker in 1-s2.0-S2590118426000298 and in
    # wzlxjtu-032. `\star` for both shapes -- pifont's open star would make
    # every document that carries one load pifont.
    "✩": "\\ensuremath{\\star}", "★": "\\ensuremath{\\star}",
    "☆": "\\ensuremath{\\star}", "⋆": "\\ensuremath{\\star}",
    # maths that reaches prose through a caption or a heading
    "×": "\\ensuremath{\\times}", "÷": "\\ensuremath{\\div}",
    "±": "\\ensuremath{\\pm}", "∓": "\\ensuremath{\\mp}",
    "−": "\\ensuremath{-}", "∗": "\\ensuremath{*}",
    "∘": "\\ensuremath{\\circ}", "∙": "\\ensuremath{\\cdot}",
    "√": "\\ensuremath{\\surd}", "∞": "\\ensuremath{\\infty}",
    "∂": "\\ensuremath{\\partial}", "∇": "\\ensuremath{\\nabla}",
    "∑": "\\ensuremath{\\sum}", "∏": "\\ensuremath{\\prod}",
    "∫": "\\ensuremath{\\int}", "≈": "\\ensuremath{\\approx}",
    "≠": "\\ensuremath{\\neq}", "≡": "\\ensuremath{\\equiv}",
    "≤": "\\ensuremath{\\leq}", "≥": "\\ensuremath{\\geq}",
    "→": "\\ensuremath{\\rightarrow}",
    "←": "\\ensuremath{\\leftarrow}",
    "↔": "\\ensuremath{\\leftrightarrow}",
    "⇒": "\\ensuremath{\\Rightarrow}",
    "⇐": "\\ensuremath{\\Leftarrow}",
    "⇔": "\\ensuremath{\\Leftrightarrow}",
    "∈": "\\ensuremath{\\in}", "∉": "\\ensuremath{\\notin}",
    "⊂": "\\ensuremath{\\subset}", "⊆": "\\ensuremath{\\subseteq}",
    "∪": "\\ensuremath{\\cup}", "∩": "\\ensuremath{\\cap}",
    "∅": "\\ensuremath{\\emptyset}",
    "∀": "\\ensuremath{\\forall}", "∃": "\\ensuremath{\\exists}",
    "¬": "\\ensuremath{\\neg}", "∧": "\\ensuremath{\\wedge}",
    "∨": "\\ensuremath{\\vee}", "⊕": "\\ensuremath{\\oplus}",
    "⊗": "\\ensuremath{\\otimes}", "∥": "\\ensuremath{\\|}",
    "⋯": "\\ensuremath{\\cdots}", "⋮": "\\ensuremath{\\vdots}",
    "…": "\\ensuremath{\\ldots}",
    "′": "\\ensuremath{{}^{\\prime}}",
    "″": "\\ensuremath{{}^{\\prime\\prime}}",
    "€": "\\texteuro",
    # U+00AD SOFT HYPHEN is a hyphenation POINT, not a hyphen: it is invisible
    # unless the line breaks there. LaTeX spells it `\-`. Surfaced by the
    # warning above on an outside document, which is what that line is for.
    "\u00ad": "\\-",
})

#: which of these need a package beyond LaTeX's own
_UNICODE_PACKAGE = {"ϰ": "amssymb", "€": "textcomp"}

#: Unicode's Private Use Area. A codepoint here is a FONT'S INTERNAL SLOT:
#: the PDF said "this glyph has no Unicode". It is not a character, no font
#: outside that document has it, and writing it out drops it silently. There
#: is nothing to translate it to, so it is removed and REPORTED.
def is_private_use(ch: str) -> bool:
    o = ord(ch)
    return (0xE000 <= o <= 0xF8FF or 0xF0000 <= o <= 0xFFFFD
            or 0x100000 <= o <= 0x10FFFD)


def strip_private_use(text: str) -> tuple[str, list[str]]:
    """`text` without its Private Use codepoints, and which they were."""
    seen = [c for c in text if is_private_use(c)]
    if not seen:
        return text, []
    return "".join(c for c in text if not is_private_use(c)), seen


#: WHAT THE STANDARD TEXT FONT ALREADY SETS -- measured, 2026-09-19.
#:
#: 840 candidates (this table, every non-ASCII character pdf2mmd emits over
#: the corpus and the 18 outside documents, and the Latin-1, Latin Extended,
#: punctuation, ligature, arrow, operator, Greek and currency blocks) were
#: each set in an `\hbox` under the preamble this file derives and the log
#: read back. 398 rendered.
#:
#: A character in this set is NOT declared, because a declaration would
#: change output that is already correct. The result is not the one you would
#: guess: Latin Modern has every Greek CAPITAL and no Greek lowercase, and it
#: has `x`, `/`, `+-`, `sum`, `sqrt`, `infinity`, `approx` and the euro.
#: That asymmetry is why this is measured rather than assumed.
_RENDERABLE_RANGES = (
    (0x00A1, 0x00AC), (0x00AE, 0x017F), (0x02DD, 0x02DD), (0x0370,
    0x0377), (0x037A, 0x037A), (0x0391, 0x03A1), (0x03A3, 0x03A9),
    (0x2010, 0x2011), (0x2013, 0x2014), (0x2016, 0x2016), (0x2018,
    0x201A), (0x201C, 0x201E), (0x2020, 0x2022), (0x2026, 0x2026),
    (0x2030, 0x2031), (0x2039, 0x2052), (0x2054, 0x2054), (0x2083,
    0x208E), (0x2090, 0x2093), (0x20A1, 0x20A1), (0x20A4, 0x20A4),
    (0x20A6, 0x20A6), (0x20A9, 0x20A9), (0x20AB, 0x20AC), (0x20B1,
    0x20B1), (0x20B9, 0x20BF), (0x2190, 0x2194), (0x21BA, 0x21C2),
    (0x2210, 0x221A), (0x221E, 0x221E), (0x2222, 0x2222), (0x2243,
    0x2248), (0x226F, 0x2276), (0x229C, 0x22A4), (0x22C8, 0x22D2),
    (0x22F5, 0x22F5), (0x2423, 0x2423), (0xFB00, 0xFB04)
)


def renders_in_text(ch: str) -> bool:
    o = ord(ch)
    return o < 0x80 or any(a <= o <= b for a, b in _RENDERABLE_RANGES)


def unicode_decls(body: str) -> tuple[list[str], list[str], list[str]]:
    r"""Declarations for the non-ASCII characters this body uses.

    Returns (`\newunicodechar` lines, extra packages, characters that will be
    DROPPED). Only characters the text font does not have are declared.

    The third list is surfaced in the preamble rather than discarded: a
    character no font here sets and this table does not name is exactly the
    failure that goes unnoticed, because LaTeX only warns about it and still
    produces a PDF.
    """
    used = sorted({c for c in body if ord(c) > 0x7F})
    lines, pkgs, lost = [], [], []
    for c in used:
        if renders_in_text(c):
            continue
        rep = TEXT_UNICODE.get(c)
        if rep is None:
            lost.append(c)
            continue
        lines.append("\\newunicodechar{%s}{%s}" % (c, rep))
        p = _UNICODE_PACKAGE.get(c)
        if p and p not in pkgs:
            pkgs.append(p)
    if lines:
        pkgs.insert(0, "newunicodechar")
    return lines, pkgs, lost


# --- dsfont: the doublestroke font -------------------------------------------
# `\mathds` is dsfont's, not amssymb's. amssymb's blackboard alphabet is
# msbm's, which has A-Z and NO DIGITS -- so the identity matrix cannot be
# written `\mathbb{1}` at all, and a reader that emits it produces LaTeX that
# sets nothing. The FONT says which package: dsrom -> doublestroke -> dsfont.
_add("dsfont", "mathds")

# --- amsmath: structures and text-in-maths -----------------------------------
_add("amsmath",
     "text", "operatorname", "binom", "dbinom", "tbinom", "dfrac", "tfrac",
     "cfrac", "overset", "underset", "substack", "boxed", "xrightarrow",
     "xleftarrow", "pmod", "bmod", "implies", "impliedby", "iff",
     "DeclareMathOperator", "begin{align}", "begin{gather}", "begin{cases}",
     # the *inner* environments too: `aligned` is what this reader emits for
     # a multi-row display, and it needs amsmath exactly as `align` does.
     "begin{aligned}", "begin{gathered}", "begin{split}", "limits")

# --- amssymb: the AMS symbol fonts MSAM and MSBM ------------------------------
_add("amssymb",
     # blackboard bold lives in MSBM
     "mathbb", "Bbbk",
     # relations
     "leqslant", "geqslant", "lesssim", "gtrsim", "eqslantless",
     "eqslantgtr", "precsim", "succsim", "subsetneq", "supsetneq",
     "nsubseteq", "nsupseteq", "nleq", "ngeq", "nless", "ngtr", "nsim",
     "nmid", "nparallel", "nrightarrow", "nleftarrow", "nleftrightarrow",
     "ntriangleleft", "ntriangleright", "varsubsetneq", "thickapprox",
     "approxeq", "backsim", "bumpeq", "Bumpeq", "doteqdot", "risingdotseq",
     "fallingdotseq", "circeq", "triangleq", "therefore", "because",
     # arrows
     "rightsquigarrow", "leftrightsquigarrow", "twoheadrightarrow",
     "twoheadleftarrow", "rightarrowtail", "leftarrowtail", "looparrowright",
     "looparrowleft", "curvearrowright", "curvearrowleft", "circlearrowright",
     "circlearrowleft", "upharpoonright", "downharpoonright",
     # shapes and misc
     "square", "blacksquare", "lozenge", "blacklozenge", "bigstar",
     "circledast", "circledcirc", "circleddash", "divideontimes",
     "leftthreetimes", "rightthreetimes", "varnothing", "complement",
     "hslash", "hbar", "backepsilon", "digamma", "varkappa", "beth",
     "gimel", "daleth", "vartriangleleft", "vartriangleright",
     "trianglelefteq", "trianglerighteq", "smallsetminus", "centerdot",
     "intercal", "doublebarwedge", "veebar", "barwedge", "boxplus",
     "boxminus", "boxtimes", "boxdot", "ltimes", "rtimes", "dotplus",
     "Subset", "Supset", "Cap", "Cup", "pitchfork", "sqsubset", "sqsupset")

# --- fonts that are their own package ----------------------------------------
_add("amsfonts", "mathfrak")
_add("mathrsfs", "mathscr")
_add("stmaryrd",
     "llbracket", "rrbracket", "llparenthesis", "rrparenthesis",
     "shortrightarrow", "shortleftarrow", "bigcurlyvee", "bigcurlywedge",
     "varobslash", "obar", "ogreaterthan", "olessthan")
_add("mathtools",
     "coloneqq", "eqqcolon", "shortmid", "vcentcolon", "colonapprox",
     "Coloneqq", "dblcolon", "xleftrightarrow", "xhookrightarrow",
     "xhookleftarrow", "xmapsto", "DeclarePairedDelimiter", "prescript",
     "adjustlimits", "smashoperator", "mathclap", "mathllap", "mathrlap",
     "underbracket", "overbracket", "splitfrac", "splitdfrac")

# --- bbm: an alternative blackboard bold, drawn from a real font rather than
# amssymb's outline caps. A document that uses it needs BOTH, since amssymb
# supplies the relations.
_add("bbm", "mathbbm", "mathbbmss", "mathbbmtt")

# --- bm: bold maths that follows the symbol's own font, unlike \boldsymbol
_add("bm", "bm", "hm", "bmdefine", "heavymath")

# --- extarrows: extensible arrows with text above AND below
_add("extarrows",
     "xlongequal", "xLongrightarrow", "xLongleftarrow", "xLongleftrightarrow",
     "xleftrightarrow", "xrightharpoondown", "xrightharpoonup",
     "xleftharpoondown", "xleftharpoonup", "xrightleftharpoons",
     "xleftrightharpoons", "xtofrom", "xdashrightarrow", "xdashleftarrow")

# --- cancel: struck-through terms, common in worked derivations
_add("cancel", "cancel", "bcancel", "xcancel", "cancelto")
_add("graphicx", "includegraphics")
# xcolor: text colour and cell backgrounds recovered from the PDF's g/rg/k
# and G/RG/K operators. Markdown cannot express either, so these appear only
# in the LaTeX projection.
_add("xcolor", "textcolor", "colorbox", "fcolorbox", "pagecolor",
     "definecolor", "color")
_add("latexsym", "Box", "Diamond", "lhd", "rhd", "unlhd", "unrhd", "mho")

# Commands that no package reliably provides, so the preamble defines them.
# A `\providecommand` is inert when the document already has the real thing,
# which makes it safe to emit unconditionally for anything we actually used.
#
# These four came from a working Mathpix-output preamble. The BODIES here are
# reasonable standard fallbacks; if the definitions in use differ, replace the
# values -- the mechanism does not care what the body is.
PROVIDE: dict[str, str] = {
    "Perp": r"\providecommand{\Perp}{\perp\!\!\!\perp}",
    "overparen": r"\providecommand{\overparen}[1]{\overset{\frown}{#1}}",
    "oiint": r"\providecommand{\oiint}{\oint\!\!\!\oint}",
    "longdiv": r"\providecommand{\longdiv}[2]{#1\overline{\smash{)}\,#2}}",
}

_CMD = re.compile(r"\\([a-zA-Z]+)")
_ENV = re.compile(r"\\begin\{([a-zA-Z*]+)\}")


def provides_for(latex: str) -> list[str]:
    r"""`\providecommand` lines for commands this document uses that no
    package defines."""
    used = {m for m in _CMD.findall(latex) if m in PROVIDE}
    return [PROVIDE[m] for m in sorted(used)]


def packages_for(latex: str) -> list[str]:
    """The packages this LaTeX needs, in a stable load order.

    Derived from what is actually present, so a document with no fraktur does
    not load amsfonts. amsmath is required by amssymb in practice and is
    listed first when either is needed.
    """
    needed = {PACKAGE_OF[m] for m in _CMD.findall(latex) if m in PACKAGE_OF}
    # `\begin{align}` and its kin are registered under the key
    # `begin{align}`, and `_CMD` only ever yielded `begin` -- so those
    # entries, which have been in this table since it was written, could
    # never fire. A projected document using `aligned` got no amsmath.
    needed |= {PACKAGE_OF["begin{" + e + "}"]
               for e in _ENV.findall(latex)
               if "begin{" + e + "}" in PACKAGE_OF}
    # Dependencies: amssymb and mathtools both assume amsmath is loaded, and
    # mathtools patches it, so it must come after.
    if needed & {"amssymb", "mathtools"}:
        needed.add("amsmath")
    # Load order matters: amsmath before amssymb, mathtools after amsmath
    # (it patches it), and fontspec last because it reconfigures fonts.
    order = ["amsmath", "amssymb", "amsfonts", "bbm", "bm", "mathtools",
             "extarrows", "cancel", "mathrsfs", "stmaryrd", "latexsym",
             "xcolor", "graphicx", "fontspec"]
    return [p for p in order if p in needed] + sorted(needed - set(order))


def unknown_commands(latex: str, known: set[str] | None = None) -> set[str]:
    """Commands we emitted that are in neither plain TeX nor the table above.

    A non-empty result is a warning that the document may not compile -- the
    same failure mode as Mathpix output, surfaced instead of shipped.
    """
    plain = known or PLAIN_TEX
    return {m for m in _CMD.findall(latex)
            if m not in plain and m not in PACKAGE_OF
            and m not in _STRUCTURE and m not in PROVIDE}


# Document-structure commands from the LaTeX kernel. Not symbols, so they
# must not be reported as unknown -- a warning that fires on `\section` tells
# the reader nothing.
_STRUCTURE = {
    "documentclass", "usepackage", "begin", "end", "section", "subsection",
    "subsubsection", "paragraph", "chapter", "part", "label", "ref", "cite",
    "index", "footnote", "caption", "item", "title", "author", "date",
    "maketitle", "tableofcontents", "newpage", "clearpage", "pagebreak",
    "hfill", "vfill", "hspace", "vspace", "centering", "raggedright",
    "textbf", "textit", "texttt", "textrm", "textsf", "emph", "bf", "it",
    "tt", "rm", "sf", "sl", "sc", "TeX", "LaTeX", "textwidth", "linewidth",
    "columnwidth", "textheight", "small", "large", "Large", "LARGE", "huge",
    "Huge", "footnotesize", "scriptsize", "tiny", "normalsize", "par",
    "noindent", "input", "include", "url", "href", "verb",
    # escapes this projector emits for TeX specials in prose
    "textasciitilde", "textasciicircum", "textbackslash",
}


# Commands available without loading anything. Not exhaustive for all of TeX,
# but covers everything this projector emits from plain/LaTeX kernel.
PLAIN_TEX = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi",
    "varpi", "rho", "varrho", "sigma", "varsigma", "tau", "upsilon", "phi",
    "varphi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda",
    "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega",
    "sum", "prod", "coprod", "int", "oint", "bigcup", "bigcap", "bigvee",
    "bigwedge", "bigoplus", "bigotimes", "bigodot", "biguplus", "bigsqcup",
    "frac", "sqrt", "overline", "underline", "widehat", "widetilde", "hat",
    "tilde", "bar", "vec", "dot", "ddot", "check", "breve", "acute", "grave",
    "left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl",
    "Bigr", "biggl", "biggr", "Biggl", "Biggr", "langle", "rangle", "lceil",
    "rceil", "lfloor", "rfloor", "backslash",
    "mathrm", "mathbf", "mathit", "mathsf", "mathtt", "mathcal", "boldsymbol",
    "times", "div", "pm", "mp", "cdot", "cdots", "ldots", "vdots", "ddots",
    "circ", "bullet", "star", "ast", "oplus", "ominus", "otimes", "oslash",
    "odot", "cap", "cup", "setminus", "wedge", "vee", "neg", "forall",
    "exists", "nabla", "partial", "infty", "emptyset", "in", "ni", "notin",
    "subset", "supset", "subseteq", "supseteq", "equiv", "sim", "simeq",
    "approx", "cong", "neq", "leq", "geq", "ll", "gg", "prec", "succ",
    "preceq", "succeq", "propto", "perp", "parallel", "mid", "top", "bot",
    "rightarrow", "leftarrow", "leftrightarrow", "Rightarrow", "Leftarrow",
    "Leftrightarrow", "mapsto", "to", "gets", "longrightarrow",
    "longleftarrow", "uparrow", "downarrow", "nearrow", "searrow", "swarrow",
    "nwarrow", "hookrightarrow", "hookleftarrow", "rightharpoonup",
    "rightharpoondown", "rightleftharpoons",
    "log", "ln", "exp", "sin", "cos", "tan", "cot", "sec", "csc", "arcsin",
    "arccos", "arctan", "sinh", "cosh", "tanh", "min", "max", "sup", "inf",
    "lim", "limsup", "liminf", "det", "dim", "ker", "deg", "gcd", "hom",
    "quad", "qquad", "hspace", "vspace", "newpage", "textbackslash",
    "prime", "ell", "Re", "Im", "wp", "aleph", "surd", "angle", "triangle",
    "diamond", "diamondsuit", "heartsuit", "spadesuit", "clubsuit", "flat",
    "sharp", "natural", "dag", "ddag", "S", "P", "copyright", "pounds",
    "dagger", "ddagger", "wr", "amalg", "uplus", "sqcap", "sqcup", "sqsubseteq", "sqsupseteq",
    "vdash", "dashv", "models", "smile", "frown", "asymp", "doteq",
    "triangleleft", "triangleright", "bigtriangleup", "bigtriangledown",
    "not", "colon", "ldotp", "cdotp",
}


_add_mathabx()
