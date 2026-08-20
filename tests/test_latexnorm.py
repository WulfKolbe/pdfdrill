"""020/021/022 — a backslash severed from its command name.

'\<newline>mathrm{e}' is a backslash that lost its command name: LaTeX reads
the gap as a control space and typesets the literal letters "mathrme". The
corpus scan (020) found ZERO such values in 87,332 raw MathPix text values
and 35,079 projected latex values — the pattern the user saw came from
copying text out of report.pdf, not from the data. These pin the detector,
the normaliser and the ingest validator so the case stays covered anyway.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.mathqc import join_severed_backslashes, severed_backslashes

SEVERED = "\\mathcal{D} g \\\nmathrm{e}^{i S},"


def test_detector_flags_severed_and_spares_real_row_breaks():
    assert severed_backslashes(SEVERED) == 1
    assert severed_backslashes(SEVERED, newline_only=True) == 1
    assert severed_backslashes(r"a \\ text") == 0        # row break
    assert severed_backslashes(r"a \\\\ text") == 0      # double row break
    assert severed_backslashes(r"a \ x") == 1            # control space + letter
    assert severed_backslashes(r"a \ x", newline_only=True) == 0
    assert severed_backslashes(r"\mathrm{e}") == 0       # already joined


def test_normaliser_joins_only_the_severing_gap():
    out, n = join_severed_backslashes(SEVERED)
    assert n == 1 and out == "\\mathcal{D} g \\mathrm{e}^{i S},"
    # every other whitespace survives untouched
    keep = "x = 1 \n  y = 2 \\\\ z"
    assert join_severed_backslashes(keep) == (keep, 0)


def test_cmd_latexnorm_stamps_and_preserves_the_original():
    from docmodel.core import Document, DocObject
    from pdfdrill.model_io import save_model, load_model
    from pdfdrill.commands import cmd_latexnorm, _model_path
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        lj = Path(d) / "doc.lines.json"
        lj.write_text('{"pages": []}')
        past = lj.stat().st_mtime - 100
        os.utime(lj, (past, past))
        doc = Document()
        doc.add(DocObject(type="Equation", props={"latex": SEVERED}))
        doc.add(DocObject(type="Equation", props={"latex": r"a \\ b"}))
        sc = Sidecar(pdf)
        mp = _model_path(sc)
        mp.parent.mkdir(parents=True, exist_ok=True)
        save_model(mp, doc)
        sc.add_fact("MODEL_BUILT")
        sc.save()

        out = cmd_latexnorm(pdf)
        assert "1 value(s) changed" in out
        objs = list(load_model(mp).objects.values())
        fixed = [o for o in objs if "latex_presevered" in o.props][0]
        assert fixed.props["latex"] == "\\mathcal{D} g \\mathrm{e}^{i S},"
        assert fixed.props["latex_presevered"] == SEVERED      # original kept
        assert fixed.props["edit_source"]["run"] >= 1          # P9 stamp
        untouched = [o for o in objs if "latex_presevered" not in o.props][0]
        assert untouched.props["latex"] == r"a \\ b"           # row break safe

        assert "0 value(s) changed" in cmd_latexnorm(pdf)      # idempotent


def test_ingest_rejects_severed_backslashes_and_counts_them():
    """022: the ingest path takes untrusted LLM/vision LaTeX, so a value whose
    backslash lost its command name is REJECTED with its identifier named —
    never stored. Real row breaks (\\\\) are ingested untouched."""
    from docmodel.core import Document, DocObject
    from pdfdrill.model_io import save_model, load_model
    from pdfdrill.commands import cmd_ingest, _model_path
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        doc = Document()
        good = DocObject(type="Equation", props={"latex": "a=b"})
        bad = DocObject(type="Equation", props={"latex": "c=d"})
        doc.add(good)
        doc.add(bad)
        sc = Sidecar(pdf)
        mp = _model_path(sc)
        mp.parent.mkdir(parents=True, exist_ok=True)
        save_model(mp, doc)

        cand = Path(d) / "cand.json"
        cand.write_text(json.dumps({"provider": "llm", "equations": [
            {"eq_id": good.id, "latex": r"x = y \\ z"},   # row break: fine
            {"eq_id": bad.id, "latex": SEVERED},           # severed: rejected
        ]}))
        out = cmd_ingest(pdf, str(cand), provider="llm")
        assert "Ingested 1" in out and "REJECTED 1" in out
        assert bad.id in out                       # the identifier is named
        objs = load_model(mp).objects
        assert objs[good.id].realizations           # good one stored
        assert not objs[bad.id].realizations        # bad one never stored
        assert Sidecar(pdf).get_evidence("ingest_llm_rejected") == 1
