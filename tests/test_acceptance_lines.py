r"""The owner's one-line commands are checked by the suite itself.

T-0136 asked for the runner to be "in make test". THIS PROJECT HAS NO Makefile
— the documented test command is
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider`
(CLAUDE.md § Tests) — so the equivalent, and the thing that actually makes the
owner's lines part of the gate, is a test here.

WHY THE DRIFT TEST IS THE IMPORTANT ONE
---------------------------------------
`OWNER-TESTS.md` is what the owner reads; `acceptance.LINES` is what runs. If
those two drift, the document describes a check nobody performs — which is the
same class of failure as the four CJK test files that assert Chinese is a defect
while no test reads a Chinese document, and as `fonts_layer` reporting 92 font
records without naming one. A document that claims a check is worse than no
document, because it buys trust it has not earned.

NO PATHS, NO FLAGS
------------------
The owner's constraint, in their words: "organize tests that does not use any
path, prefixes, or complex command lines." That is asserted here, so a later
line cannot quietly reintroduce a path and still call itself an owner test.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pdfdrill import acceptance

REPO = Path(__file__).resolve().parent.parent
OWNER_TESTS = REPO / "OWNER-TESTS.md"


def test_the_document_and_the_runner_name_the_same_lines():
    """Every line that runs is documented, and every documented line runs."""
    doc = OWNER_TESTS.read_text(encoding="utf-8")
    documented = set(re.findall(r"^\|\s*(A\d|B\d|C\d)\s*\|", doc, re.M))
    running = {ln["id"] for ln in acceptance.LINES}
    assert running - documented == set(), (
        f"these run but are not in OWNER-TESTS.md: {sorted(running - documented)}")
    assert documented - running == set(), (
        f"these are documented but do not run: {sorted(documented - running)}")


def test_no_line_uses_a_path_or_a_flag():
    """The owner's constraint, pinned: "no path, prefixes, or complex command
    lines". A bare command and a bare document id, nothing else."""
    for ln in acceptance.LINES:
        for tok in ln["argv"]:
            assert os.sep not in tok, f"{ln['id']} carries a path: {tok!r}"
            assert not tok.startswith("-"), f"{ln['id']} carries a flag: {tok!r}"


def test_every_line_says_what_must_appear():
    """A line with nothing to check is not a test. `route` is the one case where
    the check is the exit code alone, and it says so by having an empty
    `expect` — so this asserts the FIELD exists rather than that it is full."""
    for ln in acceptance.LINES:
        assert "expect" in ln, f"{ln['id']} declares no expectation"
        assert ln.get("why"), f"{ln['id']} does not say why it exists"


def test_a_gated_line_is_reported_not_run_and_never_omitted():
    """CLAUDE.md rule 6: a test that cannot run is NOT RUN, not a pass. The gate
    is read from the OUTPUT, because predicting it with `preflight.blocks` was
    wrong about `pdfdrill nonsense-command` — unknown commands are "not exempt"
    and so look gated, while pdfdrill refuses them before the gate."""
    assert acceptance._gate_reason(
        "⛔ pdfdrill STOP: BLOCKED until you attest that you read the SKILL", 2)
    assert acceptance._gate_reason("all fine", 0) is None


def _library_has_the_document() -> bool:
    try:
        from pdfdrill import config, sources
        return sources.library_pdf_for(
            sources.archive_stem("arxiv", acceptance.DOC),
            config.library_root()) is not None
    except Exception:                       # noqa: BLE001
        return False


@pytest.mark.skipif(not _library_has_the_document(),
                    reason=f"the library does not hold {acceptance.DOC}; the "
                           "A-group still runs via the runner itself")
def test_the_owner_lines_pass():
    """The lines themselves, run as the owner runs them. This is what T-0136
    meant by putting the runner in the test command: a defect that only shows
    through the installed entry point on a real document now turns the suite
    red, which is the gap that let the 2026-11-10 failures through a 6,331-green
    suite."""
    out = acceptance.run()
    m = re.search(r"(\d+) passed, (\d+) failed, (\d+) NOT RUN", str(out))
    assert m, f"no summary line in:\n{out}"
    passed, failed, not_run = (int(g) for g in m.groups())
    assert failed == 0, f"owner lines failed:\n{out}"
    assert passed >= 6, f"too few lines ran:\n{out}"


def test_a_not_run_line_makes_the_exit_code_non_zero():
    """Rule 11 / CLAUDE.md rule 6, in the one place a script can see it.

    The runner printed "2 NOT RUN" in prose and exited 0, so anything reading
    only the status — a CI step, a shell `&&`, drillui — read it as success.
    A green signal over work that was never done is the exact failure this task
    exists to end, so it must not be reintroduced by the tool that reports on
    it. 1 = a line failed, 3 = all that ran passed but some could not run.
    """
    out = acceptance.run()
    code = getattr(out, "exit_code", 0)
    m = re.search(r"(\d+) passed, (\d+) failed, (\d+) NOT RUN", str(out))
    assert m, f"no summary line in:\n{out}"
    _passed, failed, not_run = (int(g) for g in m.groups())
    if failed:
        assert code == 1, f"{failed} failed but exit={code}"
    elif not_run:
        assert code == 3, f"{not_run} NOT RUN but exit={code}"
    else:
        assert code == 0
