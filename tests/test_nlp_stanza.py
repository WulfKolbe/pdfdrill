"""
Tests for the docops Stanza NLP enhancement.

Covers (no Stanza needed):
  - clean_text markup projection
  - object_text per-type field mapping + ListItem marker folding
  - StanzaNlpMutator wiring via an injected fake annotator
    (props.nlp placement, flow order, type/page/limit selection,
     graceful skip vs. hard error when Stanza is unavailable)
And a real-Stanza smoke test that auto-skips if the model is absent.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject  # noqa: E402

from docops.base import OperatorConfig  # noqa: E402
from docops.mutators.stanza_nlp import StanzaNlpMutator  # noqa: E402
from docops.nlp_stanza import (  # noqa: E402
    MATH_PLACEHOLDER,
    StanzaAnnotator,
    StanzaUnavailable,
    clean_text,
    object_text,
)


# ---------- pure: clean_text ----------

def test_clean_strips_markup_and_keeps_prose():
    raw = "\\section*{1 Intro} As models evolve \\(E=mc^2\\), see [3] and {{X}}."
    out = clean_text(raw)
    assert "1 Intro As models evolve" in out
    assert MATH_PLACEHOLDER in out
    assert "[3]" not in out and "{{" not in out and "\\" not in out


def test_clean_empty():
    assert clean_text("") == ""
    assert clean_text("   ") == ""


# ---------- pure: object_text ----------

def _obj(type_, **props):
    return DocObject(type=type_, props=props)


def test_object_text_per_type_field():
    assert object_text(_obj("Paragraph", text="P")) == "P"
    assert object_text(_obj("Abstract", text="A")) == "A"
    assert object_text(_obj("Section", caption="S")) == "S"
    assert object_text(_obj("ListItem", content="L")) == "L"
    assert object_text(_obj("Footnote", content="F")) == "F"
    assert object_text(_obj("Page")) == ""  # not annotatable


def test_object_text_folds_listitem_marker():
    assert object_text(_obj("ListItem", marker="A.", content="First.")) == "A. First."
    assert object_text(_obj("ListItem", content="No marker.")) == "No marker."


# ---------- mutator wiring (fake annotator) ----------

class FakeAnnotator:
    """Records the clean text it is given; returns one stub sentence."""

    def __init__(self):
        self.seen = []

    def annotate(self, clean):
        self.seen.append(clean)
        if not clean.strip():
            return []
        return [{"index": 0, "text": clean, "tokens": [], "entities": []}]


class DeadAnnotator:
    def annotate(self, clean):
        raise StanzaUnavailable("no model")


def _doc():
    doc = Document()
    for o in [
        DocObject(type="Section", props={"flow_index": 0, "page": 1, "caption": "Intro"}),
        DocObject(type="Abstract", props={"flow_index": 1, "page": 1, "text": "An abstract."}),
        DocObject(type="Paragraph", props={"flow_index": 2, "page": 1, "text": "Hello \\(x\\)."}),
        DocObject(type="ListItem", props={"flow_index": 3, "page": 2, "marker": "A.", "content": "Item."}),
        DocObject(type="Footnote", props={"flow_index": 4, "page": 2, "content": "A note."}),
        DocObject(type="Page", props={"flow_index": 9, "page": 1}),  # ignored
    ]:
        doc.add(o)
    return doc


def _mutator(**params):
    return StanzaNlpMutator(OperatorConfig(op="mutator", classname="StanzaNlpMutator", params=params))


def test_mutator_annotates_all_prose_types():
    doc, fake = _doc(), FakeAnnotator()
    m = _mutator()
    m.annotator = fake
    m.apply(doc)

    annotated = {o.type for o in doc.objects.values() if o.props.get("nlp")}
    assert annotated == {"Section", "Abstract", "Paragraph", "ListItem", "Footnote"}
    assert "nlp" not in next(o for o in doc.objects.values() if o.type == "Page").props
    assert m.counters["objects_annotated"] == 5
    # ListItem marker folded; paragraph math cleaned to placeholder
    li = next(o for o in doc.objects.values() if o.type == "ListItem")
    assert li.props["nlp"]["clean_text"] == "A. Item."
    para = next(o for o in doc.objects.values() if o.type == "Paragraph")
    assert MATH_PLACEHOLDER in para.props["nlp"]["clean_text"]
    # original source field untouched
    assert para.props["text"] == "Hello \\(x\\)."


def test_mutator_respects_flow_order_types_and_limits():
    fake = FakeAnnotator()
    m = _mutator(types=["Paragraph", "Abstract", "Section"], max_page=1, limit=2)
    m.annotator = fake
    m.apply(_doc())
    # max_page=1 keeps Section/Abstract/Paragraph; flow order; limit=2 -> first two
    assert fake.seen == ["Intro", "An abstract."]


def test_mutator_skips_gracefully_when_stanza_unavailable():
    doc = _doc()
    m = _mutator()
    m.annotator = DeadAnnotator()
    m.apply(doc)  # must not raise
    assert m.counters.get("skipped_stanza_unavailable") == 1
    assert all("nlp" not in o.props for o in doc.objects.values())


def test_mutator_require_raises_when_unavailable():
    m = _mutator(require=True)
    m.annotator = DeadAnnotator()
    with pytest.raises(StanzaUnavailable):
        m.apply(_doc())


# ---------- real Stanza smoke (auto-skip) ----------

def test_real_stanza_smoke():
    doc = Document()
    doc.add(DocObject(type="Paragraph",
                      props={"flow_index": 1, "page": 1,
                             "text": "Alice studies at Peking University."}))
    m = _mutator()
    try:
        # force pipeline load now so absence skips the test (not the mutator)
        StanzaAnnotator().pipeline
    except StanzaUnavailable as exc:
        pytest.skip(f"Stanza unavailable: {exc}")
    m.apply(doc)
    nlp = next(iter(doc.objects.values())).props["nlp"]
    assert nlp["sentences"]
    lemmas = {t["lemma"] for t in nlp["sentences"][0]["tokens"]}
    assert "study" in lemmas
