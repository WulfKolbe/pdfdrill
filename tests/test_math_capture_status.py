"""`status` must report math capture LIVE, from the model itself.

The build-time NEEDS_VISION_OCR gate only fires while `model` runs. A model
built before the gate existed — or by a route that skips it — stays silent
forever, and an auditor reading the artifact sees a clean report with every
formula missing. That is the exact `silent partial success` shape: plausible
output, something quietly absent, invisible to a negative assertion.

So the check is recomputed on READ, from the object counts, and never depends
on a fact stored at build time.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.commands import _format_math_capture


def test_math_bearing_but_zero_math_is_reported_loudly():
    out = _format_math_capture(n_formula=0, n_equation=0, source="pdfminer-chars",
                               math_bearing=True, reason="math fonts (CMMI, CMSY)")
    text = " ".join(out)
    assert out, "a math paper with no math captured must never report silently"
    assert "0 math" in text or "NO math" in text
    assert "math fonts" in text                      # says WHY we know it has math
    assert "visionocr" in text or "mathpix" in text   # says how to recover


def test_captured_math_reports_the_counts():
    out = _format_math_capture(n_formula=73, n_equation=1, source="pdfminer-chars",
                               math_bearing=True, reason="")
    text = " ".join(out)
    assert "73" in text and "1" in text
    assert "visionocr" not in text                    # nothing to recover


def test_not_math_bearing_and_no_math_is_silent():
    """A prose paper with no math is CORRECT, not a failure — no noise."""
    assert _format_math_capture(0, 0, "pdfminer-chars", math_bearing=False,
                                reason="") == []


def test_keyed_source_with_zero_math_still_flagged():
    """MathPix returning no math on a math paper is also a failure worth saying."""
    out = _format_math_capture(0, 0, "mathpix", math_bearing=True, reason="eq dests")
    assert out and ("0 math" in " ".join(out) or "NO math" in " ".join(out))


def test_message_never_has_an_empty_route_name():
    """Reported by the auditor: with no lines.json the source is "", so the line
    read "the  route returned none" — a blank where the route name belongs and a
    double space. A status line that is meant to explain a failure has to name
    the thing that failed."""
    out = _format_math_capture(0, 0, "", math_bearing=True, reason="math fonts")
    body = " ".join(l.strip() for l in out)          # leading indent is by design
    assert "  " not in body, f"double space inside the message: {body!r}"
    assert "the  route" not in body
    assert "lines.json" in body, "must say what is actually missing"
