"""Where the tests look for the patched-pdfminer interpreter. One answer, in
one place, because four test files used to hard-code it and a rename left all
four pointing at nothing — silently, since each one SKIPS when the venv is
absent.

TWO WAYS TO POINT AT IT, in this order:

  PDFMM_PYTHON   an explicit interpreter. Already the convention: `pdf2mmd.sh`
                 has honoured it since before this file existed. It is what
                 makes ONE build serve several checkouts — a worktree does not
                 inherit the main checkout's venv, and a 315 MB copy per
                 worktree to run 21 tests is not a reasonable default.
  <root>/work/pdfmm-venv/bin/python
                 the installer's own default (T-0113: visible, under the
                 git-ignored work/ tree; it used to be a dot-named directory
                 under vendor/, until the owner's "NO HIDDEN FILES" rule of
                 2026-10-30).

`skip_reason()` returns a sentence naming the path it looked at and the
variable that would override it, because "fork venv not built" sent four
readers to find out for themselves which path was meant.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "work" / "pdfmm-venv" / "bin" / "python"


def fork_python() -> Path:
    """The interpreter to run fork probes with. May not exist."""
    env = os.environ.get("PDFMM_PYTHON")
    return Path(env) if env else DEFAULT


def have_fork_venv() -> bool:
    p = fork_python()
    return p.is_file() and os.access(p, os.X_OK)


def skip_reason() -> str:
    p = fork_python()
    how = "PDFMM_PYTHON" if os.environ.get("PDFMM_PYTHON") else "the default"
    return ("patched-pdfminer venv not built: no interpreter at %s (%s). "
            "Build it with `bash vendor/install-pdfminer-fork.sh`, or set "
            "PDFMM_PYTHON to an existing one." % (p, how))
