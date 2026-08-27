"""237 — the build stamp: make the artefact say what it is.

The measurement build and the reading build write THE SAME filenames, so a
phase-1 report is destroyed by the next phase-2 build and nothing on disk
records which phase the survivor is. 0902.0431's ink.json was measured against
a 20-page --min-conf 0.9 --no-legend build and now sits beside a 27-page
reading build. Every check anyone ran passed — including mine, which asked
whether any report_page exceeded the page count. It cannot catch this: a
measurement build has FEWER pages, so its page numbers always fit inside the
reading build that replaced it.
"""
import json

import pytest

from pdfdrill import report_tex as rt
from pdfdrill.commands import publish_ready
from tests.test_publish_ready import _doc, SPREAD


def _pdf(tmp_path, name="report.pdf", body=b"%PDF-1.4\n" + b"x" * 100):
    p = tmp_path / name
    p.write_bytes(body)
    return p


def test_a_stamp_describes_the_pdf_beside_it(tmp_path):
    p = _pdf(tmp_path)
    s = rt.build_stamp(p)
    assert s["bytes"] == p.stat().st_size and len(s["sha256"]) == 64
    assert rt.stamp_matches(s, p)[0]


def test_a_replaced_build_is_DETECTABLE(tmp_path):
    """The property the filenames lack."""
    p = _pdf(tmp_path)
    s = rt.build_stamp(p)
    p.write_bytes(b"%PDF-1.4\n" + b"y" * 400)          # phase 2 overwrites
    ok, why = rt.stamp_matches(s, p)
    assert not ok and "replaced" in why


def test_same_size_different_bytes_is_still_caught(tmp_path):
    p = _pdf(tmp_path)
    s = rt.build_stamp(p)
    p.write_bytes(b"%PDF-1.4\n" + b"y" * 100)          # identical length
    ok, why = rt.stamp_matches(s, p)
    assert not ok and "different bytes" in why


def test_the_phase_is_what_a_reader_acts_on(tmp_path):
    p = _pdf(tmp_path)
    m = rt.write_build_stamp(p, legend=False, ink_adopted=False,
                             prefer_refined=False, filters={})
    assert m["phase"] == "measure"
    for legend, ink in ((True, False), (False, True), (True, True)):
        r = rt.write_build_stamp(p, legend=legend, ink_adopted=ink,
                                 prefer_refined=False, filters={})
        assert r["phase"] == "reading", (legend, ink)


def test_the_stamp_lands_beside_the_report(tmp_path):
    p = _pdf(tmp_path)
    rt.write_build_stamp(p, legend=False, ink_adopted=False,
                         prefer_refined=False, filters={"max_conf": 0.5})
    on_disk = json.loads((tmp_path / rt.BUILD_STAMP).read_text())
    assert on_disk["filters"] == {"max_conf": 0.5}
    assert on_disk["phase"] == "measure"


# ------------------------------------------------------------- the gate ---

def _stamped(tmp_path, *, ink_extra=None, phase="measure"):
    pdf = _doc(tmp_path, ink=SPREAD)
    d = pdf.parent
    stamp = rt.write_build_stamp(
        d / "report.pdf", legend=(phase == "reading"),
        ink_adopted=False, prefer_refined=False, filters={})
    if ink_extra is not None:
        data = json.loads((d / "report.ink.json").read_text())
        data[rt.MEASURED_AGAINST] = ink_extra
        (d / "report.ink.json").write_text(json.dumps(data), encoding="utf-8")
    return pdf, stamp


def test_gate_passes_when_the_measurement_names_this_build(tmp_path):
    pdf, stamp = _stamped(tmp_path, ink_extra=None)
    pdf2, stamp2 = pdf, stamp
    data = json.loads((pdf.parent / "report.ink.json").read_text())
    data[rt.MEASURED_AGAINST] = stamp2
    (pdf.parent / "report.ink.json").write_text(json.dumps(data),
                                                encoding="utf-8")
    r = publish_ready(pdf)
    assert r["checks"]["ink"][0], r["checks"]["ink"][1]


def test_gate_refuses_a_measurement_of_a_DIFFERENT_build(tmp_path):
    """0902.0431 exactly: an ink.json whose build no longer exists.

    237b — checked against the SURVIVING measure-phase stamp, not against the
    published report. Under two-phase those are different files by
    construction (legend off vs on), so requiring sha equality against the
    published stamp would fail every correctly two-phased document and pass
    only the ones that skipped phase 1.
    """
    pdf, stamp = _stamped(tmp_path)          # writes report.build.measure.json
    other = dict(stamp, pages=20, bytes=999, sha256="0" * 64)
    data = json.loads((pdf.parent / "report.ink.json").read_text())
    data[rt.MEASURED_AGAINST] = other
    (pdf.parent / "report.ink.json").write_text(json.dumps(data),
                                                encoding="utf-8")
    r = publish_ready(pdf)
    assert not r["checks"]["ink"][0]
    assert "last phase=measure build" in r["checks"]["ink"][1]


def test_a_phase1_stamp_SURVIVES_the_phase2_build_that_replaces_its_pdf(tmp_path):
    """The stamp had the same collision as the thing it stamps: one filename,
    overwritten by the next build, destroying the one artefact a measurement
    needs to be checkable against."""
    p = _pdf(tmp_path)
    m = rt.write_build_stamp(p, legend=False, ink_adopted=False,
                             prefer_refined=False, filters={})
    p.write_bytes(b"%PDF-1.4\n" + b"z" * 900)          # phase 2 replaces it
    rt.write_build_stamp(p, legend=True, ink_adopted=True,
                         prefer_refined=False, filters={})
    survived = rt.measure_stamp(tmp_path)
    assert survived["sha256"] == m["sha256"]
    assert survived["phase"] == "measure"
    latest = json.loads((tmp_path / rt.BUILD_STAMP).read_text())
    assert latest["phase"] == "reading"


def test_a_correctly_two_phased_document_PASSES(tmp_path):
    """The case the assertion I first proposed would have failed: the measured
    build and the published build are different files, as designed."""
    pdf = _doc(tmp_path, ink=SPREAD)
    d = pdf.parent
    (d / "report.pdf").write_bytes(b"%PDF-1.4\n" + b"m" * 50)
    meas = rt.write_build_stamp(d / "report.pdf", legend=False,
                                ink_adopted=False, prefer_refined=False,
                                filters={})
    (d / "report.pdf").write_bytes(b"%PDF-1.4\n" + b"r" * 700)
    rt.write_build_stamp(d / "report.pdf", legend=True, ink_adopted=True,
                         prefer_refined=False, filters={})
    data = json.loads((d / "report.ink.json").read_text())
    data[rt.MEASURED_AGAINST] = meas
    (d / "report.ink.json").write_text(json.dumps(data), encoding="utf-8")
    r = publish_ready(pdf)
    assert r["checks"]["ink"][0], r["checks"]["ink"][1]


def test_gate_refuses_a_measurement_of_a_READING_build(tmp_path):
    pdf, stamp = _stamped(tmp_path, phase="reading")
    data = json.loads((pdf.parent / "report.ink.json").read_text())
    data[rt.MEASURED_AGAINST] = dict(stamp)
    (pdf.parent / "report.ink.json").write_text(json.dumps(data),
                                                encoding="utf-8")
    r = publish_ready(pdf)
    assert not r["checks"]["ink"][0]
    assert "READING build" in r["checks"]["ink"][1]


def test_gate_SAYS_SO_when_the_measurement_carries_no_stamp(tmp_path):
    """Today's state for every existing ink.json. Not a failure — an
    unrecorded provenance, named as unrecorded."""
    pdf, _ = _stamped(tmp_path)
    r = publish_ready(pdf)
    assert "unrecorded" in r["checks"]["ink"][1]


def test_gate_refuses_when_the_stamp_no_longer_matches_the_pdf(tmp_path):
    pdf, _ = _stamped(tmp_path)
    (pdf.parent / "report.pdf").write_bytes(b"%PDF-1.4\n" + b"z" * 5000)
    r = publish_ready(pdf)
    assert not r["checks"]["ink"][0]
    assert "no longer describes" in r["checks"]["ink"][1]
