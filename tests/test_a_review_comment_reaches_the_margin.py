r"""A review comment reaches the margin, and nothing else moves.

T-0156, the owner's SIXTH requirement — an AI peer review as tracked changes
AND comments. The changes come from `latexdiff` over two projections, measured
on arxiv.0912.2444's 125-equation projection: 36 errors before, 36 after, with
35 `\DIFadd` and 46 `\DIFdel` visible in the rendered PDF. A comment is not a
difference, so it is carried separately, attached to the OBJECT it is about.

`\todo`, NOT `\marginpar`. The projector already emits `\marginpar` for a
Sidenote — the DOCUMENT'S OWN margin note, which 638 exists to preserve — and
a reviewer's comment set the same way would read as the author's.

MEASURED, the same pipeline with and without 25 notes on the same model:

    plain      errors 30   overfull 45   pages 56
    withtodo   errors 30   overfull 45   pages 56

identical, so the notes cost nothing. And with NO note present, all eight
audit projections are byte-identical to the code without this change.

THE HOOK IS AT THE RENDERER'S ENTRY, not among its branches. `_render`
returns from a dozen type branches, and the first version put the check
between two of them — where it reached only the types below it and emitted
nothing at all for a Paragraph.
"""
import re

import pytest

from docmodel import DocObject, Document
from docops.base import OperatorConfig
from docops.projectors.latex import LaTeXProjector
from docops.projectors.latex_pipeline import (review_notes, todo_markup,
                                              todo_preamble)


class _Obj:
    def __init__(self, **props):
        self.props = props


def _project(*propsets):
    doc = Document()
    for i, props in enumerate(propsets):
        p = dict(props)
        p.setdefault("flow_index", i)
        doc.add(DocObject(type=p.pop("_type", "Paragraph"), props=p))
    return LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector")).project(doc)


def test_a_note_becomes_a_todo():
    assert todo_markup(_Obj(review_notes=["Check this claim"])) == \
        "\\todo{Check this claim}"


def test_several_notes_each_get_one():
    assert todo_markup(_Obj(review_notes=["First", "Second"])) == \
        "\\todo{First}\\todo{Second}"


def test_a_single_string_is_one_note():
    assert review_notes(_Obj(review_notes="Just one")) == ["Just one"]


@pytest.mark.parametrize("note,want", [
    ("50% of cases", "50\\% of cases"),
    ("a & b", "a \\& b"),
    ("x_y", "x\\_y"),
])
def test_a_note_is_escaped_like_prose(note, want):
    """A comment holding `%` would comment out the rest of its line."""
    assert todo_markup(_Obj(review_notes=[note])) == "\\todo{%s}" % want


@pytest.mark.parametrize("props", [{}, {"review_notes": []},
                                   {"review_notes": ["", "  "]},
                                   {"review_notes": None}])
def test_no_note_emits_nothing(props):
    assert todo_markup(_Obj(**props)) == ""


def test_the_package_loads_only_when_a_note_is_emitted():
    assert "todonotes" in todo_preamble("body with \\todo{x}")
    assert todo_preamble("a body with no notes") == ""


def test_the_note_reaches_the_projection():
    tex = _project({"text": "A reviewed paragraph.",
                    "review_notes": ["Is this supported?"]})
    assert "\\todo{Is this supported?}" in tex
    assert "todonotes" in tex
    assert "A reviewed paragraph." in tex


@pytest.mark.parametrize("kind", ["Paragraph", "Equation", "Theorem",
                                  "Section", "Table"])
def test_every_object_type_can_carry_a_note(kind):
    """The hook is at `_render`'s ENTRY. Placed among the type branches it
    reached only the types below it, and a Paragraph got nothing."""
    props = {"_type": kind, "review_notes": ["A note"], "text": "body",
             "latex": "a = b", "caption": "A caption", "level": 1,
             "statement": "a statement", "latex_code": "x"}
    assert "\\todo{A note}" in _project(props), kind


def test_a_document_with_no_notes_loads_no_package():
    tex = _project({"text": "Nothing to review here."})
    assert "todonotes" not in tex
    assert "\\todo" not in tex


def test_a_note_does_not_replace_the_body():
    tex = _project({"text": "The body must survive.",
                    "review_notes": ["A note"]})
    assert "The body must survive." in tex
    assert "\\todo{A note}" in tex
