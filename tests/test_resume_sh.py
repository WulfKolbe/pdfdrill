"""resume.sh is the user's own one-liner: resume ONE pinned session, always.

History, because the contract has flipped twice and each flip was learned the
hard way: the original script hardcoded a pin, the harness crashed, and the
script kept reopening the dead session. The rewrite defaulted to `--continue` —
and `--continue` trapped the user in a looped session on exit. On 2026-08-16
the user replaced the script by hand with a hardcoded `--resume <id>` one-liner
and said so. These tests pin THAT contract; when the session dies, the id in
resume.sh is edited by hand and the id below follows it.

Driven against a FAKE `claude` on PATH — no live session is ever started.
"""
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "resume.sh"

UUIDISH = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"


def _run_with_fake_claude(tmp_path, exit_code=0):
    log = tmp_path / "argv.txt"
    fake = tmp_path / "claude"
    fake.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$@" > {log}\n'
        f"exit {exit_code}\n")
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ.get('PATH', '')}")
    p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
    argv = log.read_text().split("\n") if log.exists() else []
    return p, [a for a in argv if a]


def test_exactly_one_session_id_is_pinned_in_the_script():
    """The pin is the point now — one id, edited by hand when the session dies."""
    ids = re.findall(UUIDISH, SCRIPT.read_text())
    assert len(set(ids)) == 1, f"expected exactly one pinned session id, found: {ids}"


def test_the_script_resumes_the_pinned_id_and_never_continues(tmp_path):
    pinned = re.search(UUIDISH, SCRIPT.read_text()).group(0)
    p, argv = _run_with_fake_claude(tmp_path)
    assert p.returncode == 0
    assert "--resume" in argv and pinned in argv
    assert "--continue" not in argv, "a --continue is what looped the user"


def test_a_failing_resume_is_not_masked_as_success(tmp_path):
    p, _argv = _run_with_fake_claude(tmp_path, exit_code=7)
    assert p.returncode == 7
