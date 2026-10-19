r"""The content half of the model lane: Markdown -> typed printed-line items.

Pure and total — a string in, items out — which is the whole reason it is a
separate module: the geometry half needs a 400-dpi render, and the paid half
needs money from a metered account. Everything asserted here is free.

The shapes under test are MathPix's, read off two bought readings of documents
pdfdrill already owns. Where a test says MEASURED it means that: the reference
reading does it that way, and a comment in the source names the count.
"""
from __future__ import annotations

from pdfdrill import pagemd


def types_of(md: str) -> list[str]:
    return [it.type for it in pagemd.items(md)]


def texts_of(md: str) -> list[str]:
    return [it.text for it in pagemd.items(md)]


# ── the type vocabulary is not ours to invent ──────────────────────────────

def test_every_type_emitted_is_one_the_document_model_knows():
    """A reader that invents a type puts its lines outside every gate that
    reads a type — the transclusion gate, the caption anchors, the furniture
    checks — and the line then fails silently, which is the failure class
    `line_types` exists to prevent."""
    from docmodel import line_types
    known = set()
    for fam in line_types.NON_PROSE_HOSTS.values():
        known |= set(fam)
    # the prose types the gate permits rather than forbids
    known |= {"text", "math", "footnote", "list_item", "authors", "equation"}
    unknown = pagemd.KNOWN_TYPES - known
    assert not unknown, f"types no reader downstream knows: {sorted(unknown)}"


# ── page furniture ─────────────────────────────────────────────────────────

def test_the_furniture_comment_becomes_two_page_info_lines():
    """MEASURED: MathPix emits the folio and the running head as TWO lines
    with separate boxes, because they are printed at opposite ends of one
    row. One line carrying both would be a box spanning the row."""
    its = pagemd.items("<!-- page 5 | Zusammensetzung von Gruppen. II. -->\n")
    assert [it.type for it in its] == ["page_info", "page_info"]
    assert [it.text for it in its] == ["5", "Zusammensetzung von Gruppen. II."]


def test_a_comment_without_the_page_n_shape_stays_one_line():
    its = pagemd.items("<!-- THE FOUNDATIONS OF GEOMETRY -->\n")
    assert [(it.type, it.text) for it in its] == [
        ("page_info", "THE FOUNDATIONS OF GEOMETRY")]


def test_the_running_head_printed_a_second_time_as_text_is_dropped():
    """The prompt asks for it once, in the comment. Models repeat it anyway,
    and a repeat typed as prose joins the paragraph below it — which is the
    paragraph-join defect, arrived at from the reader's side."""
    md = ("<!-- page 5 | Zusammensetzung von Gruppen. II. -->\n\n"
          "**Zusammensetzung von Gruppen. II.**        5\n\n"
          "Ebensowenig ist eine mehrfache Wurzel\n")
    its = pagemd.items(md)
    assert [it.type for it in its] == ["page_info", "page_info", "text"]
    assert its[2].text.startswith("Ebensowenig")


def test_a_thematic_break_the_model_invented_is_not_printed_text():
    its = pagemd.items("Von\n\n***\n\nDer vorliegende Theil\n")
    assert [it.type for it in its] == ["text", "text"]


# ── display math and its number ────────────────────────────────────────────

def test_a_display_becomes_math_with_mathpix_delimiters():
    its = pagemd.items("$$a+b=c$$\n")
    assert its[0].type == "math"
    assert its[0].text == "\\[\na+b=c\n\\]"


def test_a_tagged_number_is_lifted_into_its_own_equation_number_line():
    """MathPix emits the number as a SEPARATE line with its own box, and
    pdfdrill's equation-number recovery reads it there."""
    its = pagemd.items("$$x = y, \\tag{4}$$\n")
    assert [it.type for it in its] == ["math", "equation_number"]
    assert its[1].text == "(4)"
    assert its[1].numbers is its[0], "the number does not point at its display"
    assert "\\tag" not in its[0].text, "the number is still inside the body"


def test_a_number_printed_at_the_left_margin_is_lifted_too():
    """German 19th-century practice. The body must not keep it."""
    its = pagemd.items("$$(2)\\quad (X_{r}X_{s}) = 0$$\n")
    assert [it.type for it in its] == ["math", "equation_number"]
    assert its[1].text == "(2)"
    assert its[0].text == "\\[\n(X_{r}X_{s}) = 0\n\\]"


def test_a_number_printed_at_the_right_margin_is_lifted_too():
    its = pagemd.items("$$a = b \\quad (12a)$$\n")
    assert [it.type for it in its] == ["math", "equation_number"]
    assert its[1].text == "(12a)"


def test_a_prime_on_a_number_survives():
    """A primed number is a different equation from the unprimed one."""
    its = pagemd.items("$$a=b \\tag{2'}$$\n")
    assert its[1].text == "(2')"


def test_an_unnumbered_display_gets_no_number_line():
    assert types_of("$$a=b$$\n") == ["math"]


# ── footnotes: MathPix's container shape ───────────────────────────────────

def test_a_footnote_becomes_a_container_whose_children_are_text():
    """MEASURED on both reference readings: the `footnote` line has EMPTY
    text and `children_ids`; the printed lines are its children, typed
    `text`. A reader that types the lines `footnote` and writes no
    `\\footnotetext{…}` produces footnote objects with no body — 0 bodies
    measured before the wrapper, 3 after."""
    md = ("Body text here.\n\n"
          "[^1]: Herr Engel, der die Freundlichkeit gehabt hat, eine\n"
          "Correctur der vorliegenden Arbeit zu lesen, macht mich\n")
    its = pagemd.items(md)
    assert [it.type for it in its] == ["text", "footnote", "text", "text"]
    parent = its[1]
    assert parent.text == ""
    assert parent.children == [its[2], its[3]]
    assert its[2].parent is parent and its[3].parent is parent


def test_the_footnotetext_wrapper_opens_on_the_first_child_and_closes_on_the_last():
    md = "[^1]: first line\nsecond line\nthird line\n"
    its = pagemd.items(md)
    kids = its[0].children
    assert len(kids) == 3
    assert pagemd.text_display(kids[0]).startswith("\n\n\\footnotetext{\n")
    assert pagemd.text_display(kids[1]) == "second line"
    assert pagemd.text_display(kids[2]).endswith("\n}")


def test_a_single_line_footnote_opens_and_closes_on_the_same_child():
    its = pagemd.items("[^2]: one line only\n")
    disp = pagemd.text_display(its[0].children[0])
    assert disp.startswith("\n\n\\footnotetext{\n") and disp.endswith("\n}")


def test_the_footnote_label_is_rewritten_into_the_shape_its_reader_looks_for():
    r"""`FootnoteProcessor._refnum` reads `\( { }^{n} \)`. A `[^1]:` spelling
    is invisible to it, and a footnote whose refnum never parses cannot be
    paired with the marker in the text."""
    its = pagemd.items("[^1]: the note\n")
    assert its[0].children[0].text.startswith("\\( { }^{1} \\) ")


def test_a_rule_opens_the_footnote_zone_for_a_note_continued_across_a_page():
    """A footnote continued from the previous page carries no label of its
    own — the printed rule above it is the only evidence there is."""
    md = "ordinary prose\n\n______\n\nin den obigen Ausdruecken fuer\n"
    its = pagemd.items(md)
    assert [it.type for it in its] == ["text", "footnote", "text"]


# ── section headings ───────────────────────────────────────────────────────

def test_a_number_only_heading_and_its_title_become_one_container():
    """MEASURED: 9 of 9 on the reference document. MathPix emits the pair as
    a container with empty text whose children are both lines."""
    md = "## § 16.\n\nDie einfachen Systeme der Coefficienten.\n"
    its = pagemd.items(md)
    assert [it.type for it in its] == ["section_header", "text", "text"]
    assert its[0].text == ""
    assert its[0].children == [its[1], its[2]]
    assert its[1].text == "§ 16."


def test_a_heading_with_words_in_it_stays_a_single_heading():
    its = pagemd.items("## Die Jacobischen Relationen\n\nbody\n")
    assert [it.type for it in its] == ["section_header", "text"]
    assert not its[0].children


# ── tables ─────────────────────────────────────────────────────────────────

def test_a_markdown_table_becomes_a_table_container_with_simple_cells():
    """MEASURED: MathPix emits ONE `table` line carrying the whole tabular
    plus one `simple_cell` per cell with its own box. 2,364 cells on one
    14-page document — a reader that boxes the ROW has no cell geometry."""
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    its = pagemd.items(md)
    assert [it.type for it in its] == ["table"] + ["simple_cell"] * 4
    assert its[0].children == its[1:]
    assert [c.text for c in its[1:]] == ["A", "B", "1", "2"]
    assert [c.cell for c in its[1:]] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_the_tabular_is_spelled_the_way_mathpix_spells_it():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    tabular = pagemd.items(md)[0].text
    assert tabular.startswith("\\begin{tabular}[t]{|l|l|}")
    assert "\\hline A & B \\\\" in tabular
    assert tabular.rstrip().endswith("\\end{tabular}")


def test_cells_after_the_first_share_the_first_cells_ink_row():
    """They are printed side by side on ONE row of ink."""
    its = pagemd.items("| A | B | C |\n")
    cells = its[1:]
    assert cells[0].shares is None
    assert cells[1].shares is cells[0] and cells[2].shares is cells[0]


def test_the_alignment_row_prints_nothing():
    assert types_of("| A |\n| --- |\n") == ["table", "simple_cell"]


def test_a_padded_empty_row_is_dropped():
    md = "| A |\n| --- |\n| 1 |\n|  |\n"
    cells = [it for it in pagemd.items(md) if it.type == "simple_cell"]
    assert [c.text for c in cells] == ["A", "1"]


# ── prose: paragraphs, continuation, inline math ───────────────────────────

def test_a_blank_line_starts_a_paragraph_and_shows_in_text_display():
    its = pagemd.items("first para line\nsame para\n\nnew para\n")
    assert [it.para_start for it in its] == [True, False, True]
    assert pagemd.text_display(its[0]).startswith("\n\n")
    assert not pagemd.text_display(its[1]).startswith("\n")


def test_a_line_ending_in_a_hyphen_marks_the_next_as_a_broken_word():
    its = pagemd.items("Zusammen-\nsetzung der Gruppen.\n")
    assert its[1].subtype == "continues_line_hyphen"


def test_a_line_ending_without_punctuation_marks_the_next_as_a_continuation():
    its = pagemd.items("der vorliegende Theil meiner\nUntersuchungen\n")
    assert its[1].subtype == "continues_line_no_hyphen"


def test_a_finished_sentence_leaves_the_next_line_unmarked():
    its = pagemd.items("Das ist der Satz.\nEin neuer Satz folgt\n")
    assert its[1].subtype == ""


def test_inline_math_is_converted_and_emphasis_markers_go():
    its = pagemd.items("die *Gruppe* $X_{r}f$ mit **Killing**'s Satz\n")
    assert its[0].text == "die Gruppe \\(X_{r}f\\) mit Killing's Satz"


def test_two_inline_spans_on_one_line_stay_two_spans():
    its = pagemd.items("wenn $a$ und $b$ gegeben sind\n")
    assert its[0].text == "wenn \\(a\\) und \\(b\\) gegeben sind"


def test_a_display_is_not_eaten_by_the_inline_rule():
    its = pagemd.items("$$a=b$$\n")
    assert its[0].text == "\\[\na=b\n\\]"


def test_a_figure_the_model_described_is_a_diagram_not_prose():
    its = pagemd.items("[Figure: two triangles sharing a side]\n")
    assert its[0].type == "diagram"
    assert its[0].described


def test_a_figure_label_on_its_own_line_is_a_figure_label():
    assert types_of("Fig. 9.\n") == ["figure_label"]


def test_an_equation_number_has_an_empty_text_display():
    """MEASURED: it is not part of the flowed text at all."""
    its = pagemd.items("$$a=b \\tag{1}$$\n")
    assert pagemd.text_display(its[1]) == ""


def test_an_empty_page_yields_no_items():
    assert pagemd.items("") == []
    assert pagemd.items("\n\n   \n") == []
