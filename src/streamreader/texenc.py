# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Glyph names of Computer Modern by character code: TeX's encodings.

Some producers (xdvipdfmx with CFF fonts) embed Knuth's fonts without
glyph names and without a ToUnicode map, so pdfminer knows a glyph only by
its code, "(cid:20)". pdftotext reads the names out of the font program;
for these fonts the code says as much, since every cmsy10 sets its codes
in the same order (OMS), every cmmi10 in OML, cmex10 in OMX and the text
fonts in OT1.
"""
from __future__ import annotations

import re

_UPPER = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
_LOWER = [chr(c) for c in range(ord("a"), ord("z") + 1)]
_DIGITS = ("zero one two three four five six seven eight nine").split()
_GREEK_UPPER = "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split()

OMS = ("minus periodcentered multiply asteriskmath divide diamondmath "
       "plusminus minusplus circleplus circleminus circlemultiply "
       "circledivide circledot circlecopyrt openbullet bullet "
       "equivasymptotic equivalence reflexsubset reflexsuperset lessequal "
       "greaterequal precedesequal followsequal similar approxequal "
       "propersubset propersuperset lessmuch greatermuch precedes follows "
       "arrowleft arrowright arrowup arrowdown arrowboth arrownortheast "
       "arrowsoutheast similarequal arrowdblleft arrowdblright arrowdblup "
       "arrowdbldown arrowdblboth arrownorthwest arrowsouthwest proportional "
       "prime infinity element owner triangle triangleinv negationslash "
       "mapsto universal existential logicalnot emptyset Rfractur Ifractur "
       "latticetop perpendicular aleph").split() + _UPPER + (
       "union intersection unionmulti logicaland logicalor turnstileleft "
       "turnstileright floorleft floorright ceilingleft ceilingright "
       "braceleft braceright angbracketleft angbracketright bar bardbl "
       "arrowbothv arrowdblbothv backslash wreathproduct radical coproduct "
       "nabla integral unionsq intersectionsq subsetsqequal supersetsqequal "
       "section dagger daggerdbl paragraph club diamond heart spade").split()

OML = _GREEK_UPPER + (
    "alpha beta gamma delta epsilon1 zeta eta theta iota kappa lambda mu nu "
    "xi pi rho sigma tau upsilon phi chi psi omega epsilon theta1 pi1 rho1 "
    "sigma1 phi1 arrowlefttophalf arrowleftbothalf arrowrighttophalf "
    "arrowrightbothalf arrowhookleft arrowhookright triangleright "
    "triangleleft").split() + [d + "oldstyle" for d in _DIGITS] + (
    "period comma less slash greater star partialdiff").split() + _UPPER + (
    "flat natural sharp slurbelow slurabove lscript").split() + _LOWER + (
    "dotlessi dotlessj weierstrass vector tie").split()

OMX = ("parenleftbig parenrightbig bracketleftbig bracketrightbig "
       "floorleftbig floorrightbig ceilingleftbig ceilingrightbig "
       "braceleftbig bracerightbig angbracketleftbig angbracketrightbig "
       "vextendsingle vextenddouble slashbig backslashbig parenleftBig "
       "parenrightBig parenleftbigg parenrightbigg bracketleftbigg "
       "bracketrightbigg floorleftbigg floorrightbigg ceilingleftbigg "
       "ceilingrightbigg braceleftbigg bracerightbigg angbracketleftbigg "
       "angbracketrightbigg slashbigg backslashbigg parenleftBigg "
       "parenrightBigg bracketleftBigg bracketrightBigg floorleftBigg "
       "floorrightBigg ceilingleftBigg ceilingrightBigg braceleftBigg "
       "bracerightBigg angbracketleftBigg angbracketrightBigg slashBigg "
       "backslashBigg slashBig backslashBig parenlefttp parenrighttp "
       "bracketlefttp bracketrighttp bracketleftbt bracketrightbt "
       "bracketleftex bracketrightex bracelefttp bracerighttp braceleftbt "
       "bracerightbt braceleftmid bracerightmid braceex arrowvertex "
       "parenleftbt parenrightbt parenleftex parenrightex angbracketleftBig "
       "angbracketrightBig unionsqtext unionsqdisplay contintegraltext "
       "contintegraldisplay circledottext circledotdisplay circleplustext "
       "circleplusdisplay circlemultiplytext circlemultiplydisplay "
       "summationtext producttext integraltext uniontext intersectiontext "
       "unionmultitext logicalandtext logicalortext summationdisplay "
       "productdisplay integraldisplay uniondisplay intersectiondisplay "
       "unionmultidisplay logicalanddisplay logicalordisplay coproducttext "
       "coproductdisplay hatwide hatwider hatwidest tildewide tildewider "
       "tildewidest bracketleftBig bracketrightBig floorleftBig "
       "floorrightBig ceilingleftBig ceilingrightBig braceleftBig "
       "bracerightBig radicalbig radicalBig radicalbigg radicalBigg "
       "radicalbt radicalvertex radicaltp arrowvertexdbl arrowtp arrowbt "
       "bracehtipdownleft bracehtipdownright bracehtipupleft "
       "bracehtipupright arrowdbltp arrowdblbt").split()

OT1 = _GREEK_UPPER + (
    "ff fi fl ffi ffl dotlessi dotlessj grave acute caron breve macron ring "
    "cedilla germandbls ae oe oslash AE OE Oslash suppress exclam "
    "quotedblright numbersign dollar percent ampersand quoteright "
    "parenleft parenright asterisk plus comma hyphen period slash").split() + (
    _DIGITS) + ("colon semicolon exclamdown equal questiondown question "
                "at").split() + _UPPER + (
    "bracketleft quotedblleft bracketright circumflex dotaccent "
    "quoteleft").split() + _LOWER + (
    "endash emdash hungarumlaut tilde dieresis").split()

assert len(OMS) == len(OML) == len(OMX) == len(OT1) == 128

# by the family of the font's name (subset tag and size gone)
_FAMILIES = (
    (re.compile(r"^(CMSY|CMBSY|LMMATHSYMBOLS)"), OMS),
    (re.compile(r"^(CMMIB?|LMMATHITALIC)"), OML),
    (re.compile(r"^(CMEX|LMMATHEXTENSION)"), OMX),
    (re.compile(r"^CM(R|BX|SL|SS|SSBX|SSI|DUNH|B|FIB|BXSL|U|CSC|TI|BXTI)\d"), OT1),
)
_cache: dict[str, tuple | None] = {}


def name_of(fontname: str, code: int) -> str:
    """The glyph name code `code` has in the font's TeX encoding; "" where
    the font is none of Knuth's or the code is out of range."""
    table = _cache.get(fontname, ())
    if table == ():
        bare = re.sub(r"^[A-Z]{6}\+", "", fontname).upper().replace("-", "")
        table = next((t for pattern, t in _FAMILIES if pattern.match(bare)),
                     None)
        _cache[fontname] = table
    if table is None or not 0 <= code < 128:
        return ""
    return table[code]
