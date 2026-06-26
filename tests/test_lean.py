"""
LaTeX theorem -> Lean 4 export: store-then-project (lean_export) + the lean4
tiddler field. Generation is an LLM delegation (sandbox round-trip tested with
a stub response); projection is deterministic over stored code.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import lean_export
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector


def _doc():
    doc = Document(); doc.meta["bibkey"] = "2110.11150"
    t = DocObject(type="Theorem", props={
        "kind": "lemma", "printed_title": "Lemma", "number": 2, "title": "Scaling",
        "label": "thm:scaling", "statement": "If $a$ then $b$.", "flow_index": 1})
    doc.add(t)
    p = DocObject(type="Proof", props={
        "statement": "trivial.", "flow_index": 2, "proof_of": t.id})
    doc.add(p)
    t.props["proof_id"] = p.id
    return doc, t, p


def test_lean_name_and_prompt():
    assert lean_export.lean_name("thm:scaling", "lemma", 2, 0) == "thm_scaling"
    assert lean_export.lean_name("", "lemma", 2, 0) == "lemma_2"
    assert lean_export.lean_name("", "lemma", None, 3) == "lemma_4"
    doc, t, _ = _doc()
    pr = lean_export.theorem_prompt(t, 0)
    assert "Lean 4" in pr and "thm_scaling" in pr and "If $a$ then $b$." in pr


def test_project_lean_uses_stored_else_stub():
    doc, t, p = _doc()
    # no stored Lean -> sorry/stub + the proof as a comment + namespace
    txt = lean_export.project_lean(doc)
    assert "import Mathlib" in txt
    assert "namespace P2110_11150" in txt and "end P2110_11150" in txt
    assert "TODO: run `pdfdrill lean`" in txt
    assert "-- proof: trivial." in txt
    # stored Lean is used verbatim
    t.props["lean4"] = "theorem thm_scaling (a b : Prop) (h : a) : b := by sorry"
    txt2 = lean_export.project_lean(doc)
    assert "theorem thm_scaling (a b : Prop) (h : a) : b := by sorry" in txt2
    assert "TODO" not in txt2.split("-- proof:")[0]


def test_lean4_field_on_theorem_tiddler():
    doc, t, p = _doc()
    t.props["lean4"] = "theorem thm_scaling : True := by trivial"
    tids = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(doc))
    thm = next(x for x in tids if x.get("label") == "thm:scaling")
    assert thm["lean4"] == "theorem thm_scaling : True := by trivial"


def test_generate_lean_stores_via_sandbox_roundtrip(tmp_path=None):
    import tempfile
    import os
    from pdfdrill import llm_delegate as D
    doc, t, p = _doc()
    with tempfile.TemporaryDirectory() as dd:
        drill = Path(dd)
        os.environ["PDFDRILL_DELEGATE"] = "sandbox"
        try:
            # 1st call: no responses yet -> deferred, nothing stored
            res = lean_export.generate_lean(doc, drill_dir=drill, runtime=D.Runtime.SANDBOX)
            assert res["generated"] == 0 and res["deferred"] is not None
            # the agent writes the response file
            task = res["deferred"].tasks[0]
            (drill / "llm" / (task.task_id + D.RESP_SUFFIX)).write_text(
                json.dumps({"result": "```lean\ntheorem thm_scaling : True := by trivial\n```"}),
                encoding="utf-8")
            # 2nd call: ingests -> stores on the Theorem
            res2 = lean_export.generate_lean(doc, drill_dir=drill, runtime=D.Runtime.SANDBOX)
            assert res2["generated"] == 1
            assert t.props["lean4"] == "theorem thm_scaling : True := by trivial"
        finally:
            os.environ.pop("PDFDRILL_DELEGATE", None)


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
