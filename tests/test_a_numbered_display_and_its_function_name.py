"""
P4 rest: 1805.01788 p3's equation (1) is a numbered display that opens with a
spelled-out function name, `unfairness(\\rho^1, ..., \\rho^m) = ...  (1)`.

- the word, set in the text italic flush against its `(`, is one
  `\\mathit{unfairness}`, not ten maths variables;
- a maths line followed only by its equation number is a display, the number
  carried as `\\tag{1}` (the lines.json splitter then gives the number its own
  `equation_number` record and takes the tag out, so it is set once).

Judge (pin ed6eb5d) 1805 p3: 0.0092 -> 0.0080. The row is the page's own,
frozen in the fixture of the tall-bar test.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import structure as S
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "tall_bar_in_six_rows.groups.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _row():
    d = json.loads(FIX.read_text())
    rows = []
    for r in d["g"]:
        row = []
        for g in r:
            g = {k: _tup(v) for k, v in g.items()}
            g["tex"] = TexToken(*g["tex"])
            row.append(dm.GlyphNode(**g))
        rows.append(row)
    host = max(rows, key=len)
    return sorted(host, key=lambda g: g.rect[0])


def test_the_function_name_is_one_italic_word():
    full = _row()
    k = next(i for i, g in enumerate(full) if g.text == "(")
    row = full[:k + 1]                       # `unfairness(`
    merged = S._merge_function_names(row)
    words = [g.tex.latex for g in merged if g.tex.latex and "mathit" in g.tex.latex]
    assert words == [r"\mathit{unfairness}"], [g.text for g in merged]


def test_a_maths_line_with_its_number_is_a_display_with_a_tag():
    assert dm._as_display("$a = b .$ (1)", "math") == "\\[\na = b .\\tag{1}\n\\]"
    assert dm._as_display("$x$ (2.10)", "math") == "\\[\nx\\tag{2.10}\n\\]"


def test_a_sentence_with_a_number_stays_a_sentence():
    assert dm._as_display("$a$ and $b$ (2)", "math") == "$a$ and $b$ (2)"
    assert dm._as_display("see (3)", "math") == "see (3)"
