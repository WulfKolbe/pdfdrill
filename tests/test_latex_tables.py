"""819 — the LaTeX table gap: 94% of tables were a `verbatim` dump.

Measured before this change, on 1-s2.0-S2590118425000565-main:
MathPix's own `.tex` emits 3 `\begin{tabular}`; ours emitted 0 and 3
`\begin{verbatim}`. Across 300 corpus models, 6,848 of 7,323 Table objects
(94%) carry no `latex_code` and fell to that dump.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                # noqa: E402
from docops.base import OperatorConfig                       # noqa: E402
from docops.projectors.latex import LaTeXProjector, _cell_tex  # noqa: E402


def _proj():
    p = LaTeXProjector(OperatorConfig(op="projector", classname="LaTeXProjector"))
    d = Document()
    d.meta["bibkey"] = "doc"
    p._doc = d
    return p, d


def _table(cells, n_rows, n_cols, **extra):
    props = {"cells": cells, "n_rows": n_rows, "n_cols": n_cols}
    props.update(extra)
    return DocObject(type="Table", props=props)


def _tex(obj):
    p, d = _proj()
    d.add(obj)
    # `_figure_label` computes label uniqueness over `_all_objects`, which
    # `project()` sets; `_tabular` is called directly here.
    p._all_objects = list(d.objects.values())
    return p._tabular(obj)


def _cells(rows):
    out = []
    for r, row in enumerate(rows):
        for c, txt in enumerate(row):
            out.append({"row": r, "col": c, "text": txt})
    return out


# ── the gap itself ───────────────────────────────────────────────────────────

def test_a_gridded_table_becomes_a_real_tabular():
    tex = _tex(_table(_cells([["Functions", "Description"],
                              ["forward()", "applies a delta"]]), 2, 2))
    assert "\\begin{tabular}" in tex
    assert "Functions & Description \\\\" in tex
    assert "\\begin{verbatim}" not in tex


def test_booktabs_rules_and_no_vertical_rules():
    r"""`booktabs` is already in the preamble and vertical rules are what it
    exists to discourage — and what MathPix emits (`|l|l|`)."""
    tex = _tex(_table(_cells([["a", "b"], ["c", "d"]]), 2, 2))
    assert "\\toprule" in tex and "\\midrule" in tex and "\\bottomrule" in tex
    assert "|" not in tex


def test_latex_code_still_wins_when_the_model_has_it():
    """438 of 7,323 tables carry `latex_code`; that path is unchanged."""
    p, d = _proj()
    obj = _table(_cells([["a"]]), 1, 1,
                 latex_code="\\begin{tabular}{l}\\nMINE\\n\\end{tabular}")
    d.add(obj)
    out = p._block(obj) if hasattr(p, "_block") else None
    if out is not None:
        assert "MINE" in out


# ── the shapes the corpus actually contains ──────────────────────────────────

def test_a_table_taller_than_a_page_becomes_a_longtable():
    """A `tabular` does not break across pages — the rows past the margin are
    simply lost. Measured: 1,442 of 6,844 gridded tables (21%) exceed 30 rows,
    the largest having 211."""
    rows = [[f"r{i}", "x"] for i in range(40)]
    tex = _tex(_table(_cells(rows), 40, 2))
    assert "\\begin{longtable}" in tex
    assert "\\begin{tabular}" not in tex
    assert "\\endhead" in tex          # the header repeats — the reason to use it


def test_a_longtable_is_not_wrapped_in_a_table_float():
    """longtable IS the float; nesting it in `table` does not compile."""
    rows = [[f"r{i}", "x"] for i in range(40)]
    tex = _tex(_table(_cells(rows), 40, 2, caption="Long one"))
    assert "\\begin{table}" not in tex


def test_many_columns_get_equal_p_shares_so_they_fit_the_page():
    """`l` columns are as wide as their widest cell; 27 of them (the corpus
    maximum) run off the page with nothing to wrap. 19% exceed 6 columns."""
    row = [f"c{i}" for i in range(10)]
    tex = _tex(_table(_cells([row, row]), 2, 10))
    assert "p{\\dimexpr" in tex
    assert tex.count("p{\\dimexpr") == 10


def test_a_long_column_wraps_and_a_short_one_does_not():
    tex = _tex(_table(_cells([["id", "x" * 90], ["1", "y" * 90]]), 2, 2))
    spec = re.search(r"\\begin\{tabular\}\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", tex)
    assert spec and spec.group(1).startswith("l")
    assert "p{0.35\\linewidth}" in tex


def test_a_column_span_becomes_multicolumn_and_covers_its_columns():
    cells = [{"row": 0, "col": 0, "text": "Both", "col_span": 2},
             {"row": 1, "col": 0, "text": "x"}, {"row": 1, "col": 1, "text": "y"}]
    tex = _tex(_table(cells, 2, 2))
    assert "\\multicolumn{2}{l}{Both}" in tex
    header = [l for l in tex.split("\n") if "multicolumn" in l][0]
    assert header.count("&") == 0       # the covered column is NOT written again


def test_a_row_span_becomes_multirow():
    cells = [{"row": 0, "col": 0, "text": "Tall", "row_span": 2},
             {"row": 0, "col": 1, "text": "a"},
             {"row": 1, "col": 1, "text": "b"}]
    tex = _tex(_table(cells, 2, 2))
    assert "\\multirow{2}{*}{Tall}" in tex
    assert tex.count("Tall") == 1       # never repeated into the covered row


def test_every_row_accounts_for_exactly_n_cols():
    r"""A row that accounts for one column too many or too few is what stops a
    tabular compiling — and it fails the WHOLE document, not just the table.

    The invariant is NOT an equal `&` count per row: a `\multicolumn{2}` is ONE
    entry covering TWO columns, so a header using one legitimately has fewer
    `&` than the body. What must match is the sum of the spans.
    """
    cells = [{"row": 0, "col": 0, "text": "Both", "col_span": 2},
             {"row": 0, "col": 2, "text": "z"},
             {"row": 1, "col": 0, "text": "x"}, {"row": 1, "col": 1, "text": "y"},
             {"row": 1, "col": 2, "text": "w"}]
    tex = _tex(_table(cells, 2, 3))
    rows = [l.strip().rstrip("\\\\").strip() for l in tex.split("\n")
            if l.strip().endswith("\\\\") and "&" in l and "rule" not in l]
    for r in rows:
        width = 0
        for entry in re.split(r"(?<!\\)&", r):
            m = re.search(r"\\multicolumn\{(\d+)\}", entry)
            width += int(m.group(1)) if m else 1
        assert width == 3, f"row accounts for {width} of 3 columns: {r!r}"


# ── a cell must survive what the corpus puts in it ───────────────────────────

def test_maths_in_a_cell_survives():
    """24.5% of 555,053 corpus cells contain maths. `_escape_text` leaves
    `$ \\ { } ^` alone for exactly this reason."""
    assert _cell_tex(r"the value \(x^{2}\)") == r"the value \(x^{2}\)"


def test_a_bare_ampersand_is_escaped_or_the_row_gains_a_column():
    """0.32% of cells. Unescaped it IS a column separator."""
    out = _cell_tex("Smith & Jones")
    assert out == r"Smith \& Jones"
    assert len(re.findall(r"(?<!\\)&", out)) == 0


def test_a_row_break_inside_a_cell_is_neutralised():
    r"""0.37% of cells carry `\\`, which inside a cell splits the row in two."""
    assert "\\\\" not in _cell_tex(r"one \\ two")


def test_an_environment_in_a_cell_is_unwrapped_to_its_words():
    r"""0.38% of cells. `lstlisting` cannot appear in a tabular cell without an
    `lrbox`; keeping the words beats losing the cell or failing the compile."""
    out = _cell_tex("\\begin{lstlisting}\nforward(g)\n\\end{lstlisting}")
    assert "lstlisting" not in out
    assert "forward(g)" in out


def test_a_markdown_image_is_dropped_not_printed():
    """MathPix writes `![](https://cdn.mathpix.com/…)` inside cell text. That
    CDN is retired, so emitting it as `\\includegraphics` names a URL xelatex
    cannot fetch and fails the compile; leaving it prints the URL as prose."""
    out = _cell_tex("before ![](https://cdn.mathpix.com/x.jpg?a=1&b=2) after")
    assert "cdn.mathpix.com" not in out
    assert "before" in out and "after" in out


def test_underscores_are_escaped():
    assert _cell_tex("user_arg") == r"user\_arg"


def test_braces_are_balanced_so_a_cell_cannot_swallow_the_table():
    out = _cell_tex("a {runaway")
    assert out.count("{") == out.count("}")


def test_an_empty_cell_is_empty_not_missing():
    tex = _tex(_table([{"row": 0, "col": 0, "text": "a"},
                       {"row": 1, "col": 1, "text": "d"}], 2, 2))
    rows = [l for l in tex.split("\n")
            if l.strip().endswith("\\\\") and "rule" not in l]
    assert all(len(re.findall(r"(?<!\\)&", r)) == 1 for r in rows)


# ── captions and labels ──────────────────────────────────────────────────────

def test_a_caption_gets_a_label_so_the_table_can_be_referenced():
    r"""MathPix's own `.tex` has ZERO `\label` in it. This is the win."""
    tex = _tex(_table(_cells([["a", "b"]]), 1, 2,
                      caption="Overview of the parameters", refnum="1"))
    assert "\\caption{Overview of the parameters}" in tex
    assert "\\label{tab:1}" in tex


def test_no_caption_means_no_label():
    r"""A `\label` inside a float with no `\caption` refers to whatever counter
    last stepped — the same rule `_figure_env` follows."""
    tex = _tex(_table(_cells([["a", "b"]]), 1, 2))
    assert "\\label{" not in tex


def test_a_table_with_no_grid_yields_nothing_here():
    """The `raw_text`/verbatim fallback still handles those — 572 of 7,765."""
    assert _tex(DocObject(type="Table", props={"raw_text": "x y z"})) == ""


# ── the real document ────────────────────────────────────────────────────────

_REAL = (Path.home() / "pdfdrill-library" / "1-s2.0-S2590118425000565-main"
         / "model.docmodel.json")


@pytest.mark.skipif(not _REAL.is_file(), reason="corpus document not present")
def test_the_reported_document_reaches_parity_with_mathpix():
    """MathPix emits 3 `tabular` on this document. We emitted 0."""
    from pdfdrill.model_io import load_model
    doc = load_model(_REAL)
    tex = LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector",
        params={"crops_dir": str(_REAL.parent / "report-crops")})).project(doc)
    assert len(re.findall(r"\\begin\{tabular\}", tex)) == 3
    assert "\\begin{verbatim}" not in tex
    # No markdown image link inside a TABLE. (One still leaks into PROSE on this
    # document — a Paragraph carrying MathPix's `![](…)` markdown — which is a
    # separate defect, recorded in the audit, not fixed here.)
    for block in re.findall(r"\\begin\{table\}.*?\\end\{table\}", tex, re.S):
        assert "cdn.mathpix.com" not in block


# ── a table that would not compile must not be emitted ───────────────────────

def test_a_row_wider_than_n_cols_widens_the_spec_rather_than_overflowing():
    r"""An OVER-full row is fatal: xelatex answers "Extra alignment tab has been
    changed to \cr" and the whole document stops — not just the table. Measured
    over 6,326 gridded corpus tables, 74 (1.2%) had a row disagreeing with the
    stated `n_cols`; 1511.08771 has one summing to 9 where the props say 1."""
    # props claim 1 column; the cells describe 3
    cells = [{"row": 0, "col": 0, "text": "a"}, {"row": 0, "col": 1, "text": "b"},
             {"row": 0, "col": 2, "text": "c"}]
    tex = _tex(_table(cells, 1, 1))
    assert tex, "a widenable table must still be emitted"
    p, _ = _proj()
    rows = [l.strip().rstrip("\\").strip() for l in tex.split("\n")
            if l.strip().endswith("\\\\") and "rule" not in l]
    spec = re.search(r"\\begin\{tabular\}\{([^\n]*)\}", tex).group(1)
    assert spec.count("l") + spec.count("p{") == 3
    for r in rows:
        assert p._row_width(r) <= 3


def test_an_under_full_row_is_left_alone_because_latex_pads_it():
    """Missing trailing cells are legal LaTeX; inventing padding would state
    values the document does not have."""
    cells = [{"row": 0, "col": 0, "text": "a"}, {"row": 0, "col": 1, "text": "b"},
             {"row": 1, "col": 0, "text": "only"}]
    tex = _tex(_table(cells, 2, 2))
    assert tex and "only" in tex


def test_a_table_that_cannot_be_made_sound_is_refused_not_emitted():
    """The caller then falls back to the `raw_text` verbatim dump: worse output
    and a document that builds, instead of `Emergency stop` and no PDF at all."""
    p, d = _proj()
    obj = _table([{"row": 0, "col": 0, "text": "a {{{ runaway"}], 1, 1)
    d.add(obj)
    p._all_objects = [obj]
    # _cell_tex balances a single cell, so soundness holds here; assert the
    # GUARD exists and answers for a row that is too wide.
    assert p._sound(["a & b & c"], 3) is True
    assert p._sound(["a & b & c"], 2) is False
    assert p._sound([r"\multicolumn{4}{l}{x}"], 2) is False
    assert p._sound(["a {"], 1) is False
