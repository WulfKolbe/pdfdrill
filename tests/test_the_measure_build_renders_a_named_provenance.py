"""T-0116 — render a NAMED COMPETING PROVENANCE in the measure build.

WHY NOT `latex_refined`, which was the first plan. refine.py gates a
refinement on identity evidence:

    IDENTITY_EVIDENCE = frozenset({"census", "eprint", "source"})

and `chosen_latex` shows one ONLY when `verified_by` names one of those; a
refinement verified by ink alone is deliberately NOT shown, returned instead as
`refinement_state: "ink_only"` so a projection can say it exists without
asserting it is right. The tiddler fields the report reads come straight from
that (`tiddlywiki._refined_fields`). So carrying a pix2text reading as a
refinement would mean either writing `verified_by: "source"` for an OCR
reading — false, in the one field built to prevent that — or adding "pix2text"
to IDENTITY_EVIDENCE, which asserts an OCR reading is evidence about identity
and would silently promote every ink-only refinement in the corpus.

THE VOCABULARY ALREADY EXISTS and needed nothing new. `snip` writes a
competing reading as `Realization(role="latex_candidate", provenance=<name>)`
on the model object, and the TiddlyWiki projector already emits one field per
provenance: `t[f"latex_{r.provenance}"]` (tiddlywiki.py:1684). 0707.4470's
tiddlers carry `latex_tex` and `score_tex` from exactly that path. What was
missing is only that the MEASURE report — the one projection inkdrill can
measure — could not be asked to render one of them.

THE DISTINCTION THIS KEEPS. `--prefer-refined` means "show the VERIFIED
correction" and asserts something. `--render-provenance <name>` means "render
this competing reading so it can be MEASURED" and asserts nothing: the reading
earns its "confirmed" on the pixels, at report-chain distance 0, or it does
not. The two may not be combined, because a row with both would have no
defined answer and silently picking one is how a measurement comes to describe
a column nobody chose.

AND THE STAMP RECORDS WHAT WAS DONE, NOT WHAT WAS ASKED. `prefer_refined` in
`measured_against` records the FLAG, so a measurement can claim a column and
have rendered nothing from it — which is precisely what happened on 0707.4470
on 2026-11-01: 54 rows measured, 19 "clean", `prefer_refined: True`, and ZERO
rows actually refined, because the chain had regenerated the tiddlers from the
model and wiped the injection. The count and the ids are the only things that
make a true measurement distinguishable from that one.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# THIS checkout's src first: the editable install resolves `pdfdrill` to the
# main checkout, and a worktree test that omits this measures main's code.
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import report_tex as rt                            # noqa: E402

BIB = "K"


def _tids():
    """Three equation rows; the middle one carries a pix2text candidate."""
    return [
        {"title": f"{BIB}_EQ0001", "latex": r"a=b", "page": "001"},
        {"title": f"{BIB}_EQ0002", "latex": r"c=d", "page": "002",
         "latex_pix2text": r"c=d+\varepsilon", "score_pix2text": "0.9"},
        {"title": f"{BIB}_EQ0003", "latex": r"e=f", "page": "003"},
    ]


# --------------------------------------------------------------------- rows ---

def test_rows_render_the_named_provenance_where_one_exists():
    applied, absent = set(), set()
    _fo, eq, _t, _d = rt.rows_for(_tids(), BIB, render_provenance="pix2text",
                                  rendered=applied, no_candidate=absent)
    got = {r[0]: r[1] for r in eq}
    assert got[f"{BIB}_EQ0002"] == r"c=d+\varepsilon", got
    assert applied == {f"{BIB}_EQ0002"}, applied


def test_a_row_without_a_candidate_keeps_its_own_latex_and_is_listed():
    applied, absent = set(), set()
    _fo, eq, _t, _d = rt.rows_for(_tids(), BIB, render_provenance="pix2text",
                                  rendered=applied, no_candidate=absent)
    got = {r[0]: r[1] for r in eq}
    assert got[f"{BIB}_EQ0001"] == "a=b" and got[f"{BIB}_EQ0003"] == "e=f"
    assert absent == {f"{BIB}_EQ0001", f"{BIB}_EQ0003"}, absent


def test_an_empty_candidate_is_not_a_candidate():
    """A provenance that answered with an empty string has not read the row;
    rendering "" would measure a blank against the scan and call it a
    difference in the reading rather than an absence of one."""
    tids = _tids()
    tids[1]["latex_pix2text"] = "   "
    applied, absent = set(), set()
    _fo, eq, _t, _d = rt.rows_for(tids, BIB, render_provenance="pix2text",
                                  rendered=applied, no_candidate=absent)
    got = {r[0]: r[1] for r in eq}
    assert got[f"{BIB}_EQ0002"] == "c=d"
    assert applied == set() and f"{BIB}_EQ0002" in absent


def test_without_the_selector_nothing_changes():
    _fo, eq, _t, _d = rt.rows_for(_tids(), BIB)
    assert {r[0]: r[1] for r in eq}[f"{BIB}_EQ0002"] == "c=d"


# -------------------------------------------------------------------- stamp ---

def test_the_stamp_records_the_count_and_the_ids_not_the_option(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    st = rt.write_build_stamp(
        pdf, legend=False, ink_adopted=False, prefer_refined=False,
        filters={}, render_provenance="pix2text",
        rendered_ids=[f"{BIB}_EQ0002"],
        no_candidate_ids=[f"{BIB}_EQ0001", f"{BIB}_EQ0003"])
    assert st["render_provenance"] == "pix2text"
    assert st["rendered_from_provenance"] == 1, st
    assert st["rendered_ids"] == [f"{BIB}_EQ0002"], st
    assert st["no_candidate"] == 2, st
    on_disk = json.loads((tmp_path / rt.BUILD_STAMP).read_text(encoding="utf-8"))
    assert on_disk["rendered_from_provenance"] == 1


def test_a_stamp_that_rendered_nothing_says_zero(tmp_path):
    """THE DEFECT THIS FIELD EXISTS FOR. `prefer_refined: True` with zero rows
    refined is indistinguishable on disk from a real refined measurement."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    st = rt.write_build_stamp(
        pdf, legend=False, ink_adopted=False, prefer_refined=False,
        filters={}, render_provenance="pix2text",
        rendered_ids=[], no_candidate_ids=[f"{BIB}_EQ0001"])
    assert st["render_provenance"] == "pix2text"
    assert st["rendered_from_provenance"] == 0, (
        "a measurement that rendered nothing must say so")


# ---------------------------------------------------------------------- CLI ---

def test_the_cli_binds_the_selector(monkeypatch):
    """ENGINEERING 2f rule 6 — the test drives the real CLI. The manifest and
    the handler both had `--prefer-refined` while cli.py silently dropped it."""
    from pdfdrill import cli
    import pdfdrill.commands as CM
    seen = {}
    monkeypatch.setattr(CM, "cmd_reporttex",
                        lambda pdf, **kw: seen.update(kw) or "ok", raising=True)
    monkeypatch.setattr(CM, "cmd_inkreport",
                        lambda pdf, **kw: seen.update(kw) or "ok", raising=True)
    monkeypatch.setattr(cli, "_pdf", lambda a: Path("x.pdf"), raising=False)

    cli._do_reporttex(["x.pdf", "--render-provenance", "pix2text"])
    assert seen.get("render_provenance") == "pix2text", seen
    seen.clear()
    cli._do_inkreport(["x.pdf", "--render-provenance", "pix2text"])
    assert seen.get("render_provenance") == "pix2text", seen


def test_the_two_selectors_may_not_be_combined():
    """A row with a verified refinement AND a competing candidate has no
    defined answer. Refusing is the whole of the precedence rule."""
    from pdfdrill import commands as C
    with pytest.raises(SystemExit) as e:
        C.cmd_reporttex(Path("x.pdf"), prefer_refined=True,
                        render_provenance="pix2text")
    assert e.value.code == 2, e.value.code


def test_every_build_in_the_chain_renders_the_same_column():
    """557's rule: phase 1 and phase 2 may differ only by the legend.

    The first version of this change threaded the selector into the measure
    build and the restore-after-failure build and MISSED step 5, the reading
    build. The gate run showed it: report.build.measure.json carried
    render_provenance='pix2text' with 12 rows rendered, and
    report.build.reading.json carried '' with 0 — so the ink in
    `measured_against` described a report whose whole maths column differed
    from the one a reader opens. Defect 539's shape with the column in place
    of the shape.
    """
    import inspect
    from pdfdrill import commands as C
    src = inspect.getsource(C._inkreport_chain)
    calls = [i for i in range(len(src)) if src.startswith("cmd_reporttex(", i)]
    assert len(calls) >= 3, "expected the chain's three builds, found %d" % len(calls)
    for i in calls:
        # the call's own text, to its closing paren at the same depth
        depth, j = 0, i
        while j < len(src):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        call = src[i:j + 1]
        assert "render_provenance=render_provenance" in call, (
            "a build in the chain does not render the selected column:\n" + call)
