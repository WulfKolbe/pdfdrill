"""
LaTeXPipeline — the INSPECTABLE model→LaTeX generator. Each stage is a pure
function returning data you can dump and test, so `pdfdrill latex --dump-stages`
writes the transclusion lookup / citation map / bibliography as separate files
(the textscan-style inspectability the user asked for).

The stages fix the "Markdown with a LaTeX header" problem: a MathPix/scan doc's
paragraph text carries `{{<bibkey>_FO0001||FO}}` transclusion markers, which must
resolve — by ARRAY LOOKUP — to the formula's `$…$`, not be dumped raw.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.projectors import latex_pipeline as LP


def _doc_with_transclusions():
    d = Document()
    d.meta["bibkey"] = "DOC"
    # a formula the paragraph transcludes
    d.add(DocObject(type="Formula", id="DOC_FO0001",
                    props={"latex": "E = mc^2", "bibkey": "DOC", "flow_index": 1}))
    d.add(DocObject(type="Paragraph", props={
        "text": "Einstein wrote {{DOC_FO0001||FO}} in 1905.", "flow_index": 2}))
    return d


def test_transclusion_lookup_maps_title_to_latex():
    d = _doc_with_transclusions()
    lut = LP.transclusion_lookup(d)
    assert lut["DOC_FO0001"] == "E = mc^2"


def test_resolve_body_substitutes_marker_with_inline_math():
    d = _doc_with_transclusions()
    lut = LP.transclusion_lookup(d)
    out = LP.resolve_transclusions("Einstein wrote {{DOC_FO0001||FO}} in 1905.", lut)
    assert out == "Einstein wrote $E = mc^2$ in 1905."
    assert "{{" not in out                       # no raw marker left


def test_unknown_marker_is_left_readable_not_raw_braces():
    """A marker with no lookup entry must not leave `{{…​}}` (invalid LaTeX)."""
    out = LP.resolve_transclusions("see {{DOC_FO9999||FO}} here", {})
    assert "{{" not in out and "}}" not in out


def test_markdown_heading_residual_becomes_section():
    """A stray Markdown/`\\section*`-in-text heading must become a real section."""
    assert LP.resolve_headings("## Background") == "\\section{Background}"
    assert LP.resolve_headings("normal text") == "normal text"


def test_citation_map_from_citation_objects():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Citation", props={"citekey": "smith2020", "flow_index": 1}))
    d.add(DocObject(type="Citation", props={"citekey": "jones2021", "flow_index": 2}))
    keys = LP.citation_keys(d)
    assert keys == ["smith2020", "jones2021"]


def test_bibliography_block_from_references():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Reference", props={
        "citekey": "smith2020", "author": "Smith, J.", "year": "2020",
        "titlefield": "A Study", "raw_text": "Smith, J. (2020). A Study."}))
    bib = LP.bibliography_block(d)
    assert "\\begin{thebibliography}" in bib and "\\end{thebibliography}" in bib
    assert "\\bibitem{smith2020}" in bib
    assert "Smith" in bib


def test_bibliography_empty_when_no_references():
    d = Document(); d.meta["bibkey"] = "DOC"
    assert LP.bibliography_block(d) == ""


def test_stages_are_dumpable(tmp_path):
    d = _doc_with_transclusions()
    d.add(DocObject(type="Citation", props={"citekey": "e1905", "flow_index": 3}))
    stages = LP.run_stages(d)
    LP.dump_stages(stages, tmp_path)
    assert (tmp_path / "00-transclusions.json").exists()
    assert (tmp_path / "01-citations.json").exists()
    import json
    lut = json.loads((tmp_path / "00-transclusions.json").read_text())
    assert lut["DOC_FO0001"] == "E = mc^2"
