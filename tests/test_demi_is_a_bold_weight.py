r"""`Demi` / `DemiBold` is a bold weight (URW Gothic L, Bookman, Lucida ...).

lib:24ebb7777b90 p263 (held-out draw, inkdrill-11): URWGothicL-Demi3
headings read plain, 67 style findings. All 37 demi stems in texmap.json
are the family's bold.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

texmap = pytest.importorskip("pdfreader.texmap")


@pytest.mark.parametrize("name", [
    "UKTBQM+URWGothicL-Demi3", "X+URWGothicL-Demi", "X+URWBookmanL-DemiBold",
    "X+Optima-DemiBoldItalic", "X+FranklinGothicDemi", "X+LucidaSansOT-DemiItalic",
    "X+AvantGarde-Demi"])
def test_demi_is_bold(name):
    assert texmap.is_bold(name)
    assert r"\textbf" in texmap.emphasis_for({name}, ["a"], True)


@pytest.mark.parametrize("name", [
    "X+URWGothicL-Book", "X+Academica-Regular", "X+Demian-Regular"])
def test_a_demi_inside_a_word_is_not(name):
    assert not texmap.is_bold(name)
