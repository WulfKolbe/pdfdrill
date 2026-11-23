"""T-0153 #1 — a scan carrying somebody's OCR text layer is still READ.

Measured by the coordinator on e33b01a9 (git-archive export, `env -i`,
sandbox) over the 30 board73 extracts:

    21 born pages   lines.json byte-identical to the board's `ours`
     6 scans, no text layer      no reading on either side
     3 scans WITH an OCR layer   RED

On those three — BH1 p113, BH3 p91, lib:025faeafae2f p153 — the board's
`ours` (`pdfdrill glyphlines`) reads the layer: 5,652-7,538 characters at a
scan score of 0.48-0.59. `pdfdrill drill` took the scan lane, wrote geometry
only, and ended `NOT REACHED - text: no reading`.

WHICH SIDE IS WRONG. Not the router. `docs/LANES.md` lane 1 is "the PDF
carries its OWN text layer, and is not a scan with somebody's OCR underlaid",
and `route` must not call such a document born-digital: the wording of that
branch exists because two sessions lost a morning on 2026-11-02 reading
`route` say "a scan with no text layer" about a file whose `size` said it had
one. That stays.

What is wrong is the step after it. The lane contract answers which reading to
BUY. It does not answer whether to use characters that are ALREADY IN THE FILE
for free -- and `glyphlines` reads them without a key, without a network call
and without asking the lane. `drill` read "this lane buys nothing" as "this
document has no reading" and threw away 5,652-7,538 characters a page.

So the contract's own sentence about the underlay -- that it is "also the most
useful fact about the document" -- becomes a field on the decision instead of
a phrase in a reason string, and the free reader is named once, in the router,
rather than re-derived in `drill`.
"""
from __future__ import annotations

import pytest

from pdfdrill import ocr_router as r


# --------------------------------------------------------------- the fact
def _d(**kw):
    base = dict(text_layer=None, needs_ocr=None, page_count=10)
    base.update(kw)
    return r.choose_route(**base)


def test_a_text_layer_on_full_page_scans_is_marked_an_underlay():
    d = _d(text_layer=True, needs_ocr=False, scanned_images=True)
    assert d.underlay is True, (
        "the router already computes `underlay` to pick the lane; the "
        "decision has to CARRY it, or every caller re-derives it")


def test_the_underlay_does_not_change_the_lane():
    """The 2026-11-02 incident. A scan stays a scan."""
    d = _d(text_layer=True, needs_ocr=False, scanned_images=True,
           keys=frozenset(), detector=True, ink=True)
    assert d.lane == "geometry"
    assert "UNDERLAY" in d.reason, "the layer is real and the route says so"


def test_a_scan_with_no_text_layer_is_not_an_underlay():
    d = _d(text_layer=False, needs_ocr=True, scanned_images=True,
           keys=frozenset(), detector=True, ink=True)
    assert d.lane == "geometry"
    assert d.underlay is False


def test_a_born_digital_document_is_not_an_underlay():
    d = _d(text_layer=True, needs_ocr=False, scanned_images=False)
    assert d.lane == "born_digital"
    assert d.underlay is False


# ------------------------------------------------- which free reader runs
def test_the_free_reader_for_a_born_digital_page_is_the_glyph_reader():
    d = _d(text_layer=True, needs_ocr=False, scanned_images=False)
    assert r.free_reading_for(d) == "glyphlines"


def test_the_free_reader_for_an_underlay_scan_is_ALSO_the_glyph_reader():
    """The red one. The characters are in the file and they cost nothing."""
    d = _d(text_layer=True, needs_ocr=False, scanned_images=True,
           keys=frozenset(), detector=True, ink=True)
    assert r.free_reading_for(d) == "glyphlines", (
        "5,652-7,538 characters a page, free, already in the file -- and "
        "`drill` answered `text: no reading`")


def test_a_scan_with_no_text_layer_has_no_free_reader():
    d = _d(text_layer=False, needs_ocr=True, scanned_images=True,
           keys=frozenset(), detector=True, ink=True)
    assert r.free_reading_for(d) is None, (
        "there is nothing to read: the geometry lane measures the page and "
        "says so. Inventing words here is the defect LANES.md names")


def test_an_install_that_cannot_run_the_lane_has_no_free_reader():
    """`cost='none'` on the geometry lane means there is no lane at all."""
    d = _d(text_layer=False, needs_ocr=True, scanned_images=True,
           keys=frozenset(), detector=True, ink=False)
    assert d.lane == "geometry" and d.cost == "none"
    assert r.free_reading_for(d) is None


def test_a_paid_lane_has_no_free_reader():
    d = _d(text_layer=False, needs_ocr=True, scanned_images=True,
           keys=frozenset({r.MATHPIX_KEY}))
    assert d.lane == "mathpix"
    assert r.free_reading_for(d) is None


def test_the_source_lane_has_no_free_glyph_reading():
    """No text layer at all: there are no glyphs to read, the author's LaTeX
    is the reading, and `model` takes that lane itself."""
    d = _d(text_layer=False, needs_ocr=True, arxiv_source=True)
    assert d.lane == "source"
    assert r.free_reading_for(d) is None


def test_an_unclassified_document_has_no_free_reader():
    d = _d()
    assert d.lane == "unknown"
    assert r.free_reading_for(d) is None


# ------------------------------------------------------------ the wording
def test_the_reason_no_longer_says_the_layer_is_ignored():
    """It is not ignored any more, so the sentence may not say it is.

    The incident the old wording fixed was `route` DENYING a layer that
    `size` reported. That stays fixed -- the reason still names the layer --
    but a reason that says "which is ignored" while `drill` reads it is the
    same defect pointed the other way.
    """
    d = _d(text_layer=True, needs_ocr=False, scanned_images=True,
           keys=frozenset(), detector=True, ink=True)
    assert "ignored" not in d.reason.lower()
    assert "maths" in d.reason.lower(), (
        "what the underlay genuinely cannot give is the mathematics, and "
        "that is the part worth keeping from the old sentence")


def test_every_lane_still_answers_and_the_field_defaults_to_False():
    """`RouteDecision` is constructed by hand in several places."""
    d = r.RouteDecision(lane="born_digital", reason="x", command="y",
                        cost="free")
    assert d.underlay is False


# ===================================================================== drill
# The pure answers above are only worth what the dispatch does with them.
# Same shape as `test_no_lane_means_no_work.py`: the bytes are NOT a PDF on
# purpose, because this is about the dispatch and a real PDF would hide a
# defect behind a parse error.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import cli, commands, planner          # noqa: E402
from pdfdrill.sidecar import Sidecar                 # noqa: E402


def _seed(tmp_path, *, text_layer: bool) -> Path:
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.set_evidence("pages", 10)
    sc.set_evidence("text_layer", text_layer)
    sc.set_evidence("needs_ocr", not text_layer)
    for fact in (commands.SIZE_KNOWN, commands.FONTS_KNOWN,
                 commands.ABSTRACT_ABSENT, commands.TOC_ABSENT):
        sc.add_fact(fact)
    sc.save()
    return pdf


@pytest.fixture
def spy(monkeypatch):
    """Every step `drill` could take, recorded instead of run."""
    seen: dict = {}
    for name in ("cmd_gemmaocr", "cmd_glyphlines", "cmd_model", "cmd_md",
                 "cmd_geometry", "cmd_inspect"):
        monkeypatch.setattr(
            commands, name,
            (lambda n: (lambda *a, **k: seen.setdefault(n, []).append(k) or ""))(name))
    monkeypatch.setattr(r, "ink_available", lambda: True)
    monkeypatch.setattr(r, "detector_available", lambda: True)
    monkeypatch.setattr(r, "arxiv_source_for", lambda *a, **k: False)
    monkeypatch.setattr(r, "keys_present", lambda: frozenset())
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    return seen


def test_drill_reads_the_underlay_with_the_glyph_reader(tmp_path, monkeypatch,
                                                        spy):
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: True)
    pdf = _seed(tmp_path, text_layer=True)
    cli._do_drill([str(pdf)])
    assert "cmd_glyphlines" in spy, (
        "drill did not read the OCR layer that is in the file: this is the "
        "red on BH1 p113, BH3 p91 and lib:025faeafae2f p153")


def test_drill_does_not_also_run_the_geometry_only_lane_on_an_underlay(
        tmp_path, monkeypatch, spy):
    """EITHER/OR, not both. There is ONE lines.json per document and the lane
    that runs last owns it (`gemma_reader.expected_outputs`), so a geometry
    pass after the glyph reading would replace the reading with boxes."""
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: True)
    pdf = _seed(tmp_path, text_layer=True)
    cli._do_drill([str(pdf)])
    assert "cmd_gemmaocr" not in spy, (
        "the geometry-only lane ran too, and it writes the same lines.json")


def test_a_scan_with_no_text_layer_is_UNCHANGED(tmp_path, monkeypatch, spy):
    """The gate's other half: the board's 6 textless scans must not move."""
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: None)
    pdf = _seed(tmp_path, text_layer=False)
    cli._do_drill([str(pdf)])
    assert "cmd_gemmaocr" in spy and spy["cmd_gemmaocr"][0].get(
        "geometry_only") is True
    assert "cmd_glyphlines" not in spy, (
        "there is nothing to read on this document and drill tried anyway")


def test_the_note_does_not_call_an_underlay_scan_born_digital(
        tmp_path, monkeypatch, spy):
    """The 2026-11-02 incident, pointed the other way round.

    THE FIRST VERSION OF THIS TEST WAS VACUOUS and it is worth saying why.
    It asserted `"born-digital" not in note` and `"UNDERLAY" in out`, and it
    PASSED against the unfixed code: without the fix the document never
    reaches the born-digital branch at all, so the phrase is absent for the
    wrong reason, and "UNDERLAY" is in `dec.reason` either way. A test that
    cannot fail has measured nothing.

    So it asserts the POSITIVE claim too — that the note says the model was
    built from that reading, which only the branch under test emits.
    """
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: True)
    monkeypatch.setattr(planner, "reading_producer", lambda *a, **k: "glyphlines")
    pdf = _seed(tmp_path, text_layer=True)
    out = str(cli._do_drill([str(pdf)]))
    note = out.split("--- lane ---")[-1]
    assert "built from that reading" in note, (
        "the note does not say the reading it built from:\n" + note[:400])
    assert "born-digital" not in note, (
        "the note claims the author's own glyphs for somebody's OCR:\n"
        + note[:400])
    assert "UNDERLAY" in note and "no mathematics" in note, (
        "and it no longer says what the underlay cannot give:\n" + note[:400])


# ============================================== THE CASE THE SANDBOX HID
# The three board pages passed their acceptance run byte-identical -- under
# `PDFDRILL_SANDBOX=1`, which answers as the KEYLESS install. Asked with the
# real environment of the machine this was written on, where a MAKORA_API_KEY
# is present, all three route to `gemma` (metered) and the first version of
# `free_reading_for` answered None. The fix would not have fired on the
# owner's own machine, and the acceptance run could not have told anyone.
#
# A sandbox pass is not a pass on the install the user has.

def _keyed_underlay(key):
    return _d(text_layer=True, needs_ocr=False, scanned_images=True,
              keys=frozenset({key}), detector=True, ink=True)


@pytest.mark.parametrize("key,lane,cost", [("gemma", "gemma", "metered"),
                                           ("mathpix", "mathpix", "paid")])
def test_a_keyed_machine_reads_the_underlay_too(key, lane, cost):
    d = _keyed_underlay(key)
    assert (d.lane, d.cost, d.underlay) == (lane, cost, True)
    assert r.free_reading_for(d) == "glyphlines", (
        f"on a machine with a {key} key the layer goes unread -- and a key "
        f"is the one thing that cannot make free characters cost money")


def test_the_reason_says_it_on_the_keyed_lanes_as_well():
    for key in ("gemma", "mathpix"):
        assert "ARE read" in _keyed_underlay(key).reason


def test_an_install_with_no_lane_at_all_still_reads_nothing():
    """`cost="none"` is the one exclusion, and it is not about the underlay:
    that branch means this install cannot run ANY lane for this document, its
    note tells the user to fix the install, and nothing is rendered or run."""
    d = _d(text_layer=True, needs_ocr=False, scanned_images=True,
           keys=frozenset(), detector=True, ink=False)
    assert (d.lane, d.cost, d.underlay) == ("geometry", "none", True)
    assert r.free_reading_for(d) is None
    assert "ARE read" not in d.reason


def test_drill_reads_the_underlay_on_a_keyed_machine(tmp_path, monkeypatch,
                                                     spy):
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: True)
    monkeypatch.setattr(r, "keys_present", lambda: frozenset({"gemma"}))
    pdf = _seed(tmp_path, text_layer=True)
    out = str(cli._do_drill([str(pdf)]))
    assert "cmd_glyphlines" in spy, (
        "the metered lane's mere EXISTENCE stopped the free reading")
    assert "cmd_gemmaocr" not in spy, "drill spent money"
    assert "NOT RUN by `drill`" in out, "the metered lane is not named"


def test_the_exit_code_on_a_keyed_underlay_comes_from_the_verdict(
        tmp_path, monkeypatch, spy):
    """EXIT_LANE_NOT_RUN says "this document has no reading and no
    inspect.html". On an underlay it has both, so that code would be a false
    statement to every script that reads it -- which is the exact reason the
    owner made it non-zero in the first place (2026-10-21)."""
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: True)
    monkeypatch.setattr(r, "keys_present", lambda: frozenset({"gemma"}))
    monkeypatch.setattr(planner, "reading_producer", lambda *a, **k: "glyphlines")
    pdf = _seed(tmp_path, text_layer=True)
    res = cli._do_drill([str(pdf)])
    assert getattr(res, "exit_code", 0) != cli.EXIT_LANE_NOT_RUN, (
        f"drill reports {cli.EXIT_LANE_NOT_RUN} (no reading) for a document "
        f"it just read")
    assert "has no reading" not in str(res)


def test_a_keyed_scan_with_NO_underlay_is_unchanged(tmp_path, monkeypatch,
                                                     spy):
    """The regression guard: `drill` must still refuse to spend, and must
    still say so, on a scan that has nothing free to read."""
    monkeypatch.setattr(r, "scanned_images_for", lambda *a, **k: None)
    monkeypatch.setattr(r, "keys_present", lambda: frozenset({"gemma"}))
    pdf = _seed(tmp_path, text_layer=False)
    res = cli._do_drill([str(pdf)])
    assert "cmd_glyphlines" not in spy and "cmd_gemmaocr" not in spy
    assert getattr(res, "exit_code", 0) == cli.EXIT_LANE_NOT_RUN
    assert "costs money" in str(res)
