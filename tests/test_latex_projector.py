"""
LaTeXProjector — the LaTeX analog of the Markdown projector: a drilled Document
projected to a compilable `.tex` (sections, prose, display equations, inline
formulas, tables). This is the OUTPUT direction; `injectlatex` is the input one
(pull the author's source in). `pdfdrill latex` drives this.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
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
