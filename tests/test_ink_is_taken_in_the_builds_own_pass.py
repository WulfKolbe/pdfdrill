r"""SPEED (EXACT), board 118 option (d): the build's own interpreter pass makes
the same ink records `ink_boxes` makes, so `attach_ink` needs no second pass.

The twin is `ink_boxes` itself: for each page, the records the build's pass
collects (`_pages_with_order(..., ink=True)`) equal the ones a separate pass
returns, field for field and in drawing order. The 24 born board pages'
readings were byte-identical with and without the second pass.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

IB = pytest.importorskip("pdfreader.inkboxes")
pytest.importorskip("fontTools")
from pdfreader import docmodel_six as dm  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows"


@pytest.mark.parametrize("name", ["r00.pdf", "r01.pdf"])
def test_the_builds_records_equal_a_separate_pass(name):
    pdf = str(FIX / name)
    pairs = list(dm._pages_with_order(pdf, None, ink=True))
    assert pairs
    for i, (_lay, _seen, recs) in enumerate(pairs):
        assert recs is not None
        assert recs == IB.ink_boxes(pdf, i + 1)


def test_without_ink_the_pass_yields_what_it_did():
    pairs = list(dm._pages_with_order(str(FIX / "r00.pdf"), None))
    assert all(len(t) == 2 for t in pairs)
