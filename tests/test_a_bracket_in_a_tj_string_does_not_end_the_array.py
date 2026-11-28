r"""A `[` or `]` inside a string of a TJ array is text, not the array's end.

`[(is)4.5(s)-396.9([)]TJ` in arxiv.0704.0808 p5 made psstream's array scan
run on to a later `]`, losing every operator up to it (glyphdrill4-72's
comparison against pdfread: line_starts wrong on 140 library pages).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import psstream


def test_an_open_bracket_in_a_string_keeps_the_following_operators():
    data = (b"BT /F1 10 Tf 1 0 0 1 72 700 Tm [(is)4.5(s)-396.9([)]TJ ET "
            b"BT 1 0 0 1 72 600 Tm [(x)]TJ ET")
    ops = [op for _o, op in psstream.tokenize(data)]
    assert ops == ["BT", "Tf", "Tm", "TJ", "ET", "BT", "Tm", "TJ", "ET"]
    arr = [o for o, op in psstream.tokenize(data) if op == "TJ"][0][0]
    assert arr == [b"is", 4.5, b"s", -396.9, b"["]


def test_escaped_parens_and_a_close_bracket_inside_a_string():
    data = rb"[(a\)])(b\(c)(])]TJ 5 w"
    toks = list(psstream.tokenize(data))
    assert [op for _o, op in toks] == ["TJ", "w"]
    assert toks[0][0][0] == [b"a\\)]", b"b\\(c", b"]"]
