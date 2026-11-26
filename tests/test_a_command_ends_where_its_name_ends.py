"""
The Markdown's emit gate: a command ends where its name ends.

`_NEEDS_ARG` defers LaTeX whose argument-taking command has no argument, so
a renderer never shows an error box. It had no word end, so `\\textbf{` read
as `\\text` + `bf` -- an argument-less `\\text` -- and every maths span with
`\\textbf`, `\\textsc`, `\\textit` or `\\textrm` was cropped in `glyphs.md`
while `lines.json` carried its LaTeX. Found in the acceptance run of B2:
0864 p4's `\\text{\\textbf{\\textsc{Opus}}}_{\\text{spc}}` built, was judged,
and was still an image in the reader's Markdown. `\\sqrt[3]{...}` (6d90 p174)
failed the same way on its index.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.project_mmd import is_emittable


def test_text_commands_with_their_argument_are_emitted():
    assert is_emittable(r"\text{\textbf{\textsc{Opus}}}_{\text{spc}}")
    assert is_emittable(r"\textrm{d}x")
    assert is_emittable(r"\barwedge")


def test_a_root_with_its_index_is_emitted():
    assert is_emittable(r"\sqrt[3]{c - \frac{3}{4} t^{4}}")


def test_a_command_without_its_argument_is_still_deferred():
    for tex in (r"\widetilde x", r"\text x", r"\sqrt 2", r"\frac12", r"\mathbf"):
        assert not is_emittable(tex), tex
