"""882 Phase 1 — the three line types MathPix emits on sigma26-075 and we did
not: `qed_symbol` (19), `list_item` (55), `abstract` (1).

Measured before and after with `pdfdrill conformance sigma26-075`:
9 of 18 MathPix line types emitted -> 12 of 18. The six that remain are
Phase 2 (table, table_row, table_column, simple_cell) and Phase 3 (diagram,
chart).

These tests pin the DECISIONS, not the counts: a count moves when a document
changes, and a decision moving is a regression.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfreader import docmodel_six as dm                     # noqa: E402
from pdfreader import project_mmd as mmd                     # noqa: E402


# --- qed_symbol -----------------------------------------------------------

def _glyph(text, name=None):
    return types.SimpleNamespace(text=text, glyphname=name)


def test_the_qed_box_is_found_by_glyph_name_not_by_character():
    """All 20 on sigma26-075 are `squaresolid`.

    A font whose encoding reports the character wrongly still names the glyph
    correctly — that is what R2 exposed the name for.
    """
    assert dm._is_qed(_glyph("", "squaresolid"))
    assert dm._is_qed(_glyph("?", "blacksquare"))


def test_the_character_alone_is_enough_when_there_is_no_name():
    assert dm._is_qed(_glyph("■"))
    assert dm._is_qed(_glyph("∎"))


def test_an_ordinary_glyph_is_not_a_qed_box():
    for g in (_glyph("a", "a"), _glyph("-", "hyphen"), _glyph("0", "zero"),
              _glyph("▲", "triangle")):
        assert not dm._is_qed(g)


def test_a_box_that_is_not_last_is_not_a_proof_end():
    """Stated as a test because the rule is easy to lose.

    A box used as an operator in the middle of a line is not a QED mark. The
    splitter requires the LAST inked glyph to be the box.
    """
    src = (Path(__file__).resolve().parents[1]
           / "src/pdfreader/docmodel_six.py").read_text(encoding="utf-8")
    assert "if not _is_qed(ink[-1]):" in src, (
        "only a TRAILING box ends a proof")


def test_qed_text_is_not_emptied_to_match_the_reference():
    """MathPix writes text: "" and we deliberately do not.

    An empty `text` is a loss; the type already says what the line is.
    Agreeing with the reference by discarding the same information is not the
    kind of compatibility worth having (880).
    """
    src = (Path(__file__).resolve().parents[1]
           / "src/pdfreader/docmodel_six.py").read_text(encoding="utf-8")
    assert 'qed["text"] = text' in src and 'qed["text_display"] = text' in src


# --- list_item ------------------------------------------------------------

def _out(lines):
    return {"pages": [{"page": 1, "lines": lines}]}


def test_a_counter_label_on_prose_becomes_a_list_item():
    """MathPix types BOTH kinds `list_item` on sigma26-075 — the roman-numeral
    items and the bibliography entries. `type_contract` says `list_item` is
    read by `list_items` and breaks a paragraph, which is what these lines
    should do and what `text` prevented."""
    out = _out([
        {"type": "text", "text": "[4] Bianchi L., Lezioni di geometria, 1894."},
        {"type": "text", "text": "(iii) This follows by comparing (2.8) and (8.1)."},
    ])
    dm._mark_generated_text(out)
    got = out["pages"][0]["lines"]
    assert got[0]["type"] == "list_item" and got[0]["generated"] == "bib_entry"
    assert got[1]["type"] == "list_item" and got[1]["generated"] == "list_label"


def test_the_generating_command_is_still_the_latex():
    out = _out([{"type": "text",
                 "text": "[7] Knuth D., The TeXbook, Addison-Wesley, 1984."}])
    dm._mark_generated_text(out)
    assert out["pages"][0]["lines"][0]["latex"] == r"\bibliography{}"


def test_only_a_text_line_is_relabelled():
    """The order-of-certainty rule `classify_lines` states, applied here.

    A line already established as a heading, a caption or an equation number
    is not renamed by a counter shape.
    """
    out = _out([
        {"type": "section_header", "text": "References"},
        {"type": "footnote", "text": "[1] A footnote that looks like a bibitem."},
    ])
    dm._mark_generated_text(out)
    got = out["pages"][0]["lines"]
    assert got[0]["type"] == "section_header"
    assert got[1]["type"] == "footnote"


# --- abstract -------------------------------------------------------------

def test_an_abstract_label_needs_its_punctuation():
    """`Abstract.` is the publisher's label; "Abstract ideas are…" is a
    sentence. The period or colon is the whole difference, and there is no
    font evidence to fall back on: on sigma26-075 the label is body font, body
    size, not bold, run into the first sentence."""
    import re
    rx = re.compile(r"\s*([A-Za-zÄÖÜäöüß"
                    r"а-я]+)\s*[.:]")
    def is_label(t):
        m = rx.match(t)
        return bool(m and m.group(1).lower() in mmd._ABSTRACT_LABELS)
    assert is_label("Abstract. We explore a method initiated by Guichard")
    assert is_label("Zusammenfassung: Wir untersuchen")
    assert not is_label("Abstract ideas are hard to measure")


def test_the_front_matter_enders_are_a_label_set_not_a_pattern():
    """Same contract as `_ABSTRACT_LABELS` — words a publisher prints.

    Needed because an abstract with no sized heading has no sized heading to
    end it either: bounding by the next heading ran to `1 Introduction` and
    swallowed the keywords and the MSC classification.
    """
    assert "key words" in mmd._FRONT_MATTER_ENDERS
    assert "mathematics subject classification" in mmd._FRONT_MATTER_ENDERS
    assert "introduction" not in mmd._FRONT_MATTER_ENDERS, (
        "a section heading is not a front-matter label; the heading bound "
        "already handles it")


def test_the_runin_abstract_also_bounds_the_author_block():
    """The defect this exists to prevent: five lines of the abstract exported
    as `authors`, which is not a near miss, it is the wrong field."""
    src = (Path(__file__).resolve().parents[1]
           / "src/pdfreader/project_mmd.py").read_text(encoding="utf-8")
    assert "stop = runin_abstract if stop is None else min(stop, runin_abstract)" in src


def test_the_runin_label_line_is_part_of_the_abstract():
    """Unlike the sized-heading case, where the heading stays `section_header`.

    There the heading is its own line and names the abstract; here the label
    is the first glyphs OF the abstract's first sentence, so excluding its
    line would drop the sentence with it.
    """
    src = (Path(__file__).resolve().parents[1]
           / "src/pdfreader/project_mmd.py").read_text(encoding="utf-8")
    assert "if runin_abstract <= i < end" in src, (
        "the label line is INCLUSIVE in the run-in case")
