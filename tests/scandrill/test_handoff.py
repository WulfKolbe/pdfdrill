"""Stage III — the pdfdrill handoff, and the merge contract in BOTH directions.

The user's standing concern is that some commands historically *overrode* rather
than merged state. These tests pin that down against the REAL pdfdrill binary
rather than against a mock, because a mock would only prove we understand our own
assumptions.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import img2pdf
import pytest
from PIL import Image, ImageDraw

from pdfdrill.scandrill import handoff as ho
from pdfdrill.scandrill.manifest import Manifest, Page, REMOVED_BLANK
from pdfdrill.scandrill.tools import DEFAULT as TOOLS

needs_pdfdrill = pytest.mark.skipif(
    not (TOOLS.pdfdrill_home / "pdfdrill").exists(),
    reason="pdfdrill not available",
)


def _pdf(path: Path) -> Path:
    im = Image.new("RGB", (1200, 1600), "white")
    ImageDraw.Draw(im).text((80, 80), "handoff probe", fill="black")
    png = path.with_suffix(".png")
    im.save(png)
    path.write_bytes(img2pdf.convert(str(png)))
    return path


@pytest.fixture
def job(tmp_path: Path):
    pdf = _pdf(tmp_path / "job.pdf")
    m = Manifest(job="handoff", created="2026-07-15T14:30:12+02:00", lang="de-DE")
    p1 = m.add(Page(seq=0, src="raw/raw_1.png", sha256="a" * 64,
                    origin={"kind": "adf", "device": "airscan:e0", "sheet": 1,
                            "side": "front"},
                    skew_deg=0.46, blank_mean=0.87))
    p2 = m.add(Page(seq=0, src="raw/raw_2.png", sha256="b" * 64,
                    origin={"kind": "adf", "device": "airscan:e0", "sheet": 1,
                            "side": "back"},
                    skew_deg=-0.46, blank_mean=1.0))
    p2.status = REMOVED_BLANK
    return tmp_path, pdf, m


# ---- sidecar location -----------------------------------------------------------

@needs_pdfdrill
def test_sidecar_path_uses_pdfdrills_own_rule(tmp_path: Path):
    """Legacy layout: <name>.pdf.drill.json next to the PDF."""
    pdf = tmp_path / "paper.pdf"
    assert ho.sidecar_for(pdf).name == "paper.pdf.drill.json"


@needs_pdfdrill
def test_sidecar_path_handles_the_self_contained_layout(tmp_path: Path):
    """A PDF in a folder named after it is SELF-CONTAINED: <stem>/<stem>.drill.json.
    Hardcoding <pdf>.drill.json would write where pdfdrill never looks."""
    d = tmp_path / "mydoc"
    d.mkdir()
    pdf = d / "mydoc.pdf"
    got = ho.sidecar_for(pdf)
    assert got.name == "mydoc.drill.json"
    assert got.parent == d


# ---- the merge contract ---------------------------------------------------------

@needs_pdfdrill
def test_merge_writes_provenance_under_one_namespaced_key(job):
    _t, pdf, m = job
    path = ho.merge_provenance(m, pdf)
    data = json.loads(path.read_text())
    # Our key is namespaced, AND pdfdrill's own skeleton is present: we go through
    # its Sidecar class, so a sidecar we create first is still a valid pdfdrill one.
    assert "scandrill" in data
    for own in ("pdf", "pdfdrill_version", "facts", "evidence", "layers"):
        assert own in data, f"pdfdrill's own key {own!r} missing — skeleton not seeded"
    block = data["scandrill"]
    assert block["job"] == "handoff"
    assert block["lang"] == "de-DE"
    assert len(block["pages"]) == 2
    # removed pages must survive into the handoff — pdfdrill must account for them
    assert block["pages"][1]["status"] == REMOVED_BLANK
    assert block["pages"][0]["origin"]["sheet"] == 1
    assert block["pages"][0]["skew_deg"] == 0.46


@needs_pdfdrill
def test_merge_preserves_existing_pdfdrill_keys(job):
    """Direction 1: we must not clobber pdfdrill."""
    _t, pdf, m = job
    path = ho.sidecar_for(pdf)
    path.write_text(json.dumps({
        "pdf": "job.pdf", "pdfdrill_version": "0.4.0",
        "facts": ["SIZE_KNOWN"], "evidence": {"size": "1 page"},
        "pdfinfo": {"pages": 1}, "layers": {"x": 1}, "transitions": [{"cmd": "size"}],
    }))
    ho.merge_provenance(m, pdf)
    data = json.loads(path.read_text())
    assert data["facts"] == ["SIZE_KNOWN"]
    assert data["evidence"] == {"size": "1 page"}
    assert data["pdfinfo"] == {"pages": 1}
    assert data["layers"] == {"x": 1}
    assert data["transitions"] == [{"cmd": "size"}]
    assert data["scandrill"]["job"] == "handoff"


@needs_pdfdrill
def test_real_pdfdrill_run_preserves_our_key(job):
    """Direction 2 — THE test. Write our provenance, then let the REAL pdfdrill
    write the same sidecar, and prove our key survived.

    pdfdrill's Sidecar._load() reads the whole dict and save() writes it back, so
    unknown keys round-trip. If that ever changes, provenance would vanish
    silently on the first pdfdrill command — exactly the clobber this guards."""
    _t, pdf, m = job
    path = ho.merge_provenance(m, pdf)
    before = json.loads(path.read_text())["scandrill"]

    r = TOOLS.run_pdfdrill("size", pdf)          # a read-only cmd that DOES save state
    assert r.returncode == 0, r.stderr

    after = json.loads(path.read_text())
    assert "scandrill" in after, "pdfdrill CLOBBERED the scandrill provenance"
    assert after["scandrill"] == before, "pdfdrill mutated our provenance"
    # and pdfdrill really did write its own state into the same file
    assert after.get("facts"), "pdfdrill did not persist state — test is vacuous"
    assert after["pdf"] == "job.pdf"


@needs_pdfdrill
def test_merge_is_idempotent(job):
    _t, pdf, m = job
    ho.merge_provenance(m, pdf)
    first = ho.sidecar_for(pdf).read_text()
    ho.merge_provenance(m, pdf)
    assert ho.sidecar_for(pdf).read_text() == first


@needs_pdfdrill
def test_merge_refuses_a_corrupt_sidecar(job):
    _t, pdf, m = job
    ho.sidecar_for(pdf).write_text("{not json")
    with pytest.raises(ho.HandoffError, match="unreadable"):
        ho.merge_provenance(m, pdf)


# ---- analysis -------------------------------------------------------------------

@needs_pdfdrill
def test_analyze_runs_readonly_commands(job):
    _t, pdf, _m = job
    res = ho.analyze(pdf, ("size",))
    assert res["size"]["rc"] == 0
    assert "PDF" in res["size"]["out"]


@needs_pdfdrill
def test_analyze_reports_rather_than_raises_on_a_bad_command(job):
    _t, pdf, _m = job
    res = ho.analyze(pdf, ("definitely-not-a-command",))
    assert res["definitely-not-a-command"]["rc"] != 0


@needs_pdfdrill
def test_handoff_end_to_end(job):
    _t, pdf, m = job
    res = ho.handoff(m, pdf, commands=("size",))
    assert res.merged and res.sidecar.exists()
    assert res.analyses["size"]["rc"] == 0
    data = json.loads(res.sidecar.read_text())
    assert data["scandrill"]["pages"][0]["origin"]["kind"] == "adf"


def test_handoff_rejects_missing_pdf(tmp_path: Path):
    m = Manifest(job="x", created="2026-07-15T00:00:00+02:00")
    with pytest.raises(ho.HandoffError, match="no such PDF"):
        ho.handoff(m, tmp_path / "nope.pdf")


# ---- the OCR/route interaction --------------------------------------------------
#
# REAL pdfdrill route output, same scan, only --ocr differing (measured):
ROUTE_SCANNED = ("x.pdf: scanned → Gemma 4 [keyed] — scanned, 1 pages (≤20) "
                 "— small enough for Gemma.")
ROUTE_BORN = ("x.pdf: born-digital → pdfminer/text-layer [free] — born-digital "
              "(has a text layer, 1 pages).")


def _adf_manifest(ocr: dict | None = None) -> Manifest:
    m = Manifest(job="w", created="2026-07-15T00:00:00+02:00", ocr=ocr)
    m.add(Page(seq=0, src="raw/raw_1.png", origin={"kind": "adf", "sheet": 1,
                                                   "side": "front"}))
    return m


def test_warns_when_our_ocr_layer_misroutes_a_scan():
    """Our own text layer makes pdfdrill call a SCAN born-digital, sending it to
    pdfminer instead of a vision lane. Verified against the real binary."""
    m = _adf_manifest(ocr={"applied": True, "engine": "tesseract", "lang": "deu"})
    warns = ho.route_warnings(m, {"route": {"rc": 0, "out": ROUTE_BORN}})
    assert len(warns) == 1
    assert "BORN-DIGITAL" in warns[0] and "--ocr" in warns[0]


def test_no_warning_when_scan_routes_as_scanned():
    m = _adf_manifest(ocr={"applied": True, "engine": "tesseract", "lang": "deu"})
    assert ho.route_warnings(m, {"route": {"rc": 0, "out": ROUTE_SCANNED}}) == []


def test_no_warning_without_ocr_on_a_correctly_routed_scan():
    m = _adf_manifest()
    assert ho.route_warnings(m, {"route": {"rc": 0, "out": ROUTE_SCANNED}}) == []


def test_warns_on_unexpected_text_layer_even_without_our_ocr():
    m = _adf_manifest()
    warns = ho.route_warnings(m, {"route": {"rc": 0, "out": ROUTE_BORN}})
    assert len(warns) == 1 and "unexpected" in warns[0]


def test_route_warnings_tolerate_missing_analysis():
    assert ho.route_warnings(_adf_manifest(), None) == []
    assert ho.route_warnings(_adf_manifest(), {}) == []


@needs_pdfdrill
def test_ocr_provenance_reaches_the_sidecar(job):
    """The `ocr` block must travel with the PDF, so a downstream reader can tell
    an OCR text layer from born-digital text."""
    _t, pdf, m = job
    m.ocr = {"applied": True, "engine": "tesseract", "lang": "deu", "pages": 1}
    path = ho.merge_provenance(m, pdf)
    block = json.loads(path.read_text())["scandrill"]
    assert block["ocr"]["engine"] == "tesseract"
    assert block["ocr"]["applied"] is True


# ---- guardrails on what we let pdfdrill run -------------------------------------

@pytest.mark.parametrize("cmd", ["model", "mathpix", "tiddlers", "semantic", "vision"])
def test_analyze_refuses_pdfdrill_build_commands(tmp_path, cmd):
    """run_pdfdrill sets PDFDRILL_NO_PREFLIGHT=1, which walks straight through the
    SKILL's preflight gate — so the block has to live on OUR side. These commands
    cost money and are pdfdrill's call downstream, not ours."""
    pdf = _pdf(tmp_path / "x.pdf")
    with pytest.raises(ho.HandoffError, match="refusing to run pdfdrill build"):
        ho.analyze(pdf, (cmd,))


def test_analyze_refuses_build_command_mixed_with_safe_ones(tmp_path):
    pdf = _pdf(tmp_path / "x.pdf")
    with pytest.raises(ho.HandoffError, match="mathpix"):
        ho.analyze(pdf, ("size", "mathpix"))


def test_build_and_analysis_command_lists_are_disjoint():
    assert not (set(ho.ANALYSIS_COMMANDS) & set(ho.BUILD_COMMANDS))
