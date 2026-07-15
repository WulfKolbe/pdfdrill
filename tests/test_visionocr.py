"""
Keyless agent-delegated equation OCR (`pdfdrill visionocr`) + the math-bearing
gate in `cmd_model`.

The bug: on a math PDF with no MathPix key, `model` falls back to tesseract,
which cannot type equations, and silently reports a 0-equation model as success.
The fix: detect math-bearing, refuse to present a 0-equation model as complete
(set NEEDS_VISION_OCR + instruct), and add a keyless route that delegates each
rendered page to the running Claude agent for LaTeX, folded back into the
lines.json as real Equation nodes (number paired by page+y geometry).
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import openai_vision, llm_delegate, pdf_reading, commands, mathqc
from pdfdrill.commands import cmd_model, cmd_visionocr, NEEDS_VISION_OCR
from pdfdrill.sidecar import Sidecar


def _tesseract_lines(pages):
    """Minimal tesseract-shape lines.json dict."""
    return {"source": "tesseract", "pages": pages}


def _page(n, lines, w=1000.0, h=1400.0):
    return {"page": n, "image_id": None, "page_width": w, "page_height": h,
            "lines": lines}


def _text_line(lid, text, y):
    return {"id": lid, "type": "text", "text": text, "text_display": text,
            "region": {"top_left_x": 100.0, "top_left_y": y, "width": 600.0,
                       "height": 20.0}}


# --- the prompt + the parser ------------------------------------------------

def test_eq_ocr_prompt_demands_latex_and_json_array():
    p = openai_vision.EQ_OCR_PROMPT
    assert "JSON" in p and ("array" in p.lower() or "[" in p)
    assert '"latex"' in p and '"number"' in p and '"kind"' in p
    # forbids linearising (the reported failure) + forbids fabrication
    assert "_" in p and "^" in p              # tells it to keep sub/superscripts
    assert "[]" in p                          # empty page => empty array
    assert "invent" in p.lower() or "guess" in p.lower() or "fabricate" in p.lower()


def test_parse_eq_ocr_array_and_fence():
    r = llm_delegate._parse_eq_ocr('[{"page":1,"number":"B65","latex":"m_a","kind":"equation"}]')
    assert r["records"][0]["number"] == "B65" and r["records"][0]["latex"] == "m_a"
    fenced = llm_delegate._parse_eq_ocr('```json\n[{"latex":"x^2","kind":"math"}]\n```')
    assert fenced["records"][0]["latex"] == "x^2"
    assert llm_delegate._parse_eq_ocr("[]")["records"] == []          # empty page
    assert llm_delegate._parse_eq_ocr("nonsense")["records"] == []    # junk -> no records


# --- the fold: records -> lines.json -> Equation nodes ----------------------

def _read_equations(model_path):
    doc = json.loads(model_path.read_text(encoding="utf-8"))
    return [o for o in doc["objects"] if o["type"] == "Equation"]


def test_ingest_folds_records_into_equation_nodes_with_refnum():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "heim.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        sc.add_fact(NEEDS_VISION_OCR); sc.save()
        lines_path = commands._lines_json_path(pdf)
        lines_path.write_text(json.dumps(_tesseract_lines([
            _page(1, [_text_line("l0", "Setzt man gemäß (B3)", 200.0)]),
        ])), encoding="utf-8")

        fixture = Path(d) / "eqs.json"
        fixture.write_text(json.dumps([
            {"page": 1, "number": "B65", "latex": "M = m_a (F + j_0)", "kind": "equation"},
            {"page": 1, "number": "B1", "latex": "x^{2} + 1", "kind": "equation"},
        ]))

        out = cmd_visionocr(pdf, ingest=str(fixture))
        sc = Sidecar(pdf)
        assert not sc.has(NEEDS_VISION_OCR)        # cleared
        assert "2" in out                          # reports 2 equations folded
        eqs = _read_equations(commands._model_path(sc))
        assert len(eqs) == 2
        refnums = {e["props"].get("refnum") for e in eqs}
        assert refnums == {"B65", "B1"}            # numbers paired by geometry
        # the tesseract prose line is preserved (still a Paragraph somewhere)
        doc = json.loads(commands._model_path(sc).read_text(encoding="utf-8"))
        assert any(o["type"] == "Paragraph" for o in doc["objects"])


# --- the gate in cmd_model --------------------------------------------------

def test_model_gate_sets_needs_vision_on_math_doc(monkeypatch):
    monkeypatch.setenv("PDFDRILL_DELEGATE", "sandbox")
    monkeypatch.setattr(mathqc, "is_math_bearing",
                        lambda pdf, sc: (True, "math fonts: cmsy, cmex"))
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "math.pdf"; pdf.write_bytes(b"%PDF-1.4")
        lines_path = commands._lines_json_path(pdf)
        lines_path.write_text(json.dumps(_tesseract_lines([
            _page(1, [_text_line("l0", "Some prose with no typed math.", 200.0),
                      _text_line("l1", "More prose here.", 240.0)]),
        ])), encoding="utf-8")
        out = cmd_model(pdf)
        sc = Sidecar(pdf)
        assert sc.has(NEEDS_VISION_OCR)
        assert "visionocr" in out and "0 Equation" in out


def _equation_line(lid, text, y):
    """An ENRICHED-tesseract equation line: correct region, GARBLED text (tesseract
    cannot read math) — no LaTeX anywhere."""
    return {"id": lid, "type": "equation", "text": text, "text_display": text,
            "region": {"top_left_x": 100.0, "top_left_y": y, "width": 600.0,
                       "height": 24.0}}


def test_model_gate_fires_when_equations_are_ocr_garble(monkeypatch):
    """REGRESSION guard for the enriched OCR module. The old gate keyed on
    "0 Equations ⇒ math missing". The enriched tesseract path DOES emit equation
    lines — right region, GARBLED text, never LaTeX — so those garbled equations
    silently satisfied the gate and a math doc was presented as COMPLETE. The gate
    must key on missing real LaTeX: a keyless text-only source cannot produce
    LaTeX; only a gold-source overlay (added_by="latex") or MathPix can."""
    monkeypatch.setenv("PDFDRILL_DELEGATE", "sandbox")
    monkeypatch.setattr(mathqc, "is_math_bearing",
                        lambda pdf, sc: (True, "math fonts: cmsy, cmex"))
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "math_garble.pdf"; pdf.write_bytes(b"%PDF-1.4")
        commands._lines_json_path(pdf).write_text(json.dumps(_tesseract_lines([
            _page(1, [_equation_line("e0", "Ih=glly <7 =3k EUR = < | =] (4)", 300.0),
                      _text_line("l0", "Some prose.", 200.0)]),
        ])), encoding="utf-8")
        out = cmd_model(pdf)
        sc = Sidecar(pdf)
        # equation OBJECTS exist, but they carry no usable math → still a failure
        assert sc.has(NEEDS_VISION_OCR), (
            "garbled OCR equations must NOT satisfy the math gate")
        assert "visionocr" in out


def test_model_gate_warns_when_no_agent(monkeypatch):
    monkeypatch.setenv("PDFDRILL_DELEGATE", "none")
    monkeypatch.setattr(mathqc, "is_math_bearing",
                        lambda pdf, sc: (True, "display math in md layer"))
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "math2.pdf"; pdf.write_bytes(b"%PDF-1.4")
        lines_path = commands._lines_json_path(pdf)
        lines_path.write_text(json.dumps(_tesseract_lines([
            _page(1, [_text_line("l0", "Prose only.", 200.0)]),
        ])), encoding="utf-8")
        out = cmd_model(pdf)
        sc = Sidecar(pdf)
        assert sc.has(NEEDS_VISION_OCR)
        assert "WARNING" in out and "not captured" in out.lower()


def test_model_no_gate_on_nonmath(monkeypatch):
    monkeypatch.setenv("PDFDRILL_DELEGATE", "sandbox")
    monkeypatch.setattr(mathqc, "is_math_bearing", lambda pdf, sc: (False, ""))
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "plain.pdf"; pdf.write_bytes(b"%PDF-1.4")
        lines_path = commands._lines_json_path(pdf)
        lines_path.write_text(json.dumps(_tesseract_lines([
            _page(1, [_text_line("l0", "Just prose.", 200.0)]),
        ])), encoding="utf-8")
        out = cmd_model(pdf)
        sc = Sidecar(pdf)
        assert not sc.has(NEEDS_VISION_OCR)
        assert "Built unified model" in out


# --- the deferred sandbox handshake -----------------------------------------

def test_visionocr_sandbox_roundtrip(monkeypatch):
    monkeypatch.setattr(llm_delegate, "detect_runtime",
                        lambda: llm_delegate.Runtime.SANDBOX)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        commands._lines_json_path(pdf).write_text(json.dumps(_tesseract_lines([
            _page(1, [_text_line("l0", "p1 prose", 200.0)]),
            _page(2, [_text_line("l0", "p2 prose", 200.0)]),
        ])), encoding="utf-8")

        def fake_raster(_pdf, out_dir, **kw):
            out_dir.mkdir(parents=True, exist_ok=True)
            ps = []
            for n in (1, 2):
                p = out_dir / f"page-{n}.png"; p.write_bytes(b"\x89PNG" + str(n).encode())
                ps.append(p)
            return ps
        monkeypatch.setattr(pdf_reading, "rasterize", fake_raster)

        # pass 1: defer one eq_ocr request per page; it shows in `llm --show`
        out1 = cmd_visionocr(pdf)
        assert "deferred" in out1.lower() and "PDFDRILL-LLM-DELEGATION" in out1
        pend = json.loads(commands.cmd_llm(pdf, "show"))
        assert len(pend) == 2 and {p["kind"] for p in pend} == {"eq_ocr"}

        # the agent answers: page 1 has one numbered eq, page 2 has none
        llm = sc.blob_dir / "llm"
        for r in sorted(llm.glob("*.req.json")):
            req = json.loads(r.read_text()); tid = req["task_id"]
            p1 = req["image_path"].endswith("page-1.png")
            result = ('[{"page":1,"number":"7","latex":"E = m c^{2}","kind":"equation"}]'
                      if p1 else "[]")
            (llm / (tid + ".resp.json")).write_text(json.dumps(
                {"task_id": tid, "kind": "eq_ocr", "result": result}))

        # pass 2: ingest -> 1 Equation node, NEEDS_VISION_OCR cleared
        out2 = cmd_visionocr(pdf)
        eqs = _read_equations(commands._model_path(sc))
        assert len(eqs) == 1 and eqs[0]["props"].get("refnum") == "7"
        assert "1" in out2 and not Sidecar(pdf).has(NEEDS_VISION_OCR)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
