"""
Tests for the layout-element layer (pdfdrill.layout_elements + the vendored
pdfdrill.tsv_gcn GNN). Three concerns, all without rendering a real PDF:

  1. the combined-TSV page-number patch (pure string surgery);
  2. graceful degradation when there is no model AND no extract_addresses;
  3. the model path end-to-end: a tiny model trained on synthetic pages emits
     content-addressed address + BOM-line tiddlers (projection embeddings).

OCR (pdftoppm/tesseract) is stubbed out — we feed tsv_gcn its TSV directly.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import importlib.util

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None

from pdfdrill import layout_elements as le


def test_patch_page_column_renumbers_and_drops_header():
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
           "width\theight\tconf\ttext\n"
           "1\t1\t0\t0\t0\t0\t0\t0\t2480\t3508\t-1\t\n"
           "5\t1\t1\t1\t1\t1\t300\t600\t120\t40\t92\tHello\n")
    rows = le._patch_page_column(tsv, 7)
    assert len(rows) == 2                      # header dropped, 2 data rows kept
    assert all(r.split("\t")[1] == "7" for r in rows)   # page_num -> 7
    assert rows[0].split("\t")[0] == "1" and rows[1].split("\t")[11] == "Hello"


def test_find_elements_graceful_without_model_or_heuristic(monkeypatch):
    """No --model and no extract_addresses → available False, actionable msg."""
    if not HAVE_NUMPY:
        print("SKIP (numpy absent)"); return
    monkeypatch.setattr(le, "tools_available", lambda: (True, ""))
    monkeypatch.setattr(le, "build_combined_tsv",
                        lambda *a, **k: "level\tpage_num\n")
    from pdfdrill import tsv_gcn
    monkeypatch.setattr(tsv_gcn, "_HAVE_EA", False)
    with tempfile.TemporaryDirectory() as d:
        res = le.find_elements(Path("x.pdf"), model_path=None, bibkey="bk",
                               source="x.pdf", blob_dir=Path(d), force=True)
    assert res["available"] is False
    assert "no element source" in res["message"]
    assert res["tiddlers"] == []


def _train_tiny_model(tmp: Path):
    """Train a small GNN on synthetic pages; return (model_path, one_tsv_text)."""
    import numpy as np
    from pdfdrill import tsv_gcn
    rng = np.random.default_rng(1)
    files = []
    for k in range(8):
        tsv, labels = tsv_gcn.synth_page(rng)
        stem = f"page{k:03d}"
        (tmp / f"{stem}.tsv").write_text(tsv, encoding="utf-8")
        (tmp / f"{stem}.labels.json").write_text(
            json.dumps({"source": f"{stem}.tsv", "labels": labels}), encoding="utf-8")
        files.append(str(tmp / f"{stem}.tsv"))
    dataset, schema = tsv_gcn.load_dataset(files, tmp)
    model, cw = tsv_gcn.train(dataset, schema, epochs=60, d_h=16, lr=0.02,
                              seed=1, verbose=False)
    model_path = tmp / "model.npz"
    tsv_gcn.save_model(str(model_path), model, schema, cw, 16)
    return model_path, Path(files[0]).read_text(encoding="utf-8")


def test_find_elements_emits_content_addressed_tiddlers(monkeypatch):
    """With a trained model, find_elements emits address + BOM-line tiddlers
    carrying a content hash, geo-projection, and a GNN projection embedding."""
    if not HAVE_NUMPY:
        print("SKIP (numpy absent)"); return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        model_path, one_tsv = _train_tiny_model(tmp)
        monkeypatch.setattr(le, "tools_available", lambda: (True, ""))
        monkeypatch.setattr(le, "build_combined_tsv", lambda *a, **k: one_tsv)
        res = le.find_elements(Path("invoice.pdf"), model_path=model_path,
                               bibkey="demo2024", source="invoice.pdf",
                               blob_dir=tmp / "blob", force=True)
    assert res["available"] is True
    tids = res["tiddlers"]
    assert tids, "expected at least one layout element from a synthetic invoice"
    kinds = {t["kind"] for t in tids}
    assert "bom-line" in kinds                       # the synthetic table
    for t in tids:
        assert t["title"].startswith("demo2024_")
        assert t["hash"].startswith(("blake3:", "sha256:"))
        assert "layoutElement" in t["tags"]
        assert t.get("geo-projection")               # normalised bbox always set
    # BOM lines carry the learned projection embedding.
    bom = [t for t in tids if t["kind"] == "bom-line"][0]
    assert bom.get("projection") and int(bom["projection-dim"]) > 0
    # Content-addressing is deterministic: same components → same hash.
    from pdfdrill import tsv_gcn
    h1 = tsv_gcn.content_hash("address|s|postcode=50667")
    h2 = tsv_gcn.content_hash("address|s|postcode=50667")
    assert h1 == h2


def test_extract_addresses_heuristic_is_vendored_and_pure():
    """The vendored extract_addresses gives tsv_gcn its no-model address path
    (DEFAULT_POSTCODE + read_tsv + find_candidates) with NO libpostal."""
    from pdfdrill import tsv_gcn
    assert tsv_gcn._HAVE_EA is True               # heuristic enabled
    from pdfdrill import extract_addresses as ea
    import re
    tsv = ("level\tpage_num\tblock\tpar\tline\tword\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t300\t600\t200\t40\t96\tHauptstraße\n"
           "5\t1\t1\t1\t1\t2\t520\t600\t60\t40\t96\t42a\n"
           "5\t1\t1\t1\t2\t1\t300\t660\t120\t40\t95\t50667\n"
           "5\t1\t1\t1\t2\t2\t440\t660\t90\t40\t95\tKöln\n")
    segs = ea.read_tsv(tsv)
    cands = ea.find_candidates(segs, re.compile(ea.DEFAULT_POSTCODE), 3, 50)
    assert cands and any("50667" in c.text and c.bbox for c in cands)


def test_find_elements_heuristic_only_without_model(monkeypatch):
    """With extract_addresses vendored (_HAVE_EA=True) and NO model, find_elements
    still recovers an address (provenance heuristic-only), no GNN, no libpostal."""
    if not HAVE_NUMPY:
        print("SKIP (numpy absent)"); return
    import numpy as np
    from pdfdrill import tsv_gcn
    if not tsv_gcn._HAVE_EA:
        print("SKIP (extract_addresses not importable)"); return
    rng = np.random.default_rng(3)
    one_tsv, _labels = tsv_gcn.synth_page(rng)     # has an address block w/ PLZ
    monkeypatch.setattr(le, "tools_available", lambda: (True, ""))
    monkeypatch.setattr(le, "build_combined_tsv", lambda *a, **k: one_tsv)
    with tempfile.TemporaryDirectory() as d:
        res = le.find_elements(Path("x.pdf"), model_path=None, bibkey="bk",
                               source="x.pdf", blob_dir=Path(d), force=True)
    assert res["available"] is True
    assert any(t["kind"] == "address" for t in res["tiddlers"])
    assert any(e.get("source") == "heuristic-only" for e in res["elements"])
    # No model → no learned projection embedding on any tiddler.
    assert all(not t.get("projection") for t in res["tiddlers"])


def test_libpostal_enrichment_absent_is_noop():
    """When libpostal is unavailable, enrichment is a clean no-op (0)."""
    monkeypatched = le._libpostal_parser()
    # The real environment has no libpostal; enrichment must not raise / change.
    addrs = [{"kind": "address", "components": {}, "text": "Hauptstraße 42a, 50667 Köln"}]
    n = le._enrich_with_libpostal(addrs)
    if monkeypatched is None:
        assert n == 0 and addrs[0]["components"] == {}
    else:
        assert n >= 0  # libpostal present in this env — just don't crash


def test_libpostal_enrichment_fills_components(monkeypatch):
    """With a (fake) libpostal parser, a heuristic address block is parsed into
    road/house_number/postcode/city components, tagged parsed_by=libpostal."""
    def fake_parse_address(text):
        return [("hauptstraße", "road"), ("42a", "house_number"),
                ("50667", "postcode"), ("köln", "city")]
    monkeypatch.setattr(le, "_libpostal_parser", lambda: fake_parse_address)
    addrs = [{"kind": "address", "source": "heuristic-only", "components": {},
              "text": "Hauptstraße 42a, 50667 Köln", "bbox": [1, 2, 3, 4]},
             {"kind": "address", "source": "gnn-only",      # already has comps:
              "components": {"road": "Keep"}, "text": "x"}]
    n = le._enrich_with_libpostal(addrs)
    assert n == 1                                            # only the empty one
    assert addrs[0]["components"] == {"road": "hauptstraße", "house_number": "42a",
                                      "postcode": "50667", "city": "köln"}
    assert addrs[0]["parsed_by"] == "libpostal"
    assert addrs[1]["components"] == {"road": "Keep"}        # GNN labels untouched


if __name__ == "__main__":
    # A restoring monkeypatch shim so standalone runs don't leak patches between
    # tests (pytest's real fixture restores automatically).
    class _MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, old in reversed(self._undo): setattr(obj, name, old)
            self._undo = []

    def run(fn, label, mp=None):
        own = mp or _MP()
        try:
            fn(own) if fn.__code__.co_argcount else fn()
        finally:
            own.undo()
        print(f"PASS {label}")

    run(test_patch_page_column_renumbers_and_drops_header, "patch_page_column")
    run(test_extract_addresses_heuristic_is_vendored_and_pure, "heuristic_vendored")
    run(test_libpostal_enrichment_absent_is_noop, "libpostal_absent")
    run(test_libpostal_enrichment_fills_components, "libpostal_fill")
    run(test_find_elements_heuristic_only_without_model, "heuristic_only")
    run(test_find_elements_emits_content_addressed_tiddlers, "emit")
    run(test_find_elements_graceful_without_model_or_heuristic, "graceful")
    print("\nAll tests passed.")
