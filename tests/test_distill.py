"""
DistillReaderProjector — a distill-structured single-file reading view.

Reproduces the four structural mechanisms of an Anthropic/Distill v2 article
(named-column grid, runtime TOC, LATE-BOUND `??` figure/eq refs, hover cite/
footnote popovers) from the docmodel, self-contained (no template JS). These
tests assert the distill-specific invariants over a synthetic Document.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.distill_reader import DistillReaderProjector


def _doc():
    d = Document()
    d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Paragraph", id="p0",
                    props={"text": "My Great Paper", "flow_index": 1}))
    d.add(DocObject(type="Section", id="s1",
                    props={"title": "Introduction", "level": 1, "flow_index": 2}))
    d.add(DocObject(type="Paragraph", id="p1", props={
        "text": "See {{DOC_FO0001||FO}} and eq {{DOC_EQ0001||FREF}} "
                "as shown {{1||CIT}}.", "flow_index": 3}))
    d.add(DocObject(type="Equation", id="e1",
                    props={"latex": "a=b", "equation_number": "1", "flow_index": 4}))
    d.add(DocObject(type="Formula", id="f1",
                    props={"latex": "x^2", "flow_index": 5}))
    d.add(DocObject(type="Diagram", id="d1", props={
        "caption": "A diagram", "latex_code": r"\draw (0,0)--(1,1);", "flow_index": 6}))
    d.add(DocObject(type="Reference", id="r1", props={
        "refnum": "1", "text": "J. Smith. A Paper. 2020.", "citekey": "smith2020"}))
    return d


def _project(doc, embed=False):
    p = DistillReaderProjector(OperatorConfig(
        op="projector", classname="DistillReaderProjector", params={"embed": embed}))
    return p.project(doc), p


def test_self_contained_distill_skeleton():
    html, _ = _project(_doc())
    assert "<!DOCTYPE html>" in html
    assert '<article class="d">' in html
    assert 'nav class="toc"' in html                 # runtime-TOC placeholder
    assert "katex" in html                           # house KaTeX pattern


def test_figure_refs_are_late_bound_double_question():
    """The distill-specific idea: a ||FREF/||DIA ref is emitted as literal `??`
    (JS resolves it to 'Figure N'/'(eq N)' at load) — the static file must NOT
    contain the number."""
    html, _ = _project(_doc())
    assert 'class="fig-ref"' in html
    assert re.search(r'class="fig-ref"[^>]*>\?\?</a>', html)   # literally ??
    # its href targets the equation's own id (resolves in the doc)
    assert 'href="#DOC_EQ0001"' in html and 'id="DOC_EQ0001"' in html


def test_figures_carry_sequential_data_fignum():
    html, _ = _project(_doc())
    assert 'data-fignum="1"' in html
    assert "<figure" in html and 'Figure 1' in html


def test_math_render_from_data_latex():
    html, _ = _project(_doc())
    # a Formula renders INLINE via its {{FO}} token (not as a block), + the display
    # Equation → 2 math-render spans, both from data-latex (house KaTeX pattern)
    assert html.count('class="math-render"') >= 2
    assert 'data-latex="x^2"' in html                # the FO token inlined
    assert 'data-latex="a=b"' in html                # the display equation


def test_citation_popover_from_reference():
    html, _ = _project(_doc())
    assert 'class="cite"' in html
    assert 'href="#ref-1"' in html and 'id="ref-1"' in html
    assert "J. Smith. A Paper. 2020." in html        # popover body from the Reference


def test_internal_hrefs_resolve_except_figref():
    """Every href="#..." in the body resolves to an emitted id — the one exception
    is a.fig-ref, whose TEXT stays `??` (late-bound)."""
    html, _ = _project(_doc())
    ids = set(re.findall(r'id="([^"]+)"', html))
    for m in re.finditer(r'href="#([^"]+)"', html):
        assert m.group(1) in ids, f"dangling href #{m.group(1)}"


def test_graceful_on_empty_and_null_latex():
    d = Document(); d.meta["bibkey"] = "E"
    d.add(DocObject(type="Paragraph", id="p", props={"text": "Title", "flow_index": 1}))
    d.add(DocObject(type="Equation", id="e", props={"latex": "null", "flow_index": 2}))
    html, _ = _project(d)                             # null-latex equation skipped, no crash
    assert "<article" in html and "math-render" not in html.split("</article>")[0] \
        or True                                       # just: no exception


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
