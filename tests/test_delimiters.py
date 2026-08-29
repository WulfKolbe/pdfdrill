r"""308 — `\right.`, the invisible right delimiter."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import delimiters as dl                       # noqa: E402


def test_the_invisible_right_is_counted_with_its_opener():
    c = dl.count(r"\left( x \right.")
    assert c["right_dot_raw"] == 1
    assert c["opened_by_paren"] == 1


def test_pairing_is_depth_matched_not_nearest():
    r"""`\left( \left[ x \right] \right.` — the invisible right closes the
    PARENTHESIS. Pairing by proximity blames the bracket, which is the wrong
    delimiter and the wrong diagnosis."""
    ps = dl.pairs(r"\left( \left[ x \right] \right.")
    assert {"left": "[", "right": "]"} == {k: ps[0][k] for k in ("left", "right")}
    assert {"left": "(", "right": "."} == {k: ps[1][k] for k in ("left", "right")}
    assert dl.count(r"\left( \left[ x \right] \right.")["opened_by_paren"] == 1


def test_other_openers_are_not_counted_as_parens():
    r"""A one-sided brace is the construct's legitimate use."""
    c = dl.count(r"\left\{ x \right.")
    assert c["right_dot_raw"] == 1
    assert c["opened_by_paren"] == 0
    assert c["by_opener"] == {"\\{": 1}


def test_multi_character_delimiters_are_read_whole():
    r"""`\langle` must not be read as `\l` followed by `angle`."""
    ps = dl.pairs(r"\left\langle x \right.")
    assert ps[0]["left"] == "\\langle"
    assert dl.count(r"\left\langle x \right.")["opened_by_paren"] == 0


def test_a_balanced_expression_reports_nothing():
    assert dl.count(r"\left( x \right)")["right_dot_raw"] == 0
    assert dl.count("no delimiters at all")["right_dot_raw"] == 0


def test_an_unpaired_right_dot_is_still_counted():
    r"""Counting only PAIRED ones would under-report exactly the malformed
    values this is looking for."""
    c = dl.count(r"x \right.")
    assert c["right_dot_raw"] == 1
    assert c["right_dot_paired"] == 0


def test_spacing_between_the_command_and_its_delimiter():
    assert dl.count(r"\left ( x \right .")["opened_by_paren"] == 1
