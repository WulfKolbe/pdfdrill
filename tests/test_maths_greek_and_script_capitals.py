r"""maths_chars for the Mathematical Greek block, script capitals, ‖ ⋮ ⋱.

The owner's comparison with bowang/mathml2latex's unicode_map.py
(2026-11-28): 128 of its characters were missing here. They are added with
this table's own conventions, NOT upstream's values (its bold small Greek is
shifted by one from U+1D6D4, and \Alpha, \Omicron, \Nabla are not LaTeX).
The glyph-name table had also given the bold capitals `\Alpha`... with the
bold dropped.
"""
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
m = dm._maths_char


def test_bold():
    assert m("\U0001D6A8") == r"\mathbf{A}"              # bold capital alpha
    assert m("\U0001D6AA") == r"\mathbf{\Gamma}"
    assert m("\U0001D6C1") == r"\boldsymbol{\nabla}"
    assert m("\U0001D6C2") == r"\boldsymbol{\alpha}"
    assert m("\U0001D6D4") == r"\boldsymbol{\sigma}"     # upstream: \tau
    assert m("\U0001D6D5") == r"\boldsymbol{\tau}"       # upstream: \upsilon
    assert m("\U0001D6D7") == r"\boldsymbol{\varphi}"    # φ, as U+03C6
    assert m("\U0001D6DF") == r"\boldsymbol{\phi}"       # ϕ, as U+03D5
    assert m("\U0001D6C6") == r"\boldsymbol{\varepsilon}"
    assert m("\U0001D6DC") == r"\boldsymbol{\epsilon}"
    assert m("\U0001D6D0") == r"\mathbf{o}"
    assert m("\U0001D6B9") == r"\mathbf{\Theta}"


def test_italic():
    assert m("\U0001D6E2") == "A"                        # plain, as Latin
    assert m("\U0001D6E4") == r"\mathit{\Gamma}"
    assert m("\U0001D6FC") == r"\alpha"
    assert m("\U0001D718") == r"\varkappa"


def test_bold_italic():
    assert m("\U0001D71C") == r"\boldsymbol{A}"
    assert m("\U0001D71E") == r"\boldsymbol{\Gamma}"
    assert m("\U0001D736") == r"\boldsymbol{\alpha}"


def test_sans_serif_bold_and_bold_italic_read_as_bold():
    assert m("\U0001D756") == r"\mathbf{A}"
    assert m("\U0001D770") == r"\boldsymbol{\alpha}"
    assert m("\U0001D790") == r"\boldsymbol{A}"
    assert m("\U0001D7C9") == r"\boldsymbol{\varpi}"


def test_the_whole_block_names_no_command_latex_lacks():
    bad = ("\\Alpha", "\\Beta", "\\Epsilon", "\\Zeta", "\\Eta", "\\Iota",
           "\\Kappa", "\\Mu", "\\Nu", "\\Omicron", "\\omicron", "\\Rho",
           "\\Tau", "\\Chi", "\\Nabla")
    for cp in range(0x1D6A8, 0x1D7CA):
        tex = m(chr(cp))
        assert tex != chr(cp), unicodedata.name(chr(cp))
        assert not any(b + "}" in tex or tex == b for b in bad), (hex(cp), tex)


def test_script_capitals():
    for ch in "ℋℐℒℛℬℰℱℳ":
        assert m(ch) == r"\mathcal{%s}" % unicodedata.name(ch)[-1]
    assert m("℘") == r"\wp"                         # named SCRIPT CAPITAL P


def test_double_bar_and_ellipses():
    assert m("‖") == r"\Vert"
    assert m("⋮") == r"\vdots"
    assert m("⋱") == r"\ddots"


def test_the_data_file_carries_them():
    import json
    data = json.loads((Path(dm.__file__).parent / "data" / "texmap.json")
                      .read_text(encoding="utf-8"))["maths_chars"]
    assert data["\U0001D6D4"] == r"\boldsymbol{\sigma}"
    assert data["ℒ"] == r"\mathcal{L}" and data["‖"] == r"\Vert"
