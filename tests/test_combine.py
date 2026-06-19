"""
`pdfdrill combine` — merge several drilled docs into one combined store for
multi-document chat. `retrieve` over the store pools units from all docs and
cites each as `<bibkey>:<id>` so an answer is traceable to the right paper.
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.main import run, DEFAULT_CONFIG_PATH
from pdfdrill.commands import cmd_combine, cmd_retrieve, _load_combined_store
from pdfdrill.sidecar import Sidecar


def _build(d: Path, name: str, sentence: str) -> Path:
    pdf = d / f"{name}.pdf"; pdf.write_bytes(b"%PDF-1.4")
    lj = {"source": "mathpix", "pages": [{"page": 1, "lines": [
        {"id": "p", "type": "text", "text": sentence}]}]}
    ljp = d / f"{name}.lines.json"; ljp.write_text(json.dumps(lj))
    sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
    run(lines_path=str(ljp), config_path=DEFAULT_CONFIG_PATH, bibkey=name,
        out_path=str(sc.blob_dir / "model.docmodel.json"), debug_modules=[])
    return pdf


def test_combine_and_multidoc_retrieve():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p1 = _build(d, "alpha2021", "The variational autoencoder optimizes a bound.")
        p2 = _build(d, "beta2022", "Diffusion maps reveal the manifold geometry.")
        out = d / "merged.docpack"
        msg = cmd_combine(out, [p1, p2], force=True)
        assert "Combined 2 document(s)" in msg and out.exists()

        # the store carries both docs' units, ids namespaced by bibkey
        nodes, meta = _load_combined_store(out)
        ids = {n.id for n in nodes}
        assert any(i.startswith("alpha2021:") for i in ids)
        assert any(i.startswith("beta2022:") for i in ids)
        assert meta["num_docs"] == 2

        # retrieval reaches into the RIGHT document and cites bibkey:id
        r1 = json.loads(cmd_retrieve(out, "variational autoencoder", k=3, as_json=True))
        assert r1["units"] and r1["units"][0]["id"].startswith("alpha2021:")
        r2 = json.loads(cmd_retrieve(out, "diffusion manifold", k=3, as_json=True))
        assert r2["units"] and r2["units"][0]["id"].startswith("beta2022:")


def test_combine_warns_on_unbuilt_input():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p1 = _build(d, "got2021", "Built model here.")
        nope = d / "missing.pdf"; nope.write_bytes(b"%PDF-1.4")   # no model
        out = d / "m.docpack"
        msg = cmd_combine(out, [p1, nope], force=True)
        assert "Combined 1 document(s)" in msg and "Skipped" in msg and "missing.pdf" in msg


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
