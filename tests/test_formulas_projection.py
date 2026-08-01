"""
`pdfdrill formulas` — the math projection for an external de-macro / SRE pipeline.

Delivers, per Formula/Equation in flow order: the object id, the
`{{<bibkey>_FOnnnn||FO}}` transclusion placeholder, the macro-EXPANDED latex,
the author's `latex_original`, the control sequences present, and which of them
are macros THIS document defined that expansion failed to resolve.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import math_titles, TiddlyWikiProjector


def _doc():
    d = Document()
    d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={"latex": "a", "flow_index": 3}))
    d.add(DocObject(type="Equation", props={"latex": "E=mc^2", "flow_index": 5}))
    d.add(DocObject(type="Formula", props={"latex": "b", "flow_index": 1}))
    return d


def test_math_titles_numbers_per_type_in_flow_order():
    d = _doc()
    t = math_titles(d, "K")
    byflow = {o.props["flow_index"]: t[o.id] for o in d.objects.values()}
    assert byflow[1] == "K_FO0001"      # earliest formula
    assert byflow[3] == "K_FO0002"
    assert byflow[5] == "K_EQ0001"      # equations counted separately


def test_math_titles_agrees_with_the_tiddlywiki_projector():
    """THE correctness property: a placeholder handed to an external tool must
    name the tiddler the projector actually emits. A second numbering
    implementation would silently reference the wrong formula."""
    d = _doc()
    tiddlers = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(d))
    emitted = {t["title"] for t in tiddlers}
    for title in math_titles(d, "K").values():
        assert title in emitted, f"{title} is not a real tiddler title"


def test_missing_flow_index_sorts_last_like_the_projector():
    """The projector defaults a missing flow_index to 10**9 (sorts LAST).
    Defaulting to 0 would put it first and shift every later number."""
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={"latex": "x"}))            # no flow_index
    d.add(DocObject(type="Formula", props={"latex": "y", "flow_index": 2}))
    t = math_titles(d, "K")
    withflow = [o for o in d.objects.values() if "flow_index" in o.props][0]
    assert t[withflow.id] == "K_FO0001", "the flowed object must come first"


def test_projection_shape_and_expansion_visibility(tmp_path, monkeypatch):
    from pdfdrill import commands as C
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={
        "latex": "w \\in \\mathbb{R}", "latex_original": "w \\in \\reals",
        "flow_index": 1}))
    d.add(DocObject(type="Equation", props={
        "latex": "\\res(a)=b", "flow_index": 2, "refnum": "(1)"}))
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(C, "load_model", lambda p: d)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: tmp_path / "m.json")
    (tmp_path / "m.json").write_text("{}")
    monkeypatch.setattr(C, "resolve_bibkey", lambda *a, **k: "K")
    # this document DEFINES \res — so it must be reported as unresolved
    monkeypatch.setattr(C, "_document_macro_names", lambda doc, pdf=None: {"res"})

    outp = tmp_path / "proj.json"
    C.cmd_formulas(pdf, out=str(outp))
    p = json.loads(outp.read_text())

    assert p["counts"]["total"] == 2 and p["macro_table"] == "document-source"
    u0, u1 = p["units"]
    assert u0["placeholder"] == "{{K_FO0001||FO}}"
    assert u1["placeholder"] == "{{K_EQ0001||EQ}}"
    # macro expansion is VISIBLE (the whole point of latex_original)
    assert u0["latex"] == "w \\in \\mathbb{R}"
    assert u0["latex_original"] == "w \\in \\reals"
    # a document-defined macro that survived expansion is flagged
    assert u1["macros_unresolved"] == ["\\res"]
    assert "\\res" in u1["commands"]
    # spoken is the reserved SRE slot, present and null on every unit
    assert all("spoken" in u and u["spoken"] is None for u in p["units"])


def test_identical_original_is_omitted_not_echoed(tmp_path, monkeypatch):
    from pdfdrill import commands as C
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={"latex": "x", "latex_original": "x",
                                           "flow_index": 1}))
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(C, "load_model", lambda p: d)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: tmp_path / "m.json")
    (tmp_path / "m.json").write_text("{}")
    monkeypatch.setattr(C, "resolve_bibkey", lambda *a, **k: "K")
    monkeypatch.setattr(C, "_document_macro_names", lambda doc, pdf=None: None)
    outp = tmp_path / "p.json"
    C.cmd_formulas(pdf, out=str(outp))
    p = json.loads(outp.read_text())
    assert p["units"][0]["latex_original"] is None


def test_unavailable_macro_table_says_so_explicitly(tmp_path, monkeypatch):
    """An empty `macros_unresolved` must never be readable as 'nothing
    unresolved' when the table could not be determined at all."""
    from pdfdrill import commands as C
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={"latex": "\\res(a)", "flow_index": 1}))
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(C, "load_model", lambda p: d)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: tmp_path / "m.json")
    (tmp_path / "m.json").write_text("{}")
    monkeypatch.setattr(C, "resolve_bibkey", lambda *a, **k: "K")
    monkeypatch.setattr(C, "_document_macro_names", lambda doc, pdf=None: None)
    outp = tmp_path / "p.json"
    C.cmd_formulas(pdf, out=str(outp))
    p = json.loads(outp.read_text())
    assert p["macro_table"] == "unavailable"
    assert "NOT because everything resolved" in p["macro_table_note"]
    assert p["units"][0]["macros_unresolved"] == []
    assert p["units"][0]["commands"] == ["\\res"]      # still reported
