r"""An equation has a name, not a number.

T-0156, the owner's SECOND requirement. The label used to be

    label = p.get("label") or equation_label(obj)

and `common.equation_label` returns the `refnum`, so an equation's PRINTED
NUMBER was its IDENTIFIER. On 1503.00301 that put 31 labels in the .tex, every
one purely numeric and exactly the set of refnums.

A NUMBER USED AS A NAME compiles, renders, and is wrong: `\eqref{1}` resolves
only while LaTeX's own counter happens to agree with the page's, and goes
silently wrong when a section renumbers. It is also where class F's false
positives came from — 60 of 166 parenthesised tokens in prose matched an
emitted label, `(1)` six times and `(3)` nineteen times on that one document,
and those "labels" were equation numbers put there by us.

THE SCHEME IS `_figure_label`'s, which already carries the reasoning:
readable, so a reader writing `\ref{eq:8}` can guess it, but CHECKED FOR
UNIQUENESS, because a duplicate label makes every reference to it resolve to
whichever came last, silently. Equations were simply not in its count.

THE ORDER IS MEASURED. Over the eight audit e-prints' 254 equations: 29 carry
the author's own `label` (all on the two source-built documents, and it is
what the author's own `\ref` points at), 12 carry `eq_label` (the same thing
promoted onto a reading-built object), and 78 carry a `refnum` — all 78 unique
within their document.
"""
import re

import pytest

from docmodel import DocObject, Document
from docops.base import OperatorConfig
from docops.projectors.latex import LaTeXProjector


def _project(*propsets):
    doc = Document()
    for i, props in enumerate(propsets):
        p = dict(props)
        p["flow_index"] = i
        doc.add(DocObject(type="Equation", props=p))
    return LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector")).project(doc)


def _labels(tex):
    return re.findall(r"\\label\{([^}]*)\}", tex)


def test_the_authors_own_label_wins():
    assert _labels(_project({"latex": "a=b", "label": "eq:author",
                             "refnum": "7"})) == ["eq:author"]


def test_the_promoted_eq_label_comes_next():
    assert _labels(_project({"latex": "a=b", "eq_label": "eq:gold",
                             "refnum": "7"})) == ["eq:gold"]


def test_a_unique_refnum_becomes_a_readable_name():
    assert _labels(_project({"latex": "a=b", "refnum": "7"})) == ["eq:7"]


def test_a_duplicate_refnum_falls_back_to_the_object_id():
    """A duplicate label makes every reference resolve to whichever came
    last, silently — `_figure_label`'s own reason."""
    labs = _labels(_project({"latex": "a=b", "refnum": "5"},
                            {"latex": "c=d", "refnum": "5"}))
    assert len(labs) == 2
    assert all(l.startswith("eq:obj") for l in labs), labs
    assert labs[0] != labs[1]


def test_an_equation_with_nothing_is_still_addressable():
    """Requirement 2: addressable by a stable label from its obj id."""
    labs = _labels(_project({"latex": "a=b"}))
    assert len(labs) == 1 and labs[0].startswith("eq:obj")


def test_no_label_is_a_bare_number():
    tex = _project({"latex": "a=b", "refnum": "1"},
                   {"latex": "c=d", "refnum": "2"},
                   {"latex": "e=f", "refnum": "3"},
                   {"latex": "g=h"})
    for lab in _labels(tex):
        assert not lab.strip().replace(".", "").isdigit(), lab


def test_a_refnum_that_is_not_a_number_does_not_become_a_name():
    """The shape guard applies here too: `3 cdot 4` is not a name either."""
    labs = _labels(_project({"latex": "a=b", "refnum": "3 cdot 4"}))
    assert labs and labs[0].startswith("eq:obj"), labs


@pytest.mark.parametrize("refnum", ["7", "3.2", "4a", "A.1", "3.18/16"])
def test_every_real_number_shape_makes_a_name(refnum):
    assert _labels(_project({"latex": "a=b", "refnum": refnum})) == \
        ["eq:%s" % refnum]


def test_the_tag_and_the_label_now_say_different_things():
    """The point of the whole step: the number is the TAG, the name is the
    LABEL, and they are no longer the same string."""
    tex = _project({"latex": "a=b", "refnum": "7"})
    assert "\\tag{7}" in tex
    assert "\\label{eq:7}" in tex


def test_the_label_is_stable_across_two_projections():
    doc = Document()
    doc.add(DocObject(type="Equation",
                      props={"latex": "a=b", "flow_index": 0}))
    cfg = OperatorConfig(op="projector", classname="LaTeXProjector")
    first = _labels(LaTeXProjector(cfg).project(doc))
    second = _labels(LaTeXProjector(cfg).project(doc))
    assert first == second and first[0].startswith("eq:obj")
