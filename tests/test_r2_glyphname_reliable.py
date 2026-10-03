r"""R2 — a reliability flag for numbered pseudo-names, against psred's fixtures.

CR-pdfminer-single-version R2. The measured defect class is pdfTeX's Type 3 /
PK bitmap fonts, whose `/Differences` names are `a44`, `a97`, `a111`. The fork
returns them faithfully as `glyphname`, so a caller receives something shaped
like an answer that names nothing. psred had to filter them or its "never
guess" test failed.

The acceptance criterion is a pair of real documents, and it is a pair for a
reason — one of them is the trap:

    fixtures/lang/text_t1.pdf   125 glyphs, ALL pseudo-names  -> 0 reliable
    fixtures/t1.pdf             233 glyphs, real CM names     -> all reliable

`t1.pdf` contains REAL glyphs named `a` (21 of them) and `g` (9). A rule
written as `[a-z]\d*` rather than `[a-z]\d+` passes the first document and
fails the second, which is exactly why the criterion names both.

These fixtures live in the psred repo, so the tests skip rather than fail when
it is not checked out beside this one.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfreader.texmap import glyphname_reliable                # noqa: E402

PSRED = Path.home() / "psred"
ALL_PSEUDO = PSRED / "fixtures" / "lang" / "text_t1.pdf"
ALL_REAL = PSRED / "fixtures" / "t1.pdf"
CFF = PSRED / "fixtures" / "cff" / "t1_cff.pdf"


def _glyphs(pdf: Path):
    """[(glyphname, fontname)] for every LTChar, read with layout analysis OFF.

    `laparams=None` matters: pdfminer's layout analysis reorders glyphs, and
    this reads the character stream, not a reading order.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTContainer

    def walk(o):
        if isinstance(o, LTChar):
            yield o
        if isinstance(o, LTContainer):
            for c in o:
                yield from walk(c)

    out = []
    for page in extract_pages(str(pdf), laparams=None):
        for ch in walk(page):
            out.append((ch.glyphname, ch.fontname))
    return out


def _require(pdf: Path):
    if not pdf.exists():
        pytest.skip(f"psred fixture not checked out: {pdf}")
    pytest.importorskip("pdfminer.high_level")


def test_the_pseudo_name_fixture_has_no_reliable_name():
    """`text_t1.pdf` -> 0 reliable. Every name is a pdfTeX bitmap-font index."""
    _require(ALL_PSEUDO)
    glyphs = _glyphs(ALL_PSEUDO)
    assert len(glyphs) == 125, f"fixture changed: {len(glyphs)} glyphs"
    reliable = [(n, f) for n, f in glyphs if glyphname_reliable(n, f)]
    assert reliable == [], (
        "%d name(s) accepted that carry no identity: %s"
        % (len(reliable), reliable[:5]))


def test_the_real_font_fixture_keeps_every_name():
    """`t1.pdf` -> all reliable. THE TRAP: it contains real glyphs named `a`
    and `g`, so a rule that distrusts a bare letter fails here."""
    _require(ALL_REAL)
    glyphs = _glyphs(ALL_REAL)
    assert len(glyphs) == 233, f"fixture changed: {len(glyphs)} glyphs"
    rejected = [(n, f) for n, f in glyphs if not glyphname_reliable(n, f)]
    assert rejected == [], (
        "%d real font name(s) rejected: %s" % (len(rejected), rejected[:5]))
    # and the trap is actually present, or the test proves nothing
    names = {n for n, _ in glyphs}
    assert "a" in names and "g" in names, (
        "the fixture no longer contains the bare-letter names this guards")


def test_the_cff_fixture_behaves_like_the_type1_one():
    """The patch covers CFF (Type 1C) too — same document, same names."""
    _require(CFF)
    rejected = [(n, f) for n, f in _glyphs(CFF) if not glyphname_reliable(n, f)]
    assert rejected == [], rejected[:5]


def test_zapfdingbats_keeps_its_own_numbered_names():
    """`a1`…`a191` are ZapfDingbats' REAL names, so the same string means
    opposite things depending on the font. Exempted by font name rather than
    silently mis-flagged — stated here because no fixture covers it."""
    assert glyphname_reliable("a44", "ABCDEF+ZapfDingbats") is True
    assert glyphname_reliable("a44", "ABCDEF+CMR10") is False


def test_it_is_a_flag_and_not_a_gate():
    """R2 asks for a reliability flag. `untrusted_name` is the function that
    abstains; this one reports and suppresses nothing."""
    from pdfreader.texmap import untrusted_name
    assert glyphname_reliable("a44", "") is False
    assert untrusted_name("ABCDEF+CMR10", "a44") is False
