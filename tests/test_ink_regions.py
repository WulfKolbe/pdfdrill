r"""893 — the glyph's MEASURED ink, wired into the region path.

psred's #5: `region` boxes come from pdfminer, which reports the FONT's box —
every glyph of a font is equally tall, which is why a `\bigl(` from CMEX
appears to reach 8 pt into the line above. `inkboxes` reads the embedded
Type 1/CFF program and returns the outline's real extent.

Measured on wzlxjtu-011: the font box is taller than the ink by a median of
4.48 pt and up to 12.28 pt on a 10.9 pt body, and the resulting region is a
median 8 px taller and 5 px wider at 250 dpi.

Three decisions this file pins, each of which could be undone by accident:
the join is on EVIDENCE not order, `region` keeps its old value, and
measuring is off by default because it costs.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader import docmodel_six as dm                      # noqa: E402


def _g(rect, font="CMR10", size=10.0, ink=None):
    return dm.GlyphNode(id="g", page=1, rect=rect, text="x", cid=1,
                        glyphname="x", fontname=font, family="text",
                        size=size, tex=None, ink=ink)


def test_glyph_box_prefers_ink_and_falls_back_to_the_font_box():
    """One place makes that choice, so a region, a crop and a mark cannot
    disagree about which box they meant."""
    assert dm.glyph_box(_g((0, 0, 10, 10))) == (0, 0, 10, 10)
    assert dm.glyph_box(_g((0, 0, 10, 10), ink=(1, 2, 3, 4))) == (1, 2, 3, 4)


def test_an_uncovered_font_keeps_the_font_box_rather_than_a_guess():
    """`inkboxes` returns None for Type 3 and TrueType. A plausible wrong box
    is the one failure that cannot be detected downstream."""
    assert dm.glyph_box(_g((0, 0, 10, 10), ink=None)) == (0, 0, 10, 10)


def test_measuring_is_off_by_default():
    """A cost decision, not a confidence one: `ink_boxes` re-runs pdfminer
    over the page, so measuring doubles the read (1.7x measured). A corpus
    pass is ~6 h and silently making it ~12 h is the operator's call."""
    src = (ROOT / "src/pdfreader/docmodel_six.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PDFDRILL_INK_REGIONS", "")' in src
    assert "ink: \"bool | None\" = None" in src, "build() must take ink="


def test_the_join_is_on_evidence_not_on_order():
    r"""psred left this exact assumption open: "assumes pdfminer and inkboxes
    list overlaid glyphs in the same order; unverified". An order-based join
    is undetectable when it slips — every glyph gets A box, just the wrong
    one. `inkboxes` returns pdfminer's own bbox per record, so that bbox is
    the key: positional, so it identifies the glyph INSTANCE, and a mismatch
    shows up as an unmatched record rather than a shifted box."""
    import inspect
    src = inspect.getsource(dm.attach_ink)
    assert 'r["pdfminer"]' in src, "the join key must be pdfminer's own box"
    assert "zip(" not in src, "an order-based join is the thing to avoid"
    assert "unmeasured" in src, "unmatched glyphs must be counted, not hidden"


def test_the_identity_region_is_not_re_measured():
    """Identity is (document, page, region). Re-measuring `region` would
    change the identity of every row in the corpus — every crop filename,
    every inkdrill mark, every join in every list. The tighter box is offered
    BESIDE the one everything is addressed by."""
    src = (ROOT / "src/pdfreader/equations.py").read_text(encoding="utf-8")
    assert '"region_ink": self.region_ink' in src
    assert 'region_ink: dict | None = None' in src
    # and `region` is still built from the span rects, untouched
    assert "region = docmodel._px_region(rect, page, px_per_pt)" in src


def test_region_ink_is_absent_rather_than_equal_when_nothing_was_measured():
    """An equal value would read as "the ink agrees", which is a different
    claim from "we did not measure"."""
    src = (ROOT / "src/pdfreader/equations.py").read_text(encoding="utf-8")
    assert "region_ink = None" in src
    assert "if ink_rect:" in src
