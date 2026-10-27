r"""A TikZ image row renders. It did not, in either half of the report.

THE DEFECT (gemma4-ba, 2026-10-27, owner's yes relayed the same day). Every
TikZ row in evidence-image.pdf printed `(not rendered)`, and the SVG that
`pdfdrill svg` had already built was never consulted:

  * `reports/tex.py::_rendered` has exactly one route to a separate compile,
    `rt.needs_own_document`, and that predicate was XY-pic only
    (`_XY_CONSTRUCT`). A `tikzpicture` body is not legal display maths, so
    `display_safe` returns "" for it, and the row fell to `(not rendered)`.
    Measured by gemma4-ba over the 54 `svg_ok` rows of their corpus:
    `display_safe` true for 2, `needs_own_document` true for 0.
  * The 2 that `display_safe` DID accept are `tikzcd` bodies. Those are worse
    than a refusal: a commutative diagram handed to the maths parser and set in
    a longtable cell is the 239-error shape `_ampersand_safe` exists for. They
    must take the standalone route too, which is what `needs_own_document`
    being asked FIRST already guarantees.
  * `reports/html.py` renders every row's LaTeX through KaTeX, which has no
    TikZ at all, so the HTML half said `(not rendered)` for its own reason.

THE SCOPE, as the owner set it: TikZ only — `tikzpicture` and `tikzcd`, the two
names already in `report_tex._PICTURE_ENVS`, plus a body that opens with
`\usetikzlibrary`. NOT widened to everything `region_standalone.
needs_math_wrapper` admits (tabular, minipage, axis, lstlisting, …), and the
dead `report_tex.region_render` is NOT deleted here. Both are separate
decisions and both are pinned below, so widening the gate has to be a
deliberate edit to a test that says why.

THE ROUTE ALREADY EXISTED. `region_standalone` was written for exactly this
content (its docstring counts tikzpicture 762 · tikzcd 658 corpus-wide) and
says why standalone beats the in-cell workaround: "the LaTeX is alone in its
own document, `&` means what its own environment says it means, and a failure
costs one PNG instead of the report". gemma4-ba verified it by calling it
directly on three of their rows: 3 of 3 PNGs, one checked by eye.

WHAT EACH HALF SHOWS (the owner's words): the PDF shows the standalone image;
the HTML shows `props['svg']` where it exists and that same standalone image
otherwise; a failure says `(not rendered)` and gives the error in BOTH halves.
The PDF half can never show the SVG — xelatex cannot `\includegraphics` one —
and that asymmetry is pinned here so it is not mistaken for an oversight.
"""
from __future__ import annotations

import re
from pathlib import Path

from pdfdrill import report_tex as rt
from pdfdrill.reports import html as H
from pdfdrill.reports import tex as T
from pdfdrill.reports.rows import EquationRow, ImageRow

TIKZPICTURE = (r"\begin{tikzpicture}\draw (0,0) -- (1,1) node {$\hat\tau$};"
               r"\end{tikzpicture}")
TIKZCD = (r"\usetikzlibrary{cd}" "\n"
          r"\begin{tikzcd} A \otimes A \rar{m} & A \end{tikzcd}")
XY = r"\xymatrix@=40pt{A \ar[r] & B}"
MATHS = r"\frac{a}{b} = \sum_{i} x_i"

WIDTHS = (20, 20, 20, 20, 100, 30)


# --------------------------------------------------------------- the predicate

def test_a_tikz_body_must_be_compiled_as_its_own_document():
    assert rt.needs_own_document(TIKZPICTURE)
    assert rt.needs_own_document(TIKZCD)
    assert rt.needs_own_document(r"\begin{tikzpicture}[scale=2] \end{tikzpicture}")


def test_a_body_that_only_loads_a_tikz_library_is_still_tikz():
    r"""The two rows `display_safe` wrongly accepted open with
    `\usetikzlibrary{cd}`, and the owner named that spelling as a trigger of
    its own: a preamble line in a cell is not maths either."""
    assert rt.needs_own_document(r"\usetikzlibrary{cd}")
    assert rt.needs_own_document(r"\usetikzlibrary{arrows,matrix}" "\nA \\to B")


def test_xy_still_takes_the_route_it_bought():
    """836's rule is not replaced, it is joined."""
    assert rt.needs_own_document(XY)
    assert rt.needs_own_document(r"\xygraph{a}")


def test_ordinary_maths_is_still_set_in_the_cell():
    assert not rt.needs_own_document(MATHS)
    assert not rt.needs_own_document("")
    assert not rt.needs_own_document(None)


def test_the_gate_is_a_construct_not_a_substring():
    r"""`\xyzzy` was the lesson the first time. The same rule for tikz: a
    document that TALKS about tikzpicture, or a macro whose name starts with
    the library command, is ordinary content."""
    assert not rt.needs_own_document(r"\xyzzy{a}")
    assert not rt.needs_own_document("the tikzpicture environment")
    assert not rt.needs_own_document(r"\usetikzlibraryfoo{x}")


def test_the_tikz_names_come_from_the_module_s_one_list():
    """ONE PLACE TO DECIDE. The names are `_PICTURE_ENVS`, the list
    `region_render` was built on and the list the corpus measurement in its
    comment counted. A second literal list here would drift from it."""
    assert rt._PICTURE_ENVS == ("tikzpicture", "tikzcd")
    for env in rt._PICTURE_ENVS:
        assert rt.needs_own_document("\\begin{%s} x \\end{%s}" % (env, env)), env


def test_the_gate_was_not_widened_past_tikz():
    """The owner's yes covers TikZ. `region_standalone.needs_math_wrapper`
    admits tabular, minipage, axis, lstlisting and more; routing those too is a
    separate decision and must not arrive as a side effect of this one."""
    for env in ("tabular", "minipage", "axis", "groupplot", "lstlisting",
                "verbatim", "itemize", "center", "scope", "pgfonlayer"):
        assert not rt.needs_own_document("\\begin{%s} x \\end{%s}" % (env, env)), env


def test_region_render_is_still_here():
    """NOT deleted by this change. It is unreachable (no call site in src/),
    and removing it is the owner's separate call — recorded, not acted on."""
    assert callable(rt.region_render)


# ------------------------------------------------------- the compile, and once

def _fake_render(calls, png=True, err="! Undefined control sequence."):
    def _r(ident, latex, out_dir, dpi=400, timeout=90, author_preamble="",
           graphics_dir=None, texinputs=None):
        calls.append({"ident": ident, "latex": latex, "out_dir": Path(out_dir),
                      "author_preamble": author_preamble, "dpi": dpi})
        if not png:
            return None, err
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        p = Path(out_dir) / ("%s.png" % ident)
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        return p, None
    return _r


def test_the_png_is_compiled_with_the_author_s_preamble(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render(calls))
    png, err = rt.standalone_png(TIKZPICTURE, "D1", tmp_path,
                                 author_preamble="\\documentclass{book}")
    assert err == ""
    assert png is not None and png.is_file()
    assert png.parent == tmp_path / "standalone-math"
    assert calls[0]["author_preamble"] == "\\documentclass{book}"
    assert calls[0]["latex"] == TIKZPICTURE, "RAW: the wrapper is the renderer's"


def test_a_compiled_png_is_not_compiled_again(tmp_path, monkeypatch):
    """The two halves of one report ask for the same row. The PDF half pays for
    the compile and the HTML half must not pay again."""
    calls = []
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render(calls))
    first, _ = rt.standalone_png(TIKZPICTURE, "D1", tmp_path)
    second, err = rt.standalone_png(TIKZPICTURE, "D1", tmp_path)
    assert err == "" and second == first
    assert len(calls) == 1, calls


def test_a_refusal_is_remembered_so_the_second_half_is_not_charged_for_it(
        tmp_path, monkeypatch):
    """A failed xelatex costs up to the timeout and leaves no log behind
    (`region_standalone._clean` removes it). Without a memo the HTML half
    repeats every failing compile of the PDF half, and has no error to show."""
    calls = []
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render(calls, png=False))
    png, err = rt.standalone_png(TIKZPICTURE, "D1", tmp_path)
    assert png is None and "Undefined control sequence" in err
    png2, err2 = rt.standalone_png(TIKZPICTURE, "D1", tmp_path)
    assert png2 is None and err2 == err
    assert len(calls) == 1, "the refusal was recompiled"


def test_a_remembered_refusal_is_keyed_to_WHAT_was_compiled(tmp_path, monkeypatch):
    """`packages_extra` and the author's preamble are both expected to change
    under these rows (gemma4-ba's two dsfont/mathtools failures wait on
    exactly that). A memo that outlived its input would make the retry a
    no-op and report the old error forever."""
    calls = []
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render(calls, png=False))
    rt.standalone_png(TIKZPICTURE, "D1", tmp_path)
    rt.standalone_png(TIKZPICTURE, "D1", tmp_path, author_preamble=r"\usepackage{dsfont}")
    assert len(calls) == 2, "a changed preamble must be tried"
    rt.standalone_png(TIKZCD, "D1", tmp_path)
    assert len(calls) == 3, "a changed body must be tried"


# ------------------------------------------------------------------ the PDF half

def test_the_pdf_cell_shows_the_standalone_image(tmp_path, monkeypatch):
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render([]))
    r = ImageRow(identifier="D1", latex=TIKZPICTURE)
    cell = T._rendered(r, WIDTHS, tmp_path, "author preamble")
    assert "\\includegraphics" in cell
    assert "standalone-math/D1.png" in cell
    assert "(not rendered)" not in cell


def test_a_tikzcd_display_safe_would_have_accepted_goes_standalone_anyway(
        tmp_path, monkeypatch):
    """THE 2 ROWS. `display_safe` accepts these bodies; setting them in a
    longtable cell is the defect, not the remedy. The gate is asked first."""
    assert rt.display_safe(TIKZCD), "precondition: display_safe accepts it"
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render([]))
    cell = T._rendered(ImageRow(identifier="D2", latex=TIKZCD), WIDTHS,
                       tmp_path, "")
    assert "\\includegraphics" in cell
    assert "FitMath" not in cell and "tikzcd" not in cell


def test_a_bare_ampersand_is_no_longer_a_refusal(tmp_path, monkeypatch):
    r"""`_ampersand_safe` had no workaround for a `\matrix` node inside a
    tikzpicture, because a longtable claims `&`. Alone in its own document
    there is no table to claim it."""
    body = (r"\begin{tikzpicture}\matrix{ a & b \\ c & d };\end{tikzpicture}")
    assert rt._ampersand_safe(body, "tikzpicture") is None, "precondition"
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render([]))
    cell = T._rendered(ImageRow(identifier="D3", latex=body), WIDTHS, tmp_path, "")
    assert "\\includegraphics" in cell


def test_a_failed_compile_costs_one_row_and_says_why(tmp_path, monkeypatch):
    """836's rule, unchanged: one unrenderable row costs one row. What is new
    is that the row now carries the reason, which is what the owner asked for."""
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render([], png=False, err="! Undefined control sequence."))
    cell = T._rendered(ImageRow(identifier="D4", latex=TIKZPICTURE), WIDTHS,
                       tmp_path, "")
    assert cell.startswith("\\emph{(not rendered)}"), cell
    assert "Undefined control sequence" in cell
    assert "\\begin{tikzpicture}" not in cell, (
        "the failing body must not be emitted into the cell — that is the "
        "0-page report")


def test_the_pdf_half_never_shows_the_svg(tmp_path, monkeypatch):
    """xelatex cannot \\includegraphics an SVG. A row that HAS one and whose
    compile fails still refuses, rather than emitting markup into LaTeX."""
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render([], png=False))
    r = ImageRow(identifier="D5", latex=TIKZPICTURE, svg="<svg><g/></svg>")
    cell = T._rendered(r, WIDTHS, tmp_path, "")
    assert "<svg" not in cell
    assert cell.startswith("\\emph{(not rendered)}")


def test_a_listing_row_is_unchanged(tmp_path):
    """695a's route is ahead of the gate and stays there: a code listing is
    set as monospace, never compiled as a picture."""
    r = ImageRow(identifier="D6", latex="", listing="for i in range(3): pass")
    cell = T._rendered(r, WIDTHS, tmp_path, "")
    assert "includegraphics" not in cell and "range(3)" in cell


def test_an_equation_row_is_unchanged(tmp_path):
    cell = T._rendered(EquationRow(identifier="E1", latex=MATHS), WIDTHS,
                       tmp_path, "")
    assert cell.startswith("\\FitMath{$\\displaystyle")


# ----------------------------------------------------------------- the HTML half

def _html_row(r, tmp_path, author_preamble=""):
    return H._row(r, Path(tmp_path), display=False,
                  author_preamble=author_preamble)


def test_the_html_cell_prefers_the_svg_the_model_already_carries(tmp_path):
    svg = ('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
           '<path id="g0-48" d="M0 0"/><use xlink:href="#g0-48"/></svg>')
    r = ImageRow(identifier="D1", latex=TIKZPICTURE, svg=svg)
    out = _html_row(r, tmp_path)
    assert "<svg" in out and "</svg>" in out
    assert "math-render" not in out, "KaTeX has no TikZ"
    assert "<?xml" not in out, "the XML prolog must not land mid-document"


def test_the_html_svg_ids_are_namespaced(tmp_path):
    """dvisvgm restarts its glyph names at g0-1 per file and an id is
    document-global: 112 of 336 references drew the wrong glyph before
    `svg_ids` existed. This page inlines every row's SVG."""
    svg = '<svg><path id="g0-48" d="M0 0"/><use xlink:href="#g0-48"/></svg>'
    out = _html_row(ImageRow(identifier="D1_DIA_0001", latex=TIKZPICTURE,
                             svg=svg), tmp_path)
    assert 'id="g0-48"' not in out
    assert re.search(r'id="D1_DIA_0001-g0-48"', out), out
    assert 'xlink:href="#D1_DIA_0001-g0-48"' in out


def test_the_html_cell_falls_back_to_the_standalone_image(tmp_path, monkeypatch):
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render([]))
    out = _html_row(ImageRow(identifier="D2", latex=TIKZPICTURE), tmp_path)
    assert '<img src="standalone-math/D2.png"' in out
    assert "math-render" not in out


def test_the_html_cell_says_why_when_the_compile_failed(tmp_path, monkeypatch):
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render([], png=False, err="! LaTeX Error: File `dsfont.sty' not found."))
    out = _html_row(ImageRow(identifier="D3", latex=TIKZPICTURE), tmp_path)
    assert "(not rendered)" in out
    assert "dsfont.sty" in out
    assert "<img" not in out


def test_the_html_cell_reports_the_svg_error_the_model_recorded(tmp_path, monkeypatch):
    """`pdfdrill svg` records its own failure in `svg_error`. A row with that
    and no compile of its own has two reasons and must not hide either."""
    monkeypatch.setattr("pdfdrill.region_standalone.render",
                        _fake_render([], png=False, err="! timeout"))
    out = _html_row(ImageRow(identifier="D4", latex=TIKZPICTURE,
                             svg_error="dvisvgm: no output"), tmp_path)
    assert "(not rendered)" in out and "dvisvgm: no output" in out


def test_the_html_half_still_renders_ordinary_maths_with_katex(tmp_path):
    out = _html_row(EquationRow(identifier="E1", latex=MATHS), tmp_path)
    assert "math-render" in out and "standalone-math" not in out


def test_the_html_source_column_still_shows_the_tikz_body(tmp_path, monkeypatch):
    """The LaTeX-source column is the evidence; only the Rendered cell changes."""
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render([]))
    out = _html_row(ImageRow(identifier="D5", latex=TIKZPICTURE), tmp_path)
    assert "tikzpicture" in out


def test_both_halves_name_the_same_file(tmp_path, monkeypatch):
    """One row model, one image: the HTML `<img src>` and the LaTeX
    `\\includegraphics` must point at the same PNG, or one half silently
    recompiles into a second file."""
    monkeypatch.setattr("pdfdrill.region_standalone.render", _fake_render([]))
    r = ImageRow(identifier="D6", latex=TIKZPICTURE)
    tex_cell = T._rendered(r, WIDTHS, tmp_path, "")
    html_cell = _html_row(r, tmp_path)
    name = "standalone-math/D6.png"
    assert name in tex_cell and name in html_cell


# ------------------------------------------------------------------- the row

def test_the_row_carries_the_svg_and_its_error():
    """`props['svg']` and `props['svg_error']` are written by `pdfdrill svg`
    (commands.py) and were read by `formula_report` only — the evidence row
    could not see them."""
    from docmodel.core import Document, DocObject
    from pdfdrill.reports.from_document import build_rows
    doc = Document(meta={"bibkey": "DOC"})
    doc.add(DocObject(id="d1", type="Diagram",
                      props={"flow_index": 1, "latex_code": TIKZPICTURE,
                             "page": 6, "svg": "<svg/>", "svg_error": "boom"}))
    rows = build_rows(doc, "DOC")["image"]
    assert len(rows) == 1
    assert rows[0].svg == "<svg/>"
    assert rows[0].svg_error == "boom"


def test_a_row_without_a_graphic_carries_neither():
    r = ImageRow(identifier="D1")
    assert r.svg == "" and r.svg_error == ""


# ------------------------------------------------------------- the two halves

def test_the_html_half_gets_the_author_s_preamble_too(tmp_path, monkeypatch):
    """286: without the author's preamble 69 of 207 sampled regions failed on
    their own macros and figure paths. The HTML half compiles the same rows,
    so it must compile them the same way — otherwise the two halves of one
    report disagree about which rows render."""
    from pdfdrill.reports import evidence as E

    seen = {}

    def _spy(rows, kind, *, title, doc_dir, meta_lines=(), caption=None,
             ink_codes=False, author_preamble=""):
        seen["author_preamble"] = author_preamble
        return "<html></html>"

    monkeypatch.setattr(E.H, "render_page", _spy)
    res = E.build({"image": [ImageRow(identifier="D1", latex=TIKZPICTURE)]},
                  "image", "html", doc_dir=tmp_path, pdf=tmp_path / "x.pdf",
                  bibkey="DOC", history=None, px2mm=None, paper="a4",
                  landscape=False, compile_pdf=False,
                  meta={"latex_preamble": {"standalone": "\\documentclass{book}"}})
    assert res["rows"] == 1
    assert seen.get("author_preamble") == "\\documentclass{book}"
