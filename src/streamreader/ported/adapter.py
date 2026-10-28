# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""psred's atom and bar dicts, built from pdf2mmd2's flat glyph arrays.

psred works in PDF points with y upward; the arrays are page pixels with y
downward. y is flipped about a fixed height well above any page, so that
baselines stay positive: psred's parser reads "above" as base > 0 when a
formula has no full-size glyph on its main line.
"""
from __future__ import annotations

import re

from .. import mathtex
from ..bboxlayout import PX_PER_PT
from ..glyphs import Glyphs, Rules
from . import tfm
from .mathsym import tok


# pdfminer names a digit by its Adobe glyph name; psred's own decoder
# handed its token function the character.
_DIGITS = dict(zip("zero one two three four five six seven eight nine".split(),
                   "0123456789"))


_TOP = 20000.0          # page pixels: above the bottom of any page


def family(font_base: str) -> str:
    """'GVCUCT+NimbusRomNo9L-Medi' -> 'NimbusRomNo9L'; 'X+CMR10' -> 'CMR'.
    (psred lines.family)"""
    f = (font_base or "").split("+")[-1].split("-")[0]
    return re.sub(r"\d+$", "", f)


def _tok(name: str, font: str) -> tuple[str, str, bool]:
    """psred's token for a glyph, also where its table stops: sized
    delimiters and big operators are the same in every extension font as
    in CMEX (the third value says the glyph was read as CMEX's), and names
    it lacks may be in ours."""
    tex, cls = tok(name, font)
    if tex.endswith("{}"):
        again = tok(name, "CMEX10")
        if not again[0].endswith("{}"):
            return *again, True
        # a big operator of another mathematics font ('integral.disp' of
        # MnSymbol, symmetry-12-00975): an operator in every style, but
        # standing on the baseline, not hung from its top as CMEX's
        # audit 2026-10-18: not a name CMSY sets as a binary operator -
        # txfonts' and pxfonts' 'unionsq', 'unionmulti', 'coproduct' are
        # \sqcup, \uplus, \amalg, not \bigsqcup, \biguplus, \coprod
        again = tok(name + "text", "CMEX10")
        if again[1] == "bigop" and tok(name, "CMSY10")[1] != "bin":
            return *again, False
        if name in mathtex.NAMES:
            return mathtex.NAMES[name], "ord", name in _EXTENSION
    return tex, cls, False


_ACCENT_CHARS = {"\u0302": "circumflex", "\u0303": "tilde",
                 "\u0304": "macron", "\u0305": "macron",
                 "\u0307": "dotaccent", "\u0308": "dieresis",
                 "\u030c": "caron", "\u0306": "breve", "\u20d7": "vector",
                 "\u0301": "acute", "\u0300": "grave", "\u030a": "ring"}
_EXTENSION_FONT = re.compile(
    r"^(CMEX|MTEX(NC)?|MT2EX[A-Z]|[NR]?[TP]XEXA?S?|BLEX)\d*$|Extension", re.I)
_EXTENSION = frozenset(("vextendsingle", "vextenddouble", "barex"))


def atoms(g: Glyphs, rules: Rules | None = None,
          ids: list[int] | None = None) -> tuple[list[dict], list[dict]]:
    """(atoms, bars) as psred's `mathparse.atoms_from_marks` returns them,
    for the glyphs `ids` (default: all with ink) and all the page's rules."""
    from . import mathparse

    k = PX_PER_PT
    out: list[dict] = []
    seq_in_op: dict[int, int] = {}
    for i in (range(g.n) if ids is None else ids):
        if not g.text[i].strip() and g.name[i] in ("", "space"):
            continue
        font = mathtex.bare(g.fonts[g.font[i]].split("+")[-1])
        # a glyph named by its code point gets the name TeX's fonts use;
        # one with no name at all is named from its character
        given = g.name[i]
        char = g.text[i]
        nameless = (not given and len(char) == 1 and char != mathtex.UNKNOWN
                    and not 0xE000 <= ord(char) <= 0xF8FF)
        if nameless:
            given = ("uni%04X" if ord(char) < 0x10000 else "u%X") % ord(char)
        elif "." in given[1:]:
            given = given.split(".")[0]     # 'y.alt', 'summationdisplay.1'
        name, text, alphabet = mathtex.canonical(
            given, char,
            lambda n: not _tok(n, font)[0].endswith("{}"))
        if char in _ACCENT_CHARS and not given.isalpha():
            name = _ACCENT_CHARS[char]      # 'uni0303': a combining tilde
        tex, cls, extension = _tok(_DIGITS.get(name, name), font)
        if tex.endswith("{}") and name[-1:].isdigit():
            # 'Delta1': the same letter in the font's second cut
            again = _tok(name.rstrip("0123456789"), font)
            if not again[0].endswith("{}") and len(name.rstrip(
                    "0123456789")) > 1:
                tex, cls, extension = again
        if tex.endswith("{}") and tex != "\\xrightarrow{}":
            # no table has the name: the character says what it is
            if mathtex.UNICODE.get(text) is not None:
                tex = mathtex.UNICODE[text]
                if not tex:
                    continue
            elif (len(text) == 1 and text.isprintable() and text != (
                    mathtex.UNKNOWN) and not 0xE000 <= ord(text) <= 0xF8FF):
                tex = mathtex._ESCAPE.sub(lambda m: "\\" + m.group(0), text)
        # psred's table knows the Computer Modern families; a letter of an
        # alphabet font (Fraktur, bold italic, script) keeps its alphabet
        kind = mathtex.font_class(g.fonts[g.font[i]])
        if nameless:
            kind = alphabet or kind
        elif name != g.name[i] and len(name) == 1:
            # the code point says which alphabet, the font no longer does
            kind = alphabet
            if name.isalpha():
                tex, cls = name, "ord"
        letter = len(text) == 1 and text.isalpha() and text.isascii()
        if kind in mathtex._ALPHABET and letter:
            tex, cls = f"{mathtex._ALPHABET[kind]}{{{text}}}", "ord"
        elif cls == "rm" and letter and kind == "italic":
            cls = "ord"                 # any mathematics italic, not only CMMI
        elif cls == "rm" and letter and kind == "symbol" and text.isupper():
            tex, cls = f"\\mathcal{{{text}}}", "ord"
        if len(tex) == 1 and tex.isalpha() and tex.isascii() and not kind:
            # a text font: its name says whether the letter is upright
            style = mathtex.font_style(g.fonts[g.font[i]])
            if style == "italic":
                cls = "ord"
            elif style:
                tex, cls = f"{mathtex.STYLED[style]}{{{tex}}}", "ord"
        metrics = tfm.metrics(font, name)
        seq = seq_in_op.get(g.op[i], 0)
        seq_in_op[g.op[i]] = seq + 1
        x0, x1 = g.x0[i] / k, g.x1[i] / k
        if cls == "accent" and x1 - x0 < 0.2 * g.size[i]:
            # a combining mark has no advance; the parser finds the letter
            # an accent stands over by how far the two overlap
            x0, x1 = x0 - 0.15 * g.size[i], x0 + 0.15 * g.size[i]
        atom = dict(
            tex=tex, cls=cls, x0=x0, x1=x1,
            base=(_TOP - g.base[i]) / k, size=g.size[i],
            ic=(metrics["ic"] * g.size[i]) if metrics else 0.0,
            # the TFM width: says the font's metrics are known (T-0037)
            wd=(metrics["wd"] * g.size[i]) if metrics else None,
            op=g.op[i], seq=seq,
            fam="CMEX" if extension or _EXTENSION_FONT.search(font)
            else family(font))
        if cls == "bigop" and atom["fam"] in ("CMEX", "CMSY"):
            # A big operator's origin is at its top, not on the row's
            # baseline; where its middle is tells which row it stands in.
            # From the font metrics, else what cmex10's operators average.
            mid = ((metrics["ht"] - metrics["dp"]) / 2 if metrics else -0.6)
            atom["axis"] = atom["base"] + mid * g.size[i]
        out.append(atom)
    bars = []
    if rules is not None:
        for j in range(rules.n):
            bars.append(dict(x0=rules.x0[j] / k, x1=rules.x1[j] / k,
                             y=(_TOP - rules.y[j]) / k, op=-1, seq=0))
    return mathparse._join_arrows(out), bars


_DELIMITERS = frozenset(("(", ")", "[", "]", "\\{", "\\}", "|", "\\|", "/",
                         "\\langle", "\\rangle", "\\lfloor", "\\rfloor",
                         "\\lceil", "\\rceil", "\\backslash"))
_BIG = {"open": "openbig", "close": "closebig"}


def join_stacks(atoms: list[dict]) -> list[dict]:
    """The atoms of one row with every tall delimiter as one atom that
    stands on the row. An extension font sets a delimiter with its origin
    at its top, and a very tall one as pieces one below the other at the
    same x: read by their baselines the pieces are scripts of each other.
    The row splitter needs the pieces, so this comes after it."""
    def tall(a: dict) -> bool:
        return a.get("fam") == "CMEX" and a["tex"] in _DELIMITERS

    out: list[dict] = []
    stacks: list[dict] = []
    for a in atoms:
        if not tall(a):
            out.append(a)
            continue
        top = next((t for t in stacks if abs(t["x0"] - a["x0"]) < 0.5
                    and t["tex"] == a["tex"]), None)
        if top is None:
            top = dict(a)
            if a["cls"] in _BIG:
                top["cls"] = _BIG[a["cls"]]
            else:
                top["fixed"] = True
            stacks.append(top)
            out.append(top)
        else:
            top["base"] = max(top["base"], a["base"])
    return out


def encoding_glyphs(g: Glyphs, page_height_px: float) -> list[dict]:
    """featjudge's glyph dicts for `encoding.relate`, as `synth.extract(pdf,
    ink=True)` returns them: name (the character), x0, x1, base, size in PDF
    points with y upward, `ink` (x0, y0, x1, y1) or None, `glyph` (the font
    glyph name) or None. Glyphs without ink of their own (spaces) are left
    out; the order is synth's, the reverse of the stream."""
    import math
    k = PX_PER_PT
    top = page_height_px / k
    out = []
    for i in range(g.n - 1, -1, -1):
        if not g.text[i].strip():
            continue
        ink = None
        if not math.isnan(g.ix0[i]):
            ink = (g.ix0[i] / k, top - g.iy1[i] / k,
                   g.ix1[i] / k, top - g.iy0[i] / k)
        out.append(dict(name=g.text[i], x0=g.x0[i] / k, x1=g.x1[i] / k,
                        base=top - g.base[i] / k, size=g.size[i],
                        ink=ink, glyph=g.name[i] or None))
    return out
