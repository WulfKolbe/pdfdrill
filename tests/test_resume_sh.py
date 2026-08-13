"""resume.sh must land in the LIVE session, and never silently start a new one.

The script pinned a session id. The harness crashed, started a new session, and
the script kept reopening the dead one — so the work looked lost when it was
simply in the session the script would not open. A comment explaining how to
reopen a different session does not fix that; the next crash behaves the same.

So: `--continue` by default, pinning opt-in, and a pinned id that does not
resolve exits 3 rather than degrading to a fresh session. The silent degrade is
the specific behaviour that hid the work.

Driven against a FAKE `claude` on PATH, so the assertions are about the argv the
script builds and the exit code it returns, not about a live harness.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "resume.sh"


def _fake_claude(tmp_path, *, exit_code=0):
    """A stand-in that records its argv and exits how the test wants."""
    log = tmp_path / "argv.txt"
    fake = tmp_path / "claude"
    fake.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$@" > {log}\n'
        f"exit {exit_code}\n")
    fake.chmod(0o755)
    return fake, log


def _run(tmp_path, args=(), env=None, exit_code=0):
    fake, log = _fake_claude(tmp_path, exit_code=exit_code)
    e = dict(os.environ, CLAUDE_BIN=str(fake))
    e.pop("PDFDRILL_SESSION", None)
    e.update(env or {})
    p = subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, env=e)
    argv = log.read_text().split("\n") if log.exists() else []
    return p, [a for a in argv if a]


def test_the_default_is_continue_not_a_pinned_id(tmp_path):
    p, argv = _run(tmp_path)
    assert p.returncode == 0
    assert "--continue" in argv
    assert "--resume" not in argv


def test_no_session_id_is_hardcoded_anywhere_in_the_script():
    """The original pinned 7baec1d2-… in the file itself."""
    import re
    text = SCRIPT.read_text()
    uuidish = re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", text)
    assert uuidish == [], f"a session id is hardcoded: {uuidish}"


def test_an_env_var_pins_a_session(tmp_path):
    p, argv = _run(tmp_path, env={"PDFDRILL_SESSION": "abc-123"})
    assert p.returncode == 0
    assert "--resume" in argv and "abc-123" in argv
    assert "--continue" not in argv


def test_a_flag_pins_a_session(tmp_path):
    _p, argv = _run(tmp_path, args=["--session", "def-456"])
    assert "--resume" in argv and "def-456" in argv


def test_a_pinned_session_that_fails_exits_3_and_does_NOT_start_a_new_one(tmp_path):
    """The whole point. A fresh session here is indistinguishable from the work
    having vanished, which is exactly how this was mis-diagnosed."""
    p, argv = _run(tmp_path, env={"PDFDRILL_SESSION": "dead-session"}, exit_code=1)
    assert p.returncode == 3, p.stderr
    assert "--continue" not in argv, "it degraded to a new session"
    assert "dead-session" in p.stderr
    assert "NOT falling back" in p.stderr


def test_a_failing_CONTINUE_is_not_masked(tmp_path):
    """`--continue` is exec'd, so the harness's own exit code reaches the caller
    rather than being swallowed into a success."""
    p, _argv = _run(tmp_path, exit_code=7)
    assert p.returncode == 7


def test_extra_arguments_are_passed_through(tmp_path):
    _p, argv = _run(tmp_path, args=["--", "--model", "opus"])
    assert "--model" in argv and "opus" in argv


def test_a_missing_claude_binary_is_reported_not_silent(tmp_path):
    e = dict(os.environ, CLAUDE_BIN=str(tmp_path / "nope"))
    e.pop("PDFDRILL_SESSION", None)
    p = subprocess.run([str(SCRIPT)], capture_output=True, text=True, env=e)
    assert p.returncode == 2 and "not on PATH" in p.stderr
