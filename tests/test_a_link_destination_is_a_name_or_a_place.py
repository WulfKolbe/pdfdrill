r"""A link's `dest` is its name, or [page, x, y]; never str() of a PDF object.

lib:3c16fac66fdd p370 wrote `[<PDFObjRef:33>, /'XYZ', 152, 460, None]` into
lines.json and `#[<PDFObjRef:33>, ...]` into the Markdown. The form is
pdfread's (T-0174), so both readers agree.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
from pdfminer.psparser import LIT  # noqa: E402


class _Ref:
    def __init__(self, objid):
        self.objid = objid


def test_named_destinations_are_their_names():
    assert dm._dest_text(b"cite.knuth", None) == "cite.knuth"
    assert dm._dest_text(LIT("sec.2"), None) == "sec.2"
    assert dm._dest_text(None, None) is None


def test_an_explicit_destination_is_page_x_y():
    pm = {33: 4}
    assert dm._dest_text([_Ref(33), LIT("XYZ"), 152, 460.0, None], pm) == "[4, 152, 460]"
    assert dm._dest_text([_Ref(99), LIT("XYZ"), 152.5, 460, None], pm) == "[null, 152.5, 460]"
    assert dm._dest_text([_Ref(33), LIT("Fit")], pm) == "[4, null, null]"
    assert dm._dest_text([2, LIT("XYZ"), 0, 0, 0], pm) == "[3, 0, 0]"


def test_an_explicit_destination_is_no_markdown_anchor():
    from pdfreader import project_mmd as pm
    ln = dm.LinkNode(rect=(0, 0, 1, 1), uri=None, dest="[4, 152, 460]")
    assert pm._link_target(ln) is None
    ln = dm.LinkNode(rect=(0, 0, 1, 1), uri=None, dest="sec.2")
    assert pm._link_target(ln) == "#sec.2"
