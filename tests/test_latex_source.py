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
    assert sa.startswith("\\documentclass{standalone}")
    assert "\\usepackage{amsmath}" in sa
    assert "\\newcommand{\\R}" in sa or "newcommand" in sa


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
