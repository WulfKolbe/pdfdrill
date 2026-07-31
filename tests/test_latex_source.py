"""
Tests for the LaTeX-source layer (pdfdrill.latex_source): input expansion,
preamble macros, bounded-fixpoint expansion, display-equation extraction,
and the two-LaTeX (original + expanded) forms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import latex_source as ls


_TEX = r"""
\documentclass{article}
\usepackage{amsmath}
\newcommand{\R}{\mathbb{R}}
\newcommand{\norm}[1]{\left\| #1 \right\|}
\DeclareMathOperator{\Tr}{Tr}
\def\eps{\varepsilon}
\begin{document}
Intro text.
\begin{equation}\label{eq:one}
  x \in \R, \quad \norm{x} \le \eps
\end{equation}
Some prose with inline $a+b$ that must be ignored.
\begin{align*}
  \Tr(A) &= \sum_i a_{ii}
\end{align*}
\[ E = mc^2 \]
\end{document}
"""


def test_split_and_macros():
    pre, body = ls.split_preamble(_TEX)
    assert "\\documentclass" in pre and "\\begin{equation}" in body
    m = ls.extract_macros(pre)
    assert set(m) >= {"R", "norm", "Tr", "eps"}
    assert m["norm"]["nargs"] == 1
    assert m["Tr"]["body"] == "\\operatorname{Tr}"


def test_display_equation_extraction_numbered_flag():
    _, body = ls.split_preamble(_TEX)
    eqs = ls.extract_display_equations(body)
    envs = [e["env"] for e in eqs]
    assert "equation" in envs and "align" in envs and "displaymath" in envs
    eq1 = next(e for e in eqs if e["env"] == "equation")
    assert eq1["numbered"] is True and eq1["label"] == "eq:one"
    al = next(e for e in eqs if e["env"] == "align")
    assert al["numbered"] is False           # align* is starred


def test_macro_expansion_fixpoint():
    pre, body = ls.split_preamble(_TEX)
    m = ls.extract_macros(pre)
    eq1 = next(e for e in ls.extract_display_equations(body) if e["env"] == "equation")
    expanded = ls.expand_macros(eq1["latex"], m)
    assert "\\mathbb{R}" in expanded            # \R expanded
    assert "\\left\\|" in expanded              # \norm{...} expanded with arg
    assert "\\varepsilon" in expanded           # \eps expanded
    assert "\\R" not in expanded and "\\norm" not in expanded
    al = next(e for e in ls.extract_display_equations(body) if e["env"] == "align")
    assert "\\operatorname{Tr}" in ls.expand_macros(al["latex"], m)


def test_read_source_tex_file_with_input(tmp_path=None):
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        sub = os.path.join(d, "sec.tex")
        open(sub, "w").write(r"\begin{equation} y = 1 \end{equation}")
        main = os.path.join(d, "main.tex")
        open(main, "w").write(
            r"\documentclass{article}\begin{document}\input{sec}\end{document}")
        full, name = ls.read_source(main)
        assert "y = 1" in full and name == "main.tex"


def test_standalone_preamble():
    pre, _ = ls.split_preamble(_TEX)
    sa = ls.standalone_preamble(pre)
    assert sa.startswith("\\documentclass[border=2pt,class=report]{standalone}")
    assert "\\usepackage{amsmath}" in sa
    assert "\\newcommand{\\R}" in sa or "newcommand" in sa


def test_cmd_latex_attaches_tex_provenance_end_to_end():
    """Guards the full wiring: cmd_latex must attach a tex candidate to the
    matching MathPix equation (this caught a missing CLI registration once)."""
    import json, tempfile, os
    from docmodel.core import Document, DocObject, Realization
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import cmd_injectlatex, MODEL_BUILT

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "p.pdf"
        pdf.write_bytes(b"%PDF-1.7")
        # a model with one equation whose OCR latex ~ the source equation
        doc = Document()
        doc.add(DocObject(type="Equation", props={
            "latex": r"E = m c^{2}", "refnum": "1", "page": 1, "cdn_url": "u"}))
        sc = Sidecar(pdf)
        sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT)
        sc.save()
        # the author source
        tex = Path(d) / "p.tex"
        tex.write_text(r"\documentclass{article}\begin{document}"
                       r"\begin{equation} E = mc^2 \end{equation}\end{document}")

        msg = cmd_injectlatex(pdf, tex=str(tex))
        assert "Attached 1" in msg
        m = json.loads((sc.blob_dir / "model.docmodel.json").read_text())
        eq = m["objects"][0]
        tx = [r for r in eq["realizations"] if r.get("provenance") == "tex"]
        assert tx and tx[0]["props"]["latex_original"].strip().startswith("E = mc^2")


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


def test_read_source_gzipped_bare_tex():
    """arXiv serves a SINGLE-FILE submission as gzip(paper.tex), not
    gzip(tar(...)). `is_tarfile` is False for it, so before this was handled the
    plain-text fallback read the compressed bytes as LaTeX and every caller saw
    "0 display equations, 0 preamble macros" from a source that had both."""
    import gzip
    import os
    import tempfile

    src = (r"\documentclass{article}"
           r"\newcommand{\R}{\mathbb{R}}"
           r"\begin{document}"
           r"\[ x \in \R \]"
           r"\end{document}")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "1234.5678.tgz")
        # the stored member name must differ from the file on disk, which is
        # exactly how arXiv ships these
        with open(p, "wb") as raw:
            with gzip.GzipFile(filename="1234.5678.tex", mode="wb",
                               fileobj=raw) as fh:
                fh.write(src.encode())
        full, name = ls.read_source(p)

    assert r"\in" in full, "compressed bytes were read as text"
    assert name == "1234.5678.tex", "original name comes from the gzip header"
    pre, body = ls.split_preamble(full)
    assert "R" in ls.extract_macros(pre)
    assert len(ls.extract_display_equations(body)) == 1


def test_read_source_still_prefers_tar_over_gzip_branch():
    """A real .tgz (gzip of a tar) must keep taking the tarball path."""
    import io
    import os
    import tarfile
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "multi.tgz")
        payload = (r"\documentclass{article}\begin{document}"
                   r"\begin{equation} E = mc^2 \end{equation}\end{document}").encode()
        with tarfile.open(p, "w:gz") as tf:
            ti = tarfile.TarInfo("main.tex")
            ti.size = len(payload)
            tf.addfile(ti, io.BytesIO(payload))
        full, name = ls.read_source(p)

    assert "mc^2" in full and name == "main.tex"


def test_read_source_rejects_a_pdf_served_as_eprint():
    """A paper with no submitted source makes arXiv's /e-print/<id> serve the
    PDF, which lands as <id>.tgz. It is neither tar nor gzip, so it reached the
    plain-text fallback and the raw PDF bytes were parsed as LaTeX -- one real
    file yielded a fabricated "equation" scraped out of a FlateDecode stream."""
    import os
    import tempfile

    pdf_bytes = (b"%PDF-1.4\n2 0 obj\n<< /Length 1 0 R /Filter /FlateDecode >>\n"
                 b"stream\n\x78\xda\xad\x5b\x59\x00\x93\x12\x7e\xfd\nendstream\n")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "0705.4638.tgz")
        with open(p, "wb") as fh:
            fh.write(pdf_bytes)
        text, name = ls.read_source(p)

    assert text == "" and name == "", "PDF bytes must never be parsed as LaTeX"
    assert not ls.extract_display_equations(text)


def test_read_source_rejects_binary_but_keeps_utf8_tex():
    """NUL bytes never occur in .tex; accented UTF-8 must still pass."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        binary = os.path.join(d, "junk.tex")
        with open(binary, "wb") as fh:
            fh.write(b"\\begin{document}\x00\x00binary\\end{document}")
        assert ls.read_source(binary) == ("", "")

        good = os.path.join(d, "ok.tex")
        with open(good, "w", encoding="utf-8") as fh:
            fh.write(r"\begin{document}Grüße \[ x=1 \]\end{document}")
        text, name = ls.read_source(good)
        assert "Grüße" in text and name == "ok.tex"
        assert len(ls.extract_display_equations(text)) == 1


def test_def_with_parameter_text_is_extracted_and_expanded():
    """`\\def\\name#1#2{...}` was missed: the pattern demanded `{` straight
    after the name. The macro then survived into what the pipeline called
    EXPANDED LaTeX, reached the tiddler `latex` field, and the speech engine
    read it aloud as "backslash ad". hep-th/9411188 defines 155 macros this
    way; extraction went 124 -> 146 when this was fixed."""
    pre = (r"\def\ad#1#2{({\rm ad}\,#1)^{#2}}"
           r"\def\eps{\varepsilon}"
           r"\def\pair#1{[#1]}")
    m = ls.extract_macros(pre)
    assert m["ad"]["nargs"] == 2 and m["ad"]["body"] == r"({\rm ad}\,#1)^{#2}"
    assert m["eps"]["nargs"] == 0            # the zero-arg form still works
    assert m["pair"]["nargs"] == 1

    # the `{\rm ad}` inside the macro body is mapped by the font pass that runs
    # after expansion, so the result is modern LaTeX throughout
    out = ls.expand_macros(r"\ad{e_i}{1-a_{ij}}e_j=0", m)
    assert out == r"(\mathrm{ad}\,e_i)^{1-a_{ij}}e_j=0", out
    assert "\\ad" not in out


def test_delimited_def_is_left_alone_not_misparsed():
    """TeX allows a delimited parameter text (`\\def\\foo#1,#2{...}`), which
    simple argument grabbing cannot expand. Skipping beats mis-parsing."""
    m = ls.extract_macros(r"\def\foo#1,#2{#1+#2}" "\n" r"\def\ok#1{[#1]}")
    assert "ok" in m
    assert "foo" not in m, "a delimited def must not be taken as undelimited"


def test_font_switches_and_alphabets_are_mapped_not_expanded():
    """A group-scoped declaration has no body to inline, so expansion could
    never remove it: `{\\got g}` survived every pass and the speech engine read
    "backslash got g". 23 of 34 equations in hep-th/9411188 spoke a backslash
    for this reason. Mapping is the fix, not expansion."""
    pre = r"\newmathalphabet*\got{euf}{m}{n}"
    m = ls.extract_macros(pre)
    assert m["got"]["body"] is None, "an alphabet has no body to inline"
    assert m["got"]["alphabet"] == "\\mathfrak"

    out = ls.expand_macros(r"{\got g}(A) = {\got n}_+ \oplus {\got h}", m)
    assert out == r"\mathfrak{g}(A) = \mathfrak{n}_+ \oplus \mathfrak{h}", out
    assert "\\got" not in out


def test_old_font_switches_boxes_and_weight_only_switches():
    out = ls.expand_macros(r"{\bf x} + \mbox{ where } \boldmath{\rm y}", {})
    assert out == r"\mathbf{x} + \text{ where } \mathrm{y}", out

    # nested groups resolve innermost-first
    nested = ls.expand_macros(r"{\bf a {\rm b} c}", {})
    assert nested == r"\mathbf{a \mathrm{b} c}", nested

    # a switch that is not a font declaration must be untouched
    assert ls.expand_macros(r"\alpha + {\beta}", {}) == r"\alpha + {\beta}"
