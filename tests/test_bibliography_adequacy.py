"""A fact about MODEL CONTENT must be checked against the model, not remembered.

`bibliography` was `done_when: fact:BIBLIOGRAPHY_BUILT` — a sidecar fact. The
fact records that the command once ran; the References it produced live in the
model. Rebuilding the model (`model --force`, a newer lines.json, a route
change) constructs a fresh Document and the References are gone, while the fact
stays set forever.

Observed on 2209.00445v3: `steps` reported "already done: bibliography,
bibsource" while the model held 60 Citations and 0 References, so every citation
rendered as a placeholder stub. CitationPass never failed — nothing ever asked
it to run, because the machine believed the work was done.

Same shape as `model:geometry`: presence (of a fact, of a file) is not adequacy.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import planner


class _SC:
    def __init__(self, facts=()):
        self._f = set(facts)

    def has(self, f):
        return f in self._f


def _model(tmp_path, name, citations=0, references=0) -> Path:
    doc = Document()
    for i in range(citations):
        doc.add(DocObject(type="Citation", props={"citekey": f"k{i}"}))
    for i in range(references):
        doc.add(DocObject(type="Reference", props={"citekey": f"k{i}"}))
    p = tmp_path / name
    p.write_text(json.dumps(doc.to_dict()))
    return p


def test_citations_without_references_is_NOT_resolved(tmp_path):
    m = _model(tmp_path, "a.json", citations=60, references=0)
    assert planner.detect("model:citations_resolved", _SC(), Path("d.pdf"), m) is False


def test_a_stale_fact_does_not_make_it_resolved(tmp_path):
    """The exact regression: the fact is set, the References are gone."""
    m = _model(tmp_path, "b.json", citations=60, references=0)
    sc = _SC({"BIBLIOGRAPHY_BUILT", "BIBSOURCE_BUILT"})
    assert planner.detect("model:citations_resolved", sc, Path("d.pdf"), m) is False


def test_citations_with_references_is_resolved(tmp_path):
    m = _model(tmp_path, "c.json", citations=60, references=46)
    assert planner.detect("model:citations_resolved", _SC(), Path("d.pdf"), m) is True


def test_a_document_with_no_citations_needs_no_bibliography(tmp_path):
    """Nothing to resolve — must not drag every doc through a bibliography run."""
    m = _model(tmp_path, "d.json", citations=0, references=0)
    assert planner.detect("model:citations_resolved", _SC(), Path("d.pdf"), m) is True


def test_missing_model_is_not_resolved(tmp_path):
    assert planner.detect("model:citations_resolved", _SC(), Path("d.pdf"),
                          tmp_path / "nope.json") is False


def test_tiddlers_demands_a_bibliography():
    man = planner.load_manifest()
    requires, done = planner.load_graph(man)
    assert "bibliography" in requires.get("tiddlers", []), \
        "tiddlers renders citation links; it must demand the entries behind them"
    assert done.get("bibliography") == "model:citations_resolved"


def test_plan_inserts_bibliography_for_an_unresolved_doc():
    requires, _ = planner.load_graph(planner.load_manifest())
    steps = planner.plan("tiddlers", requires, satisfied={"model"})
    assert "bibliography" in steps[:-1] and steps[-1] == "tiddlers", steps
