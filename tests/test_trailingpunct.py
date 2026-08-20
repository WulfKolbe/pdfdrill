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
