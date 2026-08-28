"""256 — MathPix states how each line joins the one before it.

`subtype` carries `continues_line_no_hyphen` (join, drop the hyphen),
`continues_line_no_space` (join, KEEP it — a compound), `continues_line_space`
and `_newline` (join with a space). 1,228,183 corpus lines carry one; where the
field is absent the old heuristic still runs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.modules.dehyphenation import DehyphenationProcessor, _STATED
from docmodel.base_module import ModuleConfig
from docops.base import OperatorConfig
from docops.mutators.dehyphenate import Dehyphenate


def _mod(cls):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), "T")


def _para(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i, ln in enumerate(lines):
        ln.setdefault("id", f"l{i}")
        ln.setdefault("type", "text")
        ln.setdefault("text_display", ln["text"])
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    _mod(ParagraphProcessor).process_document(doc)
    Dehyphenate(OperatorConfig(op="mutator", classname="Dehyphenate", params={})).apply(doc)
    return doc.objects_of_type("Paragraph")[0]


def test_the_dominant_case_hyphen_already_stripped_by_mathpix():
    # 139,660 corpus lines. The old rule saw no trailing hyphen and inserted a
    # space, splitting the word: "the hy" + " " + "pothesis".
    para = _para([
        {"text": "the posterior probability that the hy"},
        {"text": "pothesis is true", "subtype": "continues_line_no_hyphen"},
    ])
    assert para.props["text"] == "the posterior probability that the hypothesis is true"


def test_no_space_keeps_a_real_compound():
    para = _para([
        {"text": "two image datasets: CIFAR-"},
        {"text": "10 and MNIST", "subtype": "continues_line_no_space"},
    ])
    assert para.props["text"] == "two image datasets: CIFAR-10 and MNIST"


def test_no_hyphen_with_a_trailing_hyphen_drops_it():
    para = _para([
        {"text": "we need more in-"},
        {"text": "formation here", "subtype": "continues_line_no_hyphen"},
    ])
    assert para.props["text"] == "we need more information here"


@pytest.mark.parametrize("sub", ["continues_line_space", "continues_line_newline"])
def test_space_and_newline_join_with_one_space(sub):
    para = _para([
        {"text": "the first line"},
        {"text": "the second line", "subtype": sub},
    ])
    assert para.props["text"] == "the first line the second line"


def test_mathpix_overrides_the_heuristic_where_they_disagree():
    # 557 corpus cases: the heuristic would drop the hyphen (next line starts
    # lowercase), MathPix says it is a compound.
    para = _para([
        {"text": "of the corre-"},
        {"text": "sponding operator", "subtype": "continues_line_no_space"},
    ])
    assert para.props["text"] == "of the corre-sponding operator"


def test_heuristic_still_runs_when_no_subtype_is_present():
    # 59% of text lines carry no subtype at all — the old behaviour must stand.
    assert _para([
        {"text": "We need more in-"},
        {"text": "formation about this."},
    ]).props["text"] == "We need more information about this."

    assert _para([
        {"text": "We define a one-"},
        {"text": "to-one correspondence here."},
    ]).props["text"] == "We define a one-to-one correspondence here."


def test_stated_map_covers_every_corpus_value():
    assert set(_STATED) == {
        "continues_line_no_hyphen", "continues_line_no_space",
        "continues_line_space", "continues_line_newline",
    }


def test_converter_module_records_which_signal_decided():
    doc = Document()
    doc.meta["bibkey"] = "T"
    lines = [
        {"id": "a", "type": "text", "text": "the hy", "text_display": "the hy"},
        {"id": "b", "type": "text", "text": "pothesis", "text_display": "pothesis",
         "subtype": "continues_line_no_hyphen"},
    ]
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    _mod(ParagraphProcessor).process_document(doc)
    _mod(DehyphenationProcessor).process_document(doc)
    bases = {a.props.get("join_basis") for a in doc.alignments if a.kind == "dehyphenate"}
    assert "mathpix" in bases
    cleaned = [s for n, s in doc.streams.items() if n.startswith("dehyphenated_para_")][0]
    # No joiner between the two chunks: "the hy" + "pothesis". The surviving
    # space is the one inside the first chunk, between the article and the word.
    assert [cleaned.payload[a]["text"] for a in cleaned.anchors] == ["the hy", "pothesis"]
    assert "".join(cleaned.payload[a]["text"] for a in cleaned.anchors) == "the hypothesis"
