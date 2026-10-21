"""The FREE geometry lane must exist on the documented install, and `doctor`
must not claim it when it cannot run.

Found by an auditing session (drillgroup T-0046 §Audit, at 28b64cef): numpy sat
only in the `[layout]` extra, so after `bash bootstrap.sh && pip install -e .`
`pdfdrill drill <scan>` exited 0, wrote nothing and said "ink geometry needs
numpy" — while `doctor` printed `[OK] the FREE geometry lane`. Two defects in
one: a last-resort lane behind an optional extra, and a report that calls it
available.

docs/LANES.md makes the geometry lane the last resort — the reading a keyless
install can always reach. Its first half is the page's own ink, which is NumPy;
the detector only TYPES the lines it finds. So NumPy is the lane's floor, not an
enhancement, and it belongs in the base dependencies.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> str:
    return (ROOT / "pyproject.toml").read_text()


def _base_deps_block() -> str:
    s = _pyproject()
    m = re.search(r"^dependencies = \[(.*?)^\]", s, re.S | re.M)
    assert m, "no base dependencies block in pyproject.toml"
    return m.group(1)


def test_numpy_is_a_base_dependency_not_an_extra():
    assert "numpy" in _base_deps_block(), (
        "numpy is not in the base dependencies: the free geometry lane — the "
        "ONLY reading a keyless install can reach for a scan — would be absent "
        "after the documented install")


def test_requirements_txt_names_numpy_too():
    """bootstrap.sh installs from requirements.txt, not from pyproject."""
    assert "numpy" in (ROOT / "requirements.txt").read_text(), (
        "bootstrap.sh installs requirements.txt; without numpy there the "
        "documented install still has no free lane")


def test_doctor_does_not_claim_the_lane_without_numpy(monkeypatch):
    """THE CASE BUILT TO FAIL (ENGINEERING 2). With the ink half missing, the
    lane is not available and `doctor` has to say so — a report that names a
    lane the install cannot run sends the reader looking elsewhere."""
    from pdfdrill import commands, ocr_router
    monkeypatch.setattr(ocr_router, "ink_available", lambda: False)
    out = commands.cmd_doctor()
    assert "FREE geometry lane" in out
    line = next(l for l in out.splitlines() if "FREE geometry lane" in l)
    assert "[n/a]" in line or "NOT" in line, (
        f"doctor still reports the lane as available without NumPy: {line!r}")
    assert "numpy" in line.lower(), "the line does not name what is missing"


def test_doctor_reports_the_lane_when_the_ink_half_is_there(monkeypatch):
    from pdfdrill import commands, ocr_router
    monkeypatch.setattr(ocr_router, "ink_available", lambda: True)
    out = commands.cmd_doctor()
    line = next(l for l in out.splitlines() if "FREE geometry lane" in l)
    assert "[OK " in line, f"the lane is available but doctor says: {line!r}"


def test_doctor_says_which_half_is_missing_when_there_is_no_detector(monkeypatch):
    """Both halves are reported, because 'no types' and 'no lane' are different
    answers and the old line could not tell them apart."""
    from pdfdrill import commands, ocr_router, yololayout
    monkeypatch.setattr(ocr_router, "ink_available", lambda: True)
    monkeypatch.setattr(yololayout, "available", lambda: False)
    out = commands.cmd_doctor()
    line = next(l for l in out.splitlines() if "FREE geometry lane" in l)
    assert "[OK " in line, "the lane still works without the detector"
    assert "NO type" in line or "no type" in line, (
        f"doctor does not say the lines come out untyped: {line!r}")
