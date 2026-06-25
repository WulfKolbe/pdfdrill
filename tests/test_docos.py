"""docOS — Step 1: the L0 selector state machine.

A persisted working SET of documents with a current folder, Unix-glob add/remove,
saved sets, and the compact state UI with level-gated command listing. No
materialization yet (L1+ is later steps); higher layers are shown as gated.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docos


def _mkfiles(d, names):
    for n in names:
        (Path(d) / n).write_bytes(b"%PDF-1.4" if n.endswith(".pdf") else b"x")


def test_cd_and_add_glob():
    with tempfile.TemporaryDirectory() as d:
        _mkfiles(d, ["a.pdf", "b.pdf", "notes.txt"])
        s = docos.DocosState(folder=d)
        n = s.add("*.pdf")
        assert n == 2
        assert sorted(os.path.basename(p) for p in s.documents) == ["a.pdf", "b.pdf"]
        # notes.txt not added (not a document type)


def test_cd_relative_and_absolute():
    with tempfile.TemporaryDirectory() as d:
        sub = Path(d) / "papers"
        sub.mkdir()
        _mkfiles(sub, ["x.pdf"])
        s = docos.DocosState(folder=d)
        s.cd("papers")
        assert Path(s.folder) == sub
        assert s.add("*.pdf") == 1


def test_add_is_deduped_and_remove_glob():
    with tempfile.TemporaryDirectory() as d:
        _mkfiles(d, ["a.pdf", "b.pdf", "c.pdf"])
        s = docos.DocosState(folder=d)
        s.add("*.pdf")
        assert s.add("a.pdf") == 0                  # already present → no dup
        assert len(s.documents) == 3
        removed = s.remove("a.pdf")
        assert removed == 1
        assert sorted(os.path.basename(p) for p in s.documents) == ["b.pdf", "c.pdf"]


def test_save_and_load_set_demotes_to_L0():
    with tempfile.TemporaryDirectory() as d:
        _mkfiles(d, ["a.pdf", "b.pdf"])
        s = docos.DocosState(folder=d)
        s.add("*.pdf")
        s.level = "L2"                              # pretend something was materialized
        s.save_set("mine")
        assert "mine" in s.sets()
        s.clear()
        assert len(s.documents) == 0
        s.level = "L3"
        s.load_set("mine")
        assert len(s.documents) == 2
        assert s.level == "L0"                      # load demotes per spec


def test_state_round_trips_to_disk():
    with tempfile.TemporaryDirectory() as d:
        os.environ["PDFDRILL_DOCOS_STATE"] = str(Path(d) / "docos.json")
        try:
            _mkfiles(d, ["a.pdf"])
            s = docos.DocosState(folder=d)
            s.add("*.pdf")
            docos.save_state(s)
            s2 = docos.load_state()
            assert len(s2.documents) == 1 and Path(s2.folder) == Path(d)
        finally:
            del os.environ["PDFDRILL_DOCOS_STATE"]


def test_ui_gates_levels_by_materialization():
    with tempfile.TemporaryDirectory() as d:
        _mkfiles(d, ["a.pdf"])
        s = docos.DocosState(folder=d)
        # empty set: only L0 actionable
        ui0 = docos.render_ui(s)
        assert "Set: 0 documents" in ui0
        s.add("*.pdf")
        ui = docos.render_ui(s)
        assert "Set: 1 documents" in ui
        assert "L1 Represent" in ui                 # available once a set is loaded
        # L2 requires L1.5 → shown gated, not available
        assert "requires L1.5" in ui


def test_dispatch_routes_l0_verbs_and_reports_planned():
    with tempfile.TemporaryDirectory() as d:
        os.environ["PDFDRILL_DOCOS_STATE"] = str(Path(d) / "docos.json")
        try:
            _mkfiles(d, ["a.pdf", "b.pdf"])
            s = docos.DocosState(folder=d)
            msg, s = docos.dispatch(s, "add *.pdf")
            assert "2" in msg and len(s.documents) == 2
            msg, s = docos.dispatch(s, "make md")          # later step
            assert "planned" in msg.lower() or "not yet" in msg.lower()
        finally:
            del os.environ["PDFDRILL_DOCOS_STATE"]


if __name__ == "__main__":
    for fn in [test_cd_and_add_glob, test_cd_relative_and_absolute,
               test_add_is_deduped_and_remove_glob,
               test_save_and_load_set_demotes_to_L0,
               test_state_round_trips_to_disk,
               test_ui_gates_levels_by_materialization,
               test_dispatch_routes_l0_verbs_and_reports_planned]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
