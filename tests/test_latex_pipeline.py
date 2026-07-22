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
    assert "\\begin{filecontents*}[overwrite]{DOC.formulas.dat}" in pre
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


def test_reference_section_ids_covers_section_and_its_content():
    """The References section + everything under it (the printed [1] M. Bahr …
    list) — so the projector skips them (thebibliography replaces them, and the
    `[1]` labels don't get mangled into \\cite)."""
    d = Document(); d.meta["bibkey"] = "DOC"
    sec = DocObject(type="Section", id="SEC_REF", props={"caption": "References"})
    d.add(sec)
    d.add(DocObject(type="Paragraph", id="P_REF1", props={
        "text": "[1] M. Bahr, …", "parent_section": "SEC_REF"}))
    d.add(DocObject(type="Section", id="SEC_INTRO", props={"caption": "Introduction"}))
    d.add(DocObject(type="Paragraph", id="P_BODY", props={
        "text": "body", "parent_section": "SEC_INTRO"}))
    ids = LP.reference_section_ids(d)
    assert "SEC_REF" in ids and "P_REF1" in ids       # the section + its list
    assert "SEC_INTRO" not in ids and "P_BODY" not in ids   # real body untouched


def test_math_unicode_normalized_in_formula_array():
    """MathPix/OCR emit a Unicode minus U+2212 (and ×, ≤, ≥ …) INSIDE formula
    LaTeX. In math mode xelatex can't render those without unicode-math, so they
    must map to LaTeX macros / ASCII in the .dat array."""
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Formula", id="DOC_FO0001",
                    props={"latex": "a − b", "flow_index": 1}))     # U+2212
    d.add(DocObject(type="Formula", id="DOC_FO0002",
                    props={"latex": "x × y ≤ z", "flow_index": 2}))  # × ≤
    order, _ = LP.formula_array(d)
    assert "−" not in order[0] and order[0] == "a - b"
    assert "\\times" in order[1] and "\\leq" in order[1]
    assert "×" not in order[1] and "≤" not in order[1]


def test_sanitize_math_leaves_normal_latex_untouched():
    assert LP.sanitize_math("\\frac{a}{b} - c") == "\\frac{a}{b} - c"


def test_balance_math_contains_a_runaway_inline_math():
    """Extraction can drop a closing `\\)` / `$`. Left as-is the unclosed inline
    math runs away into the next section ('Not allowed in LR mode'). Balance it
    PER BLOCK so the damage is contained."""
    # missing \)
    assert LP.balance_math("see \\(a+b and more") == "see \\(a+b and more\\)"
    # 2 open, 1 close → append one \)
    assert LP.balance_math("\\(x\\) then \\(y").endswith("\\)")
    assert LP.balance_math("\\(x\\) then \\(y").count("\\)") == 2
    # odd $ → append one $
    out = LP.balance_math("inline $z math")
    assert out.count("$") == 2 and out.endswith("$")
    # already balanced → untouched
    assert LP.balance_math("\\(a\\) and $b$") == "\\(a\\) and $b$"


def test_display_formula_made_inline_safe_in_array():
    """A Formula whose latex is a DISPLAY construct (aligned/split, `\\\\`, `&`)
    can't be `\\ensuremath`'d inline via `\\Expr` — 'Not allowed in LR mode'. The
    array entry strips the display env + alignment so it compiles inline."""
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Formula", id="DOC_FO0001", props={
        "latex": "\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}",
        "flow_index": 1}))
    order, _ = LP.formula_array(d)
    assert "aligned" not in order[0]        # display env stripped
    assert "&" not in order[0]              # alignment removed
    assert "\\\\" not in order[0]           # line breaks removed
    assert "a" in order[0] and "b" in order[0] and "d" in order[0]   # content kept


def test_plain_inline_formula_untouched_by_inline_safe():
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Formula", id="DOC_FO0001",
                    props={"latex": "x^2 + y^2", "flow_index": 1}))
    order, _ = LP.formula_array(d)
    assert order[0] == "x^2 + y^2"


def test_bibitem_emitted_even_with_bibtex_field():
    """A Reference from bibsource carries full `bibtex` AND structured
    author/year/title. It must still get a `\\bibitem` in thebibliography (a .bib
    needs a 2-pass bibtex compile that --compile doesn't do), formatted from the
    structured fields, specials escaped."""
    d = Document(); d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Reference", props={
        "citekey": "scholl2001objects", "author": "Scholl, Brian J", "year": "2001",
        "title": "Objects & attention: the state_of_the art",
        "bibtex": "@article{scholl2001objects, title={Objects}}"}))
    bib = LP.bibliography_block(d)
    assert "\\bibitem{scholl2001objects}" in bib
    assert "Scholl, Brian J" in bib and "(2001)" in bib
    assert "\\&" in bib and "\\_" in bib             # specials escaped


def test_clean_prose_strips_leaked_bibliography_commands():
    """Source `\\bibliography{emnlp2020}` / `\\bibliographystyle{acl_natbib}`
    leaked into prose try to load a missing .bib — the thebibliography replaces
    them, so strip them."""
    t = "thanks.\n\\bibliography{emnlp2020}\n\\bibliographystyle{acl_natbib}\nmore"
    out = LP.clean_prose(t)
    assert "\\bibliography{" not in out and "\\bibliographystyle{" not in out
    assert "thanks." in out and "more" in out


def test_clean_prose_normalizes_ligatures():
    assert LP.clean_prose("the ﬁrst conﬁguration") == "the first configuration"
    assert LP.clean_prose("eﬀective ﬂow") == "effective flow"


def test_clean_prose_strips_leaked_structural_commands():
    """A LaTeX-source build can ingest a `\\maketitle` (or `\\begin{document}`,
    `\\tableofcontents`, `\\newpage`) line as a body Paragraph. The projection
    owns that scaffolding, so a bare copy in the body is stripped — a lone
    `\\maketitle` with no `\\title` in the preamble is otherwise fatal."""
    for cmd in ("\\maketitle", "\\tableofcontents", "\\begin{document}",
                "\\end{document}", "\\newpage", "\\clearpage",
                "\\pagestyle{empty}", "\\appendix"):
        assert LP.clean_prose(cmd).strip() == "", cmd
    assert "keep" in LP.clean_prose("keep\n\\maketitle\ntext") and \
        "\\maketitle" not in LP.clean_prose("keep\n\\maketitle\ntext")


def test_leaked_title_recovers_a_title_from_prose():
    assert LP.leaked_title("\\title{A Real Title}") == "A Real Title"
    assert LP.leaked_title("no title here") is None
    assert LP.leaked_title("\\title{}") is None


def test_formula_preamble_drops_obsolete_filecontents_package():
    """The `filecontents` PACKAGE is obsolete (the env is in the kernel), and the
    default env refuses to overwrite a stale `.dat` — so no `\\usepackage{
    filecontents}` and the env carries `[overwrite]`."""
    pre = LP.formula_preamble(["a", "b"], "X.formulas.dat")
    assert "\\usepackage{filecontents}" not in pre
    assert "\\begin{filecontents*}[overwrite]{X.formulas.dat}" in pre
    assert "\\usepackage{readarray}" in pre


def test_bib_escape_is_idempotent_no_double_escape():
    """An entry already carrying `\\&`/`\\_` from the source .bbl must not become
    `\\\\&` (which our `\\\\`-collapse would then turn into a bare `&`)."""
    assert LP._bib_escape("Speech \\& language") == "Speech \\& language"
    assert LP._bib_escape("a & b") == "a \\& b"
    assert LP._bib_escape(LP._bib_escape("a & b")) == "a \\& b"


def _braces_balanced(s: str) -> bool:
    return LP._balance_braces(s) == s


def test_sanitize_bib_body_makes_broken_entries_compile_safe():
    """The real 2002.08155 breakages: truncated accents leaving unbalanced braces,
    OCR `\\\\` breaks, an unescaped `&`. Each must come out brace-balanced with no
    bare `&`."""
    import re as _re
    cases = {
        "Cho and Van Merri{\\ (2014) Learning": "Van Merri (2014)",
        "Manning (2020) {\\{": "Manning (2020) {}",
        "Rockt{\\ (2019) Language Models": "Rockt (2019)",
    }
    for raw, expect_sub in cases.items():
        out = LP._sanitize_bib_body(raw)
        assert _braces_balanced(out), out
        assert expect_sub in out, (raw, out)
    # \L accent (letter after {\) is kept and closed
    out = LP._sanitize_bib_body("Kaiser, {\\L (2017) Attention")
    assert "{\\L" in out and _braces_balanced(out)
    # a bare `&` and an OCR `\\&` both end escaped, never bare
    for raw in ("Speech & lang", "Speech \\\\& lang"):
        out = LP._sanitize_bib_body(raw)
        assert not _re.search(r"(?<!\\)&", out), (raw, out)


def test_glossary_block_renders_acronyms():
    """Acronyms → a single-pass `description` list (Acronyms section), specials
    escaped. Empty records → empty string."""
    recs = [("NLP", "natural language processing"), ("R&D", "research & dev")]
    out = LP.glossary_block(recs)
    assert "\\section*{Acronyms}" in out
    assert "\\begin{description}" in out and "\\end{description}" in out
    assert "\\item[NLP] natural language processing" in out
    assert "\\&" in out                              # specials escaped
    assert LP.glossary_block([]) == ""


def test_cit_marker_becomes_cite():
    """A source-built model transcludes citations as `{{<bibkey>_REF_<citekey>||CIT}}`
    — resolve to `\\cite{<citekey>}` (the `\\bibitem` uses the same citekey)."""
    out = LP.resolve_transclusions(
        "ELMo {{2002.08155_REF_peters2018deep||CIT}}, GPT {{2002.08155_REF_radford||CIT}}",
        {})
    assert out == "ELMo \\cite{peters2018deep}, GPT \\cite{radford}"
    assert "{{" not in out and "(?" not in out       # not left as unknown
