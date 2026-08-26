"""199 — blackboard-bold digits.

amssymb's \\mathbb is the AMS msbm font and covers A-Z only. Its digit slots
hold negated turnstiles, so \\mathbb{1} rendered U+22AE ("does not force")
rather than failing: correct source, silently wrong glyph, 758 times across
44 corpus documents.
"""
from pdfdrill import report_tex as rt
from pdfdrill import refine as rf


def _formatted():
    """What actually reaches xelatex. PREAMBLE carries a %(bbdigits)s slot,
    not the literal block — asserting on the raw template would pass while the
    call site forgot to fill it."""
    return rt.PREAMBLE % {"bbdigits": rt.MATHBB_DIGITS, "form": "",
                          "geom": "a4paper", "unicode": ""}


def test_report_preamble_loads_a_digit_capable_package():
    assert "\\usepackage{bbm}" in _formatted()


def test_every_preamble_call_site_fills_the_slot(tmp_path):
    """A slot left unfilled is a TypeError at build time, not a silent gap —
    but only if a call site is exercised. Both are, here."""
    import json
    cp = tmp_path / "changes.json"
    cp.write_text(json.dumps({"bibkey": "x", "proposals": []}), encoding="utf-8")
    out = rt.build_refined_report(cp)["out"].read_text(encoding="utf-8")
    assert "\\usepackage{bbm}" in out


def test_mathbb_dispatches_digits_without_touching_letters():
    b = rt.MATHBB_DIGITS
    assert "\\renewcommand{\\mathbb}" in b
    assert "\\mathbbm{#1}" in b          # digits go to bbm
    assert "\\pdfdrillamsbb{#1}" in b    # everything else to the AMS font
    assert "\\let\\pdfdrillamsbb\\mathbb" in b


def test_the_standalone_renderer_shares_the_report_s_fix():
    """These MUST agree. The ink comparison measures a standalone render
    against a REPORT page; if one typesets a blackboard one and the other a
    turnstile, the instrument manufactures a difference the document does not
    contain."""
    assert rt.MATHBB_DIGITS in rf.RENDER_PREAMBLE


def test_amssymb_is_still_loaded_for_the_letters():
    assert "\\usepackage{amssymb}" in _formatted()
