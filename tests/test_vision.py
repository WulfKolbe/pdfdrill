"""
Tests for the OpenAI GPT-4o vision path (pdfdrill.openai_vision + cmd_vision).

No real API call: `openai_vision.analyze_image` is monkeypatched with a fake,
and `available` is forced. Covers crop collection (incl. CDN links embedded in
a table cell with LaTeX-escaped `\\&`), the selector→latex mapping, cmd_vision
wiring/persistence, and the graceful no-key path.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.sidecar import Sidecar
from pdfdrill import openai_vision
from pdfdrill import commands
from pdfdrill import llm_delegate, net
from pdfdrill.commands import (
    cmd_vision, MODEL_BUILT, VISION_DONE, _collect_cdn_crops, _norm_crop_url,
)


_CDN = "https://cdn.mathpix.com/cropped/abc-20.jpg?height=821&width=1754&top_left_y=1564&top_left_x=255"


def test_result_to_latex_mapping():
    assert openai_vision.result_to_latex({"selector": "math", "math": "$$E=mc^2$$"}) == ("math", "E=mc^2")
    assert openai_vision.result_to_latex(
        {"selector": "tikzpicture", "tikzpicture": "\\begin{tikzpicture}\\end{tikzpicture}"}
    ) == ("tikzpicture", "\\begin{tikzpicture}\\end{tikzpicture}")
    assert openai_vision.result_to_latex({"selector": "table", "table": "\\begin{tabular}{ll}a&b\\end{tabular}"})[0] == "table"
    assert openai_vision.result_to_latex({"selector": "empty"}) == ("empty", "")
    # Office-doc selectors: text/handwriting -> text field; picture-likes -> description.
    assert openai_vision.result_to_latex({"selector": "text", "text": "Datum: 30.04.2018"}) == ("text", "Datum: 30.04.2018")
    assert openai_vision.result_to_latex({"selector": "handwriting", "text": "Grimm"}) == ("handwriting", "Grimm")
    assert openai_vision.result_to_latex({"selector": "chart", "description": "decreasing curve"}) == ("chart", "decreasing curve")
    assert openai_vision.result_to_latex({"selector": "logo", "description": "Deutsche Post posthorn"})[0] == "logo"


def test_result_to_latex_chemistry_normalization():
    # chemical_equation: bare formula gets wrapped in \ce{}, $-delimiters and
    # markdown fences stripped, existing \ce kept untouched.
    assert openai_vision.result_to_latex(
        {"selector": "chemical_equation", "mhchem": "2H2 + O2 -> 2H2O"}
    ) == ("chemical_equation", "\\ce{2H2 + O2 -> 2H2O}")
    assert openai_vision.result_to_latex(
        {"selector": "chemical_equation", "mhchem": "$\\ce{SO4^2-}$"}
    ) == ("chemical_equation", "\\ce{SO4^2-}")
    assert openai_vision.result_to_latex(
        {"selector": "chemical_equation", "mhchem": "```latex\n\\ce{CO2}\n```"}
    ) == ("chemical_equation", "\\ce{CO2}")
    # \textDelta (textgreek, NOT in the SVG preamble) is a common GPT output
    # for the heat symbol over a reaction arrow -> normalize to math-mode \Delta.
    assert openai_vision.result_to_latex(
        {"selector": "chemical_equation", "mhchem": "\\ce{->[\\text{\\textDelta}]}"}
    ) == ("chemical_equation", "\\ce{->[$\\Delta$]}")
    # chemical_structure: bare bond spec gets wrapped in \chemfig{}; existing
    # \chemfig / \schemestart blocks pass through.
    assert openai_vision.result_to_latex(
        {"selector": "chemical_structure", "chemfig": "H_3C-CH_2-OH"}
    ) == ("chemical_structure", "\\chemfig{H_3C-CH_2-OH}")
    benzene = "\\chemfig{*6(-=-=-=)}"
    assert openai_vision.result_to_latex(
        {"selector": "chemical_structure", "chemfig": benzene}
    ) == ("chemical_structure", benzene)
    scheme = "\\schemestart \\chemfig{A} \\arrow{->[cat.]} \\chemfig{B} \\schemestop"
    assert openai_vision.result_to_latex(
        {"selector": "chemical_structure", "chemfig": scheme}
    )[1] == scheme
    # Both normalized forms must pass the SVG-route renderability guard.
    from pdfdrill import svg as svgmod
    for sel, payload in ((("chemical_structure", "chemfig"), "*6(-=-=-=)"),
                         (("chemical_equation", "mhchem"), "2H2 + O2 -> 2H2O")):
        _s, code = openai_vision.result_to_latex({"selector": sel[0], sel[1]: payload})
        assert svgmod.is_latex_graphic(code), code


def _doc():
    doc = Document()
    doc.add(DocObject(type="Equation", props={"cdn_url": _CDN, "latex": "x"}))
    doc.add(DocObject(type="Picture", props={"url": _CDN.replace("-20", "-07")}))
    # A table with a CDN link embedded in a cell, LaTeX-escaped `\&`.
    cell = "\\begin{tabular}{l}![](" + _CDN.replace("-20", "-27").replace("&", "\\&") + ")\\end{tabular}"
    doc.add(DocObject(type="Table", props={"raw_text": cell}))
    return doc


def test_collect_cdn_crops_finds_embedded_table_crop():
    crops = _collect_cdn_crops(_doc())
    urls = {u for _o, u in crops}
    assert any(u.endswith("-20.jpg?height=821&width=1754&top_left_y=1564&top_left_x=255") for u in urls)
    assert any("-07.jpg" in u for u in urls)
    # The table-embedded crop is recovered with `\&` un-escaped to `&`.
    assert any("-27.jpg" in u and "\\&" not in u and "&" in u for u in urls)
    assert len(crops) == 3


def test_norm_crop_url_cleans_and_validates():
    # LaTeX-escaped `\&` (as MathPix leaves it in table cells) -> unescaped.
    dirty = "https://cdn.mathpix.com/cropped/abc-07.jpg?height=53\\&width=613\\&top_left_y=1\\&top_left_x=2"
    clean = _norm_crop_url(dirty)
    assert clean == "https://cdn.mathpix.com/cropped/abc-07.jpg?height=53&width=613&top_left_y=1&top_left_x=2"
    # Trailing punctuation trimmed.
    assert _norm_crop_url(_CDN + ").") == _CDN
    # Garbage (a cnt-array fragment) and truncated links are rejected.
    assert _norm_crop_url("0,54,3,70,5,102,cdn.mathpix.com/cropped") is None
    assert _norm_crop_url("https://cdn.mathpix.com/cropped/abc-07.jpg?height=53") is None  # missing fields
    assert _norm_crop_url("") is None


class _FakeVision:
    """Stand-in for openai_vision.analyze_image — returns a math result."""
    @staticmethod
    def analyze_image(url, **kw):
        return {"selector": "math", "math": "$$a+b$$", "gnuplot": "", "csv_data": ""}


def _make_model(tmp: Path) -> Path:
    pdf = tmp / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(_doc().to_dict()), encoding="utf-8")
    sc.add_fact(MODEL_BUILT)
    sc.save()
    return pdf


def test_cmd_vision_attaches_openai_provenance(monkeypatch):
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    monkeypatch.setattr(commands.__dict__.get("openai_vision", openai_vision), "analyze_image",
                        _FakeVision.analyze_image, raising=False)
    # cmd_vision does `from . import openai_vision`, so patch the module itself.
    monkeypatch.setattr(openai_vision, "analyze_image", _FakeVision.analyze_image)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_vision(pdf)
        assert "read 3 CDN crop" in out and "math" in out
        model = json.loads((Path(d) / "doc.pdf.drill" / "model.docmodel.json").read_text())
        objs = model["objects"] if isinstance(model["objects"], list) else list(model["objects"].values())
        oai = [r for o in objs for r in o.get("realizations", [])
               if r.get("provenance") == "openai"]
        assert len(oai) == 3
        assert oai[0]["props"]["selector"] == "math"
        assert oai[0]["props"]["latex"] == "a+b"
        assert Sidecar(pdf).has(VISION_DONE)


def test_cmd_vision_limit(monkeypatch):
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    monkeypatch.setattr(openai_vision, "analyze_image", _FakeVision.analyze_image)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_vision(pdf, limit=1)
        assert "read 1 CDN crop" in out
        assert "not yet read" in out


def test_cmd_vision_uses_graph_prompt_for_subgraph_caption(monkeypatch):
    """A crop whose owning object's caption names a graph/subgraph gets the
    TikZ-reconstruction prompt, not the default."""
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    seen = {}

    def fake_analyze(url, **kw):
        seen[url] = kw.get("prompt", "")
        return {"selector": "tikzpicture", "tikzpicture": "\\begin{tikzpicture}\\end{tikzpicture}"}

    monkeypatch.setattr(openai_vision, "analyze_image", fake_analyze)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        doc = Document()
        g = _CDN.replace("-20", "-11")
        doc.add(DocObject(type="Diagram", props={
            "cdn_url": g, "caption": "The subgraph in red is complete bipartite."}))
        doc.add(DocObject(type="Picture", props={"url": _CDN, "caption": "a photo"}))
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()
        out = cmd_vision(pdf)
        assert "graph/subgraph image(s) reconstructed as TikZ" in out
        assert openai_vision.GRAPH_TIKZ_PROMPT in seen[g]            # graph -> graph prompt
        assert seen[_CDN] == openai_vision.DEFAULT_PROMPT            # non-graph -> default


def test_cmd_vision_chem_prompt_and_latex_code_adoption(monkeypatch):
    """A crop whose owning Diagram's caption names a molecule/reaction gets the
    chemfig-reconstruction prompt; the chemfig result is adopted into the
    Diagram's empty latex_code so `pdfdrill svg` renders it like TikZ."""
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    seen = {}
    benzene = "\\chemfig{*6(-=-=-=)}"

    def fake_analyze(url, **kw):
        seen[url] = kw.get("prompt", "")
        if openai_vision.CHEM_STRUCTURE_PROMPT in seen[url]:
            return {"selector": "chemical_structure", "chemfig": benzene,
                    "gnuplot": "", "csv_data": ""}
        return {"selector": "math", "math": "$$a$$", "gnuplot": "", "csv_data": ""}

    monkeypatch.setattr(openai_vision, "analyze_image", fake_analyze)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        doc = Document()
        c = _CDN.replace("-20", "-12")
        doc.add(DocObject(type="Diagram", props={
            "cdn_url": c, "latex_code": "",
            "caption": "Scheme 2: synthesis of the target compound."}))
        doc.add(DocObject(type="Equation", props={"cdn_url": _CDN, "latex": "x"}))
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()
        out = cmd_vision(pdf)
        assert "chemistry image(s) reconstructed as chemfig/mhchem" in out
        assert "adopted into latex_code" in out
        assert openai_vision.CHEM_STRUCTURE_PROMPT in seen[c]   # chem -> chem prompt
        assert seen[_CDN] == openai_vision.DEFAULT_PROMPT       # equation -> default
        model = json.loads((Path(d) / "doc.pdf.drill" / "model.docmodel.json").read_text())
        objs = model["objects"] if isinstance(model["objects"], list) else list(model["objects"].values())
        diag = next(o for o in objs if o["type"] == "Diagram")
        assert diag["props"]["latex_code"] == benzene
        assert diag["props"]["latex_code_provenance"] == "openai"
        # The adopted code passes the SVG renderability guard (chemfig route).
        from pdfdrill import svg as svgmod
        assert svgmod.is_latex_graphic(diag["props"]["latex_code"])


def test_cmd_vision_graceful_without_key(monkeypatch):
    # No key AND no Claude agent reachable -> the friendly "set a key" message.
    monkeypatch.setattr(openai_vision, "available", lambda: False)
    monkeypatch.setattr(llm_delegate, "detect_runtime",
                        lambda: llm_delegate.Runtime.NONE)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_vision(pdf)
        assert "OPENAI_API_KEY" in out
        assert not Sidecar(pdf).has(VISION_DONE)


class _FakeResp:
    """Minimal context-manager stand-in for net.urlopen returning image bytes."""
    def __init__(self, data): self._d = data
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._d


def test_cmd_vision_delegates_in_sandbox(monkeypatch):
    # No OpenAI key, but running inside the Claude.ai sandbox: cmd_vision must
    # DEFER the crops to the agent (write request files, print the instruction)
    # and, on re-run after the agent answers, ingest them as 'openai' provenance.
    monkeypatch.setattr(openai_vision, "available", lambda: False)
    monkeypatch.setattr(llm_delegate, "detect_runtime",
                        lambda: llm_delegate.Runtime.SANDBOX)
    # CDN crops are "downloaded" to local files so the agent can read them;
    # distinct bytes per URL → three distinct content-hash tasks (as in reality).
    monkeypatch.setattr(net, "urlopen",
                        lambda url, **kw: _FakeResp(b"\x89PNG\r\n\x1a\n" + url.encode()))
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        llm_dir = Path(d) / "doc.pdf.drill" / "llm"

        # Pass 1: defer.
        out1 = cmd_vision(pdf)
        assert "deferred" in out1 and "PDFDRILL-LLM-DELEGATION" in out1
        assert not Sidecar(pdf).has(VISION_DONE)
        reqs = sorted(llm_dir.glob("*.req.json"))
        assert len(reqs) == 3, f"expected 3 request files, got {len(reqs)}"

        # Simulate the agent: answer every request with a math result.
        for rq in reqs:
            tid = rq.name[:-len(".req.json")]
            (llm_dir / (tid + ".resp.json")).write_text(json.dumps({
                "task_id": tid, "kind": "vision",
                "result": {"selector": "math", "math": "a+b"},
            }))

        # Pass 2: ingest.
        out2 = cmd_vision(pdf)
        assert "delegated to sandbox" in out2 and "3 crop" in out2
        model = json.loads((Path(d) / "doc.pdf.drill" / "model.docmodel.json").read_text())
        objs = model["objects"] if isinstance(model["objects"], list) else list(model["objects"].values())
        oai = [r for o in objs for r in o.get("realizations", [])
               if r.get("provenance") == "openai"]
        assert len(oai) == 3
        assert oai[0]["props"]["selector"] == "math"
        assert oai[0]["props"].get("delegated") == "sandbox"
        assert Sidecar(pdf).has(VISION_DONE)


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v, raising=True): self._u.append((o, n, getattr(o, n, None))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    plain = [test_result_to_latex_mapping, test_result_to_latex_chemistry_normalization,
             test_collect_cdn_crops_finds_embedded_table_crop]
    mpd = [test_cmd_vision_attaches_openai_provenance, test_cmd_vision_limit,
           test_cmd_vision_uses_graph_prompt_for_subgraph_caption,
           test_cmd_vision_chem_prompt_and_latex_code_adoption,
           test_cmd_vision_graceful_without_key,
           test_cmd_vision_delegates_in_sandbox]
    for fn in plain:
        fn(); print(f"PASS {fn.__name__}")
    for fn in mpd:
        mp = _MP()
        try:
            fn(mp); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(plain) + len(mpd)} tests passed.")
