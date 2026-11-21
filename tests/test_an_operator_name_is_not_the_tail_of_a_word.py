r"""`muslim` is not `mus` + `\lim`.

T-0154. On 2312.11532 p7 the board's own instrument — `pdfdrill glyphlines`,
the glyph reader, not the Gemma4 lane — writes the table cell

    $\mathrm{mus}\lim,$ turkish

`_merge_operator_names` walks a line's upright roman glyphs and merges a run
that EXACTLY spells one of amsopn's 38 operator names into the command. It
guards the right-hand side of that run, and says why:

    # The run must END here. TeX never sets `\sup` immediately
    # followed by another upright roman letter at a tight gap --
    # that is a WORD. `supp` is a variable name [...]

It never asks the same question on the left. The walk advances one glyph at
a time, so when `i` reaches the `l` of `muslim` the run `l`,`i`,`m` spells a
name, nothing follows it, and the guard is satisfied. `supp` is refused and
`ppsup` is not — by the identical argument, stated once.

The rule is the one already written above: a name with an upright roman
letter of the same size and baseline glued to it is a WORD. It holds on
both sides or it holds on neither.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel_six = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.docmodel_six import GlyphNode, _merge_operator_names
from pdfreader.texmap import UNKNOWN

SIZE = 10.0
ADVANCE = 5.0          # a tight gap: 0 px between boxes, well under 0.12*size


def _line(word, *, gap_before=None):
    """One line of upright roman glyphs spelling `word`, letter by letter.

    `gap_before` inserts a space-sized gap before the final `len(word) - n`
    letters are reached; it is not used by default because the defect needs
    the letters to be TIGHT, which is what makes them a word.
    """
    out = []
    x = 0.0
    for k, ch in enumerate(word):
        out.append(GlyphNode(
            id=f"g{k}", page=1, rect=(x, 0.0, x + ADVANCE, SIZE), text=ch,
            cid=ord(ch), glyphname=None, fontname="NimbusRomNo9L-Regu",
            family="text", size=SIZE, tex=UNKNOWN,
            matrix=(1, 0, 0, 1, x, 100.0)))
        x += ADVANCE
    return out


def _texts(nodes):
    return [n.text for n in sorted(nodes, key=lambda n: n.rect[0])]


def test_a_name_standing_alone_is_still_merged():
    """The pass must keep doing its job: this is why it exists."""
    assert _texts(_merge_operator_names(_line("lim"))) == ["\\lim"]
    assert _texts(_merge_operator_names(_line("sup"))) == ["\\sup"]


def test_a_name_at_the_end_of_a_word_is_not_an_operator():
    """The measured case: `muslim` on 2312.11532 p7."""
    got = _texts(_merge_operator_names(_line("muslim")))
    assert "\\lim" not in got, "muslim was read as mus + \\lim: %r" % (got,)
    assert got == list("muslim")


def test_the_right_hand_guard_still_holds():
    """`supp` is a variable name — the rule that was already there."""
    got = _texts(_merge_operator_names(_line("supp")))
    assert "\\sup" not in got and got == list("supp")


def test_a_name_inside_a_word_is_not_an_operator():
    """Both sides fail at once."""
    for word in ("climb", "deliminate", "alogical"):
        got = _texts(_merge_operator_names(_line(word)))
        assert all(not t.startswith("\\") for t in got), (word, got)


def test_a_gap_is_a_boundary():
    """A real space before the name leaves it an operator. Without this the
    fix would refuse every name that follows a word on the same line, which
    is where operators usually stand."""
    glyphs = _line("x")
    tail = _line("lim")
    for g in tail:                       # push it a whole em to the right
        g.rect = (g.rect[0] + 4 * SIZE, g.rect[1],
                  g.rect[2] + 4 * SIZE, g.rect[3])
        g.matrix = (1, 0, 0, 1, g.rect[0], 100.0)
    assert _texts(_merge_operator_names(glyphs + tail)) == ["x", "\\lim"]
