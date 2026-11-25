"""
Shared (cid:N) glyph resolution for born-digital text extraction.

pdfminer emits `(cid:N)` whenever a font gives it no usable /ToUnicode mapping.
That happens overwhelmingly on the LaTeX MATH fonts (CMEX/CMMI/CMSY, Latin
Modern, MT Extra, TX), so the unresolved codes land exactly on the mathematics —
`L(cid:0)x(cid:1)` reaching the model, the markdown and the tiddlers.

The table and resolver below were written for `nodes/ingest_pdfplumber.py` and
stayed there when the born-digital route moved to pdfminer, so the live path
carried the leak while a working fix sat one module away, unused. Keeping them
here — one table, imported by every extractor — is what stops that recurring.
"""
from __future__ import annotations

import re

_CID_MAP: dict[tuple[str, int], str] = {
    # LMMathExtension / CMEX10 — big delimiters
    ("mathextension", 0): "(", ("mathextension", 1): ")",
    ("mathextension", 4): "[", ("mathextension", 5): "]",
    ("mathextension", 12): "|", ("mathextension", 16): "/",
    ("mathextension", 18): "(", ("mathextension", 19): ")",
    ("mathextension", 22): "{", ("mathextension", 23): "}",
    ("mathextension", 26): "{", ("mathextension", 27): "}",
    ("cmex", 0): "(", ("cmex", 1): ")",
    ("cmex", 4): "[", ("cmex", 5): "]",
    ("cmex", 12): "|", ("cmex", 16): "/",
    ("cmex", 18): "(", ("cmex", 19): ")",
    ("cmex", 22): "{", ("cmex", 23): "}",
    ("cmex", 26): "{", ("cmex", 27): "}",
    # LMMathItalic / CMMI
    ("mathitalic", 15): "ε", ("mathitalic", 21): "α",
    ("mathitalic", 22): "β", ("mathitalic", 26): "ζ",
    ("mathitalic", 13): "γ",
    # LMMathSymbols / CMSY
    ("mathsymbol", 0): "−", ("mathsymbol", 16): "·",
    ("mathsymbol", 17): "×", ("mathsymbol", 20): "≤",
    ("mathsymbol", 21): "≥",
    # MathTime II (MT2xxx)
    ("mt2sy", 0): "−", ("mt2sy", 17): "≈", ("mt2sy", 20): "≤",
    ("mt2sy", 21): "≥",
    ("mt2mi", 13): "γ", ("mt2mi", 21): "α", ("mt2mi", 22): "β",
    ("mt2mi", 26): "ζ",
    ("mt2ex", 0): "(", ("mt2ex", 1): ")",
    ("mt2ex", 16): "/", ("mt2ex", 26): "{", ("mt2ex", 27): "}",
    # TX fonts (txex, txexs, txexas, txbex)
    ("txex", 0): "(", ("txex", 1): ")",
    ("txex", 12): "|", ("txex", 26): "{", ("txex", 27): "}",
    ("txex", 101): "∑", ("txex", 205): "∏",
    ("txex", 32): "√",
    # CMEX larger variants
    ("cmex", 17): "/", ("cmex", 104): "{", ("cmex", 105): "}",
    # MT2 additional
    ("mt2mi", 30): "φ", ("mt2mi", 31): "χ",
    ("mt2sy", 1): "·",
    ("mt2ex", 17): "/",
    # LINE10 (horizontal/vertical rules)
    ("line", 0): "—",
}

_CID_RE = re.compile(r"\(cid:(\d+)\)")


def resolve_cid(text: str, fontname: str) -> str:
    """Replace `(cid:N)` glyph codes with their Unicode equivalent.

    Unknown codes are RETURNED VERBATIM, never guessed or dropped: a wrong glyph
    silently corrupts a formula, whereas a visible `(cid:N)` is a legible defect
    that can be counted and reported.
    """
    if "(cid:" not in (text or ""):
        return text

    def sub(m):
        cid = int(m.group(1))
        fn = (fontname or "").lower()
        for (font_key, cid_num), repl in _CID_MAP.items():
            if cid_num == cid and font_key in fn:
                return repl
        return m.group(0)

    return _CID_RE.sub(sub, text)


def unresolved_cids(text: str) -> int:
    """How many `(cid:N)` codes remain — the honest quality signal."""
    return len(_CID_RE.findall(text or ""))


# ---------------------------------------------------------------------------
# Glyph-NAME resolution — the general route.
#
# pdfminer emits (cid:N) for these glyphs not because the PDF is missing
# information, but because the font names them with TeX names
# (`parenrightBig`, `vextenddouble`) that are absent from the Adobe Glyph List,
# so name→Unicode lookup fails. The names ARE in the PDF, in the font's
# /Differences array. Resolving by NAME therefore fixes every TeX font at once,
# instead of one (font, code) pair at a time — the per-font table below stays
# as a fallback for fonts that ship no /Differences.
# ---------------------------------------------------------------------------

# THE TABLE MOVED to `pdfreader.texmap` (B6 items 2+3): the GLYPH reader needs
# it too and could not import from this package. One table, both readers.


def glyph_name_to_char(name: str) -> str:
    """Unicode for a PostScript/TeX glyph name, or "" when unknown.

    Empty for anything unrecognised — the caller then keeps the visible
    `(cid:N)`, because a wrong glyph corrupts a formula silently while a visible
    code is a defect someone can see and count.
    """
    # BOTH TABLES, IN ONE PLACE, AND IN THIS ORDER.
    #
    # The curated TeX table first: it knows `summationdisplay` -> ∑ and the
    # size suffixes, which the Adobe list does not. Then the Adobe list, which
    # is where `macron`, `alpha`, `tau` and `reflexsubset` live — ea51847a:
    # `_resolve_glyph` named `CMR10 cid 22` correctly from the standard CM
    # encoding and this function answered "" because the curated table lacked
    # it, so 145 `(cid:N)` tokens stood in users' markdown with the name in
    # hand.
    #
    # THE ADOBE LIST SEES THE FONT'S OWN NAME ONLY, never a size-stripped one:
    # the strip turns `barex` into `bar`, which the list knows, but `barex` is
    # the EXTENSION PIECE of a tall bar and not a pipe. The curated table owns
    # the stripped route, with the entries measured for it.
    from pdfreader.texmap import tex_name_char, agl_char
    return tex_name_char(name) or agl_char((name or "").lstrip("/"))


def resolve_cid_by_name(text: str, code_to_name: dict) -> str:
    """Resolve `(cid:N)` using this font's own /Differences names."""
    if "(cid:" not in (text or "") or not code_to_name:
        return text

    def sub(m):
        return glyph_name_to_char(code_to_name.get(int(m.group(1)), "")) or m.group(0)

    return _CID_RE.sub(sub, text)


# ---------------------------------------------------------------------------
# 901 — WHEN THE FONT SHIPS NO /Differences.
#
# `resolve_cid_by_name` is the general route and fixes every TeX font at once,
# but it needs names, and it gets them from the PDF's /Differences array. A
# 2000-era dvipdfm file states `Encoding /Builtin` and ships no array at all:
# `pdffonts` on The TeXbook reports `uni no` for all 60-odd fonts, so the names
# channel is empty and 3,100 angle brackets reach the markdown as
# `(cid:104)`/`(cid:105)` — the ⟨⟩ around every syntax rule in the book.
#
# The names are not lost, they are STANDARD: `texmap.CM_ENCODING` already holds
# them, built from 391 (family, cid) pairs measured across 102 documents with
# zero disagreements. This is the third table in this codebase for one problem
# — texmap's, this module's, and a copy inside nodes/ingest_pdfplumber.py —
# which is what this module's own docstring was written to stop. Rather than
# copy the pairs a fourth time, ask texmap.
# ---------------------------------------------------------------------------
def cm_names(fontname: str) -> dict:
    """{code: glyphname} for a Computer Modern font, or {} when unknown.

    `{}` means "this font is not one I can name", which leaves the `(cid:N)`
    standing — a legible defect, never a guessed glyph.
    """
    try:
        from pdfreader import texmap
    except Exception:                                # noqa: BLE001
        return {}
    base = (fontname or "").split("+")[-1].upper()
    for family, table in texmap.CM_ENCODING.items():
        if base.startswith(family):
            return table
    # 902 — manfnt is not Computer Modern and is not in the corpus table; its
    # codes come from the book's own macros and live in their own dict so the
    # two provenances stay apart. Partial on purpose: the codes the source
    # never names are absent, so they still resolve to nothing.
    if base.startswith("MANFNT"):
        return texmap.MANFNT
    return {}
