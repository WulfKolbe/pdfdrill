r"""A chart's own labels are text the reading must carry.

Board 113, 2312.11532 p7: three diagram regions each take in two stacked
charts, so the upper chart's x-axis ticks (`200 300`) and every legend
(`k=5` `k=3` `k=1`) sat in a region's interior in DejaVuSerif -- a text face,
not the body face -- and the figure filter removed them: all 54 of the page's
unpaired original glyphs. Kept, panel (a)'s legend row `k=3` then read as
scripts of the row above it, whose y-tick `0.1` shares the legend's
baseline: `0.1 kk==53`. A script does not sit straight under a glyph of its
own size and face.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _g(text, x0, baseline, *, size=5.86, family="text", font="BXGEVL+DejaVuSerif"):
    return docmodel.GlyphNode(
        id="g%d_%d" % (int(x0 * 10), int(baseline * 10)), page=1,
        rect=(x0, baseline - 0.2 * size, x0 + 0.6 * size, baseline + 0.8 * size),
        text=text, cid=0, glyphname=None, fontname=font, family=family,
        size=size, tex=texmap.UNKNOWN, matrix=(size, 0, 0, size, x0, baseline))


def test_a_label_glyph_in_a_text_face_is_kept_inside_a_figure():
    region = [(0.0, 0.0, 100.0, 100.0)]
    label = [_g(c, 40 + 4 * i, 50) for i, c in enumerate("k=5")]
    stamp = _g("→", 60, 50, family="math-symbol", font="CMSY10")
    kept = docmodel._outside_figures(label + [stamp], region)
    assert [g.text for g in kept if g in label] == ["k", "=", "5"]
    assert stamp not in kept


def test_a_label_row_under_its_twin_is_not_its_script():
    k5 = [_g(c, 201.4 + 3.5 * i, 711.06) for i, c in enumerate("k=5")]
    tick = [_g(c, 78.5 + 2.4 * i, 710.72, size=7.33) for i, c in enumerate("0.1")]
    k3 = _g("k", 201.4, 702.46)
    assert docmodel._stacked_twin(k3, tick + k5)
    assert not docmodel._stacked_twin(k3, tick)


def test_a_true_superscript_has_no_twin_above_it():
    base = [_g("x", 10, 100, size=10.0, family="math-italic", font="CMMI10")]
    sup = _g("2", 16, 104, size=7.0, family="text-cm", font="CMR7")
    assert not docmodel._stacked_twin(sup, base)
