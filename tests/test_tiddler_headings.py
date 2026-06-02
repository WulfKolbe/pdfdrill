"""
Tests for converting leaked LaTeX sectioning commands in paragraph bodies to
native WikiText headings (tiddlywiki projector).

Bug: the PARA template is `<p>{{!!text}}</p>` and KaTeX only renders math, so a
`\\section*{...}` left in a paragraph's `text` rendered as the literal string.
`latex_sectioning_to_wikitext` converts it to the WikiText heading the document
already uses.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docops.projectors.tiddlywiki import latex_sectioning_to_wikitext as conv


def test_levels_and_star_variant():
    assert conv(r"\section*{ALL RIGHTS RESERVED}") == "! ALL RIGHTS RESERVED"
    assert conv(r"\section{Intro}") == "! Intro"
    assert conv(r"\subsection*{1.1 Formal Concepts}") == "!! 1.1 Formal Concepts"
    assert conv(r"\subsubsection{Deep}") == "!!! Deep"
    assert conv(r"\chapter*{One}") == "! One"


def test_leading_whitespace_and_trailing_prose():
    out = conv("\n\n\\section*{ALL RIGHTS RESERVED} \n\nA dissertation submitted to…")
    assert out.startswith("! ALL RIGHTS RESERVED")
    assert "A dissertation submitted" in out
    assert "\\section" not in out
    # no runs of 3+ newlines left behind
    assert "\n\n\n" not in out


def test_subsubsection_not_shadowed_by_section():
    # longest command alternative must win
    assert conv(r"\subsubsection*{X}").startswith("!!!")


def test_balanced_brace_title_keeps_transclusion():
    # A title containing a {{...||FO}} transclusion (nested braces) survives.
    src = r"\section*{4. Form the projection operator {{K_FO0179||FO}}.} \n\nNow we…"
    out = conv(src)
    assert out.startswith("! 4. Form the projection operator {{K_FO0179||FO}}.")
    assert "\\section" not in out


def test_noops():
    assert conv("") == ""
    assert conv("plain prose, no commands") == "plain prose, no commands"
    assert conv("inline $x^2$ math, no sectioning") == "inline $x^2$ math, no sectioning"
    # idempotent: running twice changes nothing more
    once = conv(r"\section*{A}")
    assert conv(once) == once


if __name__ == "__main__":
    fns = [test_levels_and_star_variant, test_leading_whitespace_and_trailing_prose,
           test_subsubsection_not_shadowed_by_section,
           test_balanced_brace_title_keeps_transclusion, test_noops]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
