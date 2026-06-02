"""
Tests for margin-aware continuity extraction (pdfdrill.continuity + cmd_continuity).

The classification (regexes + margin position) is pure and tested directly; the
render+OCR is faked for the command-level test (no tesseract needed).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import continuity, commands


def _line(text, x0, y0, x1, y1):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "page": 1}


def test_margin_position():
    assert continuity._margin(50, 20, 300, 40, 600, 1000) == "top"
    assert continuity._margin(50, 960, 400, 985, 600, 1000) == "bottom"
    assert continuity._margin(5, 500, 40, 520, 600, 1000) == "left"
    assert continuity._margin(560, 500, 595, 520, 600, 1000) == "right"
    assert continuity._margin(100, 500, 400, 520, 600, 1000) == "body"


def test_classify_seite_von_and_fortsetzung_and_control():
    lines = [
        _line("Seite 2 von 6", 50, 20, 300, 40),                 # top header
        _line("Sehr geehrte Damen und Herren,", 60, 500, 500, 520),
        _line("Fortsetzung siehe Seite 3", 50, 960, 400, 980),   # bottom footer
        _line("Druck-Nr.: ABC-123/45", 50, 985, 320, 1000),
    ]
    info = continuity.classify_lines(lines, (600, 1000))
    assert info["seq_in_doc"] == 2 and info["doc_total"] == 6
    assert info["is_continuation"] is True and info["next_seite"] == 3
    assert info["control_no"] == "ABC-123/45"          # full token, not truncated
    kinds = {m["kind"] for m in info["markers"]}
    assert {"seite_von", "fortsetzung", "control"} <= kinds
    wheres = {m["where"] for m in info["markers"]}
    assert "top" in wheres and "bottom" in wheres


def test_classify_bare_seite():
    info = continuity.classify_lines([_line("- Seite 4 -", 250, 30, 350, 50)], (600, 1000))
    assert info["seq_in_doc"] == 4 and info["doc_total"] is None
    assert info["markers"][0]["kind"] == "seite"


def test_no_markers():
    info = continuity.classify_lines([_line("just body text", 60, 500, 400, 520)], (600, 1000))
    assert info["seq_in_doc"] is None and not info["markers"]


def test_cmd_continuity_caches_and_attaches_to_pages(monkeypatch):
    from docmodel.core import Document, DocObject
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import MODEL_BUILT, CONTINUITY_BUILT

    # Fake the render+OCR: page 1 carries "Seite 1 von 2", page 2 "Seite 2 von 2".
    def fake_extract(pdf, out_dir, ppi=250, lang="deu+eng"):
        return {1: {"seq_in_doc": 1, "doc_total": 2, "is_continuation": True,
                    "next_seite": 2, "control_no": "X-9", "markers":
                    [{"text": "Seite 1 von 2", "kind": "seite_von", "where": "top"}]},
                2: {"seq_in_doc": 2, "doc_total": 2, "is_continuation": False,
                    "next_seite": None, "control_no": None, "markers":
                    [{"text": "Seite 2 von 2", "kind": "seite_von", "where": "top"}]}}
    monkeypatch.setattr(continuity, "extract_continuity", fake_extract)
    monkeypatch.setattr(continuity, "tools_available", lambda: (True, ""))

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "bundle.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        doc = Document()
        doc.add(DocObject(type="Page", props={"page_number": 1}))
        doc.add(DocObject(type="Page", props={"page_number": 2}))
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()

        out = commands.cmd_continuity(pdf)
        assert "2/2 page(s) carry a 'Seite N'" in out
        assert "Seite 1 von 2" in out and "Fortsetzung Seite 2" in out
        # Persisted in sidecar + attached to Page objects.
        sc2 = Sidecar(pdf)
        assert sc2.has(CONTINUITY_BUILT) and sc2.get_evidence("continuity")
        model = json.loads((sc.blob_dir / "model.docmodel.json").read_text())
        objs = model["objects"] if isinstance(model["objects"], list) else list(model["objects"].values())
        p1 = next(o for o in objs if o["props"].get("page_number") == 1)
        assert p1["props"]["seq_in_doc"] == 1 and p1["props"]["doc_total"] == 2
        assert p1["props"]["is_continuation"] is True and p1["props"]["control_no"] == "X-9"


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    plain = [test_margin_position, test_classify_seite_von_and_fortsetzung_and_control,
             test_classify_bare_seite, test_no_markers]
    for fn in plain:
        fn(); print(f"PASS {fn.__name__}")
    mp = _MP()
    try:
        test_cmd_continuity_caches_and_attaches_to_pages(mp); print("PASS test_cmd_continuity...")
    finally:
        mp.undo()
    print("\nAll tests passed.")
