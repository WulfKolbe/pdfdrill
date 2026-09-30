"""Tests for reading a MathPix lines.json as a second source.

Measured on arXiv 1804.10694v5: MathPix reports confidence 1.00 for the two
tables it reconstructs cleanly, 0.60-0.73 for a table it fragments into four
tabulars, and 0.28-0.44 for CODE lines -- where it inserts spaces that are not
in the listing and wraps fragments in maths mode.
"""
import json
import os

import pytest

import mathpix_merge as MM


@pytest.fixture
def reference(tmp_path):
    doc = {"pages": [{
        "page": 1,
        "lines": [
            {"type": "text", "confidence": 1.0,
             "region": {"top_left_x": 100, "top_left_y": 100,
                        "width": 200, "height": 20},
             "text": "ordinary prose"},
            {"type": "table", "confidence": 0.6,
             "region": {"top_left_x": 100, "top_left_y": 200,
                        "width": 400, "height": 300},
             "text": "\\begin{tabular}[t]{|l|l|}\n\\hline a & b \\\\\n"
                     "\\end{tabular}"},
            {"type": "code", "confidence": 0.28,
             "region": {"top_left_x": 100, "top_left_y": 600,
                        "width": 300, "height": 20},
             "text": "GPUBlock for (j0 in 0..floor ((M-2) / 32) )"},
        ]}]}
    path = tmp_path / "lines.json"
    path.write_text(json.dumps(doc))
    return MM.load(str(path))


class TestLoading:
    def test_entries_are_indexed_by_page(self, reference):
        assert set(reference.by_page) == {1}
        assert len(reference.by_page[1]) == 3

    def test_confidence_is_carried(self, reference):
        confs = sorted(e.confidence for e in reference.by_page[1])
        assert confs == [0.28, 0.6, 1.0]

    def test_a_tabular_is_recognised(self, reference):
        tabs = [e for e in reference.by_page[1] if e.is_table]
        assert len(tabs) == 1 and tabs[0].confidence == 0.6


class TestCoordinateSpace:
    """lines.json is pixels at 250 dpi, y down; the docmodel is points, y up.
    Both sides already agree on the constant, so nothing rescales."""

    def test_points_convert_to_the_pixel_region(self):
        # a 12pt-tall box at the top of a 792pt page
        px = MM._to_px((28.8, 763.2, 86.4, 777.6), 792.0)
        assert px[0] == pytest.approx(100.0, abs=1)
        assert px[1] == pytest.approx(50.0, abs=1)

    def test_a_rect_finds_its_entry(self, reference):
        # pixel region (100,100)-(300,120) -> points on a 792pt page
        k = MM.PX_PER_PT
        rect = (100 / k, 792 - 120 / k, 300 / k, 792 - 100 / k)
        hits = reference.covering(1, rect, 792.0)
        assert hits and hits[0].text == "ordinary prose"


class TestBest:
    def _rect_for(self, entry):
        k = MM.PX_PER_PT
        x0, y0, x1, y1 = entry.region
        return (x0 / k, 792 - y1 / k, x1 / k, 792 - y0 / k)

    def test_returns_the_best_overlap(self, reference):
        table = [e for e in reference.by_page[1] if e.is_table][0]
        got = reference.best(1, self._rect_for(table), 792.0)
        assert got is not None and got.is_table

    def test_a_confidence_floor_rejects_the_doubtful(self, reference):
        """The floor is the point of the merge: a 0.28 code line is the
        vendor pointing at its own weak spot."""
        code = [e for e in reference.by_page[1] if e.kind == "code"][0]
        rect = self._rect_for(code)
        assert reference.best(1, rect, 792.0, min_confidence=0.0) is not None
        assert reference.best(1, rect, 792.0, min_confidence=0.5) is None

    def test_nothing_there_returns_none(self, reference):
        assert reference.best(1, (0.0, 0.0, 5.0, 5.0), 792.0) is None

    def test_an_unknown_page_returns_none(self, reference):
        assert reference.covering(99, (0.0, 0.0, 100.0, 100.0), 792.0) == []


REAL = "/home/claude/edge/tir/mathpix.lines.json"


@pytest.mark.skipif(not os.path.exists(REAL), reason="needs a real lines.json")
class TestAgainstARealExport:
    def test_tables_are_found_with_their_confidence(self):
        ref = MM.load(REAL)
        tabs = [e for es in ref.by_page.values() for e in es if e.is_table]
        assert len(tabs) >= 5
        assert min(e.confidence for e in tabs) < 0.7, \
            "expected at least one table the vendor is unsure about"

    def test_code_is_where_the_vendor_is_least_sure(self):
        ref = MM.load(REAL)
        worst = sorted((e for es in ref.by_page.values() for e in es
                        if e.text.strip()),
                       key=lambda e: e.confidence)[:5]
        assert all(e.kind == "code" for e in worst), \
            [(e.kind, e.confidence) for e in worst]
