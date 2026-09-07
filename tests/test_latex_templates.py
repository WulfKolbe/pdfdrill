"""640-a — the LaTeX projector resolves EVERY template the TiddlyWiki projector
emits, from ONE table.

`clean` → `heading_cleanup.materialize_transclusions` rewrites `props["text"]`
with the TiddlyWiki PROJECTION, so after a full drill a paragraph's prose is

    see {{D_FN0003||FN}} and {{D_REF_a||CIT}}

not raw LaTeX. The projector knew only the array templates and the `CIT` title
tail; every other template fell through to a literal `(?D_FN0003)` printed into
the document — 63 of them on penev_A, and the 21 `\\footnotemark[n]` that 638
had won were gone. That is exactly the transclusion failure
`docs/TRANSCLUSION.md` describes: it compiles, and it reads like prose.

Three levels here:
  * the GUARD — a template added to `tiddlywiki.TEMPLATES` with no row in
    `latex_pipeline.TEMPLATE_ACTIONS` fails;
  * the BRANCHES — FN/CIT/SN/blocks render, on a real projection;
  * the REFUSAL — a template with no branch is COUNTED, never printed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject                    # noqa: E402
from docops.base import OperatorConfig                           # noqa: E402
from docops.projectors import latex_pipeline as LP               # noqa: E402
from docops.projectors.latex import LaTeXProjector               # noqa: E402
from docops.projectors.tiddlywiki import TEMPLATES, titles_by_id  # noqa: E402

PLACEHOLDER = re.compile(r"\(\?[A-Za-z0-9_]+\)")


def _project(doc: Document) -> tuple[str, dict]:
    pr = LaTeXProjector(OperatorConfig(op="projector", classname="LaTeXProjector"))
    out = pr.project(doc)
    return out, dict(getattr(pr, "_template_counts", {}))


def _doc() -> Document:
    """A document in the shape `clean` leaves: three Footnotes (so the third is
    `D_FN0003`), a Reference, a Sidenote, and a paragraph whose text is the
    MATERIALISED form."""
    d = Document()
    d.meta["bibkey"] = "D"
    for i in (1, 2, 3):
        d.add(DocObject(type="Footnote",
                        props={"refnum": str(i), "content": f"body {i}",
                               "anchor_marker": "{ }^{%d}" % i,
                               "page": 1, "flow_index": 2 + i}))
    d.add(DocObject(type="Reference",
                    props={"citekey": "a", "raw_text": "A. Author, A paper, 1999.",
                           "flow_index": 90}))
    d.add(DocObject(type="Sidenote",
                    props={"text": "a margin note", "page": 1, "flow_index": 60}))
    d.add(DocObject(type="Paragraph",
                    props={"text": "see {{D_FN0003||FN}} and {{D_REF_a||CIT}}",
                           "page": 1, "flow_index": 20}))
    return d


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------

def test_every_tiddlywiki_template_has_a_latex_branch():
    """644 put the templates in one map so a rename lands in one place. A
    template with no LaTeX action is a `(?…)` waiting to be printed."""
    missing = sorted(set(TEMPLATES) - set(LP.TEMPLATE_ACTIONS))
    assert not missing, (
        f"tiddlywiki.TEMPLATES defines {missing} with no row in "
        f"latex_pipeline.TEMPLATE_ACTIONS — add ARRAY / HANDLER / DROP")


def test_no_latex_action_names_a_template_that_does_not_exist():
    extra = sorted(set(LP.TEMPLATE_ACTIONS) - set(TEMPLATES))
    assert not extra, f"TEMPLATE_ACTIONS names {extra}, which TEMPLATES does not"


def test_every_handler_template_has_a_handler_on_the_projector():
    pr = LaTeXProjector(OperatorConfig(op="projector", classname="LaTeXProjector"))
    pr._prepare(_doc())
    wanted = {k for k, v in LP.TEMPLATE_ACTIONS.items() if v == LP.HANDLER}
    assert wanted <= set(pr._tpl_handlers), sorted(wanted - set(pr._tpl_handlers))


# ---------------------------------------------------------------------------
# the branches
# ---------------------------------------------------------------------------

def test_materialised_footnote_and_citation_project_to_real_latex():
    out, counts = _project(_doc())
    assert "\\footnotemark[3]" in out
    assert "\\footnotetext[3]{body 3}" in out
    assert "\\cite{a}" in out
    assert counts.get("resolved:FN") == 1
    assert counts.get("resolved:CIT") == 1


def test_no_literal_placeholder_survives_the_projection():
    out, _ = _project(_doc())
    assert not PLACEHOLDER.findall(out), PLACEHOLDER.findall(out)
    assert "{{" not in out and "||" not in out


def test_a_marked_footnote_body_is_printed_once_not_twice():
    """The body a materialised marker names is printed BY the marker's
    paragraph; it must not ALSO be emitted standalone — even though it sits
    EARLIER in the flow than the paragraph that marks it (`_skip_ids` is read
    once, before the first block, so the decision has to be pre-computed)."""
    out, _ = _project(_doc())
    assert out.count("\\footnotetext[3]{body 3}") == 1
    # the two unmarked bodies still print, with their printed numbers
    assert "\\footnotetext[1]{body 1}" in out
    assert "\\footnotetext[2]{body 2}" in out


def test_sup_marker_with_no_footnote_object_becomes_a_footnotemark():
    """`<sup>7</sup>` is what the tiddler projector emits for a marker whose
    refnum names no Footnote (44 of them on penev_A). Left alone it printed the
    HTML tag into the .tex."""
    d = _doc()
    p = next(o for o in d.objects.values() if o.type == "Paragraph")
    p.props["text"] = "a mark <sup>7</sup> with no body"
    out, counts = _project(d)
    assert "\\footnotemark[7]" in out
    assert "<sup>" not in out
    assert counts.get("resolved:SUP") == 1


def test_sidenote_transclusion_becomes_a_marginpar():
    d = _doc()
    p = next(o for o in d.objects.values() if o.type == "Paragraph")
    p.props["text"] = "prose {{D_SN0001||SN}} more"
    out, counts = _project(d)
    assert "\\marginpar{\\footnotesize a margin note}" in out
    assert counts.get("resolved:SN") == 1


def test_a_footnote_marker_inside_a_footnote_body_does_not_nest():
    """`\\footnotetext` inside `\\footnotetext` is a LaTeX error, and 638
    measured that a marker inside a body is usually the NEXT body's printed
    label rather than a reference. The mark is emitted; the body is not."""
    d = _doc()
    fn1 = next(o for o in d.objects.values()
               if o.type == "Footnote" and o.props["refnum"] == "1")
    fn1.props["content"] = "body 1 then {{D_FN0002||FN}} continues"
    out, _ = _project(d)
    body = next(ln for ln in out.splitlines() if "body 1 then" in ln)
    assert "\\footnotemark[2]" in body
    assert body.count("\\footnotetext") == 1          # only its own


def test_a_block_transclusion_renders_the_object_and_not_twice():
    d = _doc()
    d.add(DocObject(type="Table",
                    props={"latex_code": "\\begin{tabular}{c}x\\end{tabular}",
                           "page": 1, "flow_index": 70}))
    p = next(o for o in d.objects.values() if o.type == "Paragraph")
    p.props["text"] = "the table {{D_TAB_001||TAB}} shows"
    out, counts = _project(d)
    assert out.count("\\begin{tabular}{c}x\\end{tabular}") == 1
    assert counts.get("resolved:TAB") == 1


# ---------------------------------------------------------------------------
# the refusal — counted, never printed
# ---------------------------------------------------------------------------

def test_a_template_with_no_branch_is_counted_not_printed():
    out = LP.resolve_transclusions("x {{D_NOPE0001||NOPE}} y", {}, counts=(c := {}))
    assert out == "x  y"
    assert "(?" not in out and "{{" not in out
    assert c == {"template_unhandled:NOPE": 1}


def test_an_array_template_whose_title_is_not_indexed_is_counted_not_printed():
    out = LP.resolve_transclusions("x {{D_FO9999||FO}} y", {}, counts=(c := {}))
    assert out == "x  y"
    assert "(?" not in out
    assert c == {"unresolved_title:FO": 1}


def test_a_drop_template_renders_nothing_and_says_so():
    out = LP.resolve_transclusions("x {{D_LTX1||LTX}} y", {}, counts=(c := {}))
    assert out == "x  y"
    assert c == {"dropped:LTX": 1}


def test_the_bare_pipeline_still_resolves_a_citation_without_a_handler():
    """`resolve_transclusions` is a module-level function other code calls with
    no Document; the CIT title tail must keep working there."""
    out = LP.resolve_transclusions(
        "ELMo {{2002.08155_REF_peters2018deep||CIT}}", {}, counts=(c := {}))
    assert out == "ELMo \\cite{peters2018deep}"
    assert c == {"resolved:CIT": 1}


# ---------------------------------------------------------------------------
# the title index is the tiddler projector's own numbering, not a copy
# ---------------------------------------------------------------------------

def test_titles_by_id_numbers_footnotes_by_flow_position_not_refnum():
    """644: `refnum` restarts per page, so the title is the object's POSITION.
    A second implementation of that rule is how six bodies got one title."""
    d = _doc()
    titles = titles_by_id(d, "D")
    fns = {titles[o.id]: o.props["refnum"] for o in d.objects.values()
           if o.type == "Footnote"}
    assert fns == {"D_FN0001": "1", "D_FN0002": "2", "D_FN0003": "3"}
    assert titles[next(o.id for o in d.objects.values()
                       if o.type == "Reference")] == "D_REF_a"
