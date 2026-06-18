"""
Keyless MathPix replacement (`pdfdrill remath`): rebuild MathPix-quality Markdown
(with LaTeX math) from rendered pages by delegating each page to the Claude agent
with openai_vision.MATHPIX_MD_PROMPT — the fix for tesseract's LaTeX-free text
breaking transclusion. A page the model declines (PDFDRILL_CANNOT_RECONSTRUCT) is
skipped, never faked.
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import openai_vision, llm_delegate, pdf_reading, commands
from pdfdrill.commands import cmd_remath
from pdfdrill.sidecar import Sidecar


def test_prompt_demands_latex_and_offers_giveup():
    p = openai_vision.MATHPIX_MD_PROMPT
    assert r"\( … \)" in p or r"\(" in p          # inline LaTeX required
    assert "$$" in p                               # display LaTeX required
    assert openai_vision.GIVE_UP_SENTINEL in p     # the give-up token is named
    assert "hallucinate" in p.lower() or "guess" in p.lower()   # forbids fabrication


def test_parse_page_md_giveup_and_markdown():
    g = llm_delegate._parse_page_md(openai_vision.GIVE_UP_SENTINEL)
    assert g["given_up"] and g["markdown"] == ""
    assert llm_delegate._parse_page_md("")["given_up"]            # empty = decline
    ok = llm_delegate._parse_page_md(r"## Sec\n\nThe \(x^2\) bound. $$\nE=mc^2\n$$")
    assert not ok["given_up"] and "E=mc^2" in ok["markdown"]
    # a whole-page code fence is unwrapped
    fenced = llm_delegate._parse_page_md("```markdown\n# T\n\\(a\\)\n```")
    assert not fenced["given_up"] and "\\(a\\)" in fenced["markdown"]


def test_remath_sandbox_roundtrip(monkeypatch):
    # No real PDF/pdftoppm: fake the rasterizer to two page PNGs, force sandbox.
    monkeypatch.setattr(llm_delegate, "detect_runtime", lambda: llm_delegate.Runtime.SANDBOX)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)

        def fake_raster(_pdf, out_dir, **kw):
            out_dir.mkdir(parents=True, exist_ok=True)
            ps = []
            for n in (1, 2):
                p = out_dir / f"page-{n}.png"; p.write_bytes(b"\x89PNG" + str(n).encode())
                ps.append(p)
            return ps
        monkeypatch.setattr(pdf_reading, "rasterize", fake_raster)

        # Pass 1: defer — one page_md request per page.
        out1 = cmd_remath(pdf)
        assert "deferred" in out1 and "PDFDRILL-LLM-DELEGATION" in out1
        llm = sc.blob_dir / "llm"
        reqs = sorted(llm.glob("*.req.json"))
        assert len(reqs) == 2
        kinds = {json.loads(r.read_text())["kind"] for r in reqs}
        assert kinds == {"page_md"}

        # Agent answers: page 1 real Markdown, page 2 declines.
        for r in reqs:
            req = json.loads(r.read_text()); tid = req["task_id"]
            page1 = req["image_path"].endswith("page-1.png")
            result = (r"# Heat\n\nThe \(\lambda_i\) decay. $$\nk_t=\sum_i e^{-\lambda_i t}\n$$"
                      if page1 else openai_vision.GIVE_UP_SENTINEL)
            (llm / (tid + ".resp.json")).write_text(json.dumps(
                {"task_id": tid, "kind": "page_md", "result": result}))

        # Pass 2: ingest -> one page kept, one declined, md written.
        out2 = cmd_remath(pdf)
        assert "rebuilt 1 page" in out2 and "1 page(s) the model declined" in out2
        key = commands.resolve_bibkey(pdf, None, sc)
        md = (sc.blob_dir / f"{key}.mathpix.md").read_text()
        assert r"\(\lambda_i\)" in md and "$$" in md     # LaTeX recovered
        assert openai_vision.GIVE_UP_SENTINEL not in md  # the declined page isn't in it


def test_remath_no_agent_is_graceful(monkeypatch):
    monkeypatch.setattr(llm_delegate, "detect_runtime", lambda: llm_delegate.Runtime.NONE)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "p.pdf"; pdf.write_bytes(b"%PDF-1.4")
        out = cmd_remath(pdf)
        assert "PDFDRILL_DELEGATE=sandbox" in out and "Claude agent" in out


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
