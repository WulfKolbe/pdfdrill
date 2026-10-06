r"""890 — THE ROWS OF A MULTI-LINE DISPLAY MUST ACTUALLY BREAK.

psred found this by comparing our OWN two projections of one region rather
than ours against MathPix's: on wzlxjtu-030 p1, `page.md` emits

    dA + A \wedge \star A = 0        \tag{7}
    D\overline{A} + \overline{A} \wedge \star\overline{A} = 0   \tag{8}

and `equations.json` ran the two together with both `= 0` gone. One reader,
the row logic in one of its two outputs — `project_mmd.to_markdown` groups
fragments by baseline and emits `\begin{aligned}` (732); `equations.py` did
not, and `equations.json` is the artefact the whole corpus is addressed by.

The two rows are SEPARATE LineNodes (26 and 27, one baseline each, both
display), so the fix is in the grouping `_build_multi` already does — it had
the rows and flattened them.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader import equations as eq                           # noqa: E402


class _Span:
    def __init__(self, tex, x=0.0):
        self._t = tex
        self.id = f"s{x}"
        self.rect = (x, 0.0, x + 10.0, 10.0)


class _Line:
    def __init__(self, i):
        self.id = f"l{i}"
        self.rect = (0.0, 0.0, 100.0, 10.0)
        self.glyphs = []
        self.rules = []


class _Page:
    page = 1
    rect = (0.0, 0.0, 612.0, 792.0)
    lines: list = []


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    """Project a span as its own text, so the test is about ROW STRUCTURE."""
    from pdfreader import docmodel_six as dm
    monkeypatch.setattr(dm, "span_latex", lambda sp: sp._t, raising=False)
    monkeypatch.setattr(eq.docmodel, "span_latex", lambda sp: sp._t,
                        raising=False)
    monkeypatch.setattr(eq.docmodel, "_px_region",
                        lambda rect, page, k: {"top_left_x": 0,
                                               "top_left_y": 0,
                                               "width": 10, "height": 10},
                        raising=False)
    monkeypatch.setattr(eq.mmd, "has_content", lambda s: True, raising=False)
    monkeypatch.setattr(eq.mmd, "equation_number", lambda ln, col: None,
                        raising=False)
    monkeypatch.setattr(eq.mmd, "column_of", lambda p, ln: (0, 0),
                        raising=False)


def test_two_display_lines_become_two_aligned_rows():
    run = [(_Line(1), [_Span("a = 0")]), (_Line(2), [_Span("b = 0")])]
    got = eq._build_multi(_Page(), run, "t", 250.0 / 72.0).latex
    assert got.startswith(r"\begin{aligned}"), got
    assert got.endswith(r"\end{aligned}"), got
    assert r" \\ " in got, "the rows have to be separated by a LaTeX break"
    assert got.count("= 0") == 2, got


def test_one_display_line_is_not_wrapped():
    """A single row in an `aligned` is noise: it changes the output of every
    ordinary display for nothing. The flat join stays the default."""
    run = [(_Line(1), [_Span("a = 0")])]
    got = eq._build_multi(_Page(), run, "t", 250.0 / 72.0).latex
    assert "aligned" not in got, got
    assert got.strip() == "a = 0", got


def test_a_row_that_projects_nothing_does_not_leave_an_empty_row():
    r"""`\\ \\` is a blank line in LaTeX and changes the vertical layout. A
    row whose spans all deferred contributes no row rather than an empty one.
    """
    class _Dead(_Span):
        def __init__(self):
            super().__init__(None, 0.0)
            self.glyphs = []
            self.rules = []
    run = [(_Line(1), [_Span("a = 0")]), (_Line(2), [_Dead()]),
           (_Line(3), [_Span("b = 1")])]
    got = eq._build_multi(_Page(), run, "t", 250.0 / 72.0).latex
    assert got.count(r"\\") == 1, got
    assert r"\\ \\" not in got, got


def test_the_right_hand_side_of_a_relation_survives():
    r"""890 — `dA + A \wedge \star A = 0` came out `… = ` with the `0` gone.

    A digit is not alphabetic, so the left-hand-side rule could not reach it;
    `_solo` wants an italic letter; and the plain absorption wants mathematics
    on BOTH sides, which `0` does not have because the equation number `(7)`
    sits to its right. So a relation survived with its right-hand side
    deleted — the worst of the three states, because the row then reads as an
    equation asserting nothing and still typesets.
    """
    from pdfreader import docmodel_six as dm
    src = (ROOT / "src/pdfreader/docmodel_six.py").read_text(encoding="utf-8")
    assert "_rhs = (_mostly_math" in src, (
        "the right-hand-side rule must exist")
    assert "isalnum()" in src, (
        "alphaNUMERIC: a right-hand side is usually a number")
    assert "_is_relation(_prv)" in src, (
        "the evidence is a relation on the LEFT, mirroring _lhs")


def test_the_markdown_projector_still_owns_its_own_copy():
    """Both now break rows, and they are DIFFERENT implementations — markdown
    groups glyph fragments by baseline, equations groups spans by LineNode.
    This records that fact so a future merge is a decision and not a surprise.
    """
    src = (ROOT / "src/pdfreader/project_mmd.py").read_text(encoding="utf-8")
    assert r"\begin{aligned}" in src
    src2 = (ROOT / "src/pdfreader/equations.py").read_text(encoding="utf-8")
    assert r"\begin{aligned}" in src2


# --------------------------------------------------------------------------
# 891 — THE INKDRILL COLUMN STANDARD: the crop is LAST, the rendered LaTeX is
# the column before it, in EVERY mode. Stated by the user as the invariant all
# three table grades share, and violated by compare+reference mode, which put
# the reference text after the crop.
# --------------------------------------------------------------------------

def _header(src: str, start: int) -> str:
    i = src.index("textbf{document}", start)
    return src[i:src.index("endhead", i)]


def test_the_crop_is_the_last_column_in_every_mode():
    src = (ROOT / "src/pdfdrill/reports/eqtable.py").read_text(encoding="utf-8")
    at, n = 0, 0
    while "textbf{document}" in src[at:]:
        hdr = _header(src, at)
        at = src.index("endhead", src.index("textbf{document}", at))
        n += 1
        cells = [c.strip() for c in hdr.split("&")]
        assert "own ink" in cells[-1], (
            f"mode {n}: the LAST column must be the crop, got {cells[-1][:60]!r}")
        assert "typeset" in cells[-2], (
            f"mode {n}: the column before the crop must be the rendered "
            f"LaTeX, got {cells[-2][:60]!r}")
    assert n >= 3, f"expected at least three header variants, found {n}"


def test_the_answer_column_is_left_of_the_rendered_one():
    """A reference string is read and copied, not compared, so it belongs with
    the other text rather than between the two pictures."""
    src = (ROOT / "src/pdfdrill/reports/eqtable.py").read_text(encoding="utf-8")
    i = src.index("the answer, as text")
    j = src.index("own ink", i)
    k = src.index("typeset", i)
    assert i < k < j, "order must be: answer text, typeset, crop"


def test_the_footnote_does_not_name_fixed_column_numbers():
    """It said "column 6 is the PDF's own ink" in every mode, and in
    compare+reference mode the ink was column 5. A table whose own
    instructions point at the wrong cells is worse than one with none."""
    src = (ROOT / "src/pdfdrill/reports/eqtable.py").read_text(encoding="utf-8")
    note = src[src.index(r"\\textbf{How to read a row:}"):]
    note = note[:note.index('",') if '",' in note else 400]
    assert "column 6" not in note and "column 5" not in note, note[:200]
    assert "LAST column" in note
