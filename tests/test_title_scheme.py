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
import ast
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

def test_649_eqblock_is_gone_and_eq_is_the_display_equation_widget():
    """649 — EQBLOCK was the one template name that did not fit the
    `{{title||TPL}}` macro layer; EQ is the shape every other template uses
    (a bare kind-ish abbreviation) and the title prefix for Equation is
    already `EQ` (644's table) — the two namespaces don't collide because a
    title always precedes `||` and a template always follows it.

    The dead `EQ` link template ("see Equation 1.1") is dropped outright: its
    own comment said it was "not currently emitted by any substitution", and
    FREF does the equation-reference job (188 uses on penev_A, 647b). What
    survives under the name `EQ` is the display-equation WIDGET that used to
    be `EQBLOCK` — distinguished here by its markup, so a future edit that
    quietly puts the dead link text back under this key is caught too."""
    assert "EQBLOCK" not in TEMPLATES, "EQBLOCK must be renamed away, not kept"
    assert "EQ" in TEMPLATES
    assert "displayMode=true" in TEMPLATES["EQ"], (
        "TEMPLATES['EQ'] must be the display-equation widget (the old "
        "EQBLOCK body), not the dead inline link template")
    assert BLOCK_TEMPLATE["Equation"] == "EQ"


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


# --------------------------------------------------- rule 17, mechanically

#: Frozen per-task measurement scripts (rule 19): the exact source that
#: produced a published number. Rewriting one breaks the reproducibility that
#: is its only job, so each is whitelisted BY NAME with its reason rather than
#: by a blanket `tools/` exemption.
_FROZEN_SCRIPTS = {
    "tools/census481.py":   "481 — the identifier census behind out/481",
    "tools/parallel474.py": "474 — the parallel-corpus scan behind out/474",
    "tools/uniscan475.py":  "475 — the Unicode scan behind out/475",
    "tools/pkggap482.py":   "482 — the package-gap scan behind out/482",
    "tools/bed492.py":      "492 — the bedding measurement behind out/492",
    "tools/beddiag492.py":  "492 — the bedding diagnosis beside bed492",
    "tools/midstring486.py": "486 — the mid-string scan behind out/486",
    "tools/census509.py":   "509 — the second identifier census, out/509",
}

_ALTERNATION_RUN = re.compile(r"[A-Za-z0-9?]+(?:\|[A-Za-z0-9?]+)+")


def _second_scheme_regexes(text: str) -> list:
    """Every `A|B(|C…)` run in a string literal that is a TITLE-PREFIX
    alternation: two or more of `TITLE_SHAPES`' own prefixes, sitting where a
    title's prefix sits — immediately after the `_` that follows the bibkey.

    The `_` anchor is what separates a TITLE alternation from a TEMPLATE one:
    `{{…||(FO|EQ|FREF)}}` names templates, not shapes, and FO/EQ are both.
    `FOX?` counts once (it encodes FO and FOX at the same time).
    """
    prefixes = {s.prefix for s in TITLE_SHAPES.values()}
    out = []
    for m in _ALTERNATION_RUN.finditer(text):
        j = m.start()
        while j > 0 and text[j - 1] in "(?:":        # step back over `(?:`
            j -= 1
        if j == 0 or text[j - 1] != "_":
            continue
        n = sum(1 for part in m.group(0).split("|")
                if (part[:-1] if part.endswith("?") else part) in prefixes)
        if n >= 2:
            out.append(m.group(0))
    return out


def test_no_second_title_prefix_regex_survives_in_src_or_tools():
    """Rule 17, built FROM the table rather than from one spelling of it.

    The first version of this guard matched the literal text `(?:FOX?` /
    `(?:FOX|FO` and so could not see a capturing group, or an alternation
    where FO is not first. It passed while FOUR live shape regexes stood:
    `crossref` (`_(EQ|FOX?)`), `inkmeasure._IDENT_TOKEN`
    (`_(?:EQ|FO|TAB|DIA|IMG|H)\\d{2,}`), the dead `reccontext.TYPED`
    (`_(EQ|FOX?|TAB)\\d`) and `commands` (`_(DIA|PIC)_\\d+$`). This version
    parses every string literal in `src/` and `tools/` and asks the table.
    """
    root = Path(__file__).resolve().parent.parent
    offenders = {}
    for sub in ("src", "tools"):
        for f in sorted((root / sub).rglob("*.py")):
            rel = f.relative_to(root).as_posix()
            if rel in _FROZEN_SCRIPTS:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8",
                                             errors="replace"))
            except SyntaxError:                      # not our problem here
                continue
            runs = [r for node in ast.walk(tree)
                    if isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    for r in _second_scheme_regexes(node.value)]
            if runs:
                offenders[rel] = sorted(set(runs))
    assert offenders == {}, offenders


def test_the_guard_actually_fires():
    """Rule 11: a detector that can only see success sees nothing. Each of the
    four real spellings it missed before must trip it, and a TEMPLATE
    alternation must not."""
    for pat in (r"_(EQ|FOX?)", r"_(?:EQ|FO|TAB|DIA|IMG|H)\d{2,}",
                r"_(EQ|FOX?|TAB)\d", r"_(DIA|PIC)_\d+$"):
        assert _second_scheme_regexes(pat), pat
    assert not _second_scheme_regexes(r"\{\{([^}|]+)\|\|(FO|EQ|FREF)\}\}")
    assert not _second_scheme_regexes(r"(cat|dog|EQ)")


def test_the_whitelist_names_only_files_that_exist_and_still_offend():
    """A whitelist entry that no longer applies is a hole. Every frozen script
    must exist AND still carry the pattern it is excused for — otherwise it
    should be off the list."""
    root = Path(__file__).resolve().parent.parent
    for rel, reason in _FROZEN_SCRIPTS.items():
        f = root / rel
        assert f.is_file(), rel
        assert reason
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        runs = [r for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                for r in _second_scheme_regexes(node.value)]
        assert runs, f"{rel} no longer offends — drop it from the whitelist"


# ------------------------------------- the marker -> body invariant (644-a)

def test_each_footnote_marker_resolves_to_the_body_with_that_refnum():
    """644 renumbered footnote TITLES by flow position. The marker `{ }^{N}` in
    a paragraph must still reach the footnote whose printed refnum is N, with
    that body's text, on that paragraph's page.

    Creation order and flow order DIVERGE here on purpose — the footnotes are
    added in the order 3, 7, 11 while their `flow_index` orders them 7, 3, 11 —
    so a title assigned from either order is a different title, and the marker
    still has to land on the right body.

    WHAT IT DISCRIMINATES, measured by mutation rather than asserted:
      * re-deriving the marker target from the PRINTED refnum
        (`title_for(bibkey, "Footnote", int(rn))`, the pre-644 assumption)
        FAILS it — every marker dangles. That is the regression a reader of
        the 644 diff would most plausibly write.
      * swapping the numbering back to insertion order does NOT fail it, and
        the docstring says so rather than implying otherwise:
        `fn_by_refnum` maps a printed number to that footnote's OWN title, so
        the marker->body wiring is independent of which order the numbers came
        from. The numbering is pinned by
        `test_footnote_titles_are_unique_per_object`; this test pins the
        wiring.

    NOT COVERED, and it is 646-a: two footnotes sharing one printed refnum on
    different pages. `fn_by_refnum` is document-wide and first-wins, so both
    markers reach the FIRST body. 644 stopped the two bodies overwriting each
    other; it did not make the marker resolve per paragraph.
    """
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")

    # (page, printed refnum, flow position) — added to the doc out of order
    spec = [(1, 7), (2, 3), (3, 11)]
    para_anchor = {}
    for page, refnum in spec:
        a = mp.append(text=fr"See it \({{ }}^{{{refnum}}}\) here.",
                      _page=page, _line_index=0, type="text")
        para_anchor[refnum] = a
        par = DocObject(type="Paragraph", props={
            "text": f"See it here.", "page": page, "flow_index": page * 10})
        par.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                        role="surface"))
        doc.add(par)

    fn_anchor = {}
    for page, refnum in spec:
        b = mp.append(text=fr"\({{ }}^{{{refnum}}}\) Body {refnum}.",
                      _page=page, _line_index=1, type="footnote")
        fn_anchor[refnum] = b

    for page, refnum in [spec[1], spec[0], spec[2]]:      # 3, 7, 11 — shuffled
        fn = DocObject(type="Footnote", props={
            "refnum": refnum, "content": f"Body {refnum}", "page": page,
            "flow_index": page * 10 + 1})
        fn.add_realization(Realization(stream="mathpix_lines",
                                       start=fn_anchor[refnum],
                                       end=fn_anchor[refnum], role="surface"))
        doc.add(fn)

    from docops.conserve import project_in_memory
    tiddlers, titles, _ = project_in_memory(doc)
    by_title = {t["title"]: t for t in tiddlers}

    marker = re.compile(r"\{\{([^{}|]+)\|\|FN\}\}")
    seen = 0
    for t in tiddlers:
        if "paragraph" not in (t.get("tags") or ""):
            continue
        for m in marker.finditer(t.get("text") or ""):
            assert m.group(1) in by_title, m.group(1)   # never dangles
            seen += 1
    assert seen == len(spec), f"expected {len(spec)} markers, saw {seen}"

    # the real assertion: the marker's PRINTED number, the body's refnum and
    # the page all agree, for every marker.
    for page, refnum in spec:
        par = next(t for t in tiddlers
                   if "paragraph" in (t.get("tags") or "")
                   and str(t.get("page") or "").lstrip("0") == str(page))
        m = marker.search(par["text"])
        assert m, par["text"]
        body = by_title[m.group(1)]
        assert str(body.get("refnum")) == str(refnum), (page, refnum, body)
        assert str(body.get("page") or "").lstrip("0") == str(page), \
            (page, refnum, body.get("page"))
        assert f"Body {refnum}" in (body.get("text") or ""), body.get("text")
