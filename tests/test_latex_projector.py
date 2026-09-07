"""
LaTeXProjector — the LaTeX analog of the Markdown projector: a drilled Document
projected to a compilable `.tex` (sections, prose, display equations, inline
formulas, tables). This is the OUTPUT direction; `injectlatex` is the input one
(pull the author's source in). `pdfdrill latex` drives this.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors.latex import LaTeXProjector


def _proj():
    return LaTeXProjector(OperatorConfig(op="projector", classname="LaTeXProjector"))


def _doc():
    d = Document()
    d.meta["bibkey"] = "demo2026"
    d.meta["title"] = "A Demo Paper"
    d.meta["authors"] = ["Ada Lovelace", "Alan Turing"]
    d.add(DocObject(type="Section", props={
        "level": 1, "section_number": "1", "caption": "Introduction",
        "flow_index": 0}))
    d.add(DocObject(type="Paragraph", props={
        "text": "We study $x^2$ carefully.", "flow_index": 1}))
    d.add(DocObject(type="Equation", props={
        "latex": "E = mc^2", "refnum": "1", "label": "eq:emc",
        "flow_index": 2}))
    return d


def test_projects_a_compilable_skeleton():
    tex = _proj().project(_doc())
    assert "\\documentclass" in tex
    assert "\\begin{document}" in tex and "\\end{document}" in tex
    assert tex.index("\\begin{document}") < tex.index("\\end{document}")


def test_title_and_authors_from_meta():
    tex = _proj().project(_doc())
    assert "\\title{A Demo Paper}" in tex
    assert "Ada Lovelace" in tex and "Alan Turing" in tex     # \author
    assert "\\maketitle" in tex


def test_sections_paragraphs_equations():
    tex = _proj().project(_doc())
    assert "\\section{Introduction}" in tex
    assert "We study $x^2$ carefully." in tex
    # a display equation → equation environment with its \label
    assert "\\begin{equation}" in tex and "E = mc^2" in tex
    assert "\\label{eq:emc}" in tex


def test_display_equation_is_transcluded_via_eqexpr():
    """A display Equation renders as `\\begin{equation}\\EqExpr{i}…\\end{equation}`
    — transcluded from the readarray array, consistent with inline `\\Expr{i}`
    formulas (not the raw LaTeX inline)."""
    d = Document(); d.meta["bibkey"] = "x"
    d.add(DocObject(type="Equation", props={
        "latex": "\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}",
        "label": "eq:main", "flow_index": 0}))
    tex = _proj().project(d)
    assert "\\newcommand{\\EqExpr}" in tex                # macro defined
    assert "\\begin{equation}" in tex
    import re
    m = re.search(r"\\begin\{equation\}(.*?)\\end\{equation\}", tex, re.DOTALL)
    assert m and "\\EqExpr{" in m.group(1)               # transcluded, not raw
    assert "\\label{eq:main}" in m.group(1)              # label kept
    # the array carries the display body
    assert "\\begin{aligned}" in tex


def test_shallowest_section_anchors_to_section_not_subsection():
    """A paper whose top sections are level 2 (no level-1 in the model) must
    render its shallowest sections as `\\section` — else `\\subsection{Introduction}`
    numbers as 0.1. Anchors like the fractal-index TOC; hierarchy preserved."""
    d = Document()
    d.meta["bibkey"] = "x"
    d.add(DocObject(type="Section", props={"level": 2, "caption": "Introduction", "flow_index": 0}))
    d.add(DocObject(type="Section", props={"level": 3, "caption": "Background", "flow_index": 1}))
    d.add(DocObject(type="Section", props={"level": 2, "caption": "Method", "flow_index": 2}))
    tex = _proj().project(d)
    assert "\\section{Introduction}" in tex and "\\section{Method}" in tex   # level 2 → section
    assert "\\subsection{Background}" in tex                                  # level 3 → subsection
    assert "\\subsection{Introduction}" not in tex


def test_section_caption_with_hash_is_single_escaped():
    """A section like 'Code Summarization on C#' must escape `#` ONCE — the old
    non-idempotent escape doubled an already-escaped `C\\#` into `C\\\\#` (a line
    break + bare `#`, fatal)."""
    d = Document()
    d.meta["bibkey"] = "x"
    d.add(DocObject(type="Section", props={
        "level": 3, "caption": "Code Summarization on C\\#", "flow_index": 0}))
    tex = _proj().project(d)
    assert "C\\#}" in tex and "C\\\\#" not in tex


def test_prose_citep_and_percent_and_table_citep_normalized():
    d = Document()
    d.meta["bibkey"] = "x"
    d.add(DocObject(type="Paragraph", props={
        "text": "Following \\citep{devlin2018bert}, 15% of tokens for C# code.",
        "flow_index": 0}))
    d.add(DocObject(type="Table", props={
        "latex_code": "\\begin{tabular}{lc}\nMOSES \\citep{koehn2007moses} & 11.57 \\\\\n\\end{tabular}",
        "flow_index": 1}))
    tex = _proj().project(d)
    assert "\\cite{devlin2018bert}" in tex and "\\citep" not in tex   # prose + table
    assert "15\\% of tokens" in tex and "C\\# code" in tex            # escaped
    assert "\\citep{koehn2007moses}" not in tex                       # table normalised
    assert "11.57 \\\\" in tex                                        # table `&`/`\\` intact
    assert "MOSES \\cite{koehn2007moses} & 11.57" in tex


def test_section_depth_maps_to_subsection():
    # a level-2 section RELATIVE to a level-1 top section → \subsection
    # (min-level anchoring: shift is 0 when a level-1 section is present).
    d = Document()
    d.meta["bibkey"] = "x"
    d.add(DocObject(type="Section", props={
        "level": 1, "caption": "Top", "flow_index": 0}))
    d.add(DocObject(type="Section", props={
        "level": 2, "caption": "Details", "flow_index": 1}))
    tex = _proj().project(d)
    assert "\\section{Top}" in tex and "\\subsection{Details}" in tex


def test_output_extension_is_tex():
    assert _proj().output_extension() == ".tex"


def test_empty_latex_equation_skipped():
    """A CDN-crop-only equation (empty latex) must not emit an empty environment."""
    d = Document()
    d.meta["bibkey"] = "x"
    d.add(DocObject(type="Equation", props={"latex": "", "flow_index": 0}))
    tex = _proj().project(d)
    assert "\\begin{equation}" not in tex


def test_dict_preamble_is_coerced_not_crashed():
    """doc.meta['latex_preamble'] may be a DICT (expanded/standalone forms) — the
    projector must use a string form, not call .rstrip() on the dict (a real crash
    found projecting a model built with injectlatex)."""
    d = Document()
    d.meta["bibkey"] = "x"
    d.meta["latex_preamble"] = {"expanded": "\\documentclass{article}\n\\usepackage{amsmath}"}
    d.add(DocObject(type="Paragraph", props={"text": "hi", "flow_index": 0}))
    tex = _proj().project(d)
    assert "\\documentclass{article}" in tex and "\\begin{document}" in tex


def test_consecutive_list_items_wrapped_in_one_itemize():
    """Bare \\item is invalid LaTeX — a run of ListItems must sit inside ONE
    itemize, each preserving its original marker as the label."""
    d = Document(); d.meta["bibkey"] = "x"
    d.add(DocObject(type="ListItem", props={"marker": "1.", "content": "First", "flow_index": 0}))
    d.add(DocObject(type="ListItem", props={"marker": "*", "content": "Second", "flow_index": 1}))
    tex = _proj().project(d)
    assert tex.count("\\begin{itemize}") == 1 and tex.count("\\end{itemize}") == 1
    assert "\\item[{1.}] First" in tex and "\\item[{*}] Second" in tex
    # no bare \item outside the environment
    assert tex.index("\\begin{itemize}") < tex.index("\\item[{1.}]") < tex.index("\\end{itemize}")


def test_two_list_runs_split_by_a_paragraph_are_two_environments():
    d = Document(); d.meta["bibkey"] = "x"
    d.add(DocObject(type="ListItem", props={"marker": "-", "content": "A", "flow_index": 0}))
    d.add(DocObject(type="Paragraph", props={"text": "between", "flow_index": 1}))
    d.add(DocObject(type="ListItem", props={"marker": "-", "content": "B", "flow_index": 2}))
    tex = _proj().project(d)
    assert tex.count("\\begin{itemize}") == 2


def test_standalone_preamble_rejected_for_full_document():
    """A model's latex_preamble can be a `standalone` class (used to CROP figures
    in the SVG step). standalone typesets in a box → `\\section` errors 'Not
    allowed in LR mode'. The full-document projection must NOT use it."""
    d = Document(); d.meta["bibkey"] = "x"
    d.meta["latex_preamble"] = ("\\documentclass[border=2pt,class=report]{standalone}\n"
                                "\\usepackage{tikz}\n\\usepackage{amsmath}")
    d.add(DocObject(type="Section", props={"level": 1, "caption": "Intro", "flow_index": 0}))
    tex = _proj().project(d)
    assert "{standalone}" not in tex
    assert "\\documentclass" in tex and "article" in tex     # a real doc class
    assert "\\section{Intro}" in tex


def test_normal_article_preamble_is_kept():
    d = Document(); d.meta["bibkey"] = "x"
    d.meta["latex_preamble"] = "\\documentclass{article}\n\\usepackage{mymacros}"
    d.add(DocObject(type="Paragraph", props={"text": "hi", "flow_index": 0}))
    tex = _proj().project(d)
    assert "\\usepackage{mymacros}" in tex          # author preamble kept


# ---------------------------------------------------------------------------
# 635 — emit the table of contents as a command, not as its wreckage.
#
# The model already holds a Toc object (`docmodel.modules.toc.TocProcessor`)
# the projector used to never read (`_render` had no "Toc" branch, so a Toc
# in flow rendered ""). Real evidence (out/646.txt, out/634.txt on penev_A):
# a Toc's realization covers its own TOC-type lines block-claim-exactly, and
# any object whose ENTIRE surface realization sits inside that span is a
# fragment MathPix cut out of a contents line, never real content — the
# orphan `$T=15$` Formulas the user named. Suppressed in the PROJECTION only
# (634/646's ruling): never deleted from the model, always counted.
# ---------------------------------------------------------------------------

def _toc_doc():
    """A Toc object claiming lines 1..3 (block realization, 634/646's rule),
    a wreckage Section "Contents" OUTSIDE the Toc's own claimed range (line 0
    — exactly the boundary penev_A itself shows: TocProcessor's anchors are
    only the `table_of_contents_*`-typed lines, so a `section_header` line
    immediately before the first one falls outside the Toc's own realization
    even though it is the wreckage the user named — dropped by TITLE per the
    brief's own rule, not by Toc coverage), a Formula fragment INSIDE the
    Toc's range (line 3, no sub-anchor offset/length: a BLOCK claim, exactly
    what MathPix produces for a bare `$T=15$` TOC-line remnant), and real
    content (a genuine Section + Paragraph) after it, untouched."""
    d = Document()
    d.meta["bibkey"] = "demo"
    mp = d.ensure_stream("mathpix_lines")
    a_contents = mp.append(text="Contents", type="section_header")
    a_container = mp.append(text="", type="table_of_contents_container")
    a_item = mp.append(text="1 Introduction", type="table_of_contents_item")
    a_frag = mp.append(text="T=15", type="table_of_contents_number")
    a_head = mp.append(text="Introduction", type="section_header")
    a_body = mp.append(text="Real prose.", type="text")

    sec_contents = DocObject(type="Section", props={
        "level": 1, "caption": "Contents", "flow_index": 0})
    sec_contents.add_realization(Realization(
        stream="mathpix_lines", start=a_contents, end=a_contents,
        role="surface"))
    d.add(sec_contents)

    toc = DocObject(type="Toc", props={
        "entries": ["1 Introduction"], "derived": True})
    toc.add_realization(Realization(
        stream="mathpix_lines", start=a_container, end=a_frag,
        role="surface"))
    d.add(toc)

    frag = DocObject(type="Formula", props={"latex": "T=15", "flow_index": 1})
    frag.add_realization(Realization(
        stream="mathpix_lines", start=a_frag, end=a_frag, role="surface"))
    d.add(frag)

    sec_real = DocObject(type="Section", props={
        "level": 1, "caption": "Introduction", "flow_index": 2})
    sec_real.add_realization(Realization(
        stream="mathpix_lines", start=a_head, end=a_head, role="surface"))
    d.add(sec_real)

    para = DocObject(type="Paragraph", props={
        "text": "Real prose.", "flow_index": 3})
    para.add_realization(Realization(
        stream="mathpix_lines", start=a_body, end=a_body, role="surface"))
    d.add_child(sec_real, para)
    return d


def test_a_toc_object_emits_tableofcontents_once():
    tex = _proj().project(_toc_doc())
    assert tex.count("\\tableofcontents") == 1


def test_the_wreckage_contents_section_is_dropped_from_the_projection():
    tex = _proj().project(_toc_doc())
    assert "\\section{Contents}" not in tex
    # but the model itself must be untouched — 634/646's ruling
    doc = _toc_doc()
    assert any(o.props.get("caption") == "Contents"
               for o in doc.objects_of_type("Section"))


def test_the_toc_line_formula_fragment_is_not_emitted_standalone():
    tex = _proj().project(_toc_doc())
    assert "$T=15$" not in tex


def test_real_content_after_the_toc_region_is_untouched():
    tex = _proj().project(_toc_doc())
    assert "\\section{Introduction}" in tex
    assert "Real prose." in tex


def test_toc_region_suppressed_counts_the_section_and_the_formula():
    p = _proj()
    p.project(_toc_doc())
    counts = p._toc_region_suppressed
    assert counts.get("Section") == 1, counts
    assert counts.get("Formula") == 1, counts


def test_a_formula_outside_the_toc_range_is_not_suppressed():
    """A Formula anchored on a line the Toc's own realization does NOT span
    must render normally — suppression is evidence (Toc's claimed anchors),
    never a guess by position or by neighbouring title."""
    d = _toc_doc()
    other = d.ensure_stream("mathpix_lines").append(text="x^2", type="text")
    real_formula = DocObject(type="Formula", props={"latex": "x^2", "flow_index": 4})
    real_formula.add_realization(Realization(
        stream="mathpix_lines", start=other, end=other, role="surface"))
    d.add(real_formula)
    tex = _proj().project(d)
    assert "$x^2$" in tex


def test_an_inline_toc_line_formula_is_also_suppressed():
    """penev_A's real shape: a Formula on a TOC line usually carries only an
    INLINE (sub-anchor offset/length) realization — no Paragraph claims a
    TOC line to transclude it FROM. 634/646's block-only "claim" rule does
    not apply here (a different question, the INPUT side); the OUTPUT-side
    question is only "does this print standalone in the flow", and an inline
    fragment on a TOC line does exactly that unless suppressed too."""
    d = Document()
    d.meta["bibkey"] = "demo"
    mp = d.ensure_stream("mathpix_lines")
    a_container = mp.append(text="", type="table_of_contents_container")
    # a merged TOC row carrying a fused title+formula, MathPix-style, with
    # the Formula as an INLINE sub-span of that one line
    a_row = mp.append(text="3.7 SNR with the T=87 Ensemble",
                      type="table_of_contents_row")
    a_head = mp.append(text="Introduction", type="section_header")
    a_body = mp.append(text="Real prose.", type="text")

    toc = DocObject(type="Toc", props={"entries": ["3.7 SNR with the T=87 Ensemble"]})
    toc.add_realization(Realization(
        stream="mathpix_lines", start=a_container, end=a_row, role="surface"))
    d.add(toc)

    inline_frag = DocObject(type="Formula", props={"latex": "T=87", "flow_index": 0})
    inline_frag.add_realization(Realization(
        stream="mathpix_lines", start=a_row, end=a_row, role="surface",
        props={"offset": 14, "length": 4}))
    d.add(inline_frag)

    sec = DocObject(type="Section", props={"level": 1, "caption": "Introduction",
                                           "flow_index": 1})
    sec.add_realization(Realization(
        stream="mathpix_lines", start=a_head, end=a_head, role="surface"))
    d.add(sec)
    para = DocObject(type="Paragraph", props={"text": "Real prose.", "flow_index": 2})
    para.add_realization(Realization(
        stream="mathpix_lines", start=a_body, end=a_body, role="surface"))
    d.add_child(sec, para)

    p = _proj()
    tex = p.project(d)
    assert "$T=87$" not in tex
    assert p._toc_region_suppressed.get("Formula") == 1
    assert "\\section{Introduction}" in tex and "Real prose." in tex


def test_a_page_container_touching_the_toc_span_is_never_counted():
    """`Page` is 634/646's own CONTAINER exclusion (a Page's realization spans
    its whole page BY CONSTRUCTION, not by claim) reused here. A Page is also
    not a flow content type at all (`common.CONTENT_TYPES`), so it was never
    going to render standalone — counting it as suppressed would report an
    action that never happens (rule 11)."""
    d = _toc_doc()
    mp = d.streams["mathpix_lines"]
    page = DocObject(type="Page", props={"page": 1})
    page.add_realization(Realization(
        stream="mathpix_lines", start=mp.anchors[0], end=mp.anchors[-1],
        role="surface"))
    d.add(page)
    p = _proj()
    p.project(d)
    assert "Page" not in p._toc_region_suppressed


def test_no_toc_object_means_no_tableofcontents_and_nothing_suppressed():
    """No Toc in the model: the projector must not invent one, and a Section
    literally titled 'Contents' — with no Toc to justify replacing it — is
    left exactly as the model states it."""
    d = Document(); d.meta["bibkey"] = "x"
    sec = DocObject(type="Section", props={
        "level": 1, "caption": "Contents", "flow_index": 0})
    d.add(sec)
    p = _proj()
    tex = p.project(d)
    assert "\\tableofcontents" not in tex
    assert "\\section{Contents}" in tex
    assert p._toc_region_suppressed == {}
