"""The main .tex is the one that PULLS IN the document, not the longest one.

arXiv 2408.11646 ships a Foundations & Trends monograph: `main.tex` includes
nine chapter files, and the archive also contains `FnTarticle.tex` — the class
DOCUMENTATION example that ships with the FnT class, self-contained and
therefore longer than the wrapper.

`max(candidates, key=len)` picked the class documentation. The model was built
from it, so the drilled "paper" was 12 KB titled "Using the Foundations and
Trends(R) LaTeX Class" — which reads as a short summary per chapter, because
that is what class documentation is. The real 500 KB of chapters was never
opened, and nothing reported an error.

Length is the wrong proxy. A main file in a multi-file submission is a THIN
wrapper; what identifies it is that it includes the others.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.latex_source import find_main_tex


def test_the_file_that_includes_the_chapters_wins_over_a_longer_one():
    paths = {
        "FnTarticle.tex": "\\documentclass{FnT}\n" + ("prose about the class. " * 900),
        "main.tex": "\\documentclass{FnT}\n\\include{ch1}\n\\include{ch2}\n",
        "ch1.tex": "x" * 90000,
        "ch2.tex": "x" * 90000,
    }
    assert find_main_tex(paths) == "main.tex"


def test_a_conventional_name_breaks_a_tie_on_include_count():
    """The archive also holds `ch0-main-typo-fixes.tex`, a variant wrapper.
    Both build the document; the conventional name is the reproducible pick."""
    inc = "\\documentclass{FnT}\n" + "".join(f"\\include{{ch{i}}}\n" for i in range(1, 10))
    # Measured on the real archive: both wrappers RESOLVE 13 includes, because
    # the variant references six chapters that are not in the submission. So it
    # is a true tie, and the conventional name decides — verified against the
    # printed TOC, whose appendices ("A Online Resources", "B ... Theorem
    # Proving") match main.tex's AppendixA-Resources / AppendixB-Theorems and
    # not the variant's Notes-Instructors / Exercises / Resources.
    paths = {"ch0-main-typo-fixes.tex": inc + "\\include{ch-not-submitted}\n",
             "main.tex": inc,
             **{f"ch{i}.tex": "y" * 1000 for i in range(1, 10)}}
    assert find_main_tex(paths) == "main.tex"


def test_only_includes_that_exist_in_the_archive_count():
    """A file that \\includes names not present is not the main file of THIS
    submission — otherwise a stray template outvotes the real wrapper."""
    paths = {"template.tex": "\\documentclass{a}\n" + "".join(
                 f"\\input{{missing{i}}}\n" for i in range(20)),
             "main.tex": "\\documentclass{a}\n\\include{ch1}\n",
             "ch1.tex": "z" * 5000}
    assert find_main_tex(paths) == "main.tex"


def test_a_single_file_submission_is_unchanged():
    paths = {"paper.tex": "\\documentclass{article}\n\\begin{document}x\\end{document}"}
    assert find_main_tex(paths) == "paper.tex"


def test_length_still_decides_when_nothing_includes_anything():
    paths = {"a.tex": "\\documentclass{x}\n" + "a" * 100,
             "b.tex": "\\documentclass{x}\n" + "b" * 5000}
    assert find_main_tex(paths) == "b.tex"


def test_no_documentclass_falls_back_to_begin_document():
    paths = {"a.tex": "no class here", "b.tex": "\\begin{document}hi\\end{document}"}
    assert find_main_tex(paths) == "b.tex"


def test_no_tex_at_all_is_none():
    assert find_main_tex({}) is None
    assert find_main_tex({"readme.txt": "hello"}) is None
