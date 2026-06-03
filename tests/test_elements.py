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


if __name__ == "__main__":
    test_patch_page_column_renumbers_and_drops_header(); print("PASS patch_page_column")
    # monkeypatch shim for standalone runs (no pytest):
    class _MP:
        def setattr(self, obj, name, val): setattr(obj, name, val)
    test_find_elements_graceful_without_model_or_heuristic(_MP()); print("PASS graceful")
    test_find_elements_emits_content_addressed_tiddlers(_MP()); print("PASS emit")
    print("\nAll tests passed.")
