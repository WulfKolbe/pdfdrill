"""tools/drill_full.sh must be impossible to mistake for a clean run.

`set -e` is deliberately off in that script — a document without tables must
not abort the whole drill — and until 647 that meant a step could print a
Python traceback, scroll off the screen, and the script would carry on and
exit 0. Two of them did exactly that (`expandmath`, `formulas`, task 647).

HANDOVER-RULES rule 11: *a masked success reads exactly like a masked
failure*, and any success/failure summariser must be tested on BOTH a real
success and a real failure — a parser that can only see one of them sees
neither. So both directions are exercised here, end to end, by running the
real script against a stub `python3` on PATH.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DRILL_FULL = REPO / "tools" / "drill_full.sh"
DRILL_SANDBOX = REPO / "tools" / "drill_full_sandbox.sh"

#: a stub `python3` that answers `python3 -m pdfdrill <cmd> <doc> ...` without
#: importing pdfdrill at all, and fails (rc 3, three lines of traceback) for
#: every command named in $DRILL_TEST_FAIL.
STUB = r"""#!/usr/bin/env bash
# args: -m pdfdrill <cmd> <doc> [...]
cmd="$3"
IFS=, read -ra fails <<< "${DRILL_TEST_FAIL:-}"
for f in "${fails[@]}"; do
  if [ "$f" = "$cmd" ]; then
    echo "Traceback (most recent call last):" >&2
    echo "  File \"cmd_${cmd}.py\", line 1, in <module>" >&2
    echo "TypeError: ${cmd} exploded" >&2
    exit 3
  fi
done
echo "ok ${cmd}"
"""


def _workspace(tmp_path: Path, *, cached_mathpix: bool = False) -> tuple[Path, dict]:
    """A doc folder, a stub python3 on PATH, and the env to run the script in."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text(STUB)
    stub.chmod(0o755)

    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4\n")
    if cached_mathpix:
        (tmp_path / "doc.lines.json").write_text("{}")

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env.pop("DRILL_TEST_FAIL", None)
    return doc, env


def _run(script: Path, doc: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), doc.name],
        cwd=doc.parent, env=env, capture_output=True, text=True, timeout=120,
    )


def _steps(out: str) -> dict[str, str]:
    """The STEP TABLE as {label: rc}."""
    table = out.split("== STEP TABLE ==", 1)[1]
    rows = {}
    for line in table.splitlines():
        m = re.match(r"^(\S.*?)\s{2,}(\d+)\s+(\d+)s$", line)
        if m and m.group(1) != "STEP":
            rows[m.group(1)] = m.group(2)
    return rows


# ---------------------------------------------------------------------------
# a real success
# ---------------------------------------------------------------------------

def test_clean_run_exits_zero_and_prints_every_step(tmp_path):
    doc, env = _workspace(tmp_path)
    env["MATHPIX_APP_ID"] = ""          # deterministic: the SKIPPED branch
    r = _run(DRILL_FULL, doc, env)

    assert r.returncode == 0, r.stdout[-3000:]
    assert "== FAILED STEPS" not in r.stdout
    steps = _steps(r.stdout)
    # the whole drill, not a truncated one; every step rc 0
    assert set(steps.values()) == {"0"}
    for label in ("size", "model", "clean", "expandmath", "formulas",
                  "tiddlers", "artifacts", "status"):
        assert any(k.startswith(label) for k in steps), f"{label} missing: {steps}"
    assert re.search(r"All \d+ steps succeeded", r.stdout)


# ---------------------------------------------------------------------------
# a real failure
# ---------------------------------------------------------------------------

def test_failed_steps_are_named_with_rc_and_tail_and_exit_nonzero(tmp_path):
    doc, env = _workspace(tmp_path)
    env["MATHPIX_APP_ID"] = ""
    env["DRILL_TEST_FAIL"] = "expandmath,formulas"
    r = _run(DRILL_FULL, doc, env)

    assert r.returncode != 0, "a run with two crashed steps exited 0"
    assert "== FAILED STEPS (2 of" in r.stdout
    block = r.stdout.split("== FAILED STEPS", 1)[1]
    assert "expandmath" in block and "formulas" in block
    assert "(rc=3)" in block
    # the last 3 lines of the crash, so the failure is readable without the log
    assert "TypeError: expandmath exploded" in block
    assert "TypeError: formulas exploded" in block
    # and the steps AFTER the crash still ran (continue-on-failure preserved)
    steps = _steps(r.stdout)
    assert steps["expandmath (persist expanded + original LaTeX)"] == "3"
    assert any(k.startswith("report") for k in steps)
    assert not re.search(r"All \d+ steps succeeded", r.stdout)


def test_traceback_survives_in_the_doc_folder_log(tmp_path):
    doc, env = _workspace(tmp_path)
    env["MATHPIX_APP_ID"] = ""
    env["DRILL_TEST_FAIL"] = "expandmath"
    _run(DRILL_FULL, doc, env)

    log = doc.parent / "drill_full.log"
    assert log.exists(), "no drill_full.log beside the document"
    text = log.read_text()
    assert "----- expandmath (persist expanded + original LaTeX) (rc=3) -----" in text
    assert "Traceback (most recent call last):" in text
    # not only the failures: a clean step's output is there too
    assert "----- size (rc=0) -----" in text
    assert "ok size" in text


# ---------------------------------------------------------------------------
# the sandbox wrapper — the money guard
# ---------------------------------------------------------------------------

def test_sandbox_wrapper_never_forces_mathpix_when_lines_json_is_cached(tmp_path):
    """--force re-uploads and re-charges. A cached lines.json must take the
    'cached — no re-upload' branch, and `mathpix` must be called WITHOUT
    --force."""
    doc, env = _workspace(tmp_path, cached_mathpix=True)
    env["MATHPIX_APP_ID"] = "test-app-id"
    r = _run(DRILL_SANDBOX, doc, env)

    assert r.returncode == 0, r.stdout[-3000:]
    assert "mathpix (cached — no re-upload)" in r.stdout
    assert "--force" not in r.stdout


def test_sandbox_wrapper_is_the_same_script(tmp_path):
    """It must be a wrapper, not a copy: the failure recording lives in exactly
    one file, so it cannot be present in one script and absent in the other."""
    body = DRILL_SANDBOX.read_text()
    assert "exec bash" in body and "drill_full.sh" in body
    assert "DRILL_LOAD_ENV=1" in body and "DRILL_MATHPIX_NO_FORCE=1" in body
    assert len(body.splitlines()) < 40, "the sandbox script grew a copy again"


def test_plain_script_still_forces_when_nothing_is_cached(tmp_path):
    doc, env = _workspace(tmp_path)          # no lines.json
    env["MATHPIX_APP_ID"] = "test-app-id"
    env.pop("DRILL_MATHPIX_NO_FORCE", None)
    r = _run(DRILL_FULL, doc, env)
    assert "--force" in r.stdout
    assert r.returncode == 0, r.stdout[-3000:]
