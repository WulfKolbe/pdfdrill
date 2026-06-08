"""
Tests for TikZ/table extraction (latex_source.extract_graphics), the
\\[4pt] display-math false-match fix, and the SVG compiler (gated on whether
latex+dvisvgm are installed).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import latex_source as ls
from pdfdrill import svg as svgmod
from pdfdrill import commands


def test_ingest_source_graphics_creates_diagram_and_table_objects():
    # `pdfdrill latex` must ingest the source's TikZ/tables (e.g. commutative
    # diagrams via tikzcd) as Diagram/Table objects with latex_code, so a later
    # `pdfdrill svg` can render them — not just attach equations.
    from docmodel.core import Document
    doc = Document(); doc.meta["bibkey"] = "T"
    body = (r"intro \begin{tikzcd} A \arrow[r] & B \end{tikzcd} mid "
            r"\begin{tabular}{cc} a & b \end{tabular} end")
    n = commands.ingest_source_graphics(doc, body, {}, "T")
    assert n == 2
    digs = doc.objects_of_type("Diagram"); tabs = doc.objects_of_type("Table")
    assert len(digs) == 1 and len(tabs) == 1
    assert "tikzcd" in digs[0].props["latex_code"]
    assert digs[0].props["latex_original"] and digs[0].props["added_by"] == "latex"
    assert svgmod.is_latex_graphic(digs[0].props["latex_code"])
    # idempotent: re-ingesting the same body adds nothing
    assert commands.ingest_source_graphics(doc, body, {}, "T") == 0


def test_standalone_preamble_keeps_multiline_macro_bodies():
    # A multi-line \newcommand body must survive intact. The old line-anchored
    # regex (`\\newcommand.*`) captured only the first line, dropping the body and
    # leaving a runaway \newcommand that aborts latex (the 2510.15795 failure).
    pre = (r"\documentclass{article}" "\n"
           r"\usepackage{tikz-cd}" "\n"
           r"\newcommand\tailxrightarrow[2][]{" "\n"
           r"  \mathrel{\ooalign{$\xrightarrow[#1]{#2}$\cr" "\n"
           r"  \hidewidth$\Yright$}}" "\n"
           r"}" "\n"
           r"\newcommand{\fto}{\twoheadrightarrow}")
    sa = ls.standalone_preamble(pre)
    assert "tikz-cd" in sa
    assert "\\ooalign" in sa and "\\hidewidth" in sa      # multi-line body preserved
    assert "\\fto" in sa
    assert sa.count("{") == sa.count("}")                 # balanced (not truncated)
    assert "\\documentclass{article}" not in sa           # original docclass dropped
    assert "standalone" in sa


def test_standalone_preamble_keeps_font_primitive():
    # \font\name=... primitive font loads must survive — e.g. the Yoneda symbol
    # \yo built from \font\maljapanese=dmjhira (arXiv 2510.15795). Without the
    # \font line, \maljapanese is undefined and every \yo diagram fails.
    pre = ("\\documentclass{article}\n"
           "\\font\\maljapanese=dmjhira at 2ex\n"
           "\\def\\yo{\\textrm{\\maljapanese\\char\"48}}")
    sa = ls.standalone_preamble(pre)
    assert "\\font\\maljapanese=dmjhira at 2ex" in sa
    assert "\\def\\yo" in sa


def test_standalone_preamble_keeps_tikzset_block():
    # \tikzset{...} blocks define the custom arrow styles a tikzcd diagram uses
    # (e.g. utcofarrow in arXiv 2510.15795); the whole (multi-line, balanced)
    # block must be captured or the diagram fails with an undefined pgfkeys style.
    pre = ("\\documentclass{article}\n"
           "\\usepackage{tikz-cd}\n"
           "\\usetikzlibrary{decorations.markings}\n"
           "\\tikzset{\n"
           "  utcofarrow/.style={>->, dashed},\n"
           "  we/.style={postaction={decorate}}\n"
           "}\n"
           "\\newcommand{\\fto}{\\to}")
    sa = ls.standalone_preamble(pre)
    assert "\\usetikzlibrary{decorations.markings}" in sa   # tikz library kept
    assert "\\tikzset" in sa and "utcofarrow/.style" in sa
    assert "\\fto" in sa
    assert sa.count("{") == sa.count("}")     # full block captured, balanced


def test_rowspacing_not_mistaken_for_display_math():
    # \\[4pt] is an align row break, NOT a \[ ... \] display block.
    body = (r"\begin{align*} a &= b \\[4pt] c &= d \end{align*}"
            r" prose \[ \ell = 5 \] more")
    eqs = ls.extract_display_equations(body)
    envs = [e["env"] for e in eqs]
    assert "align" in envs
    dms = [e for e in eqs if e["env"] == "displaymath"]
    assert len(dms) == 1                      # only the real \[..\]
    assert "ell = 5" in dms[0]["latex"]
    # the align body is intact, not truncated at \\[4pt]
    al = next(e for e in eqs if e["env"] == "align")
    assert "c &= d" in al["latex"]


def test_align_body_wrapped_in_aligned_for_katex():
    body = (r"\begin{align*} \Gamma_0 &= [\,], \\[4pt] "
            r"\Gamma_{n} &= \big[[0,\Gamma_{n-1}]\big] \end{align*}")
    eq = ls.extract_display_equations(body)[0]
    # bare & / \\ must be wrapped so KaTeX can render them
    assert eq["latex"].startswith("\\begin{aligned}")
    assert eq["latex"].rstrip().endswith("\\end{aligned}")
    assert "&=" in eq["latex"] and "\\\\[4pt]" in eq["latex"]


def test_index_command_stripped_from_equation():
    body = r"\[ \deg_+(v)\index{$\deg_+$} = \sum_{e} 1 \]"
    eq = ls.extract_display_equations(body)[0]
    assert "\\index" not in eq["latex"]
    assert "\\deg_+(v)" in eq["latex"] and "\\sum" in eq["latex"]


def test_trailing_line_continuation_stripped():
    # source: "\[ \sum s(v) = 0,\ \ \ \ <newline> \]" -> dangling \ before \]
    body = "\\[ \\sum_{v} s(v) = 0,\\ \\ \\ \\\n \\]"
    eq = ls.extract_display_equations(body)[0]
    assert eq["latex"].rstrip().endswith("0,")     # trailing \ and spaces gone
    assert not eq["latex"].rstrip().endswith("\\")  # no lone trailing backslash


def test_naked_superscript_gets_empty_base():
    # the left-transpose idiom "\, ^tD" (no base before ^) is a KaTeX error;
    # _clean_eq inserts an empty base {} so it renders.
    out = ls._clean_eq(r"L = D\cdot \, ^tD = X", "")
    assert "\\, {}^tD" in out
    # real bases must NOT be altered
    assert ls._clean_eq(r"x^2 + a_b^c", "") == "x^2 + a_b^c"
    # opener / start cases
    assert ls._clean_eq(r"(^tA)", "") == "({}^tA)"
    assert ls._clean_eq(r"^{T}M", "").startswith("{}^{T}M")


def test_internal_rowbreak_not_stripped():
    # a real \\ row break inside an environment must survive _clean_eq
    assert "\\\\" in ls._clean_eq(r"\begin{cases} a \\ b \end{cases}", "")


def test_single_equation_not_wrapped():
    # a plain `equation` (no &) must NOT get an aligned wrapper
    body = r"\begin{equation} x = y + 1 \end{equation}"
    eq = ls.extract_display_equations(body)[0]
    assert "aligned" not in eq["latex"]


def test_extract_graphics_tikz_and_table():
    body = (r"\begin{figure}\begin{tikzpicture}\node{x};\end{tikzpicture}"
            r"\caption{A graph}\end{figure}"
            r"\begin{table}\begin{tabular}{ll}a&b\\\end{tabular}"
            r"\caption{A table}\end{table}")
    g = ls.extract_graphics(body)
    kinds = sorted(x["kind"] for x in g)
    assert kinds == ["Diagram", "Table"]
    tikz = next(x for x in g if x["kind"] == "Diagram")
    assert "\\begin{tikzpicture}" in tikz["code"] and "\\node{x};" in tikz["code"]
    assert tikz["caption"] == "A graph"


def test_build_source_model_includes_graphics():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        Path(d, "book.tex").write_text(
            r"\documentclass{book}\begin{document}"
            r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"
            r"\begin{tabular}{c}z\\\end{tabular}\end{document}")
        doc = ls.build_source_model(os.path.join(d, "book.tex"))
        dia = [o for o in doc.objects.values() if o.type == "Diagram"]
        tab = [o for o in doc.objects.values() if o.type == "Table"]
        assert len(dia) == 1 and len(tab) == 1
        assert dia[0].props["latex_code"].startswith("\\begin{tikzpicture}")
        assert doc.meta["source_counts"]["diagrams"] == 1


def test_svg_tools_flag_is_bool():
    assert isinstance(svgmod.tools_available(), bool)


def test_svg_compile_when_tools_present():
    if not svgmod.tools_available():
        print("  (skip: latex/dvisvgm not installed)")
        return
    res = svgmod.compile_to_svg(r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}")
    assert res["ok"], res.get("error")
    assert "<svg" in res["svg"]


def test_svg_compile_graceful_without_tools(monkeypatch):
    monkeypatch.setattr(svgmod.shutil, "which", lambda _x: None)
    res = svgmod.compile_to_svg(r"\draw (0,0)--(1,1);")
    assert res["ok"] is False and "dvisvgm" in res["error"]


def test_latexbook_autoruns_svg_and_embeds():
    """cmd_latexbook should render TikZ/tables and embed SVG in the report in
    one step (when latex/dvisvgm are present)."""
    import tempfile, os
    from pdfdrill.commands import cmd_latexbook
    with tempfile.TemporaryDirectory() as d:
        book = Path(d) / "book.tex"
        book.write_text(
            r"\documentclass{book}\begin{document}"
            r"\section{S}\begin{equation} x=1 \end{equation}"
            r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"
            r"\end{document}")
        msg = cmd_latexbook(book)
        report = (book.parent / "book.tex.drill" / "formula-report.html").read_text()
        if svgmod.tools_available():
            assert "1/1 TikZ/tables rendered to SVG" in msg
            assert "<svg" in report            # embedded inline, one step
        else:
            assert "NOT rendered" in msg or "no_svg" in msg.lower()


def test_latexbook_no_svg_skips_rendering():
    import tempfile
    from pdfdrill.commands import cmd_latexbook
    with tempfile.TemporaryDirectory() as d:
        book = Path(d) / "book.tex"
        book.write_text(
            r"\documentclass{book}\begin{document}"
            r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}\end{document}")
        msg = cmd_latexbook(book, no_svg=True)
        assert "TikZ/tables rendered" not in msg   # rendering skipped
        report = (book.parent / "book.tex.drill" / "formula-report.html").read_text()
        assert "<svg" not in report


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, fn in tests:
        mp = _MP()
        try:
            if "monkeypatch" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                fn(mp)
            else:
                fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
        finally:
            mp.undo()
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
