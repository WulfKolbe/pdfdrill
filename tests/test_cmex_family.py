r"""
852 — CMEX is a FAMILY, not a substring, and the name arrives in six shapes.

`untrusted_name` abstains from a glyph name when the font cannot legitimately
carry it: most TeX maths fonts in a dvips PDF have no /Encoding, pdfminer falls
back to StandardEncoding, and the glyph-identity fork reports that fallback as if
it were the font's own name — so `\pi^{*}(\omega_0)` read as `\pi^{*}p\omega_0q`.
A confident wrong answer, which is the failure this project exists to avoid.

The gate was `_NO_LATIN.match("CMEX\d*")`, anchored. Safe, and incomplete: it
missed the dvips spelling and the double subset tag.

THE OBVIOUS FIX WOULD HAVE BEEN WRONG, which is why this file exists. Switching
to `.search()` catches both AND catches `Yhcmex` (yhmath) and `lcmex8` (lxfonts)
— extension fonts by NAME, ordinary alphabets by CONTENT. inkdrill measured the
Type 1 programs against StandardEncoding's 149 names:

    cmex10/9/8/7   141 glyphs each,   1 standard name:  space
    cmexb10        128 glyphs,        0
    yhcmex         262 glyphs,      149   A AE B C D ...
    lcmex8         128 glyphs,      122   A B C D E F ...
    cmr10          132 glyphs,      113   — why the rule must not spread one family

Five documents in this library embed yhmath; `1712.05204` and
`annals-v174-n3-p05-s` carry `YINZZB+Yhcmex` and `BSQKFK+Yhcmex`. A substring
test marks every `A`, `B` and `C` in them untrusted.

Every fixture below is a real string from this corpus's `probe-pdffonts.txt`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest                                                  # noqa: E402

pytest.importorskip("pdfminer")

from pdfreader.texmap import is_cmex_family, untrusted_name     # noqa: E402

#: counts are instances in ~/pdfdrill-library's probes
REAL_CMEX = [
    "CMEX10", "CMEX9", "CMEX8", "CMEX7",      # 1,496
    "cmex9", "Cmex10",                        # case varies
    "TeX-cmex9", "TeX-cmex8", "TeX-cmex7",    # 26, dvips
    "VpqhhbCMEX10", "RkgmpsCMEX10",           # 4, a tag glued on after one strip
    "XfbxxqCMEX10", "YyrfbsCMEX10",
    "CMEX102", "CMEX1048",                    # INSTANCE COUNTER, not a point size
    "CMEX10~154",                             # tilde and a number
    "cmexb10",                                # bold extension
    "ABCDEF+CMEX10", "GGHPMO+VpqhhbCMEX10",   # with the outer subset tag
]

NOT_CMEX = [
    "Yhcmex", "yhcmex", "Yhcmex10",   # yhmath: 149 standard names
    "lcmex8",                         # lxfonts: 122
    "CMR10", "CMMI10", "CMSY10",      # 113 / 59 / 37 — must never be distrusted
    "cmex",                           # no size: not a real TeX font
]


@pytest.mark.parametrize("name", REAL_CMEX)
def test_every_real_shape_is_recognised(name):
    assert is_cmex_family(name), name


@pytest.mark.parametrize("name", NOT_CMEX)
def test_no_lookalike_is_recognised(name):
    assert not is_cmex_family(name), name


def test_the_substring_fix_would_have_broken_yhmath():
    """The near-miss, kept as a test so it cannot be reintroduced: a
    name-contains test passes every one of these."""
    for name in ("Yhcmex", "lcmex8", "Yhcmex10"):
        assert "cmex" in name.lower()
        assert not is_cmex_family(name)


def test_space_is_a_real_glyph_in_cmex_and_is_kept():
    """The one StandardEncoding name all four sizes legitimately carry.
    Distrusting it discards every space in every large-operator run."""
    assert untrusted_name("ABCDEF+CMEX10", "space") is False


def test_a_latin_letter_from_cmex_is_distrusted():
    """cmex names its glyphs `summationdisplay`, `parenleftbig`,
    `bracketrightBigg` — never `A`. A letter is the fallback, not the truth."""
    assert untrusted_name("ABCDEF+CMEX10", "A") is True
    assert untrusted_name("OZBJDZ+TeX-cmex7", "A") is True
    assert untrusted_name("GGHPMO+VpqhhbCMEX10", "A") is True


def test_a_latin_letter_from_yhmath_is_TRUSTED():
    """THE DOCUMENTS THE SUBSTRING FIX WOULD HAVE CORRUPTED."""
    assert untrusted_name("YINZZB+Yhcmex", "A") is False
    assert untrusted_name("BSQKFK+Yhcmex", "B") is False


def test_the_ordinary_cm_text_families_are_never_touched():
    """cmr10 has 113 StandardEncoding names and they are all real."""
    for font in ("ABCDEF+CMR10", "ABCDEF+CMMI10", "ABCDEF+CMSY10"):
        assert untrusted_name(font, "A") is False
        assert untrusted_name(font, "quotedblleft") is False


def test_a_real_cmex_glyph_name_is_trusted():
    for name in ("summationdisplay", "parenleftbig", "bracketrightBigg",
                 "radicalBigg", "integraldisplay"):
        assert untrusted_name("ABCDEF+CMEX10", name) is False
