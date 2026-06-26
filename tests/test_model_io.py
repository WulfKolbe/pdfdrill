"""
model_io + docpack/docgraph (the reference-based storage + lazy read path):
- docpack round-trip is value-lossless;
- load_model/save_model preserve the model exactly (packed sidecar preferred);
- the DocGraph fast read-path yields BYTE-IDENTICAL projector output to the
  full-Document path — proving "all projections stay correct" under the new
  storage/read layer. The hot LLM read (llmtext) is the pilot.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import docpack, model_io
from pdfdrill.docgraph import DocGraph
from docops.projectors.llm_text import LLMTextProjector, build_llm_text
from docops.base import OperatorConfig


def _model() -> Document:
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="s1", props={"caption": "Intro", "level": 1,
                                                      "flow_index": 1}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "First para.\n\nSecond block.", "flow_index": 2}))
    doc.add(DocObject(type="Equation", id="e1", props={"latex": "E = mc^2", "page": 3,
                                                       "flow_index": 3}))
    doc.add(DocObject(type="Formula", id="f1", props={"latex": "\\alpha", "flow_index": 4}))
    doc.add(DocObject(type="Formula", id="f2", props={"latex": "", "flow_index": 5}))
    return doc


def test_docpack_round_trip_lossless():
    m = _model().to_dict()
    assert docpack.unpack(docpack.pack(m)) == m


def test_save_load_model_preserves_document():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        model_io.save_model(mp, _model())
        assert model_io.packed_path(mp).exists()        # sidecar written
        back = model_io.load_model(mp)                   # prefers packed
        assert back.to_dict() == _model().to_dict()


def test_load_model_falls_back_to_plain_when_no_sidecar():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        mp.write_text(json.dumps(_model().to_dict()))    # legacy file, no sidecar
        back = model_io.load_model(mp)
        assert back.to_dict() == _model().to_dict()


def test_stale_sidecar_is_ignored():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        model_io.save_model(mp, _model())
        # an out-of-band newer write to the plain model must win over the sidecar
        import os, time
        time.sleep(0.01)
        other = _model(); other.objects["p1"].props["text"] = "CHANGED"
        mp.write_text(json.dumps(other.to_dict()))
        os.utime(mp, None)                               # bump mtime
        back = model_io.load_model(mp)
        assert back.objects["p1"].props["text"] == "CHANGED"


def test_load_docgraph_ignores_stale_sidecar():
    """load_docgraph must honor an out-of-band newer .docmodel.json (e.g. a
    command that saved via json.dump and left the .docpack stale) — else
    read-path commands like `status` serve stale data."""
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        model_io.save_model(mp, _model())                # writes plain + packed
        import os, time
        time.sleep(0.01)
        other = _model(); other.objects["p1"].props["text"] = "CHANGED"
        mp.write_text(json.dumps(other.to_dict()))       # plain only, stale sidecar
        os.utime(mp, None)
        g = model_io.load_docgraph(mp)
        node = next(n for n in g if n.id == "p1")
        assert node.props["text"] == "CHANGED"


def test_docgraph_llmtext_byte_identical_to_document():
    doc = _model()
    via_doc = LLMTextProjector(OperatorConfig(op="projector",
                               classname="LLMTextProjector")).project(doc)
    g = DocGraph(docpack.pack(doc.to_dict()))
    via_graph = build_llm_text(list(g), g.meta)
    assert via_graph == via_doc                          # the pilot proof
    assert "T_PARA_0001#1" in via_graph and "E = mc^2" in via_graph


def test_docgraph_counts_match_document():
    doc = _model()
    g = DocGraph(docpack.pack(doc.to_dict()))
    for t in ("Paragraph", "Equation", "Formula", "Section"):
        assert len(g.type_index.get(t, [])) == len(doc.objects_of_type(t))


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
