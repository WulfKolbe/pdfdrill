"""811 — two defects a consumer of 1-s2.0-S2590118425000565-main reported.

1. Section captions truncated at the first INNER brace (1,065 in 238 docs).
2. List items duplicated inside paragraphs (167,312 lines in 899 of 1,500 docs).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.modules.header import caption_in_braces, HeaderProcessor  # noqa: E402


# ── 1. the caption ───────────────────────────────────────────────────────────

def test_caption_survives_inline_math():
    r"""The reported case, verbatim from the document's own lines.json. `[^}]*`
    cut it at the `}` closing `\mathrm{RQ`, yielding the caption `\(\mathrm{RQ`."""
    display = (r"\section*{\(\mathrm{RQ}_{1}\). Can the netskip architecture "
               r"overcome the mentioned issues}")
    cmd, caption = HeaderProcessor._parse_header("", display)
    assert cmd == "section"
    assert caption == (r"\(\mathrm{RQ}_{1}\). Can the netskip architecture "
                       r"overcome the mentioned issues")
    assert caption != r"\(\mathrm{RQ"


@pytest.mark.parametrize("display,want", [
    (r"\section{Plain}", "Plain"),
    (r"\section*{Starred}", "Starred"),
    (r"\subsection{\emph{Nested} braces}", r"\emph{Nested} braces"),
    (r"\section{\textbf{a}\textit{b}}", r"\textbf{a}\textit{b}"),
    (r"\section{deep {{{nesting}}} here}", "deep {{{nesting}}} here"),
    (r"\section{}", ""),
])
def test_balanced_extraction(display, want):
    assert HeaderProcessor._parse_header("", display)[1] == want


def test_an_unterminated_section_falls_back_to_the_lines_own_text():
    r"""Not hypothetical: MathPix emits a bare `\section*{…` with no closing
    brace on a header whose text it cut — 77 of the 1,065. The line's `text`
    carries the caption in the clear, so it wins over the unclosed remainder."""
    display = "\n\n" + r"\section*{\(\mathrm{RQ}_{2}\). How do netskip compare"
    text = r"\(\mathrm{RQ}_{2}\). How do netskip compare"
    assert caption_in_braces(display, display.index("{") + 1) is None
    assert HeaderProcessor._parse_header(text, display) == ("section", text)


def test_an_unterminated_section_with_no_text_keeps_the_remainder():
    display = r"\section*{Something cut off"
    assert HeaderProcessor._parse_header("", display) == ("section", "Something cut off")


def test_the_level_still_comes_from_the_command():
    assert HeaderProcessor._parse_header("", r"\subsubsection{X}")[0] == "subsubsection"


# ── 2. the duplication ───────────────────────────────────────────────────────

BK = "t"


def _doc_from_lines(lines):
    from docmodel.core import Document
    from docmodel.modules.page import ingest_lines_json
    doc = Document()
    doc.meta["bibkey"] = BK
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i",
                                       "lines": lines}]})
    return doc


def _doc_with_a_typed_list():
    """A `list_item` container with two text children — MathPix's real shape:
    the container carries the structure and empty text, the children the words."""
    return _doc_from_lines([
        {"id": "L1", "type": "text", "text": "Prose before the list."},
        {"id": "C1", "type": "list_item", "text": "",
         "children_ids": ["K1", "K2"]},
        {"id": "K1", "type": "text", "parent_id": "C1",
         "text": "the cost of deploying the infrastructure",
         "text_display": r"\begin{itemize}\item[1.] the cost of deploying the infrastructure"},
        {"id": "K2", "type": "text", "parent_id": "C1",
         "text": "may be unaffordable for non AAA publishers;"},
        {"id": "L2", "type": "text", "text": "Prose after the list."},
    ])


def _run(doc):
    from docmodel.base_module import ModuleConfig
    from docmodel.modules.list_items import ListProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    for cls in (ListProcessor, ParagraphProcessor):
        cls(ModuleConfig(title=cls.__name__, classname=cls.__name__), BK).process_document(doc)
    return doc


def test_a_list_items_words_are_not_also_in_a_paragraph():
    doc = _run(_doc_with_a_typed_list())
    items = [o for o in doc.objects.values() if o.type == "ListItem"]
    paras = [o for o in doc.objects.values() if o.type == "Paragraph"]
    assert len(items) == 1
    assert "cost of deploying" in items[0].props["content"]
    for p in paras:
        assert "cost of deploying" not in str(p.props.get("text") or "")
        assert "unaffordable" not in str(p.props.get("text") or "")


def test_the_prose_around_the_list_still_becomes_paragraphs():
    """The fix must not weld or swallow the surrounding prose — 248's defect in
    the other direction."""
    doc = _run(_doc_with_a_typed_list())
    bodies = [str(o.props.get("text") or "")
              for o in doc.objects.values() if o.type == "Paragraph"]
    assert any("Prose before" in b for b in bodies)
    assert any("Prose after" in b for b in bodies)
    assert not any("Prose before" in b and "Prose after" in b for b in bodies)


def test_a_container_that_yields_no_content_keeps_its_children_as_prose():
    """The stamp is only for containers that PRODUCED a ListItem. An empty
    container must not silently delete its children's text."""
    doc = _doc_from_lines([
        {"id": "C1", "type": "list_item", "text": "", "children_ids": ["K1"]},
        {"id": "K1", "type": "math", "parent_id": "C1", "text": ""},
        {"id": "K2", "type": "text", "text": "Ordinary prose."},
    ])
    _run(doc)
    bodies = [str(o.props.get("text") or "")
              for o in doc.objects.values() if o.type == "Paragraph"]
    assert any("Ordinary prose" in b for b in bodies)


# ── 3. headings MathPix typed `text` ─────────────────────────────────────────

def _sections(doc):
    from docmodel.base_module import ModuleConfig
    from docmodel.modules.header import HeaderProcessor
    HeaderProcessor(ModuleConfig(title="H", classname="H"), BK).process_document(doc)
    return [o for o in doc.objects.values() if o.type == "Section"]


def _hdr(text):
    return {"type": "section_header", "text": text, "text_display": text}


def test_a_back_matter_label_typed_as_text_becomes_a_section():
    """Reported: with no `References` heading the whole bibliography is prose.
    Measured: 807 such lines in 275 of 1,500 documents."""
    doc = _doc_from_lines([
        _hdr("1. Introduction"),
        {"type": "text", "text": "Prose."},
        {"type": "text", "text": "References"},
        {"type": "text", "text": "[1] S.M. Steinberg, Videogame Marketing and PR, 2007."},
    ])
    caps = [s.props["caption"] for s in _sections(doc)]
    assert "References" in caps
    basis = {s.props["caption"]: s.props["level_basis"] for s in _sections(doc)}
    assert basis["References"] == "back_matter_label"


def test_a_numbered_gap_its_own_document_brackets_becomes_a_section():
    """4.1 and 4.3 are real headings, so a `text` line starting 4.2 between them
    is a heading — the document is the witness, not a font-size guess."""
    doc = _doc_from_lines([
        _hdr("4.1 Experimental setup"),
        {"type": "text", "text": "Prose."},
        {"type": "text", "text": "4.2. Results"},
        {"type": "text", "text": "More prose."},
        _hdr("4.3. Discussion"),
    ])
    s = {x.props["caption"]: x.props for x in _sections(doc)}
    assert "4.2. Results" in s
    assert s["4.2. Results"]["level_basis"] == "number_series_gap"
    assert s["4.2. Results"]["level"] == 2


def test_one_neighbour_alone_is_not_enough():
    """A sentence beginning with a number can supply one neighbour; only the
    series supplies both."""
    doc = _doc_from_lines([
        _hdr("4.1 Experimental setup"),
        {"type": "text", "text": "4.2. Results"},
    ])
    assert "4.2. Results" not in [s.props["caption"] for s in _sections(doc)]


def test_a_long_line_is_a_sentence_not_a_heading():
    doc = _doc_from_lines([
        _hdr("4.1 A"), _hdr("4.3 C"),
        {"type": "text", "text": "4.2. " + "x" * 120},
    ])
    assert len(_sections(doc)) == 2


def test_a_label_the_document_already_has_a_heading_for_is_not_duplicated():
    doc = _doc_from_lines([
        _hdr("References"),
        {"type": "text", "text": "References"},
    ])
    assert [s.props["caption"] for s in _sections(doc)] == ["References"]


def test_a_promoted_heading_is_not_also_a_paragraph():
    doc = _doc_from_lines([
        _hdr("1. Introduction"),
        {"type": "text", "text": "References"},
        {"type": "text", "text": "[1] Steinberg, Videogame Marketing and PR, 2007."},
    ])
    from docmodel.base_module import ModuleConfig
    from docmodel.modules.header import HeaderProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    for cls in (HeaderProcessor, ParagraphProcessor):
        cls(ModuleConfig(title="M", classname="M"), BK).process_document(doc)
    bodies = [str(o.props.get("text") or "")
              for o in doc.objects.values() if o.type == "Paragraph"]
    assert not any(b.strip().startswith("References") for b in bodies)


# ── 4. the bibliography is not a lettered list ───────────────────────────────

def test_an_author_initial_is_not_a_list_marker():
    """`D. Al-Jumeily, A. Hussain, …` was a lettered ListItem with marker `D.`.
    Measured: 6,153 such lines in 442 of 1,500 documents."""
    doc = _doc_from_lines([
        _hdr("1. Introduction"),
        {"type": "text", "text": "a. a genuine lettered item"},
        _hdr("References"),
        {"type": "text",
         "text": "D. Al-Jumeily, A. Hussain, H. Tawfik, J. Hind (Eds.), Proceedings."},
    ])
    _run(doc)
    items = [o for o in doc.objects.values() if o.type == "ListItem"]
    assert any("genuine lettered item" in str(o.props["content"]) for o in items)
    assert not any("Al-Jumeily" in str(o.props["content"]) for o in items)


def test_the_suppression_ends_at_the_next_heading():
    """An appendix after the references still gets its lexical lists."""
    doc = _doc_from_lines([
        _hdr("References"),
        {"type": "text", "text": "D. Al-Jumeily, A. Hussain, Proceedings."},
        _hdr("Appendix A"),
        {"type": "text", "text": "b. an item in the appendix"},
    ])
    _run(doc)
    items = [str(o.props["content"]) for o in doc.objects.values() if o.type == "ListItem"]
    assert any("item in the appendix" in c for c in items)
    assert not any("Al-Jumeily" in c for c in items)


def test_a_document_with_no_bibliography_is_unaffected():
    doc = _doc_from_lines([
        _hdr("1. Introduction"),
        {"type": "text", "text": "a. first"},
        {"type": "text", "text": "b. second"},
    ])
    _run(doc)
    items = [o for o in doc.objects.values() if o.type == "ListItem"]
    assert len(items) == 2


def test_a_lower_case_label_with_a_period_is_a_sentence_tail():
    """`references.` is in the corpus (1905.08669) and is the end of a sentence
    that broke across lines, not a heading. The vocabulary alone would promote
    it; capitalisation is what separates them."""
    doc = _doc_from_lines([
        _hdr("1. Introduction"),
        {"type": "text", "text": "references."},
    ])
    assert [s.props["caption"] for s in _sections(doc)] == ["1. Introduction"]


def test_an_all_caps_label_is_still_a_heading():
    doc = _doc_from_lines([
        _hdr("1. Introduction"),
        {"type": "text", "text": "BIBLIOGRAPHY"},
    ])
    assert "BIBLIOGRAPHY" in [s.props["caption"] for s in _sections(doc)]
