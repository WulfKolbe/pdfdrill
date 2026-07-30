"""
text_normalize — clean the PRIVATE-USE characters a PDF's own text layer can
carry, before that text reaches the model / llmtext / embeddings.

Why this exists. A PDF may map its glyphs to the Unicode Private Use Area
(U+E000–U+F8FF) through `/ToUnicode`. The text extracts "correctly" — every
extractor agrees — but the codepoints are *font-private*: they carry no meaning
outside that font, and they poison anything downstream that treats text as
language (search, embeddings, an LLM reading `llmtext`).

The concrete case (arXiv 1012.3259, OpenOffice.org 3.2 / Writer): the embedded
OpenSymbol subset maps its stretchy math delimiters into the PUA, so the text
layer yields

    A\\ue09et\\ue09f=A⋅e−ln\\ue09e2\\ue09f⋅t/T h⋅sin\\ue09e2π⋅f ⋅t\\ue083p \\ue09f

which is `A(t)=A·e^(−ln(2)·t/T_h)·sin(2π·f·t + p)`.

VERIFICATION (why these three are facts, not guesses). In the same document the
identity is written twice — once with PUA delimiters and once in plain ASCII
("(X + A) and (X – A)"). Substituting the mapping below turns

    \\ue09esin\\ue09eX\\ue09f\\ue083sin\\ue09eA\\ue09f\\ue09f2=−½⋅cos\\ue09e2X\\ue09f
    −½⋅cos\\ue09e2A\\ue09f\\ue083cos\\ue09eX−A\\ue09f−cos\\ue09eX\\ue083A\\ue09f

into `(sin(X)+sin(A))² = −½·cos(2X) − ½·cos(2A) + cos(X−A) − cos(X+A)` — a
correct trigonometric identity, with the open/close delimiters exactly paired.
Independently, the glyph outlines are a tall narrow 1-contour/8-curve pair (a
stretchy parenthesis and its mirror) and an 11-lineTo cross (a plus).

DELIBERATELY CONSERVATIVE. The PUA is font-private, so a *general* table cannot
exist — the same codepoint means something else in another font. We therefore
map only what has been verified, and an UNKNOWN PUA character is left ALONE and
COUNTED, never guessed at and never silently dropped. `pua_report` makes the
leftovers visible so a new font can be investigated instead of quietly polluting
the corpus.
"""
from __future__ import annotations

from collections import Counter

# Private Use Area (BMP). The supplementary planes (U+F0000+) are not used by
# the fonts we see and are left untouched.
PUA_START = 0xE000
PUA_END = 0xF8FF


def is_pua(ch: str) -> bool:
    """True for a BMP Private-Use-Area character."""
    return len(ch) == 1 and PUA_START <= ord(ch) <= PUA_END


# VERIFIED OpenSymbol (LibreOffice/OpenOffice) mappings — see the module
# docstring for the evidence. Incomplete BY DESIGN: OpenSymbol's E000–E0FF block
# holds many more glyphs; add one only once it is verified the same way.
OPENSYMBOL_PUA: dict[int, str] = {
    0xE09E: "(",   # stretchy left parenthesis
    0xE09F: ")",   # stretchy right parenthesis
    0xE083: "+",   # plus
}

# The default table applied by `normalize_pua`. Keyed by codepoint.
DEFAULT_PUA_MAP: dict[int, str] = dict(OPENSYMBOL_PUA)


def normalize_pua(text: str,
                  mapping: dict[int, str] | None = None) -> tuple[str, Counter]:
    """Replace KNOWN private-use characters with their plain-text equivalents.

    Returns `(clean_text, unmapped)` where `unmapped` counts the PUA codepoints
    that were left as-is because no verified mapping exists. Unknown PUA is
    preserved rather than dropped: losing a character silently is worse than
    carrying a visible one that `pua_report` will surface.
    """
    if not text:
        return text, Counter()
    table = DEFAULT_PUA_MAP if mapping is None else mapping
    unmapped: Counter = Counter()
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if PUA_START <= cp <= PUA_END:
            repl = table.get(cp)
            if repl is None:
                unmapped[cp] += 1
                out.append(ch)                # keep — never invent a meaning
            else:
                out.append(repl)
        else:
            out.append(ch)
    return "".join(out), unmapped


def pua_report(unmapped: Counter) -> str:
    """One prose line naming the PUA codepoints we could not map (or "" when the
    text is clean) — so an unknown font shows up instead of silently degrading
    search/embeddings."""
    if not unmapped:
        return ""
    items = ", ".join(f"U+{cp:04X}×{n}" for cp, n in sorted(unmapped.items()))
    total = sum(unmapped.values())
    return (f"{total} unmapped private-use character(s) remain ({items}) — "
            f"font-private glyphs with no verified plain-text equivalent; they "
            f"are kept verbatim. Add them to text_normalize.OPENSYMBOL_PUA once "
            f"identified.")
