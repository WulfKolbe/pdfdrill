r"""
LaTeXPipeline — the inspectable model→LaTeX generator.

TRANSCLUSION is real array lookup (the user's filecontents+readarray pattern),
NOT inline expansion: every distinct formula LaTeX goes ONCE into a `.dat` array,
and each `{{<bibkey>_FO0001||FO}}` marker becomes `\Expr{<index>}` — so a formula
used 20× is `\Expr{k}` 20×, not 20 copies. Deduped by content, so identical math
shares one slot. The stages are dumpable for inspection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.projectors import latex_pipeline as LP


def _doc_with_transclusions():
    d = Document()
    d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Formula", id="DOC_FO0001",
                    props={"latex": "E = mc^2", "bibkey": "DOC", "flow_index": 1}))
    d.add(DocObject(type="Formula", id="DOC_FO0002",
                    props={"latex": "\\int_0^1 t^n\\,dt", "flow_index": 2}))
    d.add(DocObject(type="Paragraph", props={
        "text": "Einstein wrote {{DOC_FO0001||FO}}; also {{DOC_FO0002||FO}} and "
                "again {{DOC_FO0001||FO}}.", "flow_index": 3}))
    return d


def test_formula_array_orders_and_dedupes():
    d = _doc_with_transclusions()
    order, title_index = LP.formula_array(d)
    assert order == ["E = mc^2", "\\int_0^1 t^n\\,dt"]
    assert title_index["DOC_FO0001"] == 1
    assert title_index["DOC_FO0002"] == 2


def test_duplicate_content_shares_one_slot():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Formula", id="DOC_FO0001", props={"latex": "x", "flow_index": 1}))
    d.add(DocObject(type="Formula", id="DOC_FO0007", props={"latex": "x", "flow_index": 2}))
    order, ti = LP.formula_array(d)
    assert order == ["x"]                       # one array slot
    assert ti["DOC_FO0001"] == ti["DOC_FO0007"] == 1


def test_preamble_is_filecontents_plus_readarray():
    order, _ = LP.formula_array(_doc_with_transclusions())
    pre = LP.formula_preamble(order, "DOC.formulas.dat")
    assert "\\begin{filecontents*}{DOC.formulas.dat}" in pre
    assert "\\end{filecontents*}" in pre
    assert "\\usepackage{readarray}" in pre
    assert "\\readarraysepchar{\\par}" in pre
    assert "\\newcommand{\\Expr}" in pre
    assert "E = mc^2" in pre                     # the array data

def test_resolve_marker_becomes_Expr_index_not_inline():
    d = _doc_with_transclusions()
    _order, ti = LP.formula_array(d)
    out = LP.resolve_transclusions(
        "wrote {{DOC_FO0001||FO}}; also {{DOC_FO0002||FO}}; again {{DOC_FO0001||FO}}", ti)
    assert out == "wrote \\Expr{1}; also \\Expr{2}; again \\Expr{1}"
    assert "$" not in out and "{{" not in out    # array lookup, not inline math


def test_unknown_marker_is_readable_not_raw_braces():
    out = LP.resolve_transclusions("see {{DOC_FO9999||FO}} here", {})
    assert "{{" not in out and "}}" not in out


def test_formula_data_line_is_flattened_single_line():
    """readarray splits on \\par — a formula must be ONE line (internal newlines
    flattened) or the array indexing breaks."""
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Formula", id="DOC_FO0001",
                    props={"latex": "a +\n  b", "flow_index": 1}))
    order, _ = LP.formula_array(d)
    assert "\n" not in order[0] and order[0] == "a + b"


def test_markdown_heading_residual_becomes_section():
    assert LP.resolve_headings("## Background") == "\\section{Background}"
    assert LP.resolve_headings("normal text") == "normal text"


def test_citation_map_from_citation_objects():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Citation", props={"citekey": "smith2020", "flow_index": 1}))
    d.add(DocObject(type="Citation", props={"citekey": "jones2021", "flow_index": 2}))
    assert LP.citation_keys(d) == ["smith2020", "jones2021"]


def test_bibliography_block_from_references():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Reference", props={
        "citekey": "smith2020", "author": "Smith, J.", "year": "2020",
        "titlefield": "A Study", "raw_text": "Smith, J. (2020). A Study."}))
    bib = LP.bibliography_block(d)
    assert "\\begin{thebibliography}" in bib and "\\bibitem{smith2020}" in bib


def test_stages_are_dumpable(tmp_path):
    d = _doc_with_transclusions()
    d.add(DocObject(type="Citation", props={"citekey": "e1905", "flow_index": 4}))
    LP.dump_stages(LP.run_stages(d, "DOC"), tmp_path)
    assert (tmp_path / "00-formulas.dat").exists()          # the readarray data file
    assert (tmp_path / "00-formula-index.json").exists()    # title → index map
    assert (tmp_path / "01-citations.json").exists()
    import json
    ti = json.loads((tmp_path / "00-formula-index.json").read_text())
    assert ti["DOC_FO0001"] == 1


# ── stage 1b: rewrite in-text [N] → \cite{citekey} ───────────────────────────

def _doc_with_numeric_citations():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Reference", props={"number": 1, "citekey": "Bahr2002",
                                             "author": "Bahr", "year": "2002"}))
    d.add(DocObject(type="Reference", props={"number": 11, "citekey": "Nelson1965",
                                             "author": "Nelson", "year": "1965"}))
    d.add(DocObject(type="Reference", props={"number": 12, "citekey": "Kolbe2007",
                                             "author": "Kolbe", "year": "2007"}))
    return d


def test_reference_map_number_to_citekey():
    d = _doc_with_numeric_citations()
    assert LP.reference_map(d) == {1: "Bahr2002", 11: "Nelson1965", 12: "Kolbe2007"}


def test_resolve_citations_single_and_grouped():
    m = {11: "Nelson1965", 12: "Kolbe2007"}
    assert LP.resolve_citations("see [12]) here", m) == "see \\cite{Kolbe2007}) here"
    assert LP.resolve_citations("online at [11].", m) == "online at \\cite{Nelson1965}."
    assert LP.resolve_citations("both [11, 12]", m) == "both \\cite{Nelson1965,Kolbe2007}"


def test_resolve_citations_range_expands():
    m = {11: "a", 12: "b", 13: "c"}
    assert LP.resolve_citations("refs [11-13]", m) == "refs \\cite{a,b,c}"


def test_non_reference_bracket_left_raw():
    """A [N] whose number is NOT a reference (an index/interval) stays raw."""
    m = {11: "Nelson1965"}
    assert LP.resolve_citations("array [99] and [0,1]", m) == "array [99] and [0,1]"


def test_bibitem_uses_reference_citekey():
    d = _doc_with_numeric_citations()
    bib = LP.bibliography_block(d)
    assert "\\bibitem{Nelson1965}" in bib and "\\bibitem{Kolbe2007}" in bib
