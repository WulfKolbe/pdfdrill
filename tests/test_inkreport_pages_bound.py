"""578 — --pages must reach BOTH builds and be part of the resume test.

The CLI accepted `--pages 10` on inkreport and dropped it: `_do_inkreport`
never parsed it, so it fell through into the positional list where `_pdf`
takes args[0] and ignores the rest. Every "the 21 at --pages 10" run was an
unbounded run. Same shape as 516's `--findings`.

A bound is also a content question for the resume, exactly like the formula
rule: a measurement taken against an unbounded report does not describe a
10-page one, and 463 is what adopting the wrong measurement costs.
"""
import inspect
import json

from pdfdrill import cli
from pdfdrill import commands as C
from pdfdrill import inkreport as ir
from pdfdrill import report_tex as rt


def test_cli_parses_pages_and_passes_it_on():
    src = inspect.getsource(cli._do_inkreport)
    assert '_opt(args, "--pages")' in src, "--pages is not parsed"
    assert "pages=" in src, "--pages is parsed but not passed to cmd_inkreport"


def test_cmd_inkreport_takes_pages():
    assert "pages" in inspect.signature(C.cmd_inkreport).parameters


def test_every_build_inside_inkreport_gets_the_bound():
    """A measure build of a different length measures a report nobody reads."""
    src = inspect.getsource(C.cmd_inkreport)
    calls = [l for l in src.splitlines() if "cmd_reporttex(" in l]
    assert calls, "cmd_inkreport must build"
    # each call spans lines; check the whole source has no reporttex call that
    # omits pages, by counting
    import re
    whole = re.findall(r"cmd_reporttex\((?:[^()]|\([^()]*\))*\)", src, re.S)
    assert whole, "no cmd_reporttex call found"
    # 585 — the MEASURE build is deliberately unbounded: it is the full
    # listing, and a page bound there would hide every row past page N from
    # the ink, which is the ratchet this task removed. The bound belongs to
    # the PUBLISHED report, so every reading build must still carry it.
    measure = [c for c in whole if "MEASURE_PAGES_BOUND" in c]
    reading = [c for c in whole if "MEASURE_PAGES_BOUND" not in c]
    assert len(measure) == 1, "exactly one unbounded measure build"
    missing = [c for c in reading if "pages=pages" not in c]
    assert not missing, "a reading build without the page bound: %s" % missing


def test_the_stamp_records_the_bound():
    assert "pages_bound" in inspect.signature(rt.write_build_stamp).parameters


def test_fresh_ink_refuses_when_the_bound_differs(tmp_path):
    stamp = {"sha256": "abc", "formula_rule": "none", "pages_bound": None,
             "model_sha256": None}
    (tmp_path / "report.build.measure.json").write_text(json.dumps(stamp))
    (tmp_path / "report.ink.json").write_text(json.dumps(
        {"rows": [], "measured_against": {"sha256": "abc"}}))
    why = []
    assert ir.fresh_ink(tmp_path, formula_rule="none", pages_bound=10,
                        why=why) is False
    assert "pages_bound" in why[0]


def test_fresh_ink_resumes_when_the_bound_matches(tmp_path):
    stamp = {"sha256": "abc", "formula_rule": "none", "pages_bound": 10,
             "model_sha256": None}
    (tmp_path / "report.build.measure.json").write_text(json.dumps(stamp))
    (tmp_path / "report.ink.json").write_text(json.dumps(
        {"rows": [], "measured_against": {"sha256": "abc"}}))
    why = []
    assert ir.fresh_ink(tmp_path, formula_rule="none", pages_bound=10,
                        why=why) is True, why


def test_the_pages_parameter_is_never_rebound_inside_cmd_inkreport():
    """578 — one line assigned the PLAN's page estimate to `pages`, the
    parameter carrying --pages, so the resume test, all three builds and the
    stamp received an estimate instead of the bound. No error anywhere: the
    run simply measured a different report from the one requested."""
    import ast
    tree = ast.parse(inspect.getsource(C.cmd_inkreport).lstrip())
    fn = tree.body[0]
    params = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
    assert "pages" in params
    # `findings` IS rebound on purpose — `None` means "let the profile decide"
    # (561), which is resolving a default, not discarding a request. `pages`
    # carries a value the operator typed and has no such reading.
    rebound = [n.lineno for n in ast.walk(fn)
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
               and n.id == "pages"]
    assert not rebound, (
        "cmd_inkreport rebinds `pages` at line(s) %s of the function — every "
        "later reader gets the new value silently." % rebound)


def test_the_stamp_records_the_REQUEST_not_the_built_page_count():
    """`pages, errors, demoted = res` rebinds cmd_reporttex's own `pages`
    parameter to the number of pages the compile produced. The stamp must
    still carry what was asked for: a 10-page bound on a 2-page report is a
    bound of 10, and a later unbounded run must not match it."""
    src = inspect.getsource(C.cmd_reporttex)
    assert "_pages_bound = pages" in src, "the request is not captured"
    assert "pages_bound=_pages_bound" in src, (
        "write_build_stamp is given the rebound `pages` (the built count), "
        "not the captured request")
