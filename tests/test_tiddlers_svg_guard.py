"""
The stale-tiddlers guard: `tiddlers` warns when the model has table/diagram graphics
with LaTeX source (latex_code) but no rendered `svg` yet — the exact state that made
2004.05631v1's table tiddlers come out empty (svg ran after the tiddlers were
written). The note steers to `svg` → `tiddlers --force`.
"""
import sys, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import _unrendered_graphics_note as N


def _o(t, **props):
    return types.SimpleNamespace(type=t, props=props)


def test_warns_when_latex_code_but_no_svg():
    objs = [_o("Table", latex_code=r"\begin{tabular}{cc}a&b\end{tabular}"),
            _o("Diagram", latex_code=r"\begin{tikzpicture}\draw(0,0)--(1,1);\end{tikzpicture}"),
            _o("Paragraph", text="hi")]
    note = N(objs)
    assert note and "svg" in note.lower()
    assert "2" in note                                # both graphics counted


def test_silent_when_all_rendered():
    objs = [_o("Table", latex_code="x", svg="<svg/>"),
            _o("Diagram", latex_code="y", svg="<svg/>")]
    assert N(objs) == ""


def test_code_listing_not_counted():
    # a fenced code diagram has latex_code but is NOT an svg graphic
    objs = [_o("Diagram", latex_code="```julia\nx=1\n```", subtype="code")]
    assert N(objs) == ""


def test_silent_when_no_graphics():
    assert N([_o("Paragraph", text="hi"), _o("Formula", latex="x^2")]) == ""


def test_non_graphic_latex_code_not_counted():
    # a body that `svg.is_latex_graphic` rejects (not tikz/tabular) is skipped by
    # svg forever — must NOT be flagged (the 2004.05631v1 false-positive case)
    objs = [_o("Diagram", latex_code="just some prose, not a graphic environment")]
    assert N(objs) == ""


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
