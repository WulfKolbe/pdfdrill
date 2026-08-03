"""
The invariant that would have caught the transclusion loss on its first run.

Recommended by the external auditor, and it is the right one: the existing
tests asserted what the emitter must NOT emit (`test_codelisting_bibkey.py`
checks `"||DIA}}" not in ...`) and never the positive case, so a projector that
emitted NOTHING passed every check.

Root cause it guards: `build_source_model` constructs the Document directly and
never runs `docmodel.main`, so `DocumentStructureProcessor` (procOrder 999)
never fired — Sections had no `children`, `_section_body` iterated an empty list,
and every ||TAB/||PIC/||DIA/||LI transclusion silently vanished. Only CIT/FO
survived, because those come from inline string substitution that never touches
the object tree.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector
from pdfdrill.commands import apply_document_structure


def _doc():
    """A section with one block object of each transcludable kind."""
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Section", props={"caption": "Results", "level": 1,
                                           "flow_index": 1}))
    d.add(DocObject(type="Paragraph", props={"text": "Prose here.", "flow_index": 2}))
    d.add(DocObject(type="Table", props={"latex_code": r"\begin{tabular}{l}a\end{tabular}",
                                         "caption": "T1", "flow_index": 3}))
    d.add(DocObject(type="ListItem", props={"marker": "-", "content": "item",
                                            "flow_index": 4}))
    return d


def test_sections_get_children_from_the_structure_pass():
    """INVARIANT: a model with >=1 Section must have >0 children in total.
    Zero means the post-pass did not run, and every block transclusion is lost."""
    d = _doc()
    assert sum(len(s.children or []) for s in d.objects.values()
               if s.type == "Section") == 0            # before: flat
    stats = apply_document_structure(d)
    assert stats["sections"] == 1
    assert stats["children"] > 0, "Section has no children — transclusions will vanish"
    assert stats["numbered"] == 1 and stats["roots"] == 1


def test_block_objects_are_actually_transcluded():
    """INVARIANT: each block object under a section appears as a transclusion.
    The POSITIVE assertion the suite never had."""
    d = _doc()
    apply_document_structure(d)
    ts = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(d))
    used = set()
    for t in ts:
        used.update(re.findall(r"\|\|([A-Z]+)\}\}", t.get("text") or ""))
    for tpl in ("PARA", "TAB", "LI"):
        assert tpl in used, f"||{tpl}}} never emitted — section body is empty"


def test_structure_pass_is_idempotent():
    d = _doc()
    first = apply_document_structure(d)
    second = apply_document_structure(d)
    assert second["children"] == first["children"], "children duplicated on re-run"


def test_no_sections_is_not_an_error():
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Paragraph", props={"text": "x", "flow_index": 1}))
    assert apply_document_structure(d) == {"sections": 0, "children": 0}


def test_every_nontextual_type_is_transcluded():
    """FULL COVERAGE: each non-textual object type must reach the wiki through
    its own template. This asserts the POSITIVE case for all of them at once —
    the check the suite never had, and the reason a projector emitting nothing
    passed for so long."""
    d = Document(); d.meta["bibkey"] = "K"
    n = [0]

    def add(t, **p):
        n[0] += 1
        p["flow_index"] = n[0]
        d.add(DocObject(type=t, props=p))

    add("Section", caption="Results", level=1)
    add("Paragraph", text="Prose.")
    add("Equation", latex="E=mc^2", refnum="(1)")          # DISPLAY math
    add("Table", latex_code=r"\begin{tabular}{l}a\end{tabular}", caption="T1")
    add("Picture", caption="Fig 1", cdn_url="http://x/i.png")
    add("Diagram", latex_code=r"\begin{tikzpicture}\draw(0,0);\end{tikzpicture}")
    add("ListItem", marker="-", content="an item")
    add("Abstract", text="The abstract.")
    add("Toc", text="Contents")
    add("Sidenote", content="a side note")

    apply_document_structure(d)
    ts = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(d))
    used = set()
    for t in ts:
        used.update(re.findall(r"\|\|([A-Z]+)\}\}", t.get("text") or ""))
    required = {"PARA", "EQBLOCK", "TAB", "PIC", "DIA", "LI", "ABS", "TOC", "SN"}
    assert required <= used, f"never emitted: {sorted(required - used)}"


def test_inline_formula_is_transcluded_from_paragraph_text():
    """INLINE math (Formula/FO) reaches the wiki by a DIFFERENT mechanism than
    the block types: string substitution inside a paragraph's text, not
    `section.children`. Both mechanisms must work — a flat tree kills the block
    types while FO keeps working, which is exactly what made the loss invisible.
    """
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Section", props={"caption": "R", "level": 1,
                                           "flow_index": 1}))
    d.add(DocObject(type="Formula", props={"latex": "x^2", "flow_index": 2}))
    d.add(DocObject(type="Paragraph", props={
        "text": "Let {{K_FO0001||FO}} be given.", "flow_index": 3}))
    apply_document_structure(d)
    ts = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(d))
    used = set()
    for t in ts:
        used.update(re.findall(r"\|\|([A-Z]+)\}\}", t.get("text") or ""))
    assert "FO" in used and "PARA" in used


def test_no_math_object_is_left_untranscluded():
    """Every Formula/Equation must be referenced somewhere — an object nothing
    points at renders nowhere, however correct its own tiddler is."""
    from docops.projectors.tiddlywiki import math_titles
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Section", props={"caption": "R", "level": 1,
                                           "flow_index": 1}))
    d.add(DocObject(type="Formula", props={"latex": "x^2", "flow_index": 2}))
    d.add(DocObject(type="Equation", props={"latex": "E=mc^2", "flow_index": 3}))
    d.add(DocObject(type="Paragraph", props={
        "text": "Let {{K_FO0001||FO}} be given.", "flow_index": 4}))
    apply_document_structure(d)
    ts = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(d))
    body = " ".join(str(t.get("text") or "") for t in ts)
    missing = [t for t in math_titles(d, "K").values() if "{{" + t + "||" not in body]
    assert not missing, f"math objects never transcluded: {missing}"
