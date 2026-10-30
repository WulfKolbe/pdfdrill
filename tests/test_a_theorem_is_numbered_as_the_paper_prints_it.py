r"""`\newtheorem{theorem}{Theorem}[section]` numbers 2.9, not 6.

`extract_theorems` ran one counter per shared-counter group and never applied
the `[section]` reset, which its own docstring recorded as a caveat: "the
`[section]` reset/prefix is NOT applied (plain sequential per counter group)".

Measured on arxiv.math_9807032 (2026-10-30): the model numbered Definition 1,
Definition 2, Definition 3, Conjecture 4, Conjecture 5, Theorem 6, Remark 7 …
one running count across the whole paper, while the paper itself prints
"Lemma 2.9". So every number in every projection was wrong, and so was every
`\ref` that resolved to one — the reference the reader follows says 6 where the
page says 2.9.

The declarations already carried what was needed: `scan_environments` records
each `\newtheorem`'s `reset_counter`, and `test_theorems.py`'s own fixture has
`"reset_counter": "section"` in it. Only the numbering never read it.

Two rules from LaTeX that the tests below pin, because getting either wrong
produces numbers that look plausible:
  * a starred sectioning command does NOT step the counter, so a theorem after
    `\section*{Acknowledgements}` keeps the previous section's prefix;
  * a theorem BEFORE any sectioning command has no section to be numbered
    within, and falls back to the plain count — which is also what keeps a
    fixture with no `\section` in it numbering 1, 2, 3.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import latex_source as ls                      # noqa: E402

_SECTION_RESET = [
    {"name": "theorem", "title": "Theorem", "shared_counter": "",
     "reset_counter": "section", "starred": False},
    {"name": "lemma", "title": "Lemma", "shared_counter": "theorem",
     "reset_counter": "", "starred": False},
]
_NO_RESET = [
    {"name": "theorem", "title": "Theorem", "shared_counter": "",
     "reset_counter": "", "starred": False},
]


def _numbers(body, decls=None, envs=("theorem", "lemma")):
    res = ls.extract_theorems(body, list(envs), decls or _SECTION_RESET)
    return [t["number"] for t in res["theorems"]]


def test_a_theorem_is_numbered_within_its_section():
    body = (r"\section{First}" "\n"
            r"\begin{theorem} A. \end{theorem}" "\n"
            r"\begin{theorem} B. \end{theorem}" "\n"
            r"\section{Second}" "\n"
            r"\begin{theorem} C. \end{theorem}")
    assert _numbers(body) == ["1.1", "1.2", "2.1"]


def test_the_counter_restarts_in_each_section():
    body = (r"\section{A}" "\n" r"\begin{theorem} x \end{theorem}" "\n"
            r"\section{B}" "\n" r"\begin{theorem} y \end{theorem}" "\n"
            r"\section{C}" "\n" r"\begin{theorem} z \end{theorem}")
    assert _numbers(body) == ["1.1", "2.1", "3.1"]


def test_a_shared_counter_is_shared_inside_the_section():
    r"""`\newtheorem{lemma}[theorem]{Lemma}` shares theorem's counter, so the
    lemma takes the next number in the SAME section, not its own sequence."""
    body = (r"\section{First}" "\n"
            r"\begin{theorem} A. \end{theorem}" "\n"
            r"\begin{lemma} B. \end{lemma}" "\n"
            r"\section{Second}" "\n"
            r"\begin{lemma} C. \end{lemma}")
    assert _numbers(body) == ["1.1", "1.2", "2.1"]


def test_a_starred_section_does_not_step_the_prefix():
    r"""`\section*{…}` prints no number and does not advance the counter, so a
    theorem after it belongs to the last numbered section."""
    body = (r"\section{Real}" "\n"
            r"\begin{theorem} A. \end{theorem}" "\n"
            r"\section*{Acknowledgements}" "\n"
            r"\begin{theorem} B. \end{theorem}")
    assert _numbers(body) == ["1.1", "1.2"]


def test_a_theorem_before_any_section_keeps_the_plain_count():
    """Nothing to be numbered within. This is also what keeps a fixture with no
    sectioning command at all numbering 1, 2, 3 — see test_theorems.py."""
    body = (r"\begin{theorem} A. \end{theorem}" "\n"
            r"\begin{theorem} B. \end{theorem}")
    assert _numbers(body) == [1, 2]


def test_a_declaration_with_no_reset_counter_is_untouched():
    body = (r"\section{First}" "\n"
            r"\begin{theorem} A. \end{theorem}" "\n"
            r"\section{Second}" "\n"
            r"\begin{theorem} B. \end{theorem}")
    assert _numbers(body, _NO_RESET, envs=("theorem",)) == [1, 2]


def test_a_starred_environment_is_still_unnumbered():
    decls = _SECTION_RESET + [
        {"name": "remark*", "title": "Remark", "shared_counter": "",
         "reset_counter": "section", "starred": True}]
    body = (r"\section{First}" "\n"
            r"\begin{remark*} A. \end{remark*}" "\n"
            r"\begin{theorem} B. \end{theorem}")
    nums = _numbers(body, decls, envs=("theorem", "remark*"))
    assert nums == [None, "1.1"]


def test_subsection_reset_is_honoured_too():
    decls = [{"name": "theorem", "title": "Theorem", "shared_counter": "",
              "reset_counter": "subsection", "starred": False}]
    body = (r"\section{One}" "\n" r"\subsection{A}" "\n"
            r"\begin{theorem} x \end{theorem}" "\n"
            r"\subsection{B}" "\n"
            r"\begin{theorem} y \end{theorem}")
    assert _numbers(body, decls, envs=("theorem",)) == ["1.1", "2.1"]


def test_the_number_reaches_the_markdown_as_the_paper_prints_it(tmp_path):
    """End to end: the projection a reader sees carries the printed number."""
    from docops.base import OperatorConfig
    from docops.projectors.markdown import MarkdownProjector

    tex = tmp_path / "main.tex"
    tex.write_text(
        "\\documentclass{article}\n"
        "\\newtheorem{theorem}{Theorem}[section]\n"
        "\\begin{document}\n"
        "\\section{One}\n\\section{Two}\n"
        "\\begin{theorem} The claim holds. \\end{theorem}\n"
        "\\end{document}\n", encoding="utf-8")
    doc = ls.build_source_model(str(tex), bibkey="T")
    out = MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector",
        params={"front_matter": False})).project(doc)
    assert "**Theorem 2.1.** The claim holds." in out
