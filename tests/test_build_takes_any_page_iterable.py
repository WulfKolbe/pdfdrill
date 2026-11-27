r"""
Audit A20: `build` read `pages` several times (counted, membership, indexed),
and a generator was spent by the first read. It is normalised once to a
tuple in document order. A list, tuple, set or generator of the same pages
gives the same document; an unsorted list no longer mislabels pages.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows" / "r00.pdf"


def _sig(pages):
    return [(p.page, len(p.lines), sum(len(l.glyphs) for l in p.lines)) for p in pages]


@pytest.mark.parametrize("make", [list, tuple, set, lambda r: (x for x in r)],
                         ids=["list", "tuple", "set", "generator"])
def test_every_iterable_gives_the_same_document(make):
    ref = _sig(D.build(str(FIX), range(0, 1)))
    assert ref and ref[0][2] > 0
    assert _sig(D.build(str(FIX), make(range(0, 1)))) == ref
