# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Glyphs to LaTeX, as far as one row of glyphs states it.

A token comes from the glyph's PostScript name, which survives a font
without a Unicode map; the character is only the fallback. Structure is
read from size and position: a smaller glyph above or below the row is a
superscript or subscript of what precedes it. Fractions, radicals and
matrices need the page's rules and are not built here.
"""
from __future__ import annotations

import re
import unicodedata
from .glyphs import Glyphs

# The subset tag: six capitals and a plus sign, or (some producers) words
# of a capital and five consonants set in front of the name with no sign.
_SUBSET = re.compile(r"^(?:[A-Z]{6}\+)?"
                     r"(?:(?:[B-DF-HJ-NP-TV-Z][b-df-hj-np-tv-z]{5})+(?=[A-Z]))?")
_CLASSES = (
    ("bold", re.compile(r"^(CMMIB|CMBSY|MTMIB|MT2BMI[A-Z])\d*$")),
    ("italic", re.compile(r"^(CMMI|LMMI|RTXMI|TXMI|PXMI|NTXMI|MTMI|RMTMI|"
                          r"MT2MI[A-Z]|HFBRMI|NEW[PT]XMI(_GNU)?|"
                          r"TXMIAX?|PXMIAX?|LIBERTINEMATHB?MI|"
                          r"LMMATHITALIC\d*REGULAR|PAZOMATHITALIC|"
                          r"STIXMATHITALIC|TEX_?CM_?MATHS?_?ITALIC)\d*$")),
    ("fraktur", re.compile(r"^(EUFM|EUFB)\d*$")),
    ("blackboard", re.compile(r"^(MSBM|BBM|DSROM|BBOLD)\d*$")),
    ("script", re.compile(r"^(RSFS|EUSM)\d*$")),
    ("symbol", re.compile(r"^(CMSY|CMEX|MSAM|LASY|STMARY|WASY|"
                          r"TXSY[A-C]?[SM]?|TXEX[A-C]?S?|PXSY[A-C]?[SM]?|NTXSY[A-C]?|"
                          r"MTSY[NB]?|MTEX(NC)?|MNSYMBOL[A-F]?|"
                          r"MT2SY[A-Z]|MT2EX[A-Z]|BLEX|HFBRSY|"
                          r"CAMBRIAMATH|"
                          r"LMMATHSYMBOLS\d*REGULAR|"
                          r"LMMATHEXTENSION\d*REGULAR|LATINMODERNMATHREGULAR|"
                          r"STIXMATH(EXTENSIONS)?REGULAR|STIXTWOMATH(REGULAR)?|"
                          r"TEX_?CM_?MATHS?_?(SYMBOLS|EXTENSION))\d*$")),
    # OpenType mathematics (unicode-math), XeTeX adds the encoding
    ("symbol", re.compile(r"^(LIBERTINUSMATH|XITSMATH|NEWCMMATH(BOOK)?|"
                          r"TEXGYRE(TERMES|PAGELLA|BONUM|SCHOLA|DEJAVU)MATH|"
                          r"FIRAMATH|ASANAMATH|GARAMONDMATH|EREWHONMATH|"
                          r"LATINMODERNMATH)(REGULAR|BOOK)?(IDENTITY[HV])?$")),
)
_class_cache: dict[str, str] = {}


def bare(fontname: str) -> str:
    """The font's name without its subset tag."""
    return _SUBSET.sub("", fontname)


def font_class(fontname: str) -> str:
    """'italic', 'bold', 'symbol', 'fraktur', 'blackboard', 'script', or '' for a
    font that also sets prose. Decided by the font family, never by a name
    that merely contains the word math."""
    kind = _class_cache.get(fontname)
    if kind is None:
        family = _SUBSET.sub("", fontname).upper().replace("-", "")
        kind = next((k for k, pat in _CLASSES if pat.match(family)), "")
        _class_cache[fontname] = kind
    return kind


# A text font says its slant and weight in its name only. Families that
# abbreviate (URW's Medi and Ital, Libertine's TB and TI, Computer
# Modern's CMBX and CMTI) are listed; a word inside another is not taken.
_ANY_SUBSET = re.compile(r"^[A-Za-z]{6,}\+|^[A-Z][a-z]+(?:[A-Z][a-z]+)+(?=Times)")
_CM_STYLE = re.compile(r"^CM(BXTI|BXSL|BX|B|TI|SL|SSBX|SSI|ITT|U)\d*$")
# EC and cm-super (LaTeX's T1 Computer Modern): SFRM, SFBX, SFTI, ...
_EC_STYLE = re.compile(r"^(?:EC|SF|TC)(BX|BI|SX|XC|RB|XI|XS|XT|BL|TI|SL|SI|SO|"
                       r"IT|RM|SS|TT|CC|ST|OC)\d*$")
_EC_BOLD = ("BX", "BI", "SX", "XC", "RB", "XI", "XS", "XT", "BL")
_EC_ITALIC = ("TI", "SL", "BI", "SI", "SO", "IT", "XI", "BL")
# a variable font's instance: DMSans9pt_700wght
_WEIGHT = re.compile(r"(?:_|WGHT)(\d{3})(?:WGHT)?$|_(\d{3})WGHT")
_ENCODING = re.compile(r"-IDENTITY-[HV]$")
_LIBERTINE = re.compile(r"^(?:LINLIBERTINE|LINBIOLINUM)[TO]?(Z?)(B?)(I?)\d*$")
_BOLD = re.compile(r"BOLD|DEMI|BLACK|HEAVY|[-_,.](MEDI|BD|B)(?=IT|OBL|I$|$)|"
                   r"-TIBI?$")
_ITALIC = re.compile(r"ITALIC|OBLIQUE|SLANT|KURSIV|ITAL$|[-_,][A-Z]*(IT|OBL)$|"
                     r"[-_,.](B|BD)?I$|-TIB?I$")
_style_cache: dict[str, str] = {}


# fonts that draw: LaTeX's picture lines and circles, xy-pic's arrows.
# Their glyphs are strokes of a figure, not characters
_PICTURE = re.compile(r"^(LINEW?|LCIRCLEW?|XY[A-Z]+)(\d*|-MEDIUM)$")
_picture_cache: dict[str, bool] = {}


def is_picture(fontname: str) -> bool:
    hit = _picture_cache.get(fontname)
    if hit is None:
        hit = _picture_cache[fontname] = bool(
            _PICTURE.match(bare(fontname).upper()))
    return hit


def font_style(fontname: str) -> str:
    """'italic', 'bold', 'bold italic' or '' for a font that sets prose:
    what its name says about slant and weight. A mathematics font has a
    class instead (`font_class`) and no style."""
    style = _style_cache.get(fontname)
    if style is None:
        style = ""
        if not font_class(fontname):
            name = _ENCODING.sub("", _ANY_SUBSET.sub(
                "", _SUBSET.sub("", fontname)).upper())
            cm = _CM_STYLE.match(name)
            ec = _EC_STYLE.match(name)
            lib = _LIBERTINE.match(name.replace("-", ""))
            weight = _WEIGHT.search(name)
            if ec:
                bold = ec.group(1) in _EC_BOLD
                italic = ec.group(1) in _EC_ITALIC
            elif cm:
                bold = cm.group(1).startswith(("B", "SSBX"))
                italic = cm.group(1).endswith(("TI", "SL", "SSI", "ITT", "U"))
            elif lib:
                bold, italic = bool(lib.group(2)), bool(lib.group(3))
            else:
                bold = bool(_BOLD.search(name)) or bool(
                    weight and int(weight.group(1) or weight.group(2)) >= 600)
                italic = bool(_ITALIC.search(name))
            style = " ".join(w for w, on in (("bold", bold),
                                             ("italic", italic)) if on)
        _style_cache[fontname] = style
    return style


_GREEK = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
          "nu xi pi rho sigma tau upsilon phi chi psi omega Gamma Delta Theta "
          "Lambda Xi Pi Sigma Upsilon Phi Psi Omega").split()
NAMES: dict[str, str] = {n: "\\" + n for n in _GREEK}
NAMES.update({
    "epsilon": "\\varepsilon", "epsilon1": "\\epsilon", "theta1": "\\vartheta",
    "pi1": "\\varpi", "rho1": "\\varrho", "sigma1": "\\varsigma",
    "phi1": "\\varphi", "lscript": "\\ell", "weierstrass": "\\wp",
    "partialdiff": "\\partial", "dotlessi": "\\imath", "dotlessj": "\\jmath",
    # relations and operators
    "element": "\\in", "owner": "\\ni", "minus": "-", "plusminus": "\\pm",
    "minusplus": "\\mp", "multiply": "\\times", "divide": "\\div",
    "periodcentered": "\\cdot", "asteriskmath": "*", "openbullet": "\\circ",
    "bullet": "\\bullet", "lessequal": "\\leq", "greaterequal": "\\geq",
    "equivalence": "\\equiv", "similar": "\\sim", "similarequal": "\\simeq",
    "approxequal": "\\approx", "proportional": "\\propto",
    "propersubset": "\\subset", "propersuperset": "\\supset",
    "reflexsubset": "\\subseteq", "reflexsuperset": "\\supseteq",
    "union": "\\cup", "intersection": "\\cap", "circleplus": "\\oplus",
    "circleminus": "\\ominus", "circlemultiply": "\\otimes",
    "logicaland": "\\wedge", "logicalor": "\\vee", "logicalnot": "\\neg",
    "universal": "\\forall", "existential": "\\exists",
    "emptyset": "\\emptyset", "infinity": "\\infty", "nabla": "\\nabla",
    "negationslash": "\\not", "prime": "\\prime", "radical": "\\surd",
    "arrowright": "\\rightarrow", "arrowleft": "\\leftarrow",
    "arrowboth": "\\leftrightarrow", "arrowdblright": "\\Rightarrow",
    "arrowdblleft": "\\Leftarrow", "arrowdblboth": "\\Leftrightarrow",
    "arrowup": "\\uparrow", "arrowdown": "\\downarrow", "mapsto": "\\mapsto",
    "perpendicular": "\\perp", "turnstileleft": "\\vdash",
    "dagger": "\\dagger", "daggerdbl": "\\ddagger", "star": "\\star",
    "diamondmath": "\\diamond", "backslash": "\\backslash",
    "lessmuch": "\\ll", "greatermuch": "\\gg", "precedes": "\\prec",
    "follows": "\\succ", "simequal": "\\simeq", "square": "\\square",
    # delimiters, in every size the extension font carries
    "braceleft": "\\{", "braceright": "\\}", "bar": "|", "bardbl": "\\|",
    "angbracketleft": "\\langle", "angbracketright": "\\rangle",
    "floorleft": "\\lfloor", "floorright": "\\rfloor",
    "ceilingleft": "\\lceil", "ceilingright": "\\rceil",
    # big operators
    "summationdisplay": "\\sum", "summationtext": "\\sum",
    "productdisplay": "\\prod", "producttext": "\\prod",
    "integraldisplay": "\\int", "integraltext": "\\int",
    "contintegraldisplay": "\\oint", "contintegraltext": "\\oint",
    "uniondisplay": "\\bigcup", "uniontext": "\\bigcup",
    "intersectiondisplay": "\\bigcap", "intersectiontext": "\\bigcap",
    "circleplusdisplay": "\\bigoplus", "circleplustext": "\\bigoplus",
    "circlemultiplydisplay": "\\bigotimes", "circlemultiplytext": "\\bigotimes",
    "logicalordisplay": "\\bigvee", "logicalortext": "\\bigvee",
    "logicalanddisplay": "\\bigwedge", "logicalandtext": "\\bigwedge",
    "unionsqdisplay": "\\bigsqcup", "unionsqtext": "\\bigsqcup",
    "circledotdisplay": "\\bigodot", "circledottext": "\\bigodot",
    "unionmultidisplay": "\\biguplus", "unionmultitext": "\\biguplus",
    "coproductdisplay": "\\coprod", "coproducttext": "\\coprod",
    # the rest of Computer Modern's mathematics fonts, by The TeXbook's
    # Appendix F (cmmi10, cmsy10, cmex10)
    "arrowlefttophalf": "\\leftharpoonup",
    "arrowleftbothalf": "\\leftharpoondown",
    "arrowrighttophalf": "\\rightharpoonup",
    "arrowrightbothalf": "\\rightharpoondown",
    "arrowhookleft": "\\lhook", "arrowhookright": "\\rhook",
    "triangleright": "\\triangleright", "triangleleft": "\\triangleleft",
    "flat": "\\flat", "natural": "\\natural", "sharp": "\\sharp",
    "slurbelow": "\\smile", "slurabove": "\\frown",
    "circledivide": "\\oslash", "circledot": "\\odot",
    "circlecopyrt": "\\bigcirc", "equivasymptotic": "\\asymp",
    "precedesequal": "\\preceq", "followsequal": "\\succeq",
    "arrownortheast": "\\nearrow", "arrowsoutheast": "\\searrow",
    "arrownorthwest": "\\nwarrow", "arrowsouthwest": "\\swarrow",
    "triangleinv": "\\bigtriangledown", "Rfractur": "\\Re",
    "Ifractur": "\\Im", "unionmulti": "\\uplus",
    "turnstileright": "\\dashv", "arrowbothv": "\\updownarrow",
    "arrowdblbothv": "\\Updownarrow", "wreathproduct": "\\wr",
    "coproduct": "\\amalg", "unionsq": "\\sqcup",
    "intersectionsq": "\\sqcap", "subsetsqequal": "\\sqsubseteq",
    "supersetsqequal": "\\sqsupseteq",
    "arrowtp": "\\uparrow", "arrowbt": "\\downarrow",
    "arrowdbltp": "\\Uparrow", "arrowdblbt": "\\Downarrow",
    "arrowvertexdbl": "\\|", "radicaltp": "",
    "arrowdblup": "\\Uparrow", "arrowdbldown": "\\Downarrow",
    "section": "\\S", "paragraph": "\\P", "club": "\\clubsuit",
    "diamond": "\\diamondsuit", "heart": "\\heartsuit",
    "spade": "\\spadesuit",
    "bracehtipdownleft": "", "bracehtipdownright": "",
    "bracehtipupleft": "", "bracehtipupright": "",
    "integraltp": "\\int", "integralbt": "", "integralex": "",
})
for _i, _digit in enumerate("zero one two three four five six seven eight "
                            "nine".split()):
    NAMES[_digit + "oldstyle"] = str(_i)
for _base, _tex in (("parenleft", "("), ("parenright", ")"),
                    ("bracketleft", "["), ("bracketright", "]"),
                    ("braceleft", "\\{"), ("braceright", "\\}"),
                    ("angbracketleft", "\\langle"),
                    ("angbracketright", "\\rangle"),
                    ("floorleft", "\\lfloor"), ("floorright", "\\rfloor"),
                    ("ceilingleft", "\\lceil"), ("ceilingright", "\\rceil"),
                    ("slash", "/"), ("backslash", "\\backslash"),
                    ("radical", "\\surd")):
    for _size in ("big", "Big", "bigg", "Bigg"):
        NAMES[_base + _size] = _tex
# A tall delimiter is built from pieces: the top one names it, the rest are
# its extension and say nothing more.
for _base, _tex in (("parenleft", "("), ("parenright", ")"),
                    ("bracketleft", "["), ("bracketright", "]"),
                    ("braceleft", "\\{"), ("braceright", "\\}")):
    NAMES[_base + "tp"] = _tex
    for _piece in ("ex", "bt", "mid"):
        NAMES[_base + _piece] = ""
NAMES.update({"braceex": "", "parenleftex": "", "parenrightex": "",
              "bracketleftex": "", "bracketrightex": "", "arrowvertex": "|",
              "radicalvertex": "", "radicalbt": "\\surd",
              "vextendsingle": "|", "vextenddouble": "\\|", "barex": "|",
              "triangle": "\\triangle",
              "latticetop": "\\top", "ellipsis": "\\ldots",
              "gradient": "\\nabla", "summation": "\\sum",
              "product": "\\prod", "integral": "\\int",
              "dblbracketleft": "\\llbracket",
              "dblbracketright": "\\rrbracket",
              "llbracket": "\\llbracket", "rrbracket": "\\rrbracket"})

UNICODE: dict[str, str] = {
    "−": "-", "∈": "\\in", "≤": "\\leq", "≥": "\\geq", "≠": "\\neq",
    "×": "\\times", "·": "\\cdot", "→": "\\rightarrow", "←": "\\leftarrow",
    "↔": "\\leftrightarrow", "⇒": "\\Rightarrow", "∞": "\\infty",
    "∀": "\\forall", "∃": "\\exists", "∇": "\\nabla", "∂": "\\partial",
    "∑": "\\sum", "∏": "\\prod", "∫": "\\int", "√": "\\surd", "±": "\\pm",
    "∼": "\\sim", "≃": "\\simeq", "≈": "\\approx", "≡": "\\equiv",
    "⊂": "\\subset", "⊆": "\\subseteq", "∪": "\\cup", "∩": "\\cap",
    "⊕": "\\oplus", "⊗": "\\otimes", "∅": "\\emptyset", "′": "\\prime",
    "∗": "*", "◦": "\\circ", "•": "\\bullet", "∧": "\\wedge", "∨": "\\vee",
    "∝": "\\propto", "⟨": "\\langle", "⟩": "\\rangle", "ℓ": "\\ell",
    "µ": "\\mu", "∘": "\\circ", "∣": "\\mid", "∕": "/", "⋅": "\\cdot",
    "∖": "\\backslash", "ℏ": "\\hbar", "∥": "\\|", "≅": "\\cong",
    "⊃": "\\supset", "⊇": "\\supseteq", "↦": "\\mapsto", "∉": "\\notin",
    "≪": "\\ll", "≫": "\\gg", "∓": "\\mp", "⟶": "\\longrightarrow",
    "⇔": "\\Leftrightarrow", "⊥": "\\perp", "†": "\\dagger",
    "∶": ":", "≔": ":=", "″": "\\prime\\prime", "∬": "\\iint",
    "⋆": "\\star", "⊺": "\\intercal", "∙": "\\bullet",
    "⋯": "\\cdots", "…": "\\ldots", "⋮": "\\vdots", "⋱": "\\ddots",
    "∮": "\\oint", "⨁": "\\bigoplus", "⨂": "\\bigotimes",
    "⋃": "\\bigcup", "⋂": "\\bigcap", "ℵ": "\\aleph", "℘": "\\wp",
    "ℜ": "\\Re", "ℑ": "\\Im", "∠": "\\angle", "△": "\\triangle",
    "⊤": "\\top", "¬": "\\neg", "∎": "", "□": "\\square",
    # a tall delimiter in pieces: the top one names it
    "⎛": "(", "⎜": "", "⎝": "", "⎞": ")", "⎟": "", "⎠": "",
    "⎡": "[", "⎢": "", "⎣": "", "⎤": "]", "⎥": "", "⎦": "",
    "⎧": "\\{", "⎨": "", "⎩": "", "⎪": "", "⎫": "\\}", "⎬": "", "⎭": "",
}
UNICODE.update({chr(0x3B1 + i): "\\" + n for i, n in enumerate(
    "alpha beta gamma delta varepsilon zeta eta theta iota kappa lambda mu "
    "nu xi omicron pi rho varsigma sigma tau upsilon phi chi psi omega"
    .split()) if n != "omicron"})

# characters named by texenc and OpenType mathematics
for _char, _tex in {
        "⩽": "\\leqslant", "⩾": "\\geqslant", "≺": "\\prec", "≻": "\\succ",
        "⪯": "\\preceq", "⪰": "\\succeq", "⊑": "\\sqsubseteq",
        "⊒": "\\sqsupseteq", "⊔": "\\sqcup", "⊓": "\\sqcap", "⊢": "\\vdash",
        "⊣": "\\dashv", "⊎": "\\uplus", "≀": "\\wr", "∐": "\\coprod",
        "⊖": "\\ominus", "⊘": "\\oslash", "⊙": "\\odot", "≍": "\\asymp",
        "⋄": "\\diamond", "▷": "\\triangleright", "◁": "\\triangleleft",
        "▽": "\\bigtriangledown", "↪": "\\hookrightarrow",
        "↩": "\\hookleftarrow", "⇀": "\\rightharpoonup",
        "↼": "\\leftharpoonup", "⇁": "\\rightharpoondown",
        "↽": "\\leftharpoondown", "♭": "\\flat", "♮": "\\natural",
        "♯": "\\sharp", "⌣": "\\smile", "⌢": "\\frown", "ϵ": "\\epsilon",
        "ϖ": "\\varpi", "ϱ": "\\varrho", "↗": "\\nearrow", "↘": "\\searrow",
        "↖": "\\nwarrow", "↙": "\\swarrow", "⌊": "\\lfloor", "⌋": "\\rfloor",
        "⌈": "\\lceil", "⌉": "\\rceil", "‖": "\\|", "↕": "\\updownarrow",
        "⇕": "\\Updownarrow", "∋": "\\ni", "↑": "\\uparrow",
        "↓": "\\downarrow", "⇐": "\\Leftarrow", "⇑": "\\Uparrow",
        "⇓": "\\Downarrow", "⟹": "\\Longrightarrow", "⟸": "\\Longleftarrow",
        "⟺": "\\Longleftrightarrow", "⟵": "\\longleftarrow",
        "⟼": "\\longmapsto", "∤": "\\nmid", "⊊": "\\subsetneq",
        "⨄": "\\biguplus", "⨀": "\\bigodot", "⨆": "\\bigsqcup",
        "⋀": "\\bigwedge", "⋁": "\\bigvee", "◯": "\\bigcirc"}.items():
    UNICODE.setdefault(_char, _tex)

_ALPHABET = {"fraktur": "\\mathfrak", "blackboard": "\\mathbb",
             "script": "\\mathscr", "bold": "\\boldsymbol",
             "calligraphic": "\\mathcal", "upright bold": "\\mathbf"}
STYLED = {"bold": "\\mathbf", "bold italic": "\\boldsymbol"}
_ESCAPE = re.compile(r"[#$%&_{}]")
UNKNOWN = "�"

# Glyphs whose font gives no character, and the pieces of the extension
# font that build large delimiters: the name says what they are.
CHARS: dict[str, str] = {
    "parenlefttp": "⎛", "parenleftex": "⎜", "parenleftbt": "⎝",
    "parenrighttp": "⎞", "parenrightex": "⎟",
    "parenrightbt": "⎠",
    "bracketlefttp": "⎡", "bracketleftex": "⎢",
    "bracketleftbt": "⎣", "bracketrighttp": "⎤",
    "bracketrightex": "⎥", "bracketrightbt": "⎦",
    "bracelefttp": "⎧", "braceleftmid": "⎨",
    "braceleftbt": "⎩", "braceex": "⎪", "bracerighttp": "⎫",
    "bracerightmid": "⎬", "bracerightbt": "⎭",
    "integraltp": "⌠", "integralbt": "⌡", "integralex": "⎮",
    "radicalbt": "⎷", "radicalvertex": "⎷", "radicaltp": "⎷",
    "arrowvertex": "⏐", "arrowdblvertex": "‖",
    "dotlessj": "ȷ", "suppress": "̵", "visiblespace": "␣",
    "bracehtipdownleft": "⏝", "bracehtipdownright": "⏝",
    "bracehtipupleft": "⏜", "bracehtipupright": "⏜",
    "hatwide": "ˆ", "hatwider": "ˆ", "hatwidest": "ˆ",
    "tildewide": "˜", "tildewider": "˜", "tildewidest": "˜",
    "vector": "⃗", "tie": "⁀",
    # cm-super's TS1 (textcomp): names the glyph list does not know
    "twelveudash": "\u2012", "threequartersemdash": "\u2014",
    "hyphendbl.alt": "\u2e40",
    "guarani": "\u20b2", "peso": "\u20b1", "recipe": "\u211e",
    "gnaborretni": "\u2e18", "discount": "\u2052",
    "Circumflex": "\u02c6", "Tilde": "\u02dc", "Ring": "\u02da",
    "Breve": "\u02d8", "Dotaccent": "\u02d9",
    "tieaccentlowercase": "\u2040", "tieaccentcapital": "\u2040",
    "tieaccentlowercase.new": "\u2040", "tieaccentcapital.new": "\u2040",
}
# Characters of glyphs that have one, by a name the glyph list does not
# know: cmex10's big operators and sized delimiters, cmsy10's and cmmi10's
# symbols (a glyph named by texenc). Not in CHARS, which holds the glyphs
# without a character of their own (pieces, accents) that modules treat
# apart.
NAMED: dict[str, str] = {
    # cmex10's big operators, in text and display size
    **{f"{name}{size}": char for name, char in (
        ("integral", "∫"), ("summation", "∑"), ("product", "∏"),
        ("coproduct", "∐"), ("contintegral", "∮"), ("union", "⋃"),
        ("intersection", "⋂"), ("unionmulti", "⨄"), ("logicaland", "⋀"),
        ("logicalor", "⋁"), ("circledot", "⨀"), ("circleplus", "⨁"),
        ("circlemultiply", "⨂"), ("unionsq", "⨆"))
       for size in ("text", "display")},
    # cmsy10 and cmmi10 names the glyph list does not know (texenc)
    "diamondmath": "⋄", "circleminus": "⊖", "circledivide": "⊘",
    "circledot": "⊙", "circlecopyrt": "◯", "equivasymptotic": "≍",
    "precedesequal": "⪯", "followsequal": "⪰", "lessmuch": "≪",
    "greatermuch": "≫", "follows": "≻", "arrownortheast": "↗",
    "arrowsoutheast": "↘", "similarequal": "≃", "arrownorthwest": "↖",
    "arrowsouthwest": "↙", "prime": "′", "owner": "∋", "triangle": "△",
    "triangleinv": "▽", "negationslash": "̸", "mapsto": "↦",
    "Rfractur": "ℜ", "Ifractur": "ℑ", "latticetop": "⊤", "unionmulti": "⊎",
    "turnstileleft": "⊢", "turnstileright": "⊣", "floorleft": "⌊",
    "floorright": "⌋", "ceilingleft": "⌈", "ceilingright": "⌉",
    "angbracketleft": "⟨", "angbracketright": "⟩", "bardbl": "‖",
    "arrowbothv": "↕", "arrowdblbothv": "⇕", "wreathproduct": "≀",
    "coproduct": "∐", "unionsq": "⊔", "intersectionsq": "⊓",
    "subsetsqequal": "⊑", "supersetsqequal": "⊒",
    "epsilon1": "ϵ", "pi1": "ϖ", "rho1": "ϱ", "arrowlefttophalf": "↼",
    "arrowleftbothalf": "↽", "arrowrighttophalf": "⇀",
    "arrowrightbothalf": "⇁", "arrowhookleft": "↩", "arrowhookright": "↪",
    "triangleright": "▷", "triangleleft": "◁", "star": "⋆", "flat": "♭",
    "natural": "♮", "sharp": "♯", "slurbelow": "⌣", "slurabove": "⌢",
    "lscript": "ℓ",
    **{f"{d}oldstyle": str(k) for k, d in enumerate(
        "zero one two three four five six seven eight nine".split())},
    "vextendsingle": "|", "vextenddouble": "‖", "arrowvertexdbl": "‖",
    "arrowtp": "↑", "arrowbt": "↓", "arrowdbltp": "⇑", "arrowdblbt": "⇓",
    # ... and its delimiters in four sizes
    **{f"{name}{size}": char for name, char in (
        ("parenleft", "("), ("parenright", ")"), ("bracketleft", "["),
        ("bracketright", "]"), ("braceleft", "{"), ("braceright", "}"),
        ("angbracketleft", "⟨"), ("angbracketright", "⟩"),
        ("floorleft", "⌊"), ("floorright", "⌋"), ("ceilingleft", "⌈"),
        ("ceilingright", "⌉"), ("slash", "/"), ("backslash", "\\"),
        ("radical", "√"))
       for size in ("big", "Big", "bigg", "Bigg")},

}
# Knuth's manfnt (The TeXbook, The METAFONTbook): the dangerous bend, the
# exercise triangle, and the METAFONT logo in its two alphabets
FONT_CHARS: dict[str, dict[str, str]] = {"MANFNT": {
    "char7f": "\u2621", "char78": "\u25b8",
    **{f"char{ord(c):x}": c for c in "AEFMNOT"},
    **{f"char{ord(k):x}": v for k, v in zip("hijklmn", "METAFON")},
    **{f"char{ord(k):x}": v for k, v in zip("opqrstu", "METAFON")},
}}


def char_of(fontname: str, name: str) -> str:
    """The character a glyph without one shows, from its font and glyph
    name; "" when neither says."""
    got = FONT_CHARS.get(bare(fontname).upper(), {}).get(name)
    if got is not None:
        return got
    if name in CHARS:
        return CHARS[name]
    if name in NAMED:
        return NAMED[name]
    from pdfminer.glyphlist import glyphname2unicode
    got = glyphname2unicode.get(name, "")
    # Adobe's list maps some names into the private use area
    return "" if any(0xE000 <= ord(c) <= 0xF8FF for c in got) else got


# Fonts built for Unicode mathematics name a glyph by its code point
# ('u1D465' is the italic x, 'uni2223' the divides bar), also in families
# called CMMI or CMSY. The tables here know the names TeX's own fonts use.
_UNINAME = re.compile(r"^(?:uni([0-9A-Fa-f]{4})|u([0-9A-Fa-f]{4,6}))$")
_STYLES = (("DOUBLE-STRUCK", "blackboard"), ("FRAKTUR", "fraktur"),
           ("BLACK-LETTER", "fraktur"), ("SCRIPT", "calligraphic"),
           ("BOLD ITALIC", "bold"), ("BOLD", "upright bold"),
           ("ITALIC", "italic"))
# Computer Modern's names for the Greek variants (AGL has phi and phi1 the
# other way round)
_GREEK_VARIANT = {0x3F5: "epsilon1", 0x3B5: "epsilon", 0x3D5: "phi",
                  0x3C6: "phi1", 0x3D1: "theta1", 0x3D6: "pi1",
                  0x3F1: "rho1", 0x3C2: "sigma1"}
_AGL: dict[str, list[str]] = {}


def _agl() -> dict[str, list[str]]:
    if not _AGL:
        from pdfminer.glyphlist import glyphname2unicode
        for name, char in glyphname2unicode.items():
            _AGL.setdefault(char, []).append(name)
    return _AGL


def canonical(name: str, text: str, known=None) -> tuple[str, str, str]:
    """(name, text, alphabet) for a glyph named by its code point: the
    name TeX's fonts give the character, the plain character, and the
    alphabet the code point itself says ('blackboard', 'bold', ... or '').
    Any other glyph comes back as it is. `known(name)` says whether the
    caller's table has a name; default: this module's."""
    m = _UNINAME.match(name or "")
    if not m:
        return name, text, ""
    char = chr(int(m.group(1) or m.group(2), 16))
    # one step only: the full decomposition folds the lunate epsilon and
    # the straight phi into their variants
    parts = unicodedata.decomposition(char).split()
    plain, alphabet = char, ""
    if len(parts) == 2 and parts[0] == "<font>":
        plain = chr(int(parts[1], 16))
        uname = unicodedata.name(char, "")
        alphabet = next((a for word, a in _STYLES if word in uname), "")
    code = ord(plain)
    if plain.isascii() and plain.isalnum():
        return plain, plain, alphabet
    if code in _GREEK_VARIANT:
        return _GREEK_VARIANT[code], plain, alphabet
    known = known or NAMES.__contains__
    names = _agl().get(plain, [])
    for candidate in names:
        if known(candidate):
            return candidate, plain, alphabet
    if 0x391 <= code <= 0x3C9 and names:
        return names[0], plain, alphabet
    return name, plain, alphabet


def token(kind: str, name: str, text: str) -> str:
    """The LaTeX for one glyph of font class `kind`."""
    if name and (not text or text.startswith("(cid:") or "�" in text
                 or any(ord(c) < 0x20 or 0xE000 <= ord(c) <= 0xF8FF
                        for c in text)):
        # unread: the name says what it is (texenc names nameless glyphs)
        text = char_of("", name) or text
    named, text, alphabet = canonical(name, text)
    if named != name and len(named) == 1:
        # the code point says which alphabet, the font no longer does
        kind = alphabet or ("italic" if kind else kind)
    name = named
    letter = len(text) == 1 and text.isalpha() and text.isascii()
    if letter and kind in _ALPHABET:
        return f"{_ALPHABET[kind]}{{{text}}}"
    if letter and kind == "symbol" and text.isupper() and name == text:
        return f"\\mathcal{{{text}}}"
    if name in NAMES:
        return NAMES[name]
    if text in UNICODE:
        return UNICODE[text]
    if (len(text) == 1 and text.isprintable()
            and not 0xE000 <= ord(text) <= 0xF8FF):
        return _ESCAPE.sub(lambda m: "\\" + m.group(0), text)
    return CHARS.get(name) or UNKNOWN


def is_math(g: Glyphs, i: int) -> bool:
    """A glyph from a font that only sets mathematics. Not a digit: some
    families take the digits of a table or a chart's axis from the
    mathematics italic, and a number alone is no formula."""
    return bool(font_class(g.fonts[g.font[i]])) and g.text[i] not in _DIGITS


_DIGITS = frozenset("0123456789")
_NEUTRAL = frozenset("0123456789=+-()[]/,.:;|<>!*")


def is_neutral(g: Glyphs, i: int) -> bool:
    """A glyph prose and formulas share: digits, brackets, relations set in
    the text font. It is mathematics only next to mathematics."""
    return not is_math(g, i) and g.text[i] in _NEUTRAL


FUNCTIONS = frozenset(
    "sin cos tan cot sec csc sinh cosh tanh arcsin arccos arctan log ln lg "
    "exp det dim ker deg gcd max min sup inf lim arg hom Pr".split())
SCRIPT_SIZE = 0.8       # a script is set at most this x the row's size
SCRIPT_SHIFT = 0.12     # ... and this x the row's height off its centre
_COMMAND = re.compile(r"\\[A-Za-z]+$")


def _join(tokens: list[str]) -> str:
    """Tokens with the spaces LaTeX needs after a command and MathPix puts
    before one."""
    out = ""
    for t in tokens:
        if out:
            command_next = len(t) > 1 and t[0] == "\\" and t[1].isalpha()
            if ((_COMMAND.search(out) and (t[0].isalnum() or command_next))
                    or (command_next and (out[-1].isalnum() or out[-1] == "}"))
                    or (out[-1] == "}" and t[0].isalnum())):
                out += " "
        out += t
    return out


def to_latex(g: Glyphs, glyph_ids: list[int]) -> str:
    """One row of glyphs as LaTeX, with the scripts its sizes show."""
    ids = sorted((i for i in glyph_ids if g.text[i].strip()),
                 key=lambda i: g.x0[i])
    if not ids:
        return ""
    # the row is set in the largest size present; a formula can be mostly
    # scripts, so the commonest size is not it
    main = max(g.size[i] for i in ids)
    row = [i for i in ids if g.size[i] > SCRIPT_SIZE * main] or ids
    heights = sorted(g.y1[i] - g.y0[i] for i in row
                     if font_class(g.fonts[g.font[i]]) != "symbol"
                     or len(row) == 1) or sorted(g.y1[i] - g.y0[i]
                                                 for i in row)
    height = heights[len(heights) // 2]
    centres = sorted((g.y0[i] + g.y1[i]) / 2 for i in row
                     if g.y1[i] - g.y0[i] <= 1.5 * height) or sorted(
        (g.y0[i] + g.y1[i]) / 2 for i in row)
    centre = centres[len(centres) // 2]

    out: list[str] = []
    sub: list[str] = []
    sup: list[str] = []
    word: list[str] = []        # upright letters on the row, so far

    def flush_word() -> None:
        if len(word) == 1:
            out.append("\\mathrm{" + word[0] + "}")
        elif word:
            name = "".join(word)
            out.append("\\" + name if name in FUNCTIONS
                       else "\\operatorname{" + name + "}")
        word.clear()

    def flush() -> None:
        if sub:
            out.append("_{" + _join(sub) + "}")
        if sup:
            out.append("^{" + _join(sup) + "}")
        sub.clear()
        sup.clear()

    for i in ids:
        kind = font_class(g.fonts[g.font[i]])
        tex = token(kind, g.name[i], g.text[i])
        if not tex:
            continue
        small = g.size[i] <= SCRIPT_SIZE * main
        shift = (g.y0[i] + g.y1[i]) / 2 - centre
        if small and shift < -SCRIPT_SHIFT * height:
            flush_word()
            sup.append(tex)
        elif small and shift > SCRIPT_SHIFT * height:
            flush_word()
            sub.append(tex)
        elif not kind and len(tex) == 1 and tex.isalpha() and tex.isascii():
            style = font_style(g.fonts[g.font[i]])
            if style:
                flush_word()
                flush()
                out.append(tex if style == "italic"
                           else f"{STYLED[style]}{{{tex}}}")
                continue
            flush()
            word.append(tex)
        else:
            flush_word()
            flush()
            out.append(tex)
    flush_word()
    flush()
    return _join(out)
