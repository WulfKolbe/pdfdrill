"""
Tests for two reported bugs:
  ISSUE 1 — fenced source-code listings must NOT be fed to latex→dvisvgm
            (svg guard + DiagramProcessor reclassifies them as code).
  ISSUE 2 — `--bibkey` on `model`/`tiddlers` sets the prefix, persists in the
            sidecar, and is reused by later commands.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.diagram import DiagramProcessor
from docmodel.base_module import ModuleConfig
from pdfdrill.svg import is_latex_graphic, compile_to_svg


# ---------------- ISSUE 1: svg guard ----------------

def test_is_latex_graphic_rejects_code_accepts_graphics():
    assert not is_latex_graphic("")
    assert not is_latex_graphic("```\nfunction f()\nend\n```")        # fenced
    assert not is_latex_graphic("function spin(N)\n  x=collect(1:N)")  # raw code
    assert not is_latex_graphic("x = A\\b  # Julia left-division")     # \b not a gfx cmd
    assert is_latex_graphic(r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}")
    assert is_latex_graphic(r"\draw (0,0)--(1,1);")
    assert is_latex_graphic(r"\begin{tabular}{ll}a&b\end{tabular}")


def test_compile_to_svg_skips_fenced_code_without_latex():
    r = compile_to_svg("```julia\nfunction f()\nend\n```")
    assert r["ok"] is False and r.get("skipped") is True
    assert "skipped" in r["error"]


# ---------------- ISSUE 1: DiagramProcessor reclassification ----------------

def _diagram_doc(text_display):
    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "d1", "type": "diagram", "text": "", "text_display": text_display}]}]})
    return doc


def test_fenced_code_diagram_reclassified_as_code():
    doc = _diagram_doc("```julia\nfunction f(N)\n    x=1\nend\n```")
    DiagramProcessor(ModuleConfig(title="D", classname="DiagramProcessor", proc_order=7),
                     "T").process_document(doc)
    d = doc.objects_of_type("Diagram")[0]
    assert d.props["subtype"] == "code"
    assert d.props["language"] == "julia"
    assert "function f" in d.props["code"]
    assert not d.props["latex_code"]      # never fed to svg
    assert not d.props["cdn_url"]         # not an image


def test_extract_code_multiblock_and_infostring():
    from docmodel.modules.diagram import _extract_code
    # info string -> leading token is the language
    assert _extract_code("```julia title=foo\nx=1\n```") == ("x=1", "julia")
    # concatenated blocks: interior language fence must NOT leak into the code
    code, lang = _extract_code("```julia\na=1\n```\n```julia\nb=2\n```")
    assert "```" not in code and code == "a=1\nb=2"


def test_unfenced_code_with_math_string_not_a_graphic():
    # Raw code containing a math \begin{matrix} string literal must NOT be
    # treated as a renderable graphic (only known graphic envs count).
    assert not is_latex_graphic('s = "\\begin{matrix} a \\end{matrix}"')
    assert is_latex_graphic(r"\begin{tikzcd} A \arrow[r] & B \end{tikzcd}")


# ---------------- ISSUE 2: --bibkey threading + persistence ----------------

def test_code_diagram_in_section_body_not_imaged():
    """A subtype=code Diagram that is a child of a Section must be transcluded
    plainly (its own fenced-code text), NEVER via the image-only ||DIA template."""
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    from docmodel.core import DocObject, Realization
    doc = Document()
    mp = doc.ensure_stream("mathpix_lines")
    a = mp.append(type="section_header", _page=1, text_display="Code")
    sec = DocObject(type="Section", props={"caption": "Code", "page": 1, "level": 1})
    sec.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    dia = DocObject(type="Diagram", props={"subtype": "code", "language": "julia",
                                           "code": "function f()\n  return 1\nend", "page": 1})
    dia.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    sec.children.append(dia.id); dia.parent = sec.id
    doc.add(sec); doc.add(dia)
    tids = {t["title"]: t for t in __import__("json").loads(
        TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(doc))}
    sec_tid = next(t for k, t in tids.items() if k.endswith("_H1"))
    assert "||DIA}}" not in sec_tid["text"]            # never the image template
    dia_tid = next(t for k, t in tids.items() if "_DIA" in k)
    assert dia_tid["text"].startswith("```julia") and "function f" in dia_tid["text"]
    assert "canonical_uri" not in dia_tid               # not an image


def test_resolve_and_junk_hint():
    from pdfdrill.commands import resolve_bibkey, _bibkey_hint
    assert resolve_bibkey(Path("/x/2004.05631v1.pdf")) == "2004.05631v1"   # clean stem kept
    assert resolve_bibkey(Path("/x/a.pdf"), explicit="kolbe2018hubbard") == "kolbe2018hubbard"
    assert "Tip" in _bibkey_hint("993787212-Burkhard-Heim")   # junky leading digits
    assert _bibkey_hint("2004.05631v1") == ""                  # arXiv id not flagged
    assert _bibkey_hint("kolbe2018hubbard") == ""


def test_bibkey_threads_and_persists():
    from pdfdrill.commands import cmd_model, cmd_tiddlers
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "AKolbe-BA.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
        (d / "AKolbe-BA.lines.json").write_text(json.dumps({"pages": [
            {"page": 1, "image_id": "i", "lines": [
                {"id": "l1", "type": "text", "text": "Hello world.",
                 "text_display": "Hello world."}]}]}))
        out = cmd_model(pdf, bibkey="kolbe2018hubbard")
        assert "kolbe2018hubbard" in out
        assert Sidecar(pdf).get_evidence("bibkey") == "kolbe2018hubbard"
        # tiddlers reuses the persisted key (no --bibkey) for titles + filename.
        cmd_tiddlers(pdf)
        tf = d / "AKolbe-BA.pdf.drill" / "kolbe2018hubbard.tiddlers.json"
        assert tf.exists()
        titles = [x["title"] for x in json.loads(tf.read_text())]
        assert any(t.startswith("kolbe2018hubbard_") for t in titles)
        assert "kolbe2018hubbard" in titles      # landing/document tiddler


if __name__ == "__main__":
    fns = [test_is_latex_graphic_rejects_code_accepts_graphics,
           test_compile_to_svg_skips_fenced_code_without_latex,
           test_fenced_code_diagram_reclassified_as_code,
           test_resolve_and_junk_hint, test_bibkey_threads_and_persists]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
