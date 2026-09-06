"""644 — the internal label scheme, settled in ONE table.

Every tiddler title in the projection has the shape `<bibkey>_<PREFIX><SEP><TAIL>`.
`TITLE_SHAPES` is the only place that shape is written down; `title_for` is the
only place a title is built and `parse_title` the only place one is read.

Rule 17 is the reason this file exists: three identifier regexes broke in two
days, each correct on the case it was written against. A second regex for the
same shape is the defect, so these tests pin (a) the frozen shapes as literals,
(b) the round trip through the table, and (c) that each consumer that used to
carry its own copy now asks the table.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.core import Document, DocObject, Realization
from docops.projectors.tiddlywiki import (
    BLOCK_TEMPLATE,
    TEMPLATES,
    TITLE_SHAPES,
    TiddlyWikiProjector,
    parse_title,
    tiddler_integrity,
    title_for,
    _BLOCK_TYPES_IN_SECTION,
)


# ------------------------------------------------------------------ the table

#: The shapes AS THEY ARE ON DISK today, written as literals. If a table edit
#: changes a live shape, this fails — which is the point: the crop files in
#: `report-crops/`, the identifiers printed in every evidence PDF and the
#: `REF_<citekey>` contract the LaTeX injector relies on are all named this way.
FROZEN = {
    "Paragraph":  "DOC_PARA_0001",
    "Section":    "DOC_H0001",
    "Equation":   "DOC_EQ0001",
    "Formula":    "DOC_FO0001",
    "Picture":    "DOC_PIC_0001",
    "Diagram":    "DOC_DIA_0001",
    "Table":      "DOC_TAB_001",
    "Footnote":   "DOC_FN0001",
    "Sidenote":   "DOC_SN0001",
    "ListItem":   "DOC_LI0001",
    "Abstract":   "DOC_ABS01",
    "Toc":        "DOC_TOC01",
    "Page":       "DOC_PAGE_001",
    "Theorem":    "DOC_THM0001",
    "Proof":      "DOC_PROOF0001",
    "CodeListing": "DOC_LST0001",
    "LtxCommand": "DOC_LTX1",
}


def test_the_frozen_shapes_are_what_title_for_builds():
    for kind, expected in FROZEN.items():
        assert title_for("DOC", kind, 1) == expected, kind


def test_every_kind_in_the_table_is_covered_by_the_frozen_list():
    """A new kind must be added to FROZEN too, or its shape is unpinned."""
    keyed = {k for k, s in TITLE_SHAPES.items() if s.keyed}
    assert set(TITLE_SHAPES) - keyed == set(FROZEN)


def test_keyed_shapes_build_from_a_key():
    assert title_for("DOC", "Reference", "Atick1990") == "DOC_REF_Atick1990"
    assert title_for("DOC", "SyntheticFormula", "0a1b2c") == "DOC_FOX_0a1b2c"


def test_every_shape_round_trips_title_for_to_parse_title():
    for kind, shape in TITLE_SHAPES.items():
        tail = "Atick1990" if shape.keyed else 7
        t = title_for("penev_A", kind, tail)
        p = parse_title(t)
        assert p is not None, (kind, t)
        assert p.bibkey == "penev_A", (kind, t, p)
        assert p.kind == kind, (kind, t, p)
        if shape.keyed:
            assert p.key == "Atick1990" and p.number is None, (kind, p)
        else:
            assert p.number == 7 and p.key is None, (kind, p)


def test_a_bibkey_that_itself_ends_in_a_prefix_still_parses():
    """`X_REF_FO0001` is a REFERENCE whose citekey is `FO0001`, not formula 1."""
    p = parse_title("penev_A_REF_FO0001")
    assert (p.kind, p.key, p.number) == ("Reference", "FO0001", None)


def test_parse_title_refuses_what_the_scheme_does_not_own():
    for t in ("", "DOC", "DOC_TOC", "penev_A", "report.tex", "DOC_EQ12"):
        assert parse_title(t) is None, t


def test_parse_title_strips_the_legacy_page_suffix():
    """`formula_report` names an equation `<b>_EQ0264_p003`; the `_p<NNN>` is a
    disambiguator, not part of the identity."""
    p = parse_title("Heim1979_EQ0264_p003")
    assert (p.kind, p.number) == ("Equation", 264)


# --------------------------------------------------- the projector uses it

def _one_of_every_type() -> Document:
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    types = ["Paragraph", "Section", "Equation", "Formula", "Picture",
             "Diagram", "Table", "Footnote", "Sidenote", "ListItem",
             "Abstract", "Toc", "Theorem", "Proof", "Page"]
    for i, typ in enumerate(types):
        a = mp.append(text=f"line {i}", _page=1, _line_index=i, type="text")
        o = DocObject(type=typ, props={"flow_index": i, "page_number": 1,
                                       "refnum": 1})
        o.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                      role="surface"))
        doc.add(o)
    doc.add(DocObject(type="Reference", props={"citekey": "Atick1990",
                                               "flow_index": 99}))
    return doc


def test_assign_titles_produces_only_titles_the_parser_accepts():
    doc = _one_of_every_type()
    proj = TiddlyWikiProjector.__new__(TiddlyWikiProjector)
    title, inv = proj._assign_titles(doc, "DOC")
    assert title, "no titles assigned"
    for oid, t in title.items():
        p = parse_title(t)
        assert p is not None, (oid, t)
        assert p.kind == doc.objects[oid].type, (t, p.kind,
                                                 doc.objects[oid].type)


def test_one_shape_per_object_type():
    """The user's requirement, checked mechanically: the set of titles a type
    produces reduces to ONE (prefix, separator, digit-width)."""
    doc = _one_of_every_type()
    proj = TiddlyWikiProjector.__new__(TiddlyWikiProjector)
    title, _ = proj._assign_titles(doc, "DOC")
    by_type: dict[str, set] = {}
    for oid, t in title.items():
        p = parse_title(t)
        shape = TITLE_SHAPES[p.kind]
        by_type.setdefault(doc.objects[oid].type, set()).add(shape)
    assert all(len(v) == 1 for v in by_type.values()), by_type


# ------------------------------------------------------------- FN uniqueness

def test_footnote_titles_are_unique_per_object():
    """646-a: `FN<refnum>` gave ONE title to up to six Footnote objects, so five
    of them were invisible in the wiki. A title names exactly one object."""
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    for i in range(3):
        a = mp.append(text=f"1 note {i}", _page=i + 1, _line_index=0,
                      type="footnote")
        fn = DocObject(type="Footnote",
                       props={"refnum": 1, "content": f"note {i}",
                              "flow_index": i})
        fn.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                       role="surface"))
        doc.add(fn)
    proj = TiddlyWikiProjector.__new__(TiddlyWikiProjector)
    title, _ = proj._assign_titles(doc, "DOC")
    assert len(set(title.values())) == 3, title


# ------------------------------------------------------------ the macro layer

def test_every_block_template_is_defined():
    assert set(BLOCK_TEMPLATE.values()) <= set(TEMPLATES)


def test_every_block_type_a_section_can_hold_has_a_template():
    assert _BLOCK_TYPES_IN_SECTION <= set(BLOCK_TEMPLATE)


def test_tiddler_integrity_counts_a_used_but_undefined_template():
    """A transclusion naming a template nothing defines renders NOTHING. It is
    a dangling transclusion and the integrity audit must say so."""
    tiddlers = [{"title": "DOC_PARA_0001", "text": "{{DOC_FO0001||NOSUCH}}"},
                {"title": "DOC_FO0001", "text": ""}]
    r = tiddler_integrity(tiddlers)
    assert "NOSUCH" in r["dangling"]
    tiddlers.append({"title": "NOSUCH", "text": "", "tags": "template"})
    assert tiddler_integrity(tiddlers)["dangling"] == []


# ---------------------------------------------------------------- consumers

def test_report_tex_known_templates_is_the_projector_s_own_list():
    from pdfdrill.report_tex import KNOWN_TEMPLATES
    assert set(KNOWN_TEMPLATES) == set(TEMPLATES)


def test_report_tex_typed_title_sees_every_kind_it_reports():
    """The old `_(FOX?|EQ|TAB|DIA|PIC)\\d` required a digit flush against the
    prefix, so it never matched `_TAB_001`, `_DIA_0001` or `_PIC_0001` — the
    463 guard could not see the very titles `rows_for` reports on."""
    from pdfdrill.report_tex import TYPED_TITLE
    for kind in ("Formula", "Equation", "Table", "Diagram", "Picture"):
        assert TYPED_TITLE.search(title_for("penev_A", kind, 1)), kind
    assert TYPED_TITLE.search(title_for("penev_A", "SyntheticFormula", "ab12"))
    assert not TYPED_TITLE.search("penev_A_PARA_0001")


def test_crops_kinds_come_from_the_table():
    from pdfdrill.reports.crops import KINDS_ALL
    assert set(KINDS_ALL) == {"_EQ", "_FO", "_TAB", "_DIA", "_PIC"}


def test_llm_text_titles_are_the_projector_s_shapes():
    from docops.projectors.llm_text import _title_map
    doc = _one_of_every_type()
    for oid, t in _title_map(list(doc.objects.values()), "DOC").items():
        p = parse_title(t)
        assert p is not None and p.kind == doc.objects[oid].type, t


def test_distill_titles_are_the_projector_s_shapes():
    """`_FN_001`/`_SN_003` were distill's own invention — a separator and a
    digit width the projector never emitted, so every anchor missed."""
    from docops.projectors.distill_reader import DistillReaderProjector
    doc = _one_of_every_type()
    proj = DistillReaderProjector.__new__(DistillReaderProjector)
    for oid, t in proj._title_map(list(doc.objects.values()), "DOC").items():
        p = parse_title(t)
        assert p is not None and p.kind == doc.objects[oid].type, t


def test_occurrence_titles_are_the_projector_s_shapes():
    from pdfdrill.occurrences import _titles
    doc = _one_of_every_type()
    for oid, t in _titles(list(doc.objects.values()), "DOC").items():
        p = parse_title(t)
        assert p is not None and p.kind == doc.objects[oid].type, t


def test_citation_title_and_the_table_agree():
    from pdfdrill.citekeys import citation_title
    assert citation_title("DOC", "van der Berg:2019") == \
        title_for("DOC", "Reference", "van_der_Berg_2019")
    assert citation_title("DOC", "", 4) == title_for("DOC", "Reference", "4")


def test_no_second_shape_regex_survives_in_src():
    """Rule 17, mechanically. A regex alternation of the scheme's own prefixes
    may live in exactly one module — the table's."""
    root = Path(__file__).resolve().parent.parent / "src"
    pat = re.compile(r"\(\?:?(?:FOX\?|FOX\|FO)")
    offenders = [str(p) for p in root.rglob("*.py")
                 if pat.search(p.read_text(encoding="utf-8", errors="replace"))
                 and p.name != "tiddlywiki.py"]
    assert offenders == [], offenders
