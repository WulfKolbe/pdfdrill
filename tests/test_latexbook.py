"""
Tests for the source-only LaTeX path: local .sty macro resolution
(collect_macros), section extraction, and build_source_model — used by
`pdfdrill latexbook`. No PDF, no MathPix.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import latex_source as ls


def _make_book(d: Path):
    # local style package with custom macros (mimics graphbook's mystyle.sty)
    (d / "style").mkdir()
    (d / "style" / "mystyle.sty").write_text(
        r"\newcommand{\R}{\mathbb{R}}"
        "\n\\DeclareMathOperator*{\\iadj}{iadj}\n")
    (d / "tex").mkdir()
    (d / "tex" / "ch1.tex").write_text(
        r"\section{First}"
        r"\begin{equation}\label{e1} x \in \R \end{equation}")
    (d / "book.tex").write_text(
        r"\documentclass{book}"
        "\n\\usepackage{mystyle}\n"
        r"\begin{document}\input{tex/ch1}"
        r"\begin{equation} \iadj(v) \subseteq V \end{equation}"
        r"\end{document}")
    return d / "book.tex"


def test_collect_macros_resolves_local_style_file():
    with tempfile.TemporaryDirectory() as dd:
        book = _make_book(Path(dd))
        full, _ = ls.read_source(str(book))
        pre, _ = ls.split_preamble(full)
        macros = ls.collect_macros(pre, str(book.parent))
        # \R and \iadj are defined in style/mystyle.sty, reached via \usepackage
        assert "R" in macros and "iadj" in macros
        assert macros["iadj"]["body"] == "\\operatorname{iadj}"


def test_extract_sections_in_order():
    body = r"\chapter{A} text \section{B} more \subsection{C}"
    secs = ls.extract_sections(body)
    assert [s["caption"] for s in secs] == ["A", "B", "C"]
    assert [s["level"] for s in secs] == [1, 2, 3]


def test_build_source_model_expands_style_macros():
    with tempfile.TemporaryDirectory() as dd:
        book = _make_book(Path(dd))
        doc = ls.build_source_model(str(book), bibkey="BK")
        eqs = [o for o in doc.objects.values() if o.type == "Equation"]
        secs = [o for o in doc.objects.values() if o.type == "Section"]
        assert len(eqs) == 2 and len(secs) == 1
        latexes = " ".join(e.props["latex"] for e in eqs)
        # \R -> \mathbb{R}, \iadj -> \operatorname{iadj} (expanded from .sty)
        assert "\\mathbb{R}" in latexes
        assert "\\operatorname{iadj}" in latexes
        assert "\\R" not in latexes and "\\iadj" not in latexes
        assert doc.meta["source_counts"]["macros"] >= 2


def test_build_source_model_dedupes_repeated_inline_formula():
    r"""The 2110.11150 bug: the symbol $f$ used 20 times became 20 separate FO
    tiddlers. Identical inline-formula content must map to ONE Formula object /
    one FO tiddler, transcluded everywhere (LATW FormulaScanner parity)."""
    import re
    with tempfile.TemporaryDirectory() as dd:
        tex = Path(dd) / "main.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{A}\nWe use $f$ and $g$ and again $f$ here.\n"
            "\\section{B}\nLater $f$ appears once more, also $g$.\n"
            "\\end{document}\n", encoding="utf-8")
        doc = ls.build_source_model(str(tex), bibkey="K")
        fos = [o for o in doc.objects.values() if o.type == "Formula"]
        latexes = sorted(o.props.get("latex") for o in fos)
        assert latexes == ["f", "g"]                       # was [f,f,f,g,g] before
        # every {{K_FO..||FO}} marker for f resolves to the SAME tiddler title
        marks = []
        for p in doc.objects.values():
            if p.type == "Paragraph":
                marks += re.findall(r"\{\{(K_FO\d+)\|\|FO\}\}", p.props.get("text", ""))
        # f appears 3x, g 2x → 5 markers but only 2 distinct titles
        assert len(marks) == 5 and len(set(marks)) == 2


def test_extract_sections_marks_appendix():
    r"""\appendix switches every following section into the appendix — the
    2110.11150 'large appendix' case. extract_sections must flag them so the
    TOC analysis can letter them (A, B, ...)."""
    body = (r"\section{Intro} a \section{Method} b "
            r"\appendix \section{Proofs} c \subsection{Lemmas} d")
    secs = ls.extract_sections(body)
    assert [(s["caption"], s.get("is_appendix", False)) for s in secs] == [
        ("Intro", False), ("Method", False), ("Proofs", True), ("Lemmas", True)]
    # the \begin{appendices} environment form is recognised too
    secs2 = ls.extract_sections(r"\section{Body} x \begin{appendices}\section{Extra} y")
    assert [s.get("is_appendix", False) for s in secs2] == [False, True]
    assert ls.find_appendix_pos(r"\section{X} no appendix here") == -1


def test_mark_appendix_from_source_overlays_onto_mathpix_model():
    r"""A MathPix/OCR model has Section objects but no \appendix knowledge. With
    the arXiv LaTeX source on hand (the 2110.11150 case), overlay it: every
    model section at/after the source \appendix is flagged. Tail-sticky, so it
    survives MathPix caption drift in the (large) appendix."""
    from docmodel.core import Document, DocObject
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        (d / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Introduction}\n\\section{Method}\n\\section{Experiments}\n"
            "\\appendix\n\\section{Theory}\n\\section{More Experiments}\n"
            "\\end{document}\n", encoding="utf-8")
        doc = Document(); doc.meta["bibkey"] = "z"
        # MathPix-style sections: same order, slight caption drift, NO is_appendix
        caps = ["Introduction", "Method", "Experiments", "Theory",
                "More Experiments and extra OCR words"]
        for i, c in enumerate(caps, 1):
            doc.add(DocObject(type="Section",
                              props={"caption": c, "level": 2, "flow_index": i}))
        n = ls.mark_appendix_from_source(doc, str(d))
        secs = sorted((o for o in doc.objects.values() if o.type == "Section"),
                      key=lambda o: o.props["flow_index"])
        assert n == 2
        assert [s.props.get("is_appendix", False) for s in secs] == [
            False, False, False, True, True]
        # no appendix in source → no-op
        (d / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n\\section{A}\n"
            "\\end{document}\n", encoding="utf-8")
        assert ls.mark_appendix_from_source(Document(), str(d)) == 0


def test_build_source_model_marks_appendix_sections():
    with tempfile.TemporaryDirectory() as dd:
        tex = Path(dd) / "main.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Intro}\nbody one.\n\\section{Method}\nbody two.\n"
            "\\appendix\n\\section{Proofs}\nappendix one.\n"
            "\\subsection{Lemmas}\nappendix two.\n\\end{document}\n",
            encoding="utf-8")
        doc = ls.build_source_model(str(tex), bibkey="z")
        secs = sorted((o for o in doc.objects.values() if o.type == "Section"),
                      key=lambda o: o.props.get("flow_index", 0))
        assert [s.props.get("caption") for s in secs] == [
            "Intro", "Method", "Proofs", "Lemmas"]
        assert [s.props.get("is_appendix", False) for s in secs] == [
            False, False, True, True]


def test_build_source_model_flow_order():
    with tempfile.TemporaryDirectory() as dd:
        book = _make_book(Path(dd))
        doc = ls.build_source_model(str(book))
        ordered = sorted(doc.objects.values(), key=lambda o: o.props.get("flow_index", 0))
        types = [o.type for o in ordered if o.type in ("Section", "Equation")]
        # \section, then ch1's equation, then book's second equation
        assert types == ["Section", "Equation", "Equation"]


def test_find_main_tex_real_content_and_multifile_input_expansion():
    """Multi-file \\input papers: find_main_tex must pick the \\documentclass file
    by CONTENT (not the alphabetically-first body file — the bug that truncated
    2104.08926), and build_source_model must expand \\input so body-file \\cites
    are extracted."""
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        (d / "aaa_intro.tex").write_text(   # alphabetically FIRST, no documentclass
            "Intro \\cite{alpha} and \\cite{beta}.\n", encoding="utf-8")
        (d / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n\\input{aaa_intro}\n"
            "\\begin{thebibliography}{1}\n\\bibitem{alpha} A.\n\\bibitem{beta} B.\n"
            "\\end{thebibliography}\n\\end{document}\n", encoding="utf-8")
        paths = {str(p): p.read_text() for p in d.glob("*.tex")}
        assert ls.find_main_tex(paths).endswith("main.tex")     # by content, not name
        doc = ls.build_source_model(ls.find_main_tex(paths), bibkey="z")
        cks = sorted(c.props["citekey"] for c in doc.objects.values()
                     if c.type == "Citation")
        assert cks == ["alpha", "beta"]                          # \input expanded


def test_latexbook_marks_model_built_so_projectors_dont_rebuild():
    """The mass-run collision: latexbook wrote a model but never set MODEL_BUILT,
    so projectors saw 'not built' and force-rebuilt via MathPix/OCR, clobbering
    the keyless source model. cmd_latexbook must mark it built and not look stale."""
    from pdfdrill import commands as K
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as dd:
        tex = Path(dd) / "main.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Intro}\nHello $E=mc^2$ and a display \\[ a^2+b^2=c^2 \\].\n"
            "\\end{document}\n", encoding="utf-8")
        K.cmd_latexbook(tex, no_svg=True)
        sc = Sidecar(tex)
        assert sc.has(K.MODEL_BUILT)
        mp = K._model_path(sc)
        assert mp.exists()
        # no lines.json, but built → projectors must NOT consider it stale
        assert K._stale_or_absent(sc, mp, K._lines_json_path(tex)) is False


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
