r"""
SPEED (EXACT): `LineNode.spans` recomputes `_spans` on every read, and each
line record in `to_lines_json` read it five times (confidence, gaps, text,
text_display, complete). Once per line now; the 24 born board pages'
lines.json are byte-identical, and `glyphlines` goes 2.77 -> 2.55 s/page
(72 pages, one core, both trees measured side by side).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows" / "r00.pdf"


def test_one_spans_computation_per_line(monkeypatch):
    pages = D.build(str(FIX))
    n = {"c": 0}
    orig = D._spans

    def counting(line):
        n["c"] += 1
        return orig(line)
    monkeypatch.setattr(D, "_spans", counting)
    D.to_lines_json(pages)
    assert n["c"] == sum(len(p.lines) for p in pages)
