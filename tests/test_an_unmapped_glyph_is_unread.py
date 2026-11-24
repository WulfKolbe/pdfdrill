r"""`(cid:N)` in a projection is an unread character, like U+FFFD.

B6. Five board pages carry 145 `(cid:N)` tokens in their markdown and every one
of them reported REACHED — "nothing known missing" — because `unread_chars`
counts U+FFFD and the md projector writes pdfminer's notation instead:

    lines.json   "Damit folgt für Q <FFFD> .P <FFFD> qA/"
    the md       "Damit folgt für Q $WD .P (cid:5) qA/"

Same condition, two notations, and the verdict knew one. Measured over the 21
born pages of board75 (`pdfdrill md`, installed entry point):

    0864 p4 54, lib:3c16fac66fdd p370 55, 1805.01788 p3 13,
    lib:b21e554b9232 p201 13, lib:c57ac038ae5f p293 10      -> 145, all REACHED

`(cid:5)` in a document a user reads is also visible wrongness in its own right
(rule 4), but the type of the fix here is the verdict's: a reader must not be
told a reading is complete when the reader itself recorded that it is not.
"""
from pathlib import Path
from pdfdrill import verdict


def test_fffd_is_counted(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("x � y � z", encoding="utf-8")
    assert verdict.unread_chars([f]) == 2


def test_cid_notation_is_counted(tmp_path):
    """pdfminer's own spelling of the same failure."""
    f = tmp_path / "a.md"
    f.write_text("Damit folgt für Q $WD .P (cid:5) qA/ (cid:5) qA/:", encoding="utf-8")
    assert verdict.unread_chars([f]) == 2


def test_both_notations_in_one_file(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("� and (cid:11) and (cid:213)", encoding="utf-8")
    assert verdict.unread_chars([f]) == 3


def test_a_clean_projection_counts_zero(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("$\\bar{f}_{\\mathrm{spc}}$ is fine, and so is (cid) alone.",
                 encoding="utf-8")
    assert verdict.unread_chars([f]) == 0


def test_a_page_with_cid_tokens_is_degraded():
    """The verdict itself, not just the counter."""
    v = verdict.decide(has_text=True, maths_unread=False, unread_chars=13)
    assert v.state == verdict.DEGRADED
    assert "13 unread character(s)" in v.line()
    assert v.exit_code == 4
