r"""Math on a table cell, a section heading, a title, a TOC entry or a figure
label is never a transclusion.

The requirement, in the words it was given in: "transclusion of math
expression is not performed on any kind of table, section heading, titles,
toc entries, figure and image labels". Each family below is asserted by its
own name, at each of the four sites that could reintroduce it:

  1. `FormulaProcessor.find_items`  -- the object is not created
  2. `TiddlyWikiProjector`          -- an OLD model's occurrence is not
                                       substituted into prose
  3. `inlinectx.first_occurrences`  -- a forbidden line is not the context an
                                       inline formula inherits
  4. `reports.from_document`        -- a table-only reading is not published

Site 1 is the fix; sites 2-4 are what keeps the 1,367 models already on disk
(built before the gate) from publishing the same rows anyway.
"""
import json

import pytest

from docmodel.core import Document, DocObject, Realization
from docmodel import line_types as lt
from docmodel.modules.formula import FormulaProcessor
from docmodel.base_module import ModuleConfig
from docmodel.modules.page import ingest_lines_json
from pdfdrill import inlinectx
from pdfdrill.reports.from_document import build_rows

BK = "T"

#: One line type per family the requirement names, plus the text of a line
#: carrying inline math. `_MATH_RE` sees `\( ... \)` and `$ ... $` alike.
FORBIDDEN_SAMPLE = [
    ("table", "simple_cell"),
    ("table", "table"),
    ("table", "complex_cell"),
    ("table", "table_row"),
    ("section_header", "section_header"),
    ("title", "title"),
    ("toc", "table_of_contents_item"),
    ("toc", "table_of_contents_row"),
    ("figure_label", "figure_label"),
]

#: Line types that DO host an inline formula. `list_item` and `quote` are
#: prose; `footnote` and `code` are lines whose math the requirement did not
#: name, and widening the refusal to them would be a different change.
HOSTING_SAMPLE = ["text", "list_item", "quote", "footnote", "code",
                  "pseudocode", "page_info", "authors"]


def _module(cls, bibkey=BK):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__), bibkey)


def _doc_from_lines(lines):
    doc = Document()
    doc.meta["bibkey"] = BK
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i",
                                       "lines": lines}]})
    return doc


def _line(ltype, text, **extra):
    d = {"type": ltype, "text": text, "text_display": text}
    d.update(extra)
    return d


# ---------------------------------------------------------------- the set

@pytest.mark.parametrize("fam,ltype", FORBIDDEN_SAMPLE)
def test_each_named_family_is_in_the_set_under_its_own_name(fam, ltype):
    assert ltype in lt.NO_TRANSCLUDE
    assert lt.family(ltype) == fam
    assert lt.hosts_transclusion(ltype) is False


@pytest.mark.parametrize("ltype", HOSTING_SAMPLE)
def test_a_prose_line_still_hosts(ltype):
    assert ltype not in lt.NO_TRANSCLUDE
    assert lt.family(ltype) is None
    assert lt.hosts_transclusion(ltype) is True


def test_the_flat_set_is_exactly_the_union_of_the_named_families():
    union = set()
    for members in lt.NON_PROSE_HOSTS.values():
        union |= set(members)
    assert union == set(lt.NO_TRANSCLUDE)
    assert set(lt.NON_PROSE_HOSTS) == {"table", "section_header", "title",
                                       "toc", "figure_label"}


# -------------------------------------------- site 1: no object is created

@pytest.mark.parametrize("fam,ltype", FORBIDDEN_SAMPLE)
def test_no_formula_object_is_created_from_a_forbidden_line(fam, ltype):
    doc = _doc_from_lines([_line(ltype, r"cell \(x^2\) here")])
    _module(FormulaProcessor).process_document(doc)
    assert list(doc.objects_of_type("Formula")) == []


def test_a_formula_object_is_still_created_from_prose():
    doc = _doc_from_lines([_line("text", r"the energy \(x^2\) is")])
    _module(FormulaProcessor).process_document(doc)
    assert [f.props["latex"] for f in doc.objects_of_type("Formula")] == ["x^{2}".replace("^{2}", "^2")]


def test_the_refusal_is_per_occurrence_not_per_reading():
    """The same LaTeX in a cell AND a sentence keeps its sentence.

    `FormulaProcessor` de-duplicates by value, so a per-OBJECT refusal would
    delete a real inline formula because it also happens to appear in a
    table. kohlhase-omdoc's `\\overline{\\mathcal{C}}` is exactly this: three
    occurrences inside the `Fig. 15.12` tabular and one in the sentence that
    introduces it.
    """
    doc = _doc_from_lines([
        _line("simple_cell", r"\(x^2\)"),
        _line("text", r"we set \(x^2\) below"),
    ])
    _module(FormulaProcessor).process_document(doc)
    (f,) = list(doc.objects_of_type("Formula"))
    surfaces = [r for r in f.realizations
                if r.stream == "mathpix_lines" and r.role == "surface"]
    assert len(surfaces) == 1, "the cell occurrence was realized too"
    assert lt.line_type_at(doc, surfaces[0].start) == "text"


def test_the_skip_is_counted_by_family_so_it_is_visible():
    doc = _doc_from_lines([_line("simple_cell", r"\(x^2\)"),
                           _line("table_of_contents_item", r"\(y\)")])
    mod = _module(FormulaProcessor)
    mod.process_document(doc)
    assert mod.counters.get("formula_lines_skipped_table") == 1
    assert mod.counters.get("formula_lines_skipped_toc") == 1


# ------------------------------- site 2: an old model is not substituted

def test_only_title_of_the_forbidden_families_can_reach_a_paragraph():
    """WHICH forbidden family the projector gate actually has to catch.

    A substitution is only ever applied inside `_transclude_paragraph`, so a
    forbidden line can produce a transclusion only if `ParagraphProcessor`
    admits it as prose. It admits exactly `text`, `title` and `quote`
    (`paragraph._PROSE_TYPES`) --- so of the 17 forbidden types, `title` is
    the one and only reachable case, and the projector gate is asserted
    below on `title` for that reason rather than on a family it could never
    have seen. This test is the claim's own tripwire: add a forbidden type
    to `_PROSE_TYPES` and it fails, saying the coverage argument moved.
    """
    from docmodel.modules.paragraph import _PROSE_TYPES
    assert set(_PROSE_TYPES) & set(lt.NO_TRANSCLUDE) == {"title"}


def _legacy_doc(ltype):
    """A Document shaped like a model built BEFORE the site-1 gate: the
    Formula object exists and is realized on a line the paragraph covers."""
    from docmodel.modules.page import PageProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    from docmodel.modules.document_flow import DocumentFlowProcessor
    text = r"we set \(x^2\) below"
    doc = _doc_from_lines([_line(ltype, text)])
    for cls in (PageProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    _module(DocumentFlowProcessor).process_objects(doc)
    stream = doc.stream("mathpix_lines")
    anchor = stream.anchors[0]
    f = DocObject(id="f1", type="Formula",
                  props={"latex": "x^2", "flow_index": 1, "bibkey": BK})
    f.add_realization(Realization(
        stream="mathpix_lines", start=anchor, end=anchor, role="surface",
        props={"offset": text.index(r"\("), "length": len(r"\(x^2\)")}))
    doc.add(f)
    return doc


def _project(doc):
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    from docops.base import OperatorConfig
    op = TiddlyWikiProjector(OperatorConfig(
        op="projector", classname="TiddlyWikiProjector", params={}))
    return json.loads(op.project(doc))


def test_a_legacy_object_on_a_title_line_is_not_substituted():
    arr = _project(_legacy_doc("title"))
    assert not any("||FO}}" in (t.get("text") or "") for t in arr)


def test_a_legacy_object_on_a_prose_line_is_still_substituted():
    """The control: without it, the test above passes for the wrong reason
    (an empty paragraph, a projector that never ran, a typo in the marker)."""
    arr = _project(_legacy_doc("text"))
    assert any("||FO}}" in (t.get("text") or "") for t in arr)


# --------------------------- site 3: the host line a formula inherits from

def _spans_file(tmp_path, lines):
    p = tmp_path / (BK + ".lines.json")
    p.write_text(json.dumps({"pages": [{"lines": lines}]}))
    return p


def test_the_prose_occurrence_wins_over_an_earlier_forbidden_one(tmp_path):
    p = _spans_file(tmp_path, [
        {"type": "table", "text": r"\(\alpha\)", "confidence": 0.10,
         "region": {"top_left_x": 1, "top_left_y": 1, "width": 900,
                    "height": 700}},
        {"type": "text", "text": r"we write \(\alpha\) for", "confidence": 0.99,
         "region": {"top_left_x": 2, "top_left_y": 2, "width": 800,
                    "height": 40}},
    ])
    first = inlinectx.first_occurrences(inlinectx.load_spans(str(p)))
    ctx = inlinectx.context_of(first.get(r"\alpha"))
    assert ctx["line_type"] == "text"
    assert ctx["confidence"] == 0.99
    assert ctx["height"] == 40, "inherited the table block's geometry"


def test_a_reading_that_occurs_only_on_forbidden_lines_has_no_host(tmp_path):
    p = _spans_file(tmp_path, [
        {"type": "figure_label", "text": r"Fig. 3 \(\beta\)", "confidence": 0.5},
        {"type": "simple_cell", "text": r"\(\beta\)", "confidence": 0.4},
    ])
    first = inlinectx.first_occurrences(inlinectx.load_spans(str(p)))
    assert first == {}
    assert inlinectx.context_of(first.get(r"\beta")) == {}


# ------------------------------------- site 4: what a report publishes

def _report_doc(anchor_types):
    doc = _doc_from_lines([_line(t, r"\(x^2\)") for t in anchor_types])
    stream = doc.stream("mathpix_lines")
    f = DocObject(id="f1", type="Formula",
                  props={"latex": "x^2", "flow_index": 1, "bibkey": BK})
    for a in stream.anchors:
        f.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                      role="surface",
                                      props={"offset": 0, "length": 8}))
    doc.add(f)
    return doc


@pytest.mark.parametrize("fam,ltype", FORBIDDEN_SAMPLE)
def test_a_table_only_reading_is_not_published(fam, ltype):
    rows = build_rows(_report_doc([ltype]), BK)["formula"]
    assert rows == []


def test_a_reading_that_is_also_in_prose_is_still_published():
    rows = build_rows(_report_doc(["simple_cell", "text"]), BK)["formula"]
    assert [r.identifier for r in rows] == ["T_FO0001"]


def test_a_formula_with_no_surface_realization_is_published():
    """A synthetic formula built from paragraph text has no line anchor at
    all. Absence of evidence is not a refusal."""
    doc = _doc_from_lines([_line("text", "prose")])
    doc.add(DocObject(id="f1", type="Formula",
                      props={"latex": "x^2", "flow_index": 1, "bibkey": BK}))
    assert [r.identifier for r in build_rows(doc, BK)["formula"]] == ["T_FO0001"]


# =====================================================================
# 676 --- the review's findings, each pinned by the case that exposed it
# =====================================================================

def _projected(lines):
    """Run the real pipeline over `lines` and return the tiddler array."""
    from docmodel.modules.page import PageProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    from docmodel.modules.document_flow import DocumentFlowProcessor
    doc = _doc_from_lines(lines)
    for cls in (PageProcessor, FormulaProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    _module(DocumentFlowProcessor).process_objects(doc)
    return doc, _project(doc)


# --- B1: a caption is a figure label whatever MathPix typed its lines -----

CAPTION = _line("text", r"Figure 15.12: the relation \(x^{2}\) between them")


def test_a_caption_typed_as_plain_text_is_not_transcluded():
    r"""The review's first blocking finding.

    MathPix types most captions `text`, not `figure_label` --- 11,758
    caption-start lines carrying 2,810 inline-math occurrences, against
    2,382 on `figure_label`. A type-based rule misses the larger half.
    """
    doc, arr = _projected([CAPTION])
    assert not any("||FO}}" in (t.get("text") or "") for t in arr)


def test_the_caption_paragraph_is_what_identifies_the_span():
    """`ParagraphProcessor` stamps it; nothing here re-detects it."""
    doc, _arr = _projected([CAPTION])
    kinds = {p.props.get("kind") for p in doc.objects_of_type("Paragraph")}
    assert "caption" in kinds
    assert lt.caption_anchors(doc), "the caption's anchors were not found"


def test_a_caption_row_is_not_published():
    doc, _arr = _projected([CAPTION])
    assert build_rows(doc, BK)["formula"] == []


def test_an_ordinary_paragraph_beside_a_caption_still_transcludes():
    """The control. Without it, the three tests above pass for a projector
    that simply stopped substituting."""
    doc, arr = _projected([
        CAPTION,
        _line("text", r"Ordinary prose with \(y^{3}\) inside it.",
              block_num=9, par_num=9),
    ])
    assert any("||FO}}" in (t.get("text") or "") for t in arr)
    assert [r.identifier for r in build_rows(doc, BK)["formula"]]


# --- B2: a title welded to a text line ------------------------------------

def test_a_title_welded_to_a_text_line_still_refuses_its_math():
    r"""The review's second blocking finding.

    `ParagraphProcessor` welds consecutive {text, title, quote} lines
    sharing a (block_num, par_num) group into ONE Paragraph. The first gate
    refused the catch-all only when EVERY anchor was forbidden, so a welded
    title kept the pass and its `\(...\)` came back as a synthetic FOX ---
    a title's math transcluded or not depending on line grouping.
    """
    doc, arr = _projected([
        _line("title", r"A simpler representation for \(R(4,4)\)",
              block_num=1, par_num=1),
        _line("text", "University of Waterloo Technical Report",
              block_num=1, par_num=1),
    ])
    body = " ".join(t.get("text") or "" for t in arr)
    assert "||FO}}" not in body
    assert "FOX" not in body


def test_the_text_half_of_a_welded_paragraph_keeps_its_own_math():
    r"""Per LINE, not per paragraph, and the two halves differ VISIBLY.

    The prose line's math becomes a transclusion --- a marker naming a
    Formula tiddler. The title's math is RENDERED IN PLACE by
    `mathdelims` (676/675): a `<$latex .../>` widget, which is not a
    transclusion and creates no object, so the refusal holds while the
    reader still sees typeset mathematics instead of `\(R(4,4)\)`.
    """
    doc, arr = _projected([
        _line("title", r"Heading with \(R(4,4)\)", block_num=1, par_num=1),
        _line("text", r"and prose with \(z^{5}\) in it", block_num=1,
              par_num=1),
    ])
    para = next(t for t in arr if "paragraph" in (t.get("tags") or ""))
    assert "||FO}}" in para["text"], para["text"]
    assert "<$latex text=\"R(4,4)\"" in para["text"], para["text"]
    assert r"\(R(4,4)\)" not in para["text"], "left in MathPix's delimiters"


def test_a_caption_renders_its_math_in_place_rather_than_transcluding_it():
    """The same pairing for the caption case: refused as a transclusion,
    rendered as mathematics."""
    _doc, arr = _projected([CAPTION])
    body = " ".join(t.get("text") or "" for t in arr)
    assert "||FO}}" not in body
    assert '<$latex text="x^{2}"' in body, body


def test_no_mask_character_ever_reaches_a_tiddler():
    """The mask is private. A leak would be invisible in a diff and
    visible in the wiki."""
    doc, arr = _projected([
        _line("title", r"Heading with \(R(4,4)\)", block_num=1, par_num=1),
        _line("text", r"and prose with \(z^{5}\)", block_num=1, par_num=1),
        CAPTION,
    ])
    for t in arr:
        for v in t.values():
            if isinstance(v, str):
                assert "\x00" not in v, t.get("title")


# --- B3: the span scan and the model must read the same field -------------

def test_the_host_line_scan_reads_the_field_the_model_was_built_from(tmp_path):
    r"""A `diagram` line carries `text == ""` and everything in
    `text_display`. Scanning `text` alone made every span on such a line
    invisible, so a formula built from one lost its host line --- 27
    published rows, and "rows with no host line" went 33 -> 44."""
    p = tmp_path / (BK + ".lines.json")
    p.write_text(json.dumps({"pages": [{"lines": [
        {"type": "diagram", "text": "",
         "text_display": r"caption \(\gamma\) here", "confidence": 0.8}]}]}))
    first = inlinectx.first_occurrences(inlinectx.load_spans(str(p)))
    assert r"\gamma" in first
    assert inlinectx.context_of(first[r"\gamma"])["line_type"] == "diagram"


# --- B5: the LaTeX lane --------------------------------------------------

def _latex_body(doc) -> str:
    """The typeset BODY only.

    The projection also embeds every Formula in a `readarray` data file
    (`\\begin{filecontents*}{formulas.dat}`) that `\\Expr{i}` indexes into.
    A suppressed formula stays in that array on purpose: the array is
    positional, so dropping an entry renumbers every `\\Expr` after it. An
    unreferenced entry typesets nothing, which is the property that matters
    here --- so this reads the document body, where "prints standalone" is
    a question that can actually be asked.
    """
    from docops.projectors.latex import LaTeXProjector
    from docops.base import OperatorConfig
    op = LaTeXProjector(OperatorConfig(op="projector",
                                       classname="LaTeXProjector", params={}))
    out = op.project(doc)
    return out.split("\\begin{document}", 1)[1]


def test_a_refused_formula_does_not_print_standalone_in_the_latex_lane():
    """The sixth path. A standalone `$x^2$` block is not a transclusion,
    but it is the same duplicate on a shipped surface, and task 635 already
    treated it as the same defect (for the TOC only)."""
    assert "x^2" not in _latex_body(_report_doc(["simple_cell"]))


def test_a_caption_formula_does_not_print_standalone_in_the_latex_lane():
    r"""The caption's OWN text still prints --- that is the caption, and it
    carries its math as source. What must not appear is the SECOND,
    standalone copy the Formula object would render as `$x^{2}$`."""
    doc, _arr = _projected([CAPTION])
    body = _latex_body(doc)
    assert r"\(x^{2}\)" in body, "the caption itself stopped printing"
    assert "$x^{2}$" not in body, "the Formula printed a standalone duplicate"


def test_a_prose_formula_still_prints_in_the_latex_lane():
    """The control."""
    assert "x^2" in _latex_body(_report_doc(["text"]))


# --- B7/B8: the set's own claims -----------------------------------------

def test_column_is_not_claimed_to_be_a_table():
    """`column` is a page-layout column (`paragraph.py:41`: "sidenotes"),
    not any kind of table. It was in the table family and is not."""
    assert "column" not in lt.NO_TRANSCLUDE
    assert lt.family("column") is None
    assert "table_column" in lt.NON_PROSE_HOSTS["table"]


def test_the_coverage_tripwire_covers_content_not_only_type():
    r"""676 (review B8). The first tripwire asserted
    `_PROSE_TYPES & NO_TRANSCLUDE == {"title"}` --- "no forbidden TYPE
    reaches a paragraph". The real exposure was forbidden CONTENT under a
    permitted type (a caption typed `text`), which that check cannot see.
    This asserts both halves: the type half, and that the content half has
    a gate at all."""
    from docmodel.modules.paragraph import _PROSE_TYPES, _CAPTION_START
    assert set(_PROSE_TYPES) & set(lt.NO_TRANSCLUDE) == {"title"}
    # the content half: the caption detector exists and the span helper
    # reads the stamp it produces
    assert _CAPTION_START.match("Figure 15.12: x")
    doc, _arr = _projected([CAPTION])
    assert lt.caption_anchors(doc)
