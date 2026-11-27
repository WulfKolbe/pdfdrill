r"""
B13, 1511.08771 p2709: the table header `\mathfrak{su}_7 \supset
\mathfrak{so}_7(S)` sits between full-width table rules, and a short rule
under its first column lies 1.3 pt below the second one. Read as a fraction
bar, it made the header a numerator over the first row's `138600 =`, and the
two rows became one line. A bar within 0.2 em of a rule that spans it and is
three times as wide is a table rule. Judge (pin 8a67b8a) 1511 p2709: 0.0095
-> 0.0020. The inputs are the page's own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "a_bar_pressed_against_a_table_rule.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_short_rule_under_the_header_is_the_numbers_overline():
    """J10: the bar is exactly as wide as the bold `138600` under it (x
    87.7..125.4 against 87.7..125.2), so it is that number's overline,
    `\\overline{\\mathbf{138600}}`, not a table rule. What B13 needed, that it
    is NOT a fraction bar joining the header to the row, still holds."""
    d = json.loads(FIX.read_text())["bar"]
    rule = dm.RuleNode(**{k: _tup(v) for k, v in d["rule"].items()})
    others = [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["others"]]
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    assert dm._rule_role(rule, glyphs, d["size"], others, d["page_width"]) == "overline"
