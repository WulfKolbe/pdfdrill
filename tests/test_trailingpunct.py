"""025 — a trailing sentence mark is not mathematics.

The TiddlyWiki arrangement is the model: the character lives in the text
field, the <$latex> widget holds only mathematics. `trailing_punct` is that
separation made portable, and the comparison must see NEITHER side's copy —
so a half-migrated corpus never reads as a finding storm.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.mathqc import split_trailing_punct


def test_split_lifts_only_a_top_level_mark():
    assert split_trailing_punct("x = y,") == ("x = y", ",")
    assert split_trailing_punct(r"\left(a\right).") == (r"\left(a\right)", ".")
    assert split_trailing_punct(r"\frac{a}{b};") == (r"\frac{a}{b}", ";")
    # \right. is an invisible delimiter, not a full stop
    assert split_trailing_punct(r"X \right.") == (r"X \right.", "")
    # the 024 false-positive classes: notation, and a \text{} prose tail
    assert split_trailing_punct(r"R_{6}^{*,}") == (r"R_{6}^{*,}", "")
    assert split_trailing_punct(r"\text { gilt. }") == (r"\text { gilt. }", "")
    assert split_trailing_punct("x=1") == ("x=1", "")


def test_comparison_sees_neither_sides_copy():
    """A separated value and an unseparated one must score EQUAL — that is
    what keeps the two sides from diverging while a migration is in flight."""
    from pdfdrill.scoring import normalize_latex, latex_similarity
    assert normalize_latex("x = y,") == normalize_latex("x = y")
    assert latex_similarity("a=b.", "a=b") == 1.0
    assert latex_similarity(r"\frac{a}{b},", r"\frac{a}{b}") == 1.0
    # it must not make genuinely different math compare equal
    assert latex_similarity("a=b,", "a=c") < 1.0


def test_cmd_trailingpunct_separates_stamps_and_is_idempotent():
    from docmodel.core import Document, DocObject
    from pdfdrill.model_io import save_model, load_model
    from pdfdrill.commands import cmd_trailingpunct, _model_path
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        lj = Path(d) / "doc.lines.json"
        lj.write_text('{"pages": []}')
        past = lj.stat().st_mtime - 100
        os.utime(lj, (past, past))
        doc = Document()
        eq = DocObject(type="Equation", props={"latex": "E = m c^{2},"})
        keep = DocObject(type="Equation", props={"latex": r"X \right."})
        doc.add(eq)
        doc.add(keep)
        sc = Sidecar(pdf)
        mp = _model_path(sc)
        mp.parent.mkdir(parents=True, exist_ok=True)
        save_model(mp, doc)
        sc.add_fact("MODEL_BUILT")
        sc.save()

        out = cmd_trailingpunct(pdf)
        assert "1 mark(s) moved" in out
        objs = load_model(mp).objects
        got = objs[eq.id].props
        assert got["latex"] == "E = m c^{2}"        # mathematics only
        assert got["trailing_punct"] == ","          # the character, kept
        assert got["latex_prepunct"] == "E = m c^{2},"   # original preserved
        assert got["edit_source"]["run"] >= 1        # P9 stamp
        assert "trailing_punct" not in objs[keep.id].props

        assert "0 mark(s) moved" in cmd_trailingpunct(pdf)   # idempotent


def test_report_sets_the_mark_beside_the_math_not_inside_it(tmp_path):
    from pdfdrill.report_tex import build_report
    tp = tmp_path / "k.tiddlers.json"
    tp.write_text(json.dumps([
        {"title": "k_EQ0001", "latex": "E = m c^{2}", "trailing_punct": ",",
         "page": "003", "equation_number": "(1)", "width": "10"},
    ]))
    build_report(tp, paper="a3", landscape=True)
    tex = (tmp_path / "report.tex").read_text()
    # the math cell renders the mathematics, then the character as text
    assert r"\FitMath{$\displaystyle E = m c^{2}$}," in tex


def test_build_report_with_crops_consumes_every_row_field(tmp_path):
    """Coverage hole that let a real failure through: the widest-crop loop
    only runs when crops AND px2mm are given, so the 5-vs-6 tuple mismatch
    introduced with trailing_punct passed every test and then failed on all
    four books at migration time."""
    from pdfdrill.report_tex import build_report
    crops = tmp_path / "crops"
    crops.mkdir()
    # a minimal but real JPEG so jpg_width() has something to read
    try:
        from PIL import Image
        Image.new("RGB", (120, 30), "white").save(crops / "k_EQ0001.jpg")
    except Exception:
        (crops / "k_EQ0001.jpg").write_bytes(b"\xff\xd8\xff\xdb" + b"\x00" * 600)
    tp = tmp_path / "k.tiddlers.json"
    tp.write_text(json.dumps([
        {"title": "k_EQ0001", "latex": "E = m c^{2}", "trailing_punct": ",",
         "page": "003", "equation_number": "(1)", "width": "120"},
        {"title": "k_FO0001", "latex": "x_{5}", "trailing_punct": "."},
    ]))
    r = build_report(tp, crops=crops, paper="a3", landscape=True, px2mm=0.1)
    assert r["equations"] == 1 and r["formulas"] == 1
    tex = (tmp_path / "report.tex").read_text()
    assert r"\FitMath{$\displaystyle E = m c^{2}$}," in tex
    assert r"\FitMath{$\displaystyle x_{5}$}." in tex


def test_demoted_row_keeps_parity_because_neither_side_shows_the_mark():
    """The branch bh2 could not exercise (inkdrill, 2026-08-20): a row whose
    LaTeX will not typeset falls back to '(not rendered)', so there is no
    math box for the mark to sit after. Parity still holds — BEFORE the
    migration the mark was inside a latex value that never rendered either,
    so both sides show exactly '(not rendered)' and no mark."""
    from pdfdrill.report_tex import row
    # A value renderable() genuinely refuses. NOT `\[ x \] \end{itemize}`
    # any more — that shape is now REPAIRED (the stray closer is dropped), so
    # using it here would silently stop exercising the demoted-row branch this
    # test exists for. An environment opened and never closed still cannot
    # typeset, and is the honest specimen.
    bad = r"\frac{a}{b} \begin{array}{c} 1"
    # 099 inserted the Conf. column third, so Source is index 3 and the
    # Rendered cell this test is about is index 4. Indexing from the END
    # would survive the next column too, but the row may or may not carry a
    # Scan image, so the count from the left is the stable one.
    cell = lambda r: r.split("&")[4].strip()
    pre = row("id", bad + ",", "007")        # unmigrated: mark inside latex
    post = row("id", bad, "007", punct=",")  # migrated: mark separated out
    assert cell(pre) == cell(post) == r"\emph{(not rendered)} \\ \hline"
    assert "," not in cell(post)             # no orphan mark after the text

    # and a trailing mark never decides whether a value renders, so the
    # migration cannot move a row between the rendered and demoted classes
    from pdfdrill.report_tex import renderable
    for v in (r"x = y", r"\frac{a}{b}", bad, r"a & b"):
        assert bool(renderable(v)) == bool(renderable(v + ","))
