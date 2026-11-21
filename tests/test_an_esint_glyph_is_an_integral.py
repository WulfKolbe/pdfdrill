r"""A font that holds only integral signs does not hold accents.

T-0156, found by inkdrill-10 and settled by rendering the page. On
lib:6d90e8d27b8b p174 the subset `TUJKXG+Gdvdkgesint10` — the `esint`
package's font, which contains integral signs and nothing else — carries no
ToUnicode, so pdfminer falls back to a standard encoding and names its
glyphs `acute` and `circumflex`. The reader believed the names and wrote
accents: that page's L2 reads `'$´ ´$'` and L17 carries a bare `ˆ`.

MEASURED on that page: cid 30 named `acute` ×8, cid 31 named `circumflex`
×7, both in `TUJKXG+Gdvdkgesint10`, box widths 4.53 and 5.33 at 9.6 pt.

THE OUTLINE DECIDES, which is the rule the coordinator fixed after the same
font misled both of us. Rendered at 600 dpi with the project's own cutter
and read:

    cid 31   '∫ x dx = ∫ −t dt'  and  '∫ sin t dt'   a display-size ∫
    cid 30   '∫ dx/x = ∫ 2dt/t'                      the text-size ∫

Both are a plain `\int`; the width difference is the text/display pair that
a `largesymbols` font keeps for one symbol. In LaTeX one writes `\int` and
TeX chooses the size, so both map to `\int`.

WHY THE CID AND NOT THE NAME, AND WHY ONLY TWO. The names are the
subsetter's and they are wrong. The cids are the codes in THIS document's
encoding, so a cid table is document-specific in principle: another
producer's esint subset may number its glyphs differently. Only these two
have been rendered and read, so only these two are mapped, and any other
esint cid keeps today's behaviour.

WHAT IS GENERAL IS THE REFUSAL. An `esint` font contains integral signs and
nothing else, so an accent name from one is not evidence of an accent
whatever the cid. That half applies to every esint subset and removes the
`´`/`ˆ` from the reading even where the symbol cannot yet be named.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

texmap = pytest.importorskip("pdfreader.texmap")


def test_the_two_rendered_cids_are_integrals():
    for cid in (30, 31):
        tok = texmap.project("math-extension", "acute", cid,
                             "TUJKXG+Gdvdkgesint10")
        assert tok.latex == r"\int", (cid, tok)


def test_an_accent_name_from_an_esint_font_is_refused():
    """The general half: the font holds no accents, so the name is not
    evidence. An unmapped esint cid abstains rather than inventing one."""
    tok = texmap.project("math-extension", "circumflex", 99,
                         "TUJKXG+Gdvdkgesint10")
    assert tok.latex != r"\hat", tok
    assert tok.latex is None or tok.latex.startswith("\\int"), tok


def test_an_accent_from_an_ordinary_font_is_still_an_accent():
    """0864's `Saarbr\"ucken` depends on this: a dieresis from a TEXT font
    is a real accent and `_compose_text_accents` needs it."""
    tok = texmap.project("text", "dieresis", 200, "ABCDEF+NimbusRomNo9L-Regu")
    assert tok.latex == r"\ddot", tok
    tok = texmap.project("text", "acute", 194, "ABCDEF+CMR10")
    assert tok.latex == r"\acute", tok


def test_a_font_merely_containing_the_letters_esint_is_not_matched():
    """Scoped to the family name as TeX writes it, so a face called
    `Bluesint` or `Desinto` is untouched."""
    tok = texmap.project("text", "acute", 194, "ABCDEF+Desinto")
    assert tok.latex == r"\acute", tok
