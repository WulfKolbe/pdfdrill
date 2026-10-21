# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), psred/mathsym.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""mathsym - one glyph (name, font) -> (LaTeX token, class).

CONTRACT
    tok(name, font_base) -> (latex, cls)
      cls: 'ord' 'bin' 'rel' 'open' 'close' 'punct' 'bigop' 'radical'
           'rm' (an upright letter from CMR/a text font: part of an operator
           name or \\mathrm run, grouped by the parser)
    Unknown glyph names come back as ('\\\\name{}', 'ord') -- visible, never
    dropped. The FONT decides: 'A' in CMSY is \\mathcal{A}, in CMMI an italic
    A, in CMR/text fonts an upright letter.
Covers Computer Modern (CMR, CMMI, CMSY, CMEX) glyph names as ps2write
writes them; other maths fonts are unverified.
"""
from __future__ import annotations

import re

GREEK = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
         "pi rho sigma tau upsilon phi chi psi omega").split()
UGREEK = "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split()
# pdf2mmd2: in cmmi the glyph `epsilon1` is \epsilon and `epsilon` is
# \varepsilon (typeset $\epsilon\varepsilon$ and read the names back);
# psred had the two the other way round.
VAR = {"epsilon1": "\\epsilon", "epsilon": "\\varepsilon", "theta1": "\\vartheta", "pi1": "\\varpi",
       "rho1": "\\varrho", "sigma1": "\\varsigma", "phi1": "\\varphi"}

SYM = {  # name -> (latex, cls)
    "plus": ("+", "bin"), "minus": ("-", "bin"), "hyphen": ("-", "bin"),
    "equal": ("=", "rel"), "less": ("<", "rel"), "greater": (">", "rel"),
    "multiply": ("\\times", "bin"), "divide": ("\\div", "bin"),
    "periodcentered": ("\\cdot", "bin"), "asteriskmath": ("\\ast", "bin"),
    "plusminus": ("\\pm", "bin"), "minusplus": ("\\mp", "bin"),
    "circleplus": ("\\oplus", "bin"), "circlemultiply": ("\\otimes", "bin"),
    "circledot": ("\\odot", "bin"), "union": ("\\cup", "bin"), "intersection": ("\\cap", "bin"),
    "logicaland": ("\\wedge", "bin"), "logicalor": ("\\vee", "bin"),
    "lessequal": ("\\leq", "rel"), "greaterequal": ("\\geq", "rel"),
    "similar": ("\\sim", "rel"), "approxequal": ("\\approx", "rel"),
    "equivalence": ("\\equiv", "rel"), "proportional": ("\\propto", "rel"),
    "element": ("\\in", "rel"), "owner": ("\\ni", "rel"),
    "propersubset": ("\\subset", "rel"), "propersuperset": ("\\supset", "rel"),
    "reflexsubset": ("\\subseteq", "rel"), "reflexsuperset": ("\\supseteq", "rel"),
    "arrowright": ("\\to", "rel"), "arrowleft": ("\\leftarrow", "rel"),
    "arrowdblright": ("\\Rightarrow", "rel"), "arrowdblboth": ("\\Leftrightarrow", "rel"),
    "arrowboth": ("\\leftrightarrow", "rel"), "mapsto": ("\\mapsto", "rel"),
    "perpendicular": ("\\perp", "rel"), "negationslash": ("\\not", "rel"),
    "infinity": ("\\infty", "ord"), "partialdiff": ("\\partial", "ord"),
    "prime": ("\\prime", "ord"),
    "nabla": ("\\nabla", "ord"), "emptyset": ("\\emptyset", "ord"),
    "universal": ("\\forall", "ord"), "existential": ("\\exists", "ord"),
    "logicalnot": ("\\neg", "ord"), "aleph": ("\\aleph", "ord"), "ell": ("\\ell", "ord"),
    "dotlessi": ("\\imath", "ord"), "dotlessj": ("\\jmath", "ord"),
    "weierstrass": ("\\wp", "ord"), "Rfractur": ("\\Re", "ord"), "Ifractur": ("\\Im", "ord"),
    "comma": (",", "punct"), "period": (".", "ord"), "semicolon": (";", "punct"),
    "colon": (":", "rel"), "slash": ("/", "ord"), "exclam": ("!", "close"),
    "bar": ("|", "ord"), "bardbl": ("\\|", "ord"),
    "parenleft": ("(", "open"), "parenright": (")", "close"),
    "bracketleft": ("[", "open"), "bracketright": ("]", "close"),
    "braceleft": ("\\{", "open"), "braceright": ("\\}", "close"),
    "angbracketleft": ("\\langle", "open"), "angbracketright": ("\\rangle", "close"),
    "floorleft": ("\\lfloor", "open"), "floorright": ("\\rfloor", "close"),
    "ceilingleft": ("\\lceil", "open"), "ceilingright": ("\\rceil", "close"),
    "radical": ("\\sqrt", "radical"), "underscore": ("\\_", "ord"),
}
# maths accents (CMR/CMMI glyphs placed over a nucleus)
ACCENT = {"tilde": "\\tilde", "asciitilde": "\\tilde", "macron": "\\bar", "dotaccent": "\\dot",
          "dieresis": "\\ddot", "acute": "\\acute", "grave": "\\grave", "circumflex": "\\hat",
          "asciicircum": "\\hat", "breve": "\\breve", "caron": "\\check", "ring": "\\mathring",
          "vector": "\\vec"}
# CMEX's wide accents, three sizes each (sigma26-073 EQ0232: 'hatwide'
# was unmapped in psred AND in pdfdrill's reader)
WIDE_ACCENT = {n: "\\widehat" for n in ("hatwide", "hatwider", "hatwidest")}
WIDE_ACCENT.update({n: "\\widetilde" for n in ("tildewide", "tildewider", "tildewidest")})
ASCII = {"+": "plus", "=": "equal", "(": "parenleft", ")": "parenright",
         "[": "bracketleft", "]": "bracketright", ",": "comma", ".": "period",
         "<": "less", ">": "greater", "/": "slash", "-": "hyphen", ";": "semicolon",
         ":": "colon", "!": "exclam", "|": "bar", "_": "underscore"}
BIG = {"integral": "\\int", "summation": "\\sum", "product": "\\prod", "union": "\\bigcup",
       "intersection": "\\bigcap", "contintegral": "\\oint", "coproduct": "\\coprod",
       "circleplus": "\\bigoplus", "circlemultiply": "\\bigotimes",
       # pdf2mmd2: the rest of cmex10's operators (formula 69 of the
       # round-trip sample left \bigwedge as an unmapped name)
       "logicaland": "\\bigwedge", "logicalor": "\\bigvee",
       "unionsq": "\\bigsqcup", "unionmulti": "\\biguplus",
       "circledot": "\\bigodot"}
_BIG = re.compile(r"^(integral|summation|product|union|intersection|contintegral|coproduct|"
                  r"circleplus|circlemultiply|logicaland|logicalor|unionsq|unionmulti|"
                  r"circledot)(text|display)$")
_DELIM = re.compile(r"^(paren|bracket|brace|angbracket|floor|ceiling|slash|backslash)"
                    r"(left|right)?(bigg|Bigg|big|Big|bt|mid|ex|tp)$")   # longest first
_RAD = re.compile(r"^radical(big|Big|bigg|Bigg|bt|vertex|vertical)")


def fam(font_base: str) -> str:
    f = (font_base or "").split("+")[-1].upper()
    for k in ("CMEX", "CMSY", "CMMI", "CMBX", "CMR", "CMTI", "CMSS", "CMTT", "MSBM", "MSAM"):
        if f.startswith(k):
            return k
    return "TEXT"


def tok(name: str, font_base: str):
    f = fam(font_base)
    name = ASCII.get(name, name)
    if f == "CMEX":
        m = _BIG.match(name)
        if m:
            return BIG[m.group(1)], "bigop"
        if _RAD.match(name):
            return "\\sqrt", "radical"
        m = _DELIM.match(name)
        if m:
            base = m.group(1) + (m.group(2) or "")
            if base in SYM:
                tex, cls = SYM[base]
                size = {"big": "big", "Big": "Big", "bigg": "bigg", "Bigg": "Bigg"}.get(m.group(3))
                if size and cls in ("open", "close"):
                    # the size NAME fixes the glyph: \biggl[ draws exactly bracketleftbigg
                    return "\\" + size + ("l" if cls == "open" else "r") + tex, cls + "big"
                return tex, cls
    if f == "CMSY" and re.fullmatch(r"[A-Z]", name):
        return f"\\mathcal{{{name}}}", "ord"
    if f == "MSBM" and re.fullmatch(r"[A-Z]", name):
        return f"\\mathbb{{{name}}}", "ord"
    if name in VAR:                      # pdf2mmd2: before the plain names
        return VAR[name], "ord"
    if name in GREEK:
        return "\\" + name, "ord"
    if name in UGREEK:
        return "\\" + name, "ord"
    if name in VAR:
        return VAR[name], "ord"
    if name in SYM:
        return SYM[name]
    if re.fullmatch(r"[0-9]", name):
        return name, "ord"
    if re.fullmatch(r"[A-Za-z]", name):
        if f == "CMBX":
            return f"\\mathbf{{{name}}}", "ord"      # bold vectors: \\ve q (sigma26-075)
        return name, ("ord" if f in ("CMMI", "CMSY", "MSBM", "MSAM", "CMTI") else "rm")
    if name in ACCENT and f != "CMEX":
        return ACCENT[name], "accent"
    if f == "CMEX" and name in WIDE_ACCENT:        # \widehat / \widetilde (EQ0232)
        return WIDE_ACCENT[name], "accent"
    if name in ("ff", "fi", "fl", "ffi", "ffl"):
        return name, "rm"
    # LaTeX's own declarations (fontmath.ltx, amssymb.sty): AMS glyph names
    # differ from the commands ('defines' = \\triangleq); fallback only
    from . import latexsyms
    hit = latexsyms.table().get((f, name))
    if hit:
        return hit
    return f"\\{name}{{}}", "ord"
