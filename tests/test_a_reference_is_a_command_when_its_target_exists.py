r"""A reference is a command when its target exists, and text otherwise.

T-0156, the owner's fifth requirement. `_PROSE_CLEAN` flattens
`\ref{tab:x}` to `(tab:x)`, keeping the target as text — its own comment
records that it used to collapse everything to the literal "(ref)" and that
3452 references lost their target that way. Promoting them back is the
requirement; promoting them blindly is not, because a `\ref` against a label
nothing defines is "Reference undefined", which the FIRST requirement counts
as a failure. That is what cost `cleveref` its place in `_AUTHOR_PACKAGES`.

ONE RULE, BOTH DIRECTIONS, which is why the 18 dangling cleveref commands on
arxiv.2402.03975 need no special case: they point at list-item labels we do
not emit, so the same test demotes them to text. When list items arrive their
labels enter the emitted set and the same rule promotes them, unchanged.

WHY THE MODEL IS CONSULTED AND NOT ONLY THE BODY. Measured over the eight
audit documents: 166 parenthesised tokens equal an emitted label, and 60 of
them — 36% — were never a reference. `(1)` six times and `(3)` NINETEEN times
on 1503.00301, against labels named "1" and "3"; all four documents carrying
them are reading-built, with no source and therefore no reference ever
flattened. A rewrite driven by the text alone would have written `\ref{3}`
nineteen times on one page. So the body answers "is this label emitted" and
the model answers "was this span a reference".

On arxiv.0912.2444: 109 records in 33 objects, 93 whose label the body emits,
0 body occurrences not backed by a record, 0 numeric labels.
"""
import re

import pytest

from docops.projectors.latex_pipeline import resolve_xrefs
from pdfdrill.latex_source import (_clean_prose, _flattened_xrefs,
                                   _xref_prop)


class _Obj:
    def __init__(self, xrefs):
        self.props = {"xrefs": xrefs} if xrefs else {}


class _Doc:
    def __init__(self, objects):
        self.objects = objects


def _doc(*records):
    return _Doc([_Obj(list(records))])


def _rec(label):
    return {"label": label, "source": "(%s)" % label}


# ---------------------------------------------------------------- recording

def test_every_recorded_source_is_findable_in_the_cleaned_prose():
    """The keystone: `source` is what the cleaner writes, verbatim."""
    for chunk in [r"see \ref{tab:x} now",
                  r"\eqref{eq:1} and \cref{a_b}",
                  r"spaced \ref{ x } here",
                  r"\autoref{fig:2}, \Cref{sec:3}",
                  r"\ref{a}\ref{b}\ref{c}"]:
        cleaned = _clean_prose(chunk)
        for rec in _flattened_xrefs(chunk):
            assert rec["source"] in cleaned, (chunk, rec, cleaned)


def test_a_spaced_label_keeps_its_spaces_on_both_sides():
    # a stripped source would not be found; a stripped label would not match
    # a `\label{ x }` the projector emits
    [rec] = _flattened_xrefs(r"see \ref{ x }")
    assert rec["source"] == "( x )"
    assert rec["label"] == " x "


def test_an_empty_reference_records_nothing():
    assert _flattened_xrefs(r"\ref{}") == []
    assert _flattened_xrefs(r"\ref{   }") == []


def test_no_reference_means_no_prop_at_all():
    # absent, not empty: a document referencing nothing gets no model churn
    assert _xref_prop("plain prose") == {}
    assert "xrefs" in _xref_prop(r"see \ref{a}")


@pytest.mark.parametrize("cmd", ["ref", "eqref", "autoref", "cref", "Cref"])
def test_every_flattened_command_is_recorded(cmd):
    assert _flattened_xrefs("\\%s{tab:x}" % cmd) == [_rec("tab:x")]


# --------------------------------------------------------------- promoting

def test_a_reference_whose_label_is_emitted_becomes_a_command():
    body, counts = resolve_xrefs(_doc(_rec("tab:x")),
                                 "see (tab:x)\n\\label{tab:x}")
    assert r"\ref{tab:x}" in body
    assert counts["promoted"] == 1


def test_a_reference_whose_label_is_not_emitted_stays_text():
    body, counts = resolve_xrefs(_doc(_rec("tab:x")), "see (tab:x)\n")
    assert "(tab:x)" in body
    assert r"\ref" not in body
    assert counts["promoted"] == 0 and counts["left_as_text"] == 1


def test_the_false_positive_class_is_refused():
    """`(3)` against a label named "3", with no record: 19 of these on one
    page of 1503.00301, and every one of them ordinary parenthesised prose."""
    body, counts = resolve_xrefs(_doc(), "equation (3) shows\n\\label{3}")
    assert "(3)" in body
    assert r"\ref" not in body
    assert counts["promoted"] == 0


def test_a_recorded_source_is_promoted_only_as_often_as_recorded():
    # two occurrences in the body, one record -> one promotion
    body, counts = resolve_xrefs(_doc(_rec("a")),
                                 "(a) and again (a)\n\\label{a}")
    assert counts["promoted"] == 1
    assert body.count(r"\ref{a}") == 1
    assert body.count("(a)") == 1


def test_several_records_promote_several_occurrences():
    body, counts = resolve_xrefs(_doc(_rec("a"), _rec("a")),
                                 "(a) and again (a)\n\\label{a}")
    assert counts["promoted"] == 2
    assert body.count(r"\ref{a}") == 2


def test_a_record_whose_source_left_the_body_is_counted_not_guessed():
    body, counts = resolve_xrefs(_doc(_rec("gone")), "nothing here\n\\label{gone}")
    assert counts["not_found"] == 1
    assert counts["promoted"] == 0


# ---------------------------------------------------------------- demoting

@pytest.mark.parametrize("cmd", ["ref", "eqref", "cref", "labelcref", "Cref",
                                 "autoref"])
def test_a_dangling_command_becomes_text(cmd):
    body, counts = resolve_xrefs(_doc(), "see \\%s{enum:first} now" % cmd)
    assert "(enum:first)" in body
    assert "\\%s{" % cmd not in body
    assert counts["demoted"] == 1


def test_a_command_whose_label_exists_is_left_alone():
    body, counts = resolve_xrefs(_doc(), "see \\ref{tab:x}\n\\label{tab:x}")
    assert r"\ref{tab:x}" in body
    assert counts["demoted"] == 0


def test_the_eighteen_dangling_cleveref_commands():
    """arxiv.2402.03975's shape: \\labelcref at list-item labels we do not
    emit. They demote now and promote themselves when list items exist."""
    body = (r"\labelcref{enum:first} \labelcref{enum:second} "
            r"\cref{main_algo}" "\n" r"\label{main_algo}")
    out, counts = resolve_xrefs(_doc(), body)
    assert "(enum:first)" in out and "(enum:second)" in out
    assert r"\cref{main_algo}" in out      # its label IS emitted
    assert counts["demoted"] == 2


def test_no_undefined_reference_can_survive_the_rule():
    """The property the gate rests on: every reference command left in the
    body has its label emitted in the same body."""
    body = (r"(a) (b) \ref{c} \labelcref{d} (e)" "\n"
            r"\label{a} \label{c} \label{e}")
    out, _ = resolve_xrefs(_doc(_rec("a"), _rec("b"), _rec("e")), body)
    labels = set(re.findall(r"\\label\s*\{([^}]*)\}", out))
    for m in re.finditer(r"\\(?:ref|eqref|autoref|cref|Cref|labelcref)"
                         r"\s*\{([^{}]*)\}", out):
        assert m.group(1) in labels, (m.group(0), labels)


def test_an_empty_document_is_unchanged():
    body = "plain text with (parentheses) and no labels"
    out, counts = resolve_xrefs(_doc(), body)
    assert out == body
    assert counts == {"promoted": 0, "left_as_text": 0, "demoted": 0,
                      "not_found": 0}


# ------------------------------------------------- against the REAL Document

def test_the_records_are_read_off_a_real_document():
    """`Document.objects` is a dict KEYED BY ID.

    Every test above passes against a stub whose `objects` is a LIST, and the
    first implementation iterated the mapping itself — yielding id strings,
    which carry no `props`. It found nothing, changed nothing, and every unit
    test still passed; only the reference census over the eight documents
    showed it (paired 15, unmoved). So one test builds a real `Document`.
    """
    from docmodel import DocObject, Document

    from docops.projectors.latex_pipeline import _xref_records

    doc = Document()
    doc.add(DocObject(type="Paragraph",
                      props={"text": "see (tab:x)",
                             "xrefs": [{"label": "tab:x",
                                        "source": "(tab:x)"}]}))
    doc.add(DocObject(type="Paragraph", props={"text": "no references"}))

    assert _xref_records(doc) == [{"label": "tab:x", "source": "(tab:x)"}]

    body, counts = resolve_xrefs(doc, "see (tab:x)\n\\label{tab:x}")
    assert r"\ref{tab:x}" in body
    assert counts["promoted"] == 1


def test_a_real_document_with_no_records_changes_nothing():
    from docmodel import DocObject, Document

    doc = Document()
    doc.add(DocObject(type="Paragraph", props={"text": "equation (3)"}))
    body = "equation (3) shows\n\\label{3}"
    out, counts = resolve_xrefs(doc, body)
    assert out == body
    assert counts["promoted"] == 0


# ------------------------------- the spelling the body actually carries

def test_a_flattened_reference_is_found_in_its_escaped_spelling():
    r"""By the time the body is rendered, a flattened reference is PROSE, so
    `escape_prose_specials` has escaped its specials: `(a_b)` is written
    `(a\_b)`.

    Looking only for the recorded spelling missed 40 of the 46 distinct
    sources on arxiv.2402.03975 — 105 records, every one a label with an
    underscore, and every one present in the body in escaped form. The first
    implementation reported them as `not_found`, which reads like lost prose
    and was really a matcher that did not know its own pipeline.
    """
    body, counts = resolve_xrefs(_doc(_rec("main_algo")),
                                 "see (main\\_algo)\n\\label{main_algo}")
    assert r"\ref{main_algo}" in body
    assert counts["promoted"] == 1 and counts["not_found"] == 0


def test_the_unescaped_spelling_still_works():
    body, counts = resolve_xrefs(_doc(_rec("plain")),
                                 "see (plain)\n\\label{plain}")
    assert r"\ref{plain}" in body
    assert counts["promoted"] == 1


@pytest.mark.parametrize("label", ["a_b", "a%b", "a&b", "a#b", "x_y_z"])
def test_every_escaped_special_in_a_label_is_found(label):
    from docops.projectors.latex_pipeline import escape_prose_specials
    body = "see %s\n\\label{%s}" % (escape_prose_specials("(%s)" % label),
                                    label)
    out, counts = resolve_xrefs(_doc(_rec(label)), body)
    assert "\\ref{%s}" % label in out, (label, out)
    assert counts["promoted"] == 1


def test_a_label_needing_no_escape_offers_one_spelling_only():
    from docops.projectors.latex_pipeline import _body_spellings
    assert _body_spellings("(tab:x)") == ["(tab:x)"]
    assert _body_spellings("(a_b)") == ["(a_b)", "(a\\_b)"]


def test_a_reference_the_author_wrapped_in_parentheses():
    r"""The source `(\cref{x})` flattens to `((x))`, so the recorded `(x)` is
    a substring and the promotion must land inside the author's own brackets.
    """
    body, counts = resolve_xrefs(_doc(_rec("x")), "shown ((x))\n\\label{x}")
    assert r"(\ref{x})" in body
    assert counts["promoted"] == 1


def test_not_found_still_counts_a_source_that_truly_left():
    body, counts = resolve_xrefs(_doc(_rec("gone")),
                                 "nothing at all\n\\label{gone}")
    assert counts["not_found"] == 1 and counts["promoted"] == 0
