#!/usr/bin/env python3
r"""test_table — the table pipeline, fed deliberately malformed elements.

    python3 -m pytest test_table.py -q

The table is a MEASUREMENT instrument: if it drops an equation quietly, every
number taken from it is wrong and nothing says so. These tests assert the two
properties that matter --

    every gold equation gets a row
    every block a source emitted is either matched or listed

-- and that malformed input is REFUSED VISIBLY rather than swallowed.

Needs $PDFDRILL_SRC for `report_tex` (the preamble and the compile gate) and
xelatex for the probe tests, which skip without it.
"""
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("eq", _here / "eqtable_716.py")
eq = importlib.util.module_from_spec(_s)
_s.loader.exec_module(eq)


#: Things a reader really does emit, each of which has broken something.
MALFORMED = [
    r"\frac{a}{",                      # unbalanced brace
    r"\left( a + b",                   # \left with no \right
    r"a \right)",                      # \right with no \left
    r"\bogusmacro{x}",                 # undefined command
    r"x \text{50% done}",              # a comment character
    r"m_{ij} = \text{#}\{k\}",         # a parameter character
    r"\text{gb_imp}",                  # a subscript in text mode
    r"\begin{aligned}&\log x\end{aligned}",   # leading & under mathtools
    r"\begin{aligned}a\\ \end{aligned}",      # trailing row separator
    r"",                               # empty
    r"   ",                            # whitespace only
    r"\bigl( \bigr)",                  # a pair with nothing in it
    "x" * 4000,                        # very long
    r"\alpha \uE000 \beta",            # a private-use codepoint
]


def test_key_never_raises_and_never_returns_none():
    for s in MALFORMED:
        k = eq.key(s)
        assert isinstance(k, str)


def test_md_blocks_survives_a_malformed_document(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("\n\n".join(["intro"] + ["$$\n%s\n$$" % s for s in MALFORMED]),
                  encoding="utf-8")
    blocks = eq.md_blocks(md)
    # the empty and whitespace-only ones are dropped; everything else survives
    assert len(blocks) == len([s for s in MALFORMED if s.strip()])


def test_gold_equations_survives_a_malformed_source(tmp_path):
    gt = tmp_path / "1_gt.tex"
    gt.write_text("\\begin{document}\n"
                  + "\n".join(r"\begin{equation}%s\end{equation}" % s
                              for s in MALFORMED)
                  + "\n\\end{document}\n", encoding="utf-8")
    gold = eq.gold_equations(gt)
    assert len(gold) == len([s for s in MALFORMED if s.strip()])


def test_every_gold_equation_is_matched_or_left_unmatched():
    """`align` must account for every gold equation and every block.

    Not "most of them": a gold equation with no match gets None, and a block
    claimed by nobody appears in the leftovers. Anything else is an equation
    that has quietly left the table.
    """
    gold = [("equation", s) for s in MALFORMED if s.strip()]
    blocks = [s for s in MALFORMED if s.strip()] + [r"\zeta = 1"]
    at, left = eq.align(gold, blocks)
    assert len(at) == len(gold)                       # a verdict for each
    claimed = {h[0] for h in at if h is not None}
    assert claimed.isdisjoint(left)                   # no block counted twice
    assert set(left) | claimed <= set(range(len(blocks)))


def test_a_cell_is_never_blank():
    """A blank cell cannot be told from "did not render", which is the
    confusion this table exists to prevent."""
    for s in MALFORMED:
        c = eq.cell(s)
        assert c.strip(), repr(s)
        if s.strip():
            assert ("FitMath" in c) or ("will not typeset" in c), repr(s)


def test_cell_text_of_a_row_out_of_range_falls_back_to_the_block():
    blocks = [r"\begin{aligned}a\\ b\end{aligned}"]
    assert eq.cell_text(blocks, (0, 99)) == blocks[0]
    assert eq.cell_text(blocks, None) == ""


def test_a_percent_sign_cannot_reach_the_table_unescaped():
    """`%` starts a comment: written plain it eats the rest of the row.
    It cost 29 errors and 21 demoted rows once."""
    c = eq.cell(r"x \text{50\% done}")
    body = c.split("%")
    # every `%` in the emitted cell is preceded by a backslash
    assert all(p.endswith("\\") for p in body[:-1]), c


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="needs xelatex")
def test_the_probe_convicts_the_guilty_and_clears_the_innocent():
    pre = ("\\documentclass{article}\n\\usepackage{amsmath}\n"
           "\\begin{document}")
    good = [r"a=b", r"\frac{1}{2}", r"\text{\#}", r"\alpha+\beta"]
    bad = [r"\bogusmacro{x}"]
    work = Path(tempfile.mkdtemp())
    found = eq.unrenderable_cells(good + bad, pre, work)
    assert found == set(bad), found


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


def test_an_unrenderable_cell_does_not_end_the_row():
    r"""757 — inside a longtable cell `\\` ENDS THE ROW. The unrenderable
    form used it, and looked safe only because it had never appeared in
    anything but the last column. In wzlxjtu-041's unmatched table it landed
    in the third, and `(will not typeset)` came out under the No column with
    every following cell shifted one to the left."""
    # `\bogusmacro{x}` passes the STATIC gate -- only the compile probe
    # catches it. An unbalanced brace is what `display_safe` refuses.
    for bad in (r"\frac{a}{", r"\left( a + b", r"x \text{50% done}"):
        c = eq.cell(bad)
        assert "will not typeset" in c, bad
        assert "\\\\" not in c, c


def test_alignat_loses_its_column_count_but_keeps_its_mathematics(tmp_path):
    r"""759 — `\begin{alignat*}{3}` takes an ARGUMENT. It was not in ENVS at
    all, so wzlxjtu-082's second equation had never been counted."""
    gt = tmp_path / "1_gt.tex"
    gt.write_text("\\begin{document}\n"
                  r"\begin{alignat*}{3} p_0(h)\equiv 1 \end{alignat*}"
                  "\n\\end{document}\n", encoding="utf-8")
    gold = eq.gold_equations(gt)
    assert len(gold) == 1
    assert gold[0][1].startswith("p_0(h)"), gold[0][1]


def test_no_other_environment_loses_a_leading_braced_group(tmp_path):
    r"""And the argument strip must apply to `alignat` ONLY. Applied to every
    environment it ate real mathematics -- wzlxjtu-026's `{\cal C}^2 = 1`
    lost its `{\cal C}` -- and the corpus correct count fell by nine for a
    change meant to add one."""
    gt = tmp_path / "1_gt.tex"
    gt.write_text("\\begin{document}\n"
                  r"\begin{equation}{\cal C}^2 = 1\end{equation}"
                  "\n\\end{document}\n", encoding="utf-8")
    gold = eq.gold_equations(gt)
    assert gold[0][1] == r"{\cal C}^2 = 1", gold[0][1]


# --- 764: one entry per equation NUMBER ------------------------------------

def _gold(tmp_path, body):
    gt = tmp_path / "1_gt.tex"
    gt.write_text("\\begin{document}\n" + body + "\n\\end{document}\n",
                  encoding="utf-8")
    return eq.gold_equations(gt)


def test_an_align_of_two_rows_is_two_equations(tmp_path):
    r"""764 — wzlxjtu-031's third gold equation sets two rows of `align`,
    and the page shows two numbered displays, (3) and (4). This reader read
    both exactly; one matched and the other was listed as matching no gold
    equation at all."""
    gold = _gold(tmp_path, r"\begin{align} A&=x\\ \bar{A}&=y \end{align}")
    assert [b for _, b in gold] == [r"A&=x", r"\bar{A}&=y"]


def test_a_starred_align_numbers_nothing_and_stays_one(tmp_path):
    gold = _gold(tmp_path, r"\begin{align*} A&=x\\ \bar{A}&=y \end{align*}")
    assert len(gold) == 1


def test_a_nonumber_row_joins_the_numbered_row_below_it(tmp_path):
    r"""How an author breaks ONE long equation over two lines."""
    gold = _gold(tmp_path,
                 r"\begin{align} A&=x+\nonumber\\ &\quad y \end{align}")
    assert len(gold) == 1
    assert "y" in gold[0][1] and "A" in gold[0][1]


def test_a_row_break_inside_a_nested_environment_is_not_a_row(tmp_path):
    r"""`\\` inside `cases` is a row of the CASES, not of the display."""
    gold = _gold(tmp_path,
                 r"\begin{align} f&=\begin{cases}1\\2\end{cases} \end{align}")
    assert len(gold) == 1


def test_a_row_break_inside_braces_is_not_a_row(tmp_path):
    gold = _gold(tmp_path,
                 r"\begin{align} f&=\substack{a\\b} \end{align}")
    assert len(gold) == 1


def test_a_skip_after_the_break_is_not_mathematics(tmp_path):
    r"""`\\[2mm]` — the bracketed length is spacing, not a row."""
    gold = _gold(tmp_path, r"\begin{align} A&=x\\[2mm] B&=y \end{align}")
    assert [b for _, b in gold] == [r"A&=x", r"B&=y"]


def test_equation_is_never_split(tmp_path):
    r"""`equation` numbers ONCE however many `\\` a `split` inside it has."""
    gold = _gold(tmp_path,
                 r"\begin{equation}\begin{split}A&=x\\&=y\end{split}\end{equation}")
    assert len(gold) == 1


def test_the_rows_of_one_environment_keep_their_order(tmp_path):
    gold = _gold(tmp_path,
                 r"\begin{equation}Z\end{equation}"
                 r"\begin{align} A&=x\\ B&=y\\ C&=z \end{align}")
    assert [b for _, b in gold] == ["Z", r"A&=x", r"B&=y", r"C&=z"]


# --- 765: the document name on every page the table runs onto --------------

def test_a_table_that_runs_over_a_page_says_whose_it_is():
    r"""765 — wzlxjtu-031 starts at the foot of one page with two rows and
    continues at the top of the next with fifteen. `longtable` repeats the
    column header there and nothing else, so those fifteen rows sat under
    `No | gold | MathPix | pdf2mmd` with no document name on the page, and
    the two rows left behind read as the whole of it."""
    heads = ("No", "gold (author)", "MathPix", "pdf2mmd")
    s = eq.table_open("wzlxjtu-031 — gold 17", (10, 119, 119, 118),
                      heads, "wzlxjtu-031")
    assert "\\endfirsthead" in s and "\\endhead" in s
    assert s.index("\\endfirsthead") < s.index("\\endhead")
    assert s.count("wzlxjtu-031 — continued") == 1
    assert s.count("\\textbf{MathPix}") == 2      # first head, and the repeat


def test_the_first_page_head_is_not_the_continuation_head():
    heads = ("No", "gold (author)", "MathPix", "pdf2mmd")
    s = eq.table_open("c", (10, 119, 119, 118), heads, "slug")
    first = s.split("\\endfirsthead")[0]
    assert "continued" not in first


# --- 766: the appendix must not look like the document's own table ---------

def test_the_appendix_names_the_source_and_never_says_no_gold():
    r"""766 — the appendix had the document table's four columns and a gold
    column reading "no gold" in every row. Searching the file for a document
    lands on two sections with its name, and the second one — one row, an
    empty MathPix column, "no gold" — reads as the DOCUMENT having no
    equations and no gold. Reported for 041, and again for 031, whose table
    above it carries all seventeen."""
    rows = eq.appendix_rows(["m0", "m1"], [1], ["p0"], [0])
    assert len(rows) == 2
    assert rows[0].startswith("MathPix & ") and "m1" in rows[0]
    assert rows[1].startswith("pdf2mmd & ") and "p0" in rows[1]
    assert not any("no gold" in r for r in rows)
    assert all(r.count("&") == 1 for r in rows), "two columns, not four"


def test_the_appendix_of_a_document_with_nothing_left_over_is_empty():
    assert eq.appendix_rows(["m"], [], ["p"], []) == []
