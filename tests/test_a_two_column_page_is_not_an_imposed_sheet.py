r"""A two-column paper was read as an imposed sheet, and the layout pass paid
400 dpi and a whole detector run to throw its own work away.

MEASURED, 2026-10-29, cold, through the installed entry point, on 2016icpr.pdf
(6 pages, A4, two columns, born-digital with its own text layer):

    pdfdrill geometry --layout        263.93 s     — 44 s/page
    pdfdrill profile (the only command the manifest calls `slow`)
                                       21.98 s     —  3.7 s/page

and `geometry --layout`'s whole answer was "the sheets carry several printed
pages each, so the detector's boxes are in printed-page coordinates and the
model's pages are the PDF's — not placed". `pdfdrill drill` ran that pass
unconditionally: 116.88 s of a 120.73 s drill, 97%, for nothing. Library-wide,
9 of 271 sidecars that ran geometry carry a kept `layout_geometry` result.

WHAT THE DETECTOR ACTUALLY SAW (nup.detect over the 400 dpi renders, 3307x4677,
A4 aspect 1.41):

    page 1  1-up      page 3  2x2  quarter aspects 1.22 1.61 1.29 1.54
    page 2  1-up      page 5  2x2                  1.31 1.48 1.35 1.53
    page 4  1-up      page 6  3-up                 1.27 1.56 2.83

So the pieces have PLAUSIBLE PAGE ASPECTS and no threshold on shape reaches
them — the first thing tried here was an aspect window, and the measurement
above is what refused it. What separates these documents is not geometry at
all:

  AN IMPOSED SHEET IS A FACT ABOUT SCANNING. `nup` exists for penev_A, a thesis
  PHOTOGRAPHED four printed pages to a sheet. A born-digital PDF's page IS the
  printed page, by construction — the producer wrote one page object per page —
  and `model`'s `page` already indexes it. So when the document has its own
  text layer the imposition question is not asked: `split(nup="1")`, the
  module's own explicit door, instead of `nup="auto"`.

  The cost is a born-digital 2-up handout, which reads as 1-up. That is the
  pre-existing behaviour, `--nup` says otherwise explicitly, and the module's
  own asymmetry holds: a false POSITIVE cuts an ordinary page through the
  middle of a sentence, a false negative leaves the lane where it already was.

AND THE CHEAP QUESTION NOW COMES FIRST. `_layout_geometry` ran
`yololayout.detect` over every page and THEN asked whether the sheets were
1-up. The guard needs only `amap`, which exists three lines above the detector
call, so on every document the misread touched, the detector ran and its answer
was discarded by the next statement.
"""
import pytest

from pdfdrill import commands as C


def _pdf(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    return p


def _stub_layout(monkeypatch, tmp_path, *, text_layer, amap):
    """Everything `_layout_geometry` reaches outside itself, recorded."""
    from pdfdrill import nup as _nup, pdf_reading as _pr, word_boxes as _wb
    from pdfdrill import yololayout as _yolo
    seen: dict = {"detect": 0, "split_nup": None}
    monkeypatch.setattr(_yolo, "available", lambda: True)
    monkeypatch.setattr(_yolo, "detect",
                        lambda *a, **k: seen.__setitem__("detect",
                                                         seen["detect"] + 1))
    monkeypatch.setattr(_yolo, "load_for", lambda *a, **k: [])
    monkeypatch.setattr(_pr, "rasterize",
                        lambda *a, **k: [tmp_path / "page-0001.png"])
    monkeypatch.setattr(_pr, "page_of", lambda p: 1)
    monkeypatch.setattr(_wb, "has_text_layer", lambda p: text_layer)

    def _split(sheets, out_dir, **kw):
        seen["split_nup"] = kw.get("nup", "auto")
        return amap

    monkeypatch.setattr(_nup, "split", _split)
    return seen


# --------------------------------------------------------------------------- #
#  The discriminator: who is allowed to be an imposed sheet
# --------------------------------------------------------------------------- #

def test_a_born_digital_page_is_never_asked_whether_it_is_imposed(
        tmp_path, monkeypatch):
    """THE CASE BUILT TO FAIL. 2016icpr has a text layer, so its PDF page is
    its printed page and the detector's boxes are in the model's own frame."""
    pdf = _pdf(tmp_path)
    seen = _stub_layout(monkeypatch, tmp_path, text_layer=True,
                        amap={"1": {"sheet": 1, "box": [0, 0, 10, 10]}})
    monkeypatch.setattr(C, "_place_layout", lambda *a, **k: {"boxed": 3},
                        raising=False)
    from pdfdrill import layoutgeom
    monkeypatch.setattr(layoutgeom, "png_size", lambda p: (10, 10))
    monkeypatch.setattr(layoutgeom, "place", lambda *a, **k: {"boxed": 3})

    stats, why = C._layout_geometry(pdf, C.Sidecar(pdf), object())
    assert seen["split_nup"] == "1", (
        "a document with its own text layer must be split as 1-up, not `auto`")
    assert why == "", why
    assert stats == {"boxed": 3}
    assert seen["detect"] == 1, "and the detector must actually have run"


def test_a_scan_is_still_split_into_its_printed_pages(tmp_path, monkeypatch):
    """THE CONTROL. penev_A is why this module exists: no text layer, so the
    imposition is asked for and the answer is honoured."""
    pdf = _pdf(tmp_path)
    seen = _stub_layout(monkeypatch, tmp_path, text_layer=False, amap={
        "1": {"sheet": 1, "box": [0, 0, 10, 10]},
        "2": {"sheet": 1, "box": [10, 0, 20, 10]}})

    stats, why = C._layout_geometry(pdf, C.Sidecar(pdf), object())
    assert seen["split_nup"] == "auto", (
        "a scan's imposition is still detected, or penev_A's 88 printed pages "
        "collapse back into 22 sheets")
    assert stats == {}
    assert "several printed pages each" in why, why


# --------------------------------------------------------------------------- #
#  The order: the cheap question before the expensive answer
# --------------------------------------------------------------------------- #

def test_the_detector_does_not_run_when_its_answer_will_be_discarded(
        tmp_path, monkeypatch):
    """264 s of 400 dpi and YOLO, thrown away by the next line."""
    pdf = _pdf(tmp_path)
    seen = _stub_layout(monkeypatch, tmp_path, text_layer=False, amap={
        "1": {"sheet": 1, "box": [0, 0, 10, 10]},
        "2": {"sheet": 1, "box": [10, 0, 20, 10]}})

    stats, why = C._layout_geometry(pdf, C.Sidecar(pdf), object())
    assert stats == {} and "several printed pages each" in why
    assert seen["detect"] == 0, (
        "the detector ran before the question that discards its answer")


# --------------------------------------------------------------------------- #
#  And `drill` does not spend it unasked
# --------------------------------------------------------------------------- #

def test_drill_does_not_run_the_400_dpi_layout_pass_unasked():
    r"""`drill` is the shallow entry point the SKILL promises: "Always starts
    shallow … and escalates only when the question demands it". It called
    `cmd_geometry(pdf, layout=True)` unconditionally, which is 9.5 s/page — 12x
    the per-page cost of the only command the manifest calls `slow`.

    The cheap fusion stays (it is what gives the inspector its boxes) and the
    detector pass is now asked for only when `layoutgeom.candidate_count` says
    it would place something. The two behaviours are tested in
    `tests/test_drill_chain.py`; what this asserts is that the DECISION exists
    at all, because a future edit that drops the guard restores the 97%."""
    import inspect as _inspect
    from pdfdrill import cli
    src = _inspect.getsource(cli._do_drill)
    assert "_layout_candidates(pdf)" in src.replace(" ", ""), (
        "drill must ask whether the pass would change anything before it "
        "spends 9.5 s/page on it")
    assert "cmd_geometry(pdf" in src.replace(" ", ""), (
        "the cheap pdftotext geometry fusion must still run — it is what "
        "stops the inspector showing a box-less page")
    assert "geometry --layout" in src, (
        "and the pass must be NAMED when it is skipped, with its command")
