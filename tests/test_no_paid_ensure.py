r"""159 — an auto-inserted prerequisite must never reach a paid step.

`--ensure` is documented to run the OFFLINE prerequisites and merely NAME the
paid ones, and planner.ensure enforces that by refusing any step marked
`network: true`. The guarantee leaked one level down: `model` is offline in the
manifest, but cmd_model calls cmd_mathpix directly when no lines.json exists.

Observed, not theorised — `reporttex --ensure` on bradley_spring22 (no
lines.json) bought 32 MathPix pages on 2026-08-24 during a run whose whole
point was to avoid spending.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import no_paid_steps, paid_blocked, cmd_mathpix


def test_flag_is_off_by_default():
    assert paid_blocked() is False


def test_flag_is_set_inside_the_block_and_restored_after():
    with no_paid_steps():
        assert paid_blocked() is True
    assert paid_blocked() is False


def test_flag_is_restored_even_when_the_block_raises():
    """A failed prerequisite must not leave paid steps disabled for the rest of
    the process — nor leave them ENABLED if the guard is entered again."""
    try:
        with no_paid_steps():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert paid_blocked() is False


def test_nesting_restores_to_the_outer_state():
    with no_paid_steps():
        with no_paid_steps():
            assert paid_blocked() is True
        assert paid_blocked() is True
    assert paid_blocked() is False


def test_cmd_mathpix_refuses_without_touching_the_network(tmp_path):
    """The check is at the NETWORK boundary, so it holds no matter how deep the
    auto-chain that reached it was."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with no_paid_steps():
        out = cmd_mathpix(pdf)
    assert "NOT run" in out
    assert "pdfdrill mathpix doc.pdf" in out       # names the explicit command
    # nothing was written: no sidecar, no outputs
    assert not (tmp_path / "doc.lines.json").exists()


def test_planner_ensure_wraps_its_prerequisite_run():
    """The guard must be applied in planner.ensure itself, not left to callers —
    a parameter would have to thread through ~45 cmd_model call sites."""
    import inspect
    from pdfdrill import planner
    src = inspect.getsource(planner.ensure)
    assert "no_paid_steps()" in src
    assert src.index("with no_paid_steps()") < src.index("fn([pdf_arg])")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
