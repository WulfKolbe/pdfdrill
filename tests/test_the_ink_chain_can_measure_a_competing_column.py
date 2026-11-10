"""T-0116 phase 2 — the ink chain must be able to measure a reading other than
the stored one, or no competing provenance can ever be confirmed.

THE GAP, measured 2026-11-01. `reporttex --prefer-refined` builds a report
whose rendered column carries `latex_refined` instead of `latex`
(`report_tex.rows_for`: `if refined and title in refined: latex =
refined[title]["refined"]`). The ink chain's own measure build does NOT pass
it:

    cmd_reporttex(pdf, compile_pdf=True, legend=False,
                  formulas=MEASURE_FORMULA_RULE, findings=MEASURE_FINDINGS,
                  pages=MEASURE_PAGES_BOUND, ink_bullets=False, cellrect=True)

so `prefer_refined` falls to its default False and the chain re-renders the
STORED reading. The consequence is not a missing feature, it is a wrong
answer: build a refined report by hand, run `pdfdrill inkreport`, and the
chain silently replaces your build with an unrefined one and hands back
distances for MathPix while you believe you are reading distances for the
competing column. I came within one command of reporting exactly that for
pix2text on 0707.4470.

This is why T-0116 records pix2text as "NOT integrated". The missing piece was
never a provider or a row namespace — the readings join the report's rows by
string (the row identifier IS the tiddler title, report_tex.py:2933), and
6,356 of 6,367 of them resolve. What is missing is that nothing can ask the
measure build to render anything but the stored LaTeX.

AND THE DISTANCE HAS TO COME FROM THIS CHAIN, not from a cheaper comparison.
`refine.py`'s docstring records why, from its own measurement: handed a
standalone render and a scan crop, inkdrill `compare` answers "no cells (no
ink region with >= 2 holes -- no table on this page)", because its lattice is
built from a RULED TABLE. refine.py therefore uses its own crop-level metric,
|Δcomponents| + |Δholes|, which is a different number from the `distance` in
ink-verdicts.csv. "Confirmed at distance 0" means this chain's distance, so
the competing column has to be measured through a report.
"""
import ast
import inspect
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# THIS CHECKOUT'S src, FIRST. The editable install resolves `pdfdrill` to the
# MAIN checkout, so a test file in a worktree that imports it without this line
# measures main's code and reports it as the branch's. Mine did, and said the
# threading was missing after I had already written it. `tests/test_eqlist.py`
# has carried this line since long before; it is the convention here.
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import commands as C                               # noqa: E402


def _measure_build_call() -> str:
    """The source of step 2, the measure build, as this repo's own
    test_measure_is_the_full_listing.py slices it."""
    src = inspect.getsource(C._inkreport_chain)
    i = src.index("2 — the MEASURE build")
    j = src.index("2b —", i)
    return src[i:j]


def test_the_measure_build_renders_the_column_it_was_asked_for():
    """The defect itself: step 2 must thread `prefer_refined` through."""
    call = _measure_build_call()
    assert "prefer_refined=prefer_refined" in call, (
        "the measure build does not pass prefer_refined, so the chain always "
        "re-renders the stored reading:\n" + call)


def test_the_chain_and_both_its_entry_points_take_prefer_refined():
    """A flag the chain honours but no caller can set is unreachable — the
    shape `--no-legend` already had before 404 made it internal."""
    for fn in (C._inkreport_chain, C.cmd_inkreport, C.cmd_residuals):
        params = inspect.signature(fn).parameters
        assert "prefer_refined" in params, (
            "%s cannot be asked to measure a competing column" % fn.__name__)
        assert params["prefer_refined"].default is False, (
            "%s must default to measuring the STORED reading" % fn.__name__)


def test_the_manifest_declares_the_flag_on_the_ink_commands():
    """`commands.yaml` is the single source of truth (CLAUDE.md). A capability
    that is not in the manifest is invisible to the planner, `status`, `steps`
    and `--ensure` — audit A4's shape, and the reason `--no-legend` was
    unreachable from the documented surface."""
    text = (ROOT / ".claude" / "skills" / "pdfdrill" / "commands.yaml").read_text(
        encoding="utf-8")
    for cmd in ("inkreport", "residuals"):
        m = re.search(r"^- name: %s$(.*?)(?=^- name: |\Z)" % cmd, text,
                      re.S | re.M)
        assert m, "no %s block in commands.yaml" % cmd
        assert "--prefer-refined" in m.group(1), (
            "%s does not declare --prefer-refined" % cmd)


def test_the_measurement_records_which_column_it_measured():
    """`measured_against` already carries `prefer_refined` (observed in
    0707.4470's report.ink.json). A measurement that does not say which
    reading it rendered cannot be told apart from one that rendered the other,
    and two such files are indistinguishable on disk."""
    from pdfdrill import report_tex as rt
    src = inspect.getsource(rt.build_record) if hasattr(rt, "build_record") \
        else inspect.getsource(rt)
    assert '"prefer_refined"' in src, (
        "report_tex's build record must write prefer_refined into the stamp, "
        "or a measurement cannot say which column it rendered")


def test_the_stored_reading_stays_the_default_everywhere():
    """No call site may turn this on by itself. The ink of record measures the
    document's own reading; a competing column is measured only when asked."""
    tree = ast.parse(inspect.getsource(C._inkreport_chain))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "cmd_reporttex"):
            continue
        for kw in node.keywords:
            if kw.arg == "prefer_refined":
                assert isinstance(kw.value, ast.Name), (
                    "prefer_refined must be threaded from the caller, never "
                    "hard-coded in the chain")


# --------------------------------------------------------------------------
# THE CLI. The gap my first five tests missed.
# --------------------------------------------------------------------------

def test_the_cli_binds_the_flag_to_the_handler(monkeypatch):
    """THE MANIFEST AND THE HANDLER ARE NOT THE CLI.

    `commands.yaml` declared `--prefer-refined`, `cmd_inkreport` and
    `cmd_residuals` both took it, the measure build threaded it — and the flag
    still did nothing, because `cli.py` parses argv by hand: each handler
    strips the switches it knows from `pdf_args` and passes named kwargs. An
    unlisted switch is neither stripped nor passed, so it fell through into the
    PDF argument list and was silently ignored.

    The gate run proved it the expensive way: 108 s of chain, 55 rows
    measured, and `measured_against.prefer_refined` came back False. The stamp
    is the only reason I did not report MathPix's distances as pix2text's.
    """
    from pdfdrill import cli
    seen = {}

    def fake_inkreport(pdf, **kw):
        seen.update(kw); return "ok"

    def fake_residuals(pdf, **kw):
        seen.update(kw); return "ok"

    import pdfdrill.commands as CM
    monkeypatch.setattr(CM, "cmd_inkreport", fake_inkreport, raising=True)
    monkeypatch.setattr(CM, "cmd_residuals", fake_residuals, raising=True)
    monkeypatch.setattr(cli, "_pdf", lambda a: Path("x.pdf"), raising=False)

    cli._do_inkreport(["x.pdf", "--prefer-refined"])
    assert seen.get("prefer_refined") is True, (
        "inkreport did not pass prefer_refined to its handler: %r" % (seen,))

    seen.clear()
    cli._do_residuals(["x.pdf", "--measure", "--prefer-refined"])
    assert seen.get("prefer_refined") is True, (
        "residuals did not pass prefer_refined to its handler: %r" % (seen,))


def test_the_flag_is_not_left_in_the_pdf_arguments():
    """An unstripped switch reaches `_pdf()` as if it were a path. That is the
    same silent-unknown-argument family as the bare positional which built a
    2.5 GB list over the wrong library earlier today: the CLI should never
    carry a switch it understands into a path list."""
    import inspect
    from pdfdrill import cli
    for fn in (cli._do_inkreport, cli._do_residuals):
        src = inspect.getsource(fn)
        i = src.index("pdf_args")
        strip = src[i:src.index("return", i)]
        assert "--prefer-refined" in strip, (
            "%s does not strip --prefer-refined from pdf_args" % fn.__name__)
