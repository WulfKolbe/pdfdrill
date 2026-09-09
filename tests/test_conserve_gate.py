"""656 — conserve becomes a gate.

The transclusion audit (2026-09) found that `conserve` already catches every
one of the seven-plus object types (Theorem, Proof, CodeListing, Algorithm,
AlgorithmStep, List, Link, MathTail) that never reach the reader, and that
nothing runs it. This does not make those types reachable — that is a
separate, larger task — it makes their absence impossible to miss: a
RATCHET against a checked-in baseline (`conserve_baseline.json`), with a
verified-route classification (`BY_DESIGN`) so the report shows the real
violations first instead of drowning them in Page/TableCell/TableRow/Toc.

THE FIXTURE is not a single-purpose synthetic (the shape test_conserve.py
uses for isolated behaviour) — it carries ONE object of every type the
2026-09 transclusion-audit measured LIVE as unreachable on a real document
(1811.06102 for Theorem/Proof, narcissus for CodeListing, 2602.12042v1 for
Algorithm/AlgorithmStep, kolbe2018hubbard for Link/List; MathTail had no
live sample, so its shape is built from `cmd_tailsplit`'s own docstring
instead), plus one of every BY_DESIGN type (Page, Table+TableCell+TableRow,
Toc). It is deliberately not a copy of any one real `model.docmodel.json`
(those are large, license-bound, and never committed to this repo per
`docs/HANDOVER-RULES.md` rule 19) — it is a small, portable document built
from the REAL shapes those types take in production code, named here so a
change to any of TITLE_SHAPES / _BLOCK_TYPES_IN_SECTION / BLOCK_TEMPLATE /
_build_inventory that starts reaching one of them makes this fixture's own
`test_gate_passes_at_its_recorded_baseline` fail loudly (a FIXED entry, per
`format_gate_report`) rather than silently drifting. Rule 11: every check
here is exercised on a real PASS and a real FAIL of the same summariser.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.conserve import (BY_DESIGN, classify_unreachable, conserve,
                             format_gate_report, gate)

BIBKEY = "GATE"


def _reachable_base(doc: Document) -> DocObject:
    """One Section (root- and TOC-listed) holding one Paragraph — everything
    else added by the caller stays OUTSIDE this reachable spine unless it is
    explicitly wired in, exactly like `test_conserve.py::_conserved`."""
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text="Hello world.", _page=1, _line_index=1, type="text")
    sec = DocObject(type="Section", props={
        "caption": "Introduction", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={
        "text": "Hello world.", "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines",
                                    start=body, end=body, role="surface"))
    doc.add_child(sec, par)
    return sec


def _gated_fixture() -> Document:
    """One reachable Section+Paragraph, one object of every BY_DESIGN type,
    and one object of every VIOLATION type the audit measured."""
    doc = Document()
    doc.meta["bibkey"] = BIBKEY
    sec = _reachable_base(doc)
    mp = doc.streams["mathpix_lines"]

    # ---- BY_DESIGN: Page (73076/1362 corpus-wide, addressed by field only)
    pg_anchor = mp.append(text="page furniture", _page=1, _line_index=2,
                          type="page_info")
    page_obj = DocObject(type="Page", props={"page_number": 1})
    page_obj.add_realization(Realization(stream="mathpix_lines",
                                         start=pg_anchor, end=pg_anchor,
                                         role="surface"))
    doc.add(page_obj)

    # ---- BY_DESIGN: Table + TableCell/TableRow (content folds into the
    # Table's own raw_text — docmodel/modules/table.py:60-61)
    tab_anchor = mp.append(text="a\tb", _page=1, _line_index=3, type="table")
    table_obj = DocObject(type="Table", props={
        "page": 1, "flow_index": 2, "raw_text": "a\tb"})
    table_obj.add_realization(Realization(stream="mathpix_lines",
                                          start=tab_anchor, end=tab_anchor,
                                          role="surface"))
    doc.add_child(sec, table_obj)
    for kind in ("TableRow", "TableCell"):
        cell = DocObject(type=kind, props={"text": "a"})
        cell.add_realization(Realization(stream="mathpix_lines",
                                         start=tab_anchor, end=tab_anchor,
                                         role="surface"))
        doc.add(cell)

    # ---- BY_DESIGN: Toc (262 — rebuilt as the <bibkey>_TOC index instead)
    toc_a = mp.append(text="1 Introduction .... 1", _page=2, _line_index=4,
                      type="toc")
    toc_obj = DocObject(type="Toc", props={"flow_index": 9})
    toc_obj.add_realization(Realization(stream="mathpix_lines",
                                        start=toc_a, end=toc_a, role="surface"))
    doc.add(toc_obj)

    # ---- VIOLATION: Theorem + Proof (1811.06102: TITLE_SHAPES rows exist,
    # tiddlers ARE emitted (tiddlywiki.py's unconditional theorem/proof
    # loops), neither is in _BLOCK_TYPES_IN_SECTION/BLOCK_TEMPLATE, so
    # neither is ever transcluded from a reachable Section — "not reached".)
    thm_a = mp.append(text="Theorem 1. Statement.", _page=1, _line_index=5,
                      type="text")
    proof_obj = DocObject(type="Proof", props={"statement": "Trivial."})
    proof_obj.add_realization(Realization(stream="mathpix_lines",
                                          start=thm_a, end=thm_a,
                                          role="surface"))
    doc.add(proof_obj)
    thm_obj = DocObject(type="Theorem", props={
        "kind": "theorem", "number": 1, "statement": "Statement.",
        "proof_id": proof_obj.id})
    thm_obj.add_realization(Realization(stream="mathpix_lines",
                                        start=thm_a, end=thm_a,
                                        role="surface"))
    doc.add(thm_obj)

    # ---- VIOLATION: CodeListing (narcissus: TITLE_SHAPES row exists, but
    # `_build_inventory` never collects "codelistings" — code_listing_
    # tiddlers() is dead code — so no title is ever assigned: "no tiddler".)
    code_a = mp.append(text="def f(): pass", _page=1, _line_index=6,
                       type="code")
    code_obj = DocObject(type="CodeListing", props={
        "code": "def f(): pass", "language": "python", "line_count": 1})
    code_obj.add_realization(Realization(stream="mathpix_lines",
                                         start=code_a, end=code_a,
                                         role="surface"))
    doc.add(code_obj)

    # ---- VIOLATION: Algorithm + AlgorithmStep (2602.12042v1: no row in
    # TITLE_SHAPES at all, no projector reference of any kind.)
    algo_a = mp.append(text="Algorithm 1", _page=1, _line_index=7,
                       type="pseudocode")
    algo_obj = DocObject(type="Algorithm", props={"caption": "Algorithm 1"})
    algo_obj.add_realization(Realization(stream="mathpix_lines",
                                         start=algo_a, end=algo_a,
                                         role="surface"))
    doc.add(algo_obj)
    step_obj = DocObject(type="AlgorithmStep", props={"text": "Step 1."})
    step_obj.add_realization(Realization(stream="mathpix_lines",
                                         start=algo_a, end=algo_a,
                                         role="surface"))
    doc.add(step_obj)

    # ---- VIOLATION: Link (kolbe2018hubbard: promoted from PDF hyperlink
    # annotations, `src/pdfdrill/annotations.py`; no projector reference.)
    link_a = mp.append(text="see http://example.org", _page=1,
                       _line_index=8, type="text")
    link_obj = DocObject(type="Link", props={
        "uri": "http://example.org", "anchor_text": "", "context": "see"})
    link_obj.add_realization(Realization(stream="mathpix_lines",
                                         start=link_a, end=link_a,
                                         role="surface"))
    doc.add(link_obj)

    # ---- VIOLATION: List (kolbe2018hubbard: `cmd_lists` builds a pure
    # nesting/structure marker, no TITLE_SHAPES row, no projector reference —
    # the underlying ListItems can still be reachable on their own, which is
    # exactly why this is measured on the List object, not its items.)
    list_obj = DocObject(type="List", props={
        "indent_norm": 0, "list_type": "unordered"})
    doc.add(list_obj)

    # ---- VIOLATION: MathTail (`cmd_tailsplit`, commands.py ~16197-16250:
    # holds the prose tail split off a math region's LaTeX; no TITLE_SHAPES
    # row, no projector reference — same code-path absence as Algorithm/
    # List/Link, not live-tested in the audit for lack of a local sample.)
    tail_a = mp.append(text="for all x in X", _page=1, _line_index=9,
                       type="text")
    tail_obj = DocObject(type="MathTail", props={"text": "for all x in X"})
    tail_obj.add_realization(Realization(stream="mathpix_lines",
                                         start=tail_a, end=tail_a,
                                         role="surface"))
    doc.add(tail_obj)

    return doc


#: The baseline this fixture is pinned to. One of each violation type, one
#: object each -- matching `_gated_fixture` exactly.
_FIXTURE_BASELINE = {
    BIBKEY: {
        "Theorem": 1, "Proof": 1, "CodeListing": 1, "Algorithm": 1,
        "AlgorithmStep": 1, "Link": 1, "List": 1, "MathTail": 1,
    },
}


# --------------------------------------------------------- classification

def test_by_design_types_are_the_five_verified_routes():
    """The standard `CONTAINER_TYPES` sets: name the route, or don't list it.
    Pinned so an addition here is a deliberate, reviewed change."""
    assert set(BY_DESIGN) == {"Page", "TableCell", "TableRow", "Toc", "Document"}
    for kind, route in BY_DESIGN.items():
        assert len(route) > 20, f"{kind}: route not substantiated"


def test_out_of_scope_types_all_carry_a_reason():
    from docops.conserve import OUT_OF_SCOPE
    assert OUT_OF_SCOPE                                  # non-empty
    assert not (set(OUT_OF_SCOPE) & set(BY_DESIGN))       # disjoint
    for kind, reason in OUT_OF_SCOPE.items():
        assert len(reason) > 20, f"{kind}: reason not substantiated"


def test_classify_unreachable_separates_by_design_from_violations():
    res = conserve(_gated_fixture())
    cls = classify_unreachable(res["reachability"])
    assert cls["by_design"] == {"Page": 1, "TableCell": 1, "TableRow": 1, "Toc": 1}
    assert "Table" not in cls["by_design"]          # the Table ITSELF is reached
    assert cls["out_of_scope"] == {}
    assert cls["violations"] == {
        "Theorem": 1, "Proof": 1, "CodeListing": 1, "Algorithm": 1,
        "AlgorithmStep": 1, "Link": 1, "List": 1, "MathTail": 1,
    }


# --------------------------------------------------------------- (a) PASS

def test_gate_passes_at_its_recorded_baseline():
    doc = _gated_fixture()
    g = gate(doc, baseline=_FIXTURE_BASELINE)
    assert g["passed"] is True, g
    assert g["has_baseline_row"] is True
    assert g["new_types"] == {} and g["increased"] == {} and g["decreased"] == {}
    assert g["matched"] == _FIXTURE_BASELINE[BIBKEY]
    assert g["by_design"]["Page"] == 1
    report = format_gate_report(g)
    assert report.startswith(f"conserve --gate {BIBKEY}: PASS")
    # a PASS still shows the numbers it passed on (not just the word)
    assert "at baseline:" in report
    assert "by design" in report


# --------------------------------------------------------- (b) NEW type

def test_gate_fails_on_a_genuinely_new_unreachable_type():
    """A type that is neither BY_DESIGN, OUT_OF_SCOPE, nor in the baseline.
    Citation is the sharpest example available: no `TITLE_SHAPES` row at all
    (the identical structural mechanism as Algorithm/Link/etc — code-level
    fact, not measured), yet the transclusion-audit explicitly declined to
    call it a violation. This fixture's baseline does not carry it, so the
    gate reports it NEW regardless of which class it belongs to — the same
    behaviour a real ninth violation type would get on a document that has
    never recorded one (rule 11's real failure, alongside the PASS above)."""
    doc = _gated_fixture()
    mp = doc.streams["mathpix_lines"]
    a = mp.append(text="(Smith 1999)", _page=1, _line_index=10, type="text")
    cit = DocObject(type="Citation", props={"citekey": "Smith1999"})
    cit.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                    role="surface"))
    doc.add(cit)

    g = gate(doc, baseline=_FIXTURE_BASELINE)
    assert g["passed"] is False
    assert g["new_types"] == {"Citation": 1}
    assert g["increased"] == {} and g["decreased"] == {}
    report = format_gate_report(g)
    assert report.startswith(f"conserve --gate {BIBKEY}: FAIL")
    assert "NEW unreachable type: Citation" in report


# --------------------------------------------------------- (c) INCREASE

def test_gate_fails_on_an_increase_over_the_baseline():
    doc = _gated_fixture()
    mp = doc.streams["mathpix_lines"]
    a = mp.append(text="Theorem 2. Another.", _page=1, _line_index=11,
                  type="text")
    thm2 = DocObject(type="Theorem", props={"kind": "theorem", "number": 2,
                                            "statement": "Another."})
    thm2.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                     role="surface"))
    doc.add(thm2)

    g = gate(doc, baseline=_FIXTURE_BASELINE)
    assert g["passed"] is False
    assert g["increased"] == {"Theorem": {"baseline": 1, "now": 2}}
    assert g["new_types"] == {} and g["decreased"] == {}
    report = format_gate_report(g)
    assert "INCREASED: Theorem 1 -> 2" in report


# --------------------------------------------------------- (d) DECREASE

def test_gate_fails_on_a_decrease_and_asks_for_a_baseline_update():
    """Fewer than the baseline is GOOD NEWS and still fails the gate: a
    silently-accepted drop is exactly how a stale baseline entry survives a
    fix (656's own 'the baseline can only shrink, on purpose' rule)."""
    doc = Document()
    doc.meta["bibkey"] = BIBKEY
    sec = _reachable_base(doc)
    # only Theorem/Proof present -- every OTHER baselined type reads 0
    mp = doc.streams["mathpix_lines"]
    thm_a = mp.append(text="Theorem 1. Statement.", _page=1, _line_index=5,
                      type="text")
    thm_obj = DocObject(type="Theorem", props={"kind": "theorem", "number": 1})
    thm_obj.add_realization(Realization(stream="mathpix_lines", start=thm_a,
                                        end=thm_a, role="surface"))
    doc.add(thm_obj)

    g = gate(doc, baseline=_FIXTURE_BASELINE)
    assert g["passed"] is False
    assert g["new_types"] == {} and g["increased"] == {}
    # Theorem itself matches (1 == 1); every OTHER baselined type dropped to 0
    assert g["matched"] == {"Theorem": 1}
    assert set(g["decreased"]) == {
        "Proof", "CodeListing", "Algorithm", "AlgorithmStep", "Link",
        "List", "MathTail"}
    for d in g["decreased"].values():
        assert d["now"] == 0
    report = format_gate_report(g)
    assert "FIXED: Proof 1 -> 0" in report
    assert "remove it from conserve_baseline.json" in report


# ------------------------------------------- (out of scope) does not gate

def test_an_out_of_scope_unreachable_object_neither_fails_nor_hides():
    """A Paragraph (OUT_OF_SCOPE: incidental gaps, 645-a/646-j) that reaches
    nothing does not make the gate FAIL and is not silently dropped either —
    it shows up in `out_of_scope`, and the PASS/FAIL verdict ignores it."""
    doc = _gated_fixture()
    mp = doc.streams["mathpix_lines"]
    a = mp.append(text="an orphan paragraph", _page=3, _line_index=12,
                  type="text")
    orphan = DocObject(type="Paragraph", props={"page": 3, "flow_index": 20})
    orphan.add_realization(Realization(stream="mathpix_lines", start=a,
                                       end=a, role="surface"))
    doc.add(orphan)                          # not a child of any Section

    g = gate(doc, baseline=_FIXTURE_BASELINE)
    assert g["passed"] is True, g
    assert g["out_of_scope"] == {"Paragraph": 1}
    assert "Paragraph" not in g["violations"]
    report = format_gate_report(g)
    assert "out of scope" in report
    assert "Paragraph=1" in report


# --------------------------------------------- (e) unknown bibkey -> zero tolerance

def test_gate_gives_an_unaudited_document_zero_tolerance():
    doc = _gated_fixture()
    g = gate(doc, baseline={})           # no row at all for BIBKEY
    assert g["passed"] is False
    assert g["has_baseline_row"] is False
    assert g["new_types"] == {
        "Theorem": 1, "Proof": 1, "CodeListing": 1, "Algorithm": 1,
        "AlgorithmStep": 1, "Link": 1, "List": 1, "MathTail": 1,
    }
    report = format_gate_report(g)
    assert "no baseline row for this bibkey" in report


def test_load_baseline_reads_the_committed_file():
    """The gate's DATA half really is a file on disk, not a dict only ever
    passed in by a test."""
    from docops.conserve import load_baseline
    baseline = load_baseline()
    assert isinstance(baseline, dict)
    assert BIBKEY not in baseline, (
        "the test fixture's bibkey must never collide with a real, "
        "committed baseline entry")


# ------------------------------------------------------- (review finding 7)
# The seven real-document rows in conserve_baseline.json cannot be exercised
# by running the gate against them (rule 19: those models are private,
# license-bound content this repo's CI cannot see) -- but "parses as a
# dict" is not the same claim as "every row is well-formed", and a row
# naming an EXEMPT type would be silently inert forever (classify_
# unreachable never routes a BY_DESIGN/OUT_OF_SCOPE type into `violations`,
# so gate() would never even look at such an entry). This is the more than
# parseability check the review asked for.

def test_every_committed_baseline_row_names_only_ratchet_eligible_types():
    from docops.conserve import BY_DESIGN, OUT_OF_SCOPE, load_baseline
    baseline = load_baseline()
    assert baseline, "the committed baseline is empty -- nothing to check"
    exempt = set(BY_DESIGN) | set(OUT_OF_SCOPE)
    for bibkey, row in baseline.items():
        assert row, f"{bibkey}: an empty row means the document has zero " \
                     "recorded violations -- write it as {{}} deliberately " \
                     "or drop the bibkey, not both"
        for kind, count in row.items():
            assert kind not in exempt, (
                f"{bibkey}: {kind!r} is BY_DESIGN or OUT_OF_SCOPE -- a "
                f"baseline row naming it is never read by classify_"
                f"unreachable's 'violations' bucket and would be silently "
                f"inert forever")
            assert isinstance(count, int) and not isinstance(count, bool), (
                f"{bibkey}: {kind!r} count {count!r} is not an int")
            assert count > 0, (
                f"{bibkey}: {kind!r} count is {count} -- a zero-or-negative "
                f"entry belongs to `decreased`/removal, not the baseline")


def test_a_committed_baseline_row_gates_a_document_at_that_exact_count():
    """Not just well-formed data -- a row from the real file, replayed
    through a synthetic document carrying exactly that many objects of that
    type, passes the SAME gate() a real invocation would use. This is the
    closest a CI-portable test can get to "run the gate over a real
    baseline row" without committing the private model that produced it
    (rule 19) -- see the DEVIATION note in out/656.txt for why that gap
    exists at all."""
    from docops.conserve import gate, load_baseline
    baseline = load_baseline()
    bibkey, row = next(iter(baseline.items()))
    kind, n = next(iter(row.items()))

    doc = Document()
    doc.meta["bibkey"] = bibkey
    _reachable_base(doc)
    mp = doc.streams["mathpix_lines"]
    for i in range(n):
        a = mp.append(text=f"item {i}", _page=1, _line_index=100 + i,
                     type="text")
        o = DocObject(type=kind, props={})
        o.add_realization(Realization(stream="mathpix_lines", start=a,
                                      end=a, role="surface"))
        doc.add(o)

    g = gate(doc, baseline=baseline)
    assert g["matched"] == {kind: n}, g
    assert kind not in g["new_types"] and kind not in g["increased"] \
        and kind not in g["decreased"]
