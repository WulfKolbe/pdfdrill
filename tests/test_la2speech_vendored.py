"""
Gate for the VENDORED la2speech suite.

`tests/la2speech/test_latex2speech.py` is the upstream project's own script-style
runner, kept verbatim apart from its imports (which now address the package
rather than a sibling directory). pytest cannot collect it, so this drives it as
a subprocess — otherwise vendored code silently rots outside the suite, which is
exactly what vendoring is supposed to prevent.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "la2speech" / "test_latex2speech.py"


def test_vendored_la2speech_suite_passes():
    assert RUNNER.is_file(), "the vendored la2speech runner is missing"
    env = dict(os.environ)
    # Point it at whichever engine this machine has; without one its SRE-backed
    # tests SKIP (they do not fail), so the gate is still meaningful offline.
    for cand in (env.get("PDFDRILL_SRE_DIR"),
                 ROOT / "src" / "pdfdrill" / "la2speech" / "sre",
                 Path.home() / "la2speech" / "sre"):
        if cand and Path(cand).is_dir():
            env["SRE_DIR"] = str(cand)
            break
    r = subprocess.run([sys.executable, str(RUNNER)], capture_output=True,
                       text=True, timeout=900, cwd=str(ROOT), env=env)
    tail = (r.stdout or "")[-1500:] + (r.stderr or "")[-500:]
    assert "FAILED 0" in tail, f"vendored la2speech suite reported failures:\n{tail}"
    assert r.returncode == 0, f"runner exited {r.returncode}:\n{tail}"
