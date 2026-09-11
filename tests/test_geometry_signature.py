"""670 — fresh_ink could not see a code change.

`fresh_ink` asked four (then five, 578) content questions about a stored
measurement and none of them asked whether the report BUILDER that produced
it is the one that would run now. 463 and 625 are the two incidents this
closes: `--profile published` dropping a section (463), and a `\\` inside a
`p{}` cell that put every Scan image on a second line and made every
residual measure an empty cell (625, out/625.txt) — both changed the report's
measured GEOMETRY while every existing check stayed green.

`report_tex.geometry_signature()` is a hash over the SOURCE (AST, not text,
so a comment or docstring edit changes nothing) of a NAMED set of functions
— `report_tex.GEOMETRY_FUNCS` — that emit or interpret the report's
zref/savepos marks. `fresh_ink`'s sixth content question compares it against
`report.build.measure.json["geometry_sha256"]`, and — unlike the leniency the
model check above it gives an absent field — treats a MISSING recorded
signature as a mismatch, not a pass: every stamp on disk predates this
check by construction, and "not recorded" is exactly the shape of the
defect this exists to close, not a reason to wave it through.

Rule 17 (docs/HANDOVER-RULES.md): several fixtures below are built so the
OTHER five questions already pass, so a failure can only be attributed to
the sixth.
"""
import inspect
import json
import os

from pdfdrill import cli
from pdfdrill import commands as C
from pdfdrill import inkreport as ir
from pdfdrill import report_tex as rt


# ---------------------------------------------------------------------------
# the signature mechanism itself
# ---------------------------------------------------------------------------

def test_geometry_signature_is_deterministic():
    assert rt.geometry_signature() == rt.geometry_signature()


def test_geometry_signature_changes_when_a_marked_function_s_code_changes(
        monkeypatch):
    """The mechanism test: mutate one function ON THE NAMED LIST and the
    signature must move. `crop_cell` is the exact function 625 fixed."""
    before = rt.geometry_signature()

    def _different_crop_cell(*a, **k):
        return "a different implementation"

    monkeypatch.setattr(rt, "crop_cell", _different_crop_cell)
    after = rt.geometry_signature()
    assert before != after


def test_geometry_signature_is_unmoved_by_a_function_NOT_on_the_list(
        monkeypatch):
    """The complementary direction: `esc_text` renders CONTENT (escaping),
    never a mark, position or size, and is not in GEOMETRY_FUNCS. Changing
    it must not cost anyone a remeasurement."""
    before = rt.geometry_signature()

    def _different_esc_text(*a, **k):
        return "different"

    monkeypatch.setattr(rt, "esc_text", _different_esc_text)
    after = rt.geometry_signature()
    assert before == after


def test_ast_dump_ignores_comments_and_whitespace_the_way_the_signature_relies_on():
    """The design claim in `geometry_signature`'s docstring, checked
    directly: two functions that differ ONLY by a comment (the exact shape
    of 625's own fix — three sentences of "why" beside two lines of "what")
    parse to the same AST, so hashing the AST rather than the source text is
    what keeps a comment edit from costing a needless remeasurement."""
    import ast
    a = "def f(x):\n    # nothing to see here\n    return x + 1\n"
    b = ("def f(x):\n"
         "    # 625 -- a completely different, much longer explanation of\n"
         "    # why this line is the way it is, spanning several sentences.\n"
         "    return x + 1\n")
    assert ast.dump(ast.parse(a)) == ast.dump(ast.parse(b))
    c = "def f(x):\n    return x + 2\n"          # an actual code change
    assert ast.dump(ast.parse(a)) != ast.dump(ast.parse(c))


# ---------------------------------------------------------------------------
# the guard: the named set cannot silently drift
# ---------------------------------------------------------------------------

_NAMING_PATTERNS = ("cellrect", "crop_cell", "_img_cell", "col_widths",
                    "table_open", "_rule_", "page_height_bp", "auto_px2mm")


def test_every_function_matching_the_known_geometry_naming_patterns_is_named():
    """670's guard. `crop_cell`/`_cellrect_table_open` are the two functions
    625 actually fixed; everything else in GEOMETRY_FUNCS was found by
    generalising their naming convention. This inverts that discovery into a
    check: a NEW function that fits the same convention (a future
    `_cellrect_foo`, a second `crop_cell`-shaped helper, ...) must be in
    GEOMETRY_FUNCS or this fails — the set cannot silently stay behind the
    code the way `fresh_ink`'s docstring said a stale constant would.

    This cannot catch a same-shaped function given an UNRELATED name (`row`
    is the one already-known example — see GEOMETRY_FUNCS's own comment);
    that is a named limit of a mechanical naming check, not a silent one.
    """
    import re
    pattern = re.compile("|".join(_NAMING_PATTERNS))
    matched = {name for name, obj in vars(rt).items()
              if inspect.isfunction(obj) and obj.__module__ == rt.__name__
              and pattern.search(name)}
    missing = matched - set(rt.GEOMETRY_FUNCS)
    assert not missing, (
        "function(s) matching a known geometry naming pattern are not in "
        "GEOMETRY_FUNCS: %s -- add them, or explain why not (like `row`)"
        % sorted(missing))


def test_geometry_funcs_is_exactly_the_reviewed_set():
    """Pins the set so a change to it is a deliberate diff to THIS test, not
    a silent edit three files away. Order-independent on purpose — the hash
    itself is order-stable (each function's name is hashed alongside its
    AST), so reordering the tuple is not a geometry change."""
    assert set(rt.GEOMETRY_FUNCS) == {
        "cellrect_reset", "_rule_mark", "_rule_above", "_cellrect_header_mark",
        "_cellrect_table_open", "_cellrect_marks", "_cellrect_col_marks",
        "_cellrect_row", "_img_cell", "crop_cell", "col_widths", "table_open",
        "row", "cellrect_from_aux", "page_height_bp", "auto_px2mm",
    }
    assert len(rt.GEOMETRY_FUNCS) == len(set(rt.GEOMETRY_FUNCS)), \
        "no name should be listed twice"
    for name in rt.GEOMETRY_FUNCS:
        assert hasattr(rt, name), "%s is in GEOMETRY_FUNCS but not defined" % name


# ---------------------------------------------------------------------------
# 670 review, finding 2 — the second, independent mark-emission copy
# (607C) found inline in build_report's Image-regions (DIA) table
# ---------------------------------------------------------------------------

def test_row_and_the_dia_table_both_go_through_the_shared_emitter():
    """A second, independent reimplementation of row()'s own mark sequence
    was found inline in build_report, outside GEOMETRY_FUNCS and outside
    the naming-pattern guard. Both must now call the ONE shared emitter,
    `_cellrect_row`, rather than either calling the low-level primitives
    directly."""
    row_src = inspect.getsource(rt.row)
    build_report_src = inspect.getsource(rt.build_report)
    assert "_cellrect_row(" in row_src, "row() no longer calls the emitter"
    assert "_cellrect_row(" in build_report_src, (
        "build_report's DIA table no longer calls the shared emitter")
    # and NOT reimplemented inline in build_report any more -- these three
    # primitives should appear only inside _cellrect_row itself now
    for prim in ("_cellrect_marks(", "_rule_mark(", "_cellrect_col_marks("):
        assert prim not in build_report_src, (
            "build_report still calls %s directly -- a third copy of the "
            "sequence, not a call to _cellrect_row" % prim)


def test_row_delegates_to_cellrect_row_functionally_not_just_textually(
        monkeypatch):
    """The source-text check above can't tell a real call from a decoy
    string. Spy on the real function and confirm row() actually invokes it
    with this row's own title."""
    calls = []
    real = rt._cellrect_row

    def _spy(title, cells):
        calls.append((title, list(cells)))
        return real(title, cells)

    monkeypatch.setattr(rt, "_cellrect_row", _spy)
    rt.cellrect_reset(True)
    rt.row("EQ0007", "x+1", 3)
    assert len(calls) == 1
    assert calls[0][0] == "EQ0007"


def test_cellrect_row_wraps_marks_around_an_arbitrary_cell_list():
    """Direct mechanism test of the extracted emitter (the same style
    tests/test_column_rules_ordered.py already uses for _CELLRECT state):
    the open mark is glued onto the FIRST cell, the first row of a table
    gets one column mark per cell, and the second row's `rule_above_key`
    is the first row's `rule_below_key` -- the bookkeeping `row()` and the
    DIA table both relied on before this was one function."""
    rt.cellrect_reset(True)
    rt._cellrect_table_open()
    out1 = rt._cellrect_row("EQ0001", ["A", "B", "C"])
    out2 = rt._cellrect_row("EQ0002", ["D", "E", "F"])
    assert "A" in out1 and "\\pdrowpos{pdr00001a}" in out1
    assert out1.rstrip("\n").endswith("\\hline\\noalign{\\pdrulepos{rul00002}}")
    row1, row2 = rt._CELLRECT["map"]
    assert row1["identifier"] == "EQ0001" and row2["identifier"] == "EQ0002"
    assert row1["rule_below_key"] is not None
    assert row2["rule_above_key"] == row1["rule_below_key"]
    # only the first row of the table gets column marks (4 = 3 cells + 1
    # right-edge mark, per _cellrect_col_marks's own docstring)
    assert len(rt._CELLRECT["cols"][rt._CELLRECT["table"]]) == 4
    assert "col" not in out2  # the second row gets none


def test_no_third_call_site_for_the_row_marking_sequence():
    """670 review: 'search once more for a third site.' Grepped across the
    whole module for every direct caller of the three low-level primitives
    row()/the DIA table used to duplicate between them. Exactly one now:
    `_cellrect_row` itself. `table_open`/the DIA header separately call
    `_cellrect_table_open`/`_cellrect_header_mark` directly (a third and
    fourth caller of THOSE two primitives) -- named here explicitly as NOT
    the same defect: those are direct reuse of an already-hashed primitive
    with no extra judgement or bookkeeping duplicated around them, unlike
    the sequence-plus-bookkeeping row() and the DIA table used to
    reimplement independently.
    """
    import pathlib
    src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    for prim in ("_cellrect_marks(", "_rule_mark(", "_cellrect_col_marks("):
        sites = [i for i in range(len(src)) if src.startswith(prim, i)]
        # one definition site (`def _cellrect_marks(` etc.) plus exactly one
        # call site, inside _cellrect_row's own body
        calls = [i for i in sites if not src[:i].rstrip().endswith("def")]
        assert len(calls) == 1, (
            "%s is called from %d places, expected exactly 1 (inside "
            "_cellrect_row)" % (prim, len(calls)))


# ---------------------------------------------------------------------------
# 670 review, finding 3 — a repeat of 665 (PREAMBLE font metrics)
# ---------------------------------------------------------------------------

def test_font_metrics_preamble_extracts_the_five_665_lines():
    extracted = rt.font_metrics_preamble()
    assert r"\usepackage[no-math]{fontspec}" in extracted
    assert r"\setmainfont{DejaVu Serif}" in extracted
    assert r"\setmonofont{DejaVu Sans Mono}[Scale=MatchLowercase]" in extracted
    assert r"\newfontfamily\fbmath{Noto Sans Math}" in extracted
    assert r"\newfontfamily\fbcjk{Noto Sans CJK JP}" in extracted
    assert len(extracted.splitlines()) == 5


def test_a_665_style_preamble_edit_moves_the_signature(monkeypatch):
    """The actual regression: task 665 changed `\\usepackage{fontspec}` to
    `\\usepackage[no-math]{fontspec}`. Reproduced directly against the
    extraction function (not the whole PREAMBLE, which this task does not
    touch) to prove it would have been caught."""
    before = rt.geometry_signature()
    pre_665 = rt.PREAMBLE.replace(
        r"\usepackage[no-math]{fontspec}", r"\usepackage{fontspec}")
    monkeypatch.setattr(rt, "PREAMBLE", pre_665)
    after = rt.geometry_signature()
    assert before != after


def test_geometry_signature_documents_all_four_kinds_of_input():
    """670 review finding 9 -- CELLRECT_PREAMBLE was hashed but never named
    in the docstring. Both non-function inputs must be named now."""
    doc = rt.geometry_signature.__doc__
    assert "CELLRECT_PREAMBLE" in doc
    assert "font_metrics_preamble" in doc


# ---------------------------------------------------------------------------
# fresh_ink's sixth question
# ---------------------------------------------------------------------------

def _doc(tmp_path, *, model=True):
    d = tmp_path / "doc"
    d.mkdir()
    pdf = d / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    if model:
        (d / "model.docmodel.json").write_text(json.dumps(
            {"meta": {"bibkey": "doc", "pages": [{"page": 1}]}, "objects": []}))
    return pdf, d


def _resumable(d, *, sha="abc123", rule="", geometry="__current__"):
    """An ink + measure stamp that agree, dated in the resumable order, on
    every OTHER question fresh_ink asks (rule 17: isolates the sixth).

    `geometry="__current__"` records the REAL current signature (so all six
    questions pass); a string records that literal value; None omits the
    field (the pre-670 stamp shape)."""
    stamp = {"sha256": sha, "pages": 20, "phase": "measure", "formula_rule": rule}
    if geometry is not None:
        stamp["geometry_sha256"] = (rt.geometry_signature()
                                    if geometry == "__current__" else geometry)
    (d / "report.build.measure.json").write_text(json.dumps(stamp))
    ink = d / "report.ink.json"
    ink.write_text(json.dumps(
        {"rows": [{"id": "x_EQ0001"}], "measured_against": {"sha256": sha}}))
    os.utime(ink, (10 ** 9, 10 ** 9))
    os.utime(d / "report.build.measure.json", (10 ** 9 - 100, 10 ** 9 - 100))
    return ink


def test_resume_survives_when_the_current_code_matches_the_recorded_signature(
        tmp_path):
    """A measurement made by the CURRENT code resumes — the direction that
    must keep working, or this check destroys the reason fresh_ink exists."""
    pdf, d = _doc(tmp_path)
    _resumable(d, geometry="__current__")
    assert ir.fresh_ink(d) is True


def test_resume_refuses_when_the_recorded_signature_is_from_different_code(
        tmp_path):
    """A measurement made by DIFFERENT code (625's actual incident, modelled
    directly) does not resume, even though the other five questions agree
    with each other perfectly."""
    pdf, d = _doc(tmp_path)
    why = []
    _resumable(d, geometry="0" * 64)          # a code version that never ran
    assert ir.fresh_ink(d, why=why) is False
    assert "different code" in why[0]


def test_resume_refuses_when_no_geometry_signature_was_ever_recorded(
        tmp_path):
    """The transition case: every stamp written before 670 has no
    geometry_sha256 at all. `model_state`'s check treats an absent field as
    unknown-therefore-pass; this question must NOT reuse that leniency, or
    it reopens exactly the loophole 625 exploited -- generalised from "no
    known defect at the time" to "the field a live incident was named for".
    """
    pdf, d = _doc(tmp_path)
    why = []
    _resumable(d, geometry=None)
    assert ir.fresh_ink(d, why=why) is False
    assert "does not record" in why[0]


def test_accept_stale_geometry_overrides_only_that_one_question(tmp_path):
    """The deliberate escape valve, for an operator who has independently
    confirmed the code has not moved -- never the default."""
    pdf, d = _doc(tmp_path)
    _resumable(d, geometry=None)
    assert ir.fresh_ink(d, accept_stale_geometry=False) is False
    assert ir.fresh_ink(d, accept_stale_geometry=True) is True


def test_accept_stale_geometry_does_not_paper_over_a_DIFFERENT_defect(
        tmp_path):
    """670's docstring promises the override reaches ONLY the geometry
    question, never the other five. A formula-rule mismatch (463's own
    incident) must still refuse even with accept_stale_geometry=True."""
    pdf, d = _doc(tmp_path)
    why = []
    _resumable(d, rule="", geometry=None)
    assert ir.fresh_ink(d, formula_rule="none", accept_stale_geometry=True,
                        why=why) is False
    assert "formula rule" in why[0]


def test_a_fixture_where_only_the_sixth_question_can_fail_still_resumes_when_it_passes(
        tmp_path):
    """Rule 17: a fixture where the first five questions already fail
    cannot discriminate the sixth. This is the converse control -- the same
    fixture with a matching signature must resume, proving the earlier
    refusal in the missing/mismatched tests is attributable to the sixth
    question alone and not to some other difference between the fixtures."""
    pdf, d = _doc(tmp_path)
    _resumable(d, sha="zzz999", rule="unresolved", geometry="__current__")
    assert ir.fresh_ink(d, formula_rule="unresolved") is True


# ---------------------------------------------------------------------------
# the report.build.measure.json writer records it
# ---------------------------------------------------------------------------

def test_write_build_stamp_records_geometry_sha256(tmp_path):
    pdf_out = tmp_path / "report.pdf"
    pdf_out.write_bytes(b"%PDF-1.4\n")
    stamp = rt.write_build_stamp(pdf_out, legend=False, ink_adopted=False,
                                 prefer_refined=False, filters={})
    assert stamp["geometry_sha256"] == rt.geometry_signature()
    on_disk = json.loads((tmp_path / rt.BUILD_STAMP).read_text())
    assert on_disk["geometry_sha256"] == rt.geometry_signature()


# ---------------------------------------------------------------------------
# the CLI surface reaches the parameter
# ---------------------------------------------------------------------------

def test_cli_residuals_parses_accept_stale_geometry_and_passes_it_on():
    src = inspect.getsource(cli._do_residuals)
    assert "--accept-stale-geometry" in src
    assert "accept_stale_geometry=" in src


def test_cli_inkreport_parses_accept_stale_geometry_and_passes_it_on():
    src = inspect.getsource(cli._do_inkreport)
    assert "--accept-stale-geometry" in src
    assert "accept_stale_geometry=" in src


def test_cmd_residuals_and_cmd_inkreport_take_accept_stale_geometry():
    assert "accept_stale_geometry" in inspect.signature(
        C.cmd_residuals).parameters
    assert "accept_stale_geometry" in inspect.signature(
        C.cmd_inkreport).parameters
    assert "accept_stale_geometry" in inspect.signature(
        C._inkreport_chain).parameters
    assert "accept_stale_geometry" in inspect.signature(
        ir.fresh_ink).parameters
