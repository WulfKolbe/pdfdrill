r"""A CJK font is not a typewriter face (user report, arxiv.2209.02970).

Every CJK ideograph advances by one em by design, and `isalpha()` is True for
them, so the CJK subfonts of a pdfTeX CJK document (gbsnu4e ...) measured
"monospace" and their runs came out in `\texttt`. Only cased letters (Lu, Ll,
Lt) count toward the alphabet test; ligature texts ("fi") still count.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

texmap = pytest.importorskip("pdfreader.texmap")


def test_uniform_cjk_is_not_monospace():
    ideographs = [chr(0x4E00 + i) for i in range(200)]
    samples = [("ABC+gbsnu4e", 10.0, 10.0, c) for c in ideographs]
    assert "gbsnu4e" not in texmap.measure_monospace(samples)


def test_a_latin_typewriter_still_is():
    letters = "abcdefghijklmnopqrstuvwxyz" * 5 + "fi"
    samples = [("XYZ+lmt-regular", 5.25, 10.0, c) for c in letters]
    samples.append(("XYZ+lmt-regular", 5.25, 10.0, "fi"))
    assert "lmt-regular" in texmap.measure_monospace(samples)
