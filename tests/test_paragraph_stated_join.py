"""T-0010 b — the paragraph composer must honour the join MathPix states.

`ParagraphProcessor` writes `Paragraph.props.text`, which is what every
projector reads. It joined every line with a space, ignoring the `subtype`
sitting in the same payload, so a `continues_line_no_hyphen` line came out as
"Transformations gruppen": a space inserted into the middle of a word. On
Killing, Math. Ann. 33 (1889) that was 31 of 143 such joins (21.7%).

The join rule itself was already written down twice — `_STATED` in
`docmodel.modules.dehyphenation` and `docops.mutators.dehyphenate` — and
`tests/test_dehyphenate_stated.py` covered it. What that test did was run the
`Dehyphenate` MUTATOR over the composed paragraph, and no build command runs
it: `pdfdrill model` ran the composer alone. The rule was tested in a stage the
product does not execute. These tests compose and assert, with no mutator in
between.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.modules.dehyphenation import DehyphenationProcessor
from docmodel.base_module import ModuleConfig


def _mod(cls):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), "T")


def _compose(lines):
    """Build the model the way a build command does: composer, no mutator."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i, ln in enumerate(lines):
        ln.setdefault("id", f"l{i}")
        ln.setdefault("type", "text")
        ln.setdefault("text_display", ln["text"])
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    _mod(ParagraphProcessor).process_document(doc)
    return doc


def _text(lines):
    return _compose(lines).objects_of_type("Paragraph")[0].props["text"]


def test_no_hyphen_on_an_already_stripped_line_joins_with_nothing():
    # The German compound that made this visible: Math. Ann. 33, p. 1.
    assert _text([
        {"text": "der stetigen endlichen Transformations"},
        {"text": "gruppen", "subtype": "continues_line_no_hyphen"},
    ]) == "der stetigen endlichen Transformationsgruppen"


def test_no_hyphen_with_a_trailing_hyphen_drops_it():
    assert _text([
        {"text": "die Bedingungs-"},
        {"text": "gleichungen", "subtype": "continues_line_no_hyphen"},
    ]) == "die Bedingungsgleichungen"


def test_no_hyphen_never_amputates_a_final_letter():
    # `_no_hyphen` says "no extra character", not "remove one".
    assert _text([
        {"text": "beein"},
        {"text": "trächtigt", "subtype": "continues_line_no_hyphen"},
    ]) == "beeinträchtigt"


def test_no_space_keeps_a_real_compound():
    assert _text([
        {"text": "two image datasets: CIFAR-"},
        {"text": "10 and MNIST", "subtype": "continues_line_no_space"},
    ]) == "two image datasets: CIFAR-10 and MNIST"


@pytest.mark.parametrize("sub", ["continues_line_space", "continues_line_newline"])
def test_space_and_newline_join_with_one_space(sub):
    assert _text([
        {"text": "the first line"},
        {"text": "the second", "subtype": sub},
    ]) == "the first line the second"


def test_no_subtype_still_joins_with_a_space():
    # 59% of corpus text lines carry no subtype; the heuristic downstream owns
    # them, and the composer must not change what it did there.
    assert _text([
        {"text": "the first line"},
        {"text": "the second"},
    ]) == "the first line the second"


def test_the_composer_and_the_cleaned_stream_agree():
    """The invariant the defect broke.

    `DehyphenationProcessor` builds a derived stream holding the same text,
    joined correctly. On the Killing model 229 of those streams sat beside 225
    paragraphs whose `props.text` disagreed with them. Whichever a reader
    picked changed the answer, and nothing said which was authoritative.
    """
    lines = [
        {"text": "der stetigen endlichen Transformations"},
        {"text": "gruppen, deren Bedingungs-", "subtype": "continues_line_no_hyphen"},
        {"text": "gleichungen hier", "subtype": "continues_line_no_hyphen"},
        {"text": "angegeben sind", "subtype": "continues_line_space"},
    ]
    doc = _compose(lines)
    _mod(DehyphenationProcessor).process_document(doc)
    para = doc.objects_of_type("Paragraph")[0]
    cleaned = next(r for r in para.realizations if r.role == "cleaned")
    stream = doc.stream(cleaned.stream)
    joined = "".join(
        stream.payload[a].get("text") or ""
        for a in stream.slice_anchors(cleaned.start, cleaned.end)
    )
    assert para.props["text"] == joined.strip()


# --- the other three composers (T-0010) -----------------------------------
# A paragraph is not the only object built by concatenating continuation
# lines. The list item, the abstract and the sidenote each did the same join,
# each with its own `" ".join`, so the stated subtype was ignored four times
# over. Appendix G is where this shows: its rules are ListItems, not
# Paragraphs, and rule 7 read "bound ary item".

from docmodel.modules.list_items import ListProcessor
from docmodel.modules.abstract import AbstractProcessor
from docmodel.modules.sidenote import SidenoteProcessor
from docmodel.text_utils import join_stated_lines


def test_a_two_line_list_item_honours_the_stated_join():
    doc = Document()
    doc.meta["bibkey"] = "T"
    lines = [
        {"id": "c0", "type": "list_item", "text": "",
         "children_ids": ["c1", "c2"]},
        {"id": "c1", "type": "text", "text": "7. Set the glue of the bound"},
        {"id": "c2", "type": "text", "text": "ary item",
         "subtype": "continues_line_no_hyphen"},
    ]
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    _mod(ListProcessor).process_document(doc)
    item = doc.objects_of_type("ListItem")[0]
    assert item.props["content"] == "Set the glue of the boundary item"


def test_an_abstract_honours_the_stated_join():
    doc = Document()
    doc.meta["bibkey"] = "T"
    lines = [
        {"id": "a0", "type": "abstract", "text": "", "children_ids": ["a1", "a2"]},
        {"id": "a1", "type": "text", "text": "we show that the measure"},
        {"id": "a2", "type": "text", "text": "ment is sound",
         "subtype": "continues_line_no_hyphen"},
    ]
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    _mod(AbstractProcessor).process_document(doc)
    assert doc.objects_of_type("Abstract")[0].props["text"] == \
        "we show that the measurement is sound"


def test_the_sidenote_keeps_its_own_heuristic_where_nothing_is_stated():
    # `_concat_with_softhyphens` owned every line before T-0010 and still owns
    # the ones that state nothing: a leading space joins, a trailing hyphen is
    # a soft break, anything else takes one space.
    assert SidenoteProcessor._concat_with_softhyphens(
        [("a trailing hyphen-", ""), ("joins", "")]) == "a trailing hyphenjoins"
    # A line that already carries its joiner keeps exactly one space. The old
    # code appended the leading whitespace verbatim, so three spaces stayed
    # three; one space — the case that occurs — is byte-identical.
    assert SidenoteProcessor._concat_with_softhyphens(
        [("already spaced", ""), (" words", "")]) == "already spaced words"
    assert SidenoteProcessor._concat_with_softhyphens(
        [("two plain", ""), ("lines", "")]) == "two plain lines"
    # and the stated join wins over all three
    assert SidenoteProcessor._concat_with_softhyphens(
        [("the measure", ""), ("ment", "continues_line_no_hyphen")]) == "the measurement"


def test_every_line_contributes_exactly_once():
    """Gate 1 — multiplicity. Each source line appears once in the composed text."""
    lines = [
        {"text": "the first line of the paragraph"},
        {"text": "the second line", "subtype": "continues_line_space"},
        {"text": "and the third", "subtype": "continues_line_space"},
    ]
    text = _text(lines)
    for ln in lines:
        assert text.count(ln["text"]) == 1, f"{ln['text']!r} appears {text.count(ln['text'])}x"


# --- T-0010 a: composed once ------------------------------------------------
# The container path stamps `_in_list_item` so the paragraph composer declines
# its children (811). The LEXICAL path stamped nothing, so every lexically
# detected item was composed twice: once as the item (its marker line alone,
# cut mid-sentence) and once inside a paragraph that ran on through the whole
# list. On texbook Appendix G one paragraph held 46 lines -- rules 6 to 22 --
# while those rules each stood as a ListItem beside it.

def _compose_with_lists(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i, ln in enumerate(lines):
        ln.setdefault("id", f"l{i}")
        ln.setdefault("type", "text")
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    _mod(ListProcessor).process_document(doc)
    _mod(ParagraphProcessor).process_document(doc)
    return doc


def test_a_lexical_list_item_is_not_also_composed_as_prose():
    doc = _compose_with_lists([
        {"text": "1. If the current item is a rule, translate it"},
        {"text": "into a box of the same size",
         "subtype": "continues_line_space"},
        {"text": "2. If the current item is glue, do this"},
    ])
    items = doc.objects_of_type("ListItem")
    assert [i.props["marker"] for i in items] == ["1.", "2."]
    # the continuation belongs to item 1, joined as stated
    assert items[0].props["content"] == \
        "If the current item is a rule, translate it into a box of the same size"
    # and no paragraph composed any of it a second time
    prose = " ".join(p.props["text"] for p in doc.objects_of_type("Paragraph"))
    assert "current item" not in prose, prose


def test_a_lexical_item_spans_the_lines_it_folded_in():
    doc = _compose_with_lists([
        {"text": "1. first line of the item"},
        {"text": "and its continuation", "subtype": "continues_line_space"},
    ])
    item = doc.objects_of_type("ListItem")[0]
    surface = next(r for r in item.realizations if r.role == "surface")
    stream = doc.stream("mathpix_lines")
    assert len(stream.slice_anchors(surface.start, surface.end)) == 2


def test_a_continuation_line_does_not_start_a_list_item():
    """The guard that keeps the claim safe.

    `_detect_marker` reads a leading token, so German prose gives it one:
    "z. B." yields the marker "z.". Six of Killing's seven lexical items were
    this kind of false positive, and every one carries a `continues_line_*`
    subtype -- lines.json saying the line continues the sentence above it, so
    the token cannot be a marker. All 22 genuine rules of Appendix G carry no
    subtype. Before the claim such an item was harmless duplication; now it
    would take its line out of the prose, so the guard is load-bearing.
    """
    doc = _compose_with_lists([
        {"text": "Die Wurzeln sind sämmtlich reell, und es gilt"},
        {"text": "z. B. dass alle Unterdeterminanten verschwinden",
         "subtype": "continues_line_space"},
    ])
    assert doc.objects_of_type("ListItem") == []
    prose = doc.objects_of_type("Paragraph")[0].props["text"]
    assert "z. B. dass alle Unterdeterminanten" in prose


def test_a_marker_line_that_starts_a_line_is_still_an_item():
    # The seventh Killing item carries no subtype and stays one.
    doc = _compose_with_lists([
        {"text": "Die Bedingungen sind die folgenden:"},
        {"text": "a) es sollen alle Unterdeterminanten verschwinden"},
    ])
    assert [i.props["marker"] for i in doc.objects_of_type("ListItem")] == ["a)"]


def test_a_line_that_states_no_join_keeps_its_own_layout():
    """The regression the first pass of T-0010 caused, caught by the audit.

    `text_display` carries MathPix's own layout, and a leading "\\n\\n" is it
    saying the line begins a block. All 34 numbered rules of texbook Appendix G
    start one that way and none carries a `continues_line_*` subtype.
    Normalizing whitespace on EVERY join stripped that, and 8 of the 34 --
    13a, 15b, 15c, 15e, 18b, 18c, 18e, 18f -- stopped beginning a line in the
    projection and stood mid-paragraph after the rule above them. Only a
    STATED join is normalized; a line that states nothing is joined verbatim.
    """
    text = _text([
        {"text": "13. If the current item is an Op atom, mark it",
         "text_display": "13. If the current item is an Op atom, mark it"},
        {"text": "and continue",
         "text_display": "and continue", "subtype": "continues_line_space"},
        {"text": "13a. If limits are not to be typeset",
         "text_display": "\n\n13a. If limits are not to be typeset"},
    ])
    # the stated join is normalized to one space ...
    assert "mark it and continue" in text
    # ... and the block break the next line declares survives
    assert "\n\n13a." in text, repr(text)
