r"""The layout detector's wrapper: what it reads, what it refuses, what it hides.

No model runs here. The detector is torch in another interpreter and a test
suite that needed it would be a test suite nobody runs; what IS tested is
everything around it — parsing its output, reconciling two detectors that find
the same formula, and the two failure modes that must stay named rather than
silent (no interpreter, no weights).

The reason the lane wants it at all, measured on penev_A: 5 of 116 display
formulas and 3 of 116 equation numbers boxed by the ink alignment alone,
against 110 and 112 with these boxes as anchors.
"""
from __future__ import annotations

import os

import pytest

from pdfdrill import yololayout as Y

TSV = (
    "model\tcls\tconf\tx1\ty1\tx2\ty2\n"
    "layout\tplain text\t0.91\t100\t100\t900\t400\n"
    "layout\tisolate_formula\t0.88\t200\t450\t800\t520\n"
    "layout\tformula_caption\t0.72\t850\t470\t920\t510\n"
    "layout\tfigure\t0.95\t120\t600\t880\t1000\n"
    "layout\tabandon\t0.64\t450\t40\t520\t70\n"
    "layout\tfigure_caption\t0.61\t300\t1010\t700\t1040\n"
    "mfd\tisolated\t0.80\t205\t455\t795\t515\n"
    "mfd\tembedding\t0.70\t310\t150\t360\t175\n"
)


def _write(tmp_path, name="page-0001.yolo.tsv", text=TSV):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_parses_every_row_and_skips_the_header(tmp_path):
    dets = Y.load(_write(tmp_path))
    assert len(dets) == 8
    assert dets[0].model == "layout" and dets[0].cls == "plain text"
    assert dets[0].box == (100.0, 100.0, 900.0, 400.0)
    assert dets[0].conf == pytest.approx(0.91)


def test_a_missing_tsv_is_no_boxes_and_not_an_error(tmp_path):
    """The lane must keep working WITHOUT the detector — it then aligns
    unanchored, which is exactly what it did before this module existed. A
    reader that raised here would make an optional capability mandatory."""
    assert Y.load(tmp_path / "nope.yolo.tsv") == []
    assert Y.load_for(tmp_path, tmp_path / "page-0042.png") == []


def test_a_truncated_or_unparsable_row_is_dropped_not_fatal(tmp_path):
    dets = Y.load(_write(tmp_path, text=(
        "model\tcls\tconf\tx1\ty1\tx2\ty2\n"
        "layout\tplain text\t0.9\t1\t2\t3\t4\n"
        "layout\tbroken\t0.9\t1\t2\n"
        "layout\tnan\tnope\t1\t2\t3\t4\n"
        "\n"
        "layout\ttitle\t0.5\t5\t6\t7\t8\n")))
    assert [d.cls for d in dets] == ["plain text", "title"]


# --------------------------------------------------------------------------- #
#  Reconciling the two detectors
# --------------------------------------------------------------------------- #

def test_the_two_detectors_finding_one_formula_give_one_anchor(tmp_path):
    """The layout box is kept. Letting the near-duplicate MFD box through
    would hand the alignment two anchors for one printed object, and then one
    of them is necessarily wrong."""
    boxes = Y.display_boxes(Y.load(_write(tmp_path)))
    assert boxes == [(200.0, 450.0, 800.0, 520.0)]


def test_an_mfd_box_that_is_a_piece_of_a_layout_box_is_not_its_own_formula():
    """One column of a formula block, one line of a system. The model writes
    those as separate `$$` items and the group-splitting in `align_anchored`
    handles them; a second anchor inside the first would not."""
    dets = [Y.Det("layout", Y.DISPLAY_LAYOUT, 0.9, (100, 100, 900, 400)),
            Y.Det("mfd", Y.DISPLAY_MFD, 0.8, (120, 120, 300, 180))]
    assert Y.display_boxes(dets) == [(100, 100, 900, 400)]


def test_an_mfd_formula_the_layout_model_missed_is_kept():
    dets = [Y.Det("layout", Y.DISPLAY_LAYOUT, 0.9, (100, 100, 900, 200)),
            Y.Det("mfd", Y.DISPLAY_MFD, 0.8, (100, 600, 900, 700))]
    assert Y.display_boxes(dets) == [(100, 100, 900, 200),
                                     (100, 600, 900, 700)]


def test_display_boxes_come_back_top_to_bottom():
    dets = [Y.Det("layout", Y.DISPLAY_LAYOUT, 0.9, (0, 900, 10, 950)),
            Y.Det("layout", Y.DISPLAY_LAYOUT, 0.9, (0, 100, 10, 150))]
    assert [b[1] for b in Y.display_boxes(dets)] == [100, 900]


def test_each_selector_returns_only_its_own_class(tmp_path):
    dets = Y.load(_write(tmp_path))
    assert Y.eqnum_boxes(dets) == [(850.0, 470.0, 920.0, 510.0)]
    assert Y.figure_boxes(dets) == [(120.0, 600.0, 880.0, 1000.0)]
    assert Y.inline_boxes(dets) == [(310.0, 150.0, 360.0, 175.0)]
    assert Y.abandon_boxes(dets) == [(450.0, 40.0, 520.0, 70.0)]
    assert Y.caption_boxes(dets) == [(300.0, 1010.0, 700.0, 1040.0)]


def test_the_mfd_weights_call_inline_math_embedding():
    """A detail that silently empties `inline_boxes` if it is forgotten: the
    shipped weights say "embedding" where newer ones say "inline"."""
    assert "embedding" in Y.INLINE_CLASSES and "inline" in Y.INLINE_CLASSES


def test_figure_boxes_are_largest_first():
    """So a box nested inside another is seen second and cannot whiten the
    outer one's content before it is considered."""
    dets = [Y.Det("layout", "figure", 0.9, (0, 0, 10, 10)),
            Y.Det("layout", "table", 0.9, (0, 0, 100, 100))]
    assert Y.figure_boxes(dets)[0] == (0, 0, 100, 100)


# --------------------------------------------------------------------------- #
#  Whitening, which happens BEFORE the paid read
# --------------------------------------------------------------------------- #

def test_whiten_erases_the_boxes_and_leaves_the_rest(tmp_path):
    """Two reasons, and they are separate. The model stops transcribing a
    picture — which it does at length, inventing axis labels that are printed
    nowhere — and the ink alignment afterwards sees no figure strokes to hand
    to a passing text line."""
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image", reason="Pillow")
    arr = np.zeros((100, 100), dtype="uint8")        # all ink
    src = tmp_path / "p.png"
    Image.fromarray(arr, mode="L").save(src)
    out = Y.whiten(src, [(10, 10, 40, 40)], tmp_path / "w" / "p.png")
    got = np.asarray(Image.open(out).convert("L"))
    assert got[25, 25] == 255                        # inside the box
    assert got[80, 80] == 0                          # outside it
    # the pad reaches just past the box and no further
    assert got[9, 25] == 255 and got[5, 25] == 0


def test_whiten_clips_a_box_that_runs_off_the_page(tmp_path):
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image", reason="Pillow")
    src = tmp_path / "p.png"
    Image.fromarray(np.zeros((50, 50), dtype="uint8"), mode="L").save(src)
    out = Y.whiten(src, [(-20, -20, 500, 500)], tmp_path / "w.png")
    assert (np.asarray(Image.open(out).convert("L")) == 255).all()


# --------------------------------------------------------------------------- #
#  The two failure modes, which must be named
# --------------------------------------------------------------------------- #

def test_no_interpreter_is_a_named_refusal_and_not_a_silent_skip(tmp_path,
                                                                 monkeypatch):
    monkeypatch.setattr(Y, "interpreter", lambda: None)
    with pytest.raises(Y.DetectorMissing) as exc:
        Y.detect([tmp_path / "page-0001.png"], tmp_path / "out")
    assert Y.INTERPRETER_ENV in str(exc.value)


def test_uncached_weights_refuse_rather_than_download(tmp_path, monkeypatch):
    """pdfdrill routes every network call through `net.urlopen` so a blocked
    host raises a typed, host-named error. A subprocess quietly fetching
    300 MB of weights would be the one call that escaped that, so the download
    is an explicit opt-in."""
    monkeypatch.setattr(Y, "interpreter", lambda: "/usr/bin/true")
    monkeypatch.setattr(Y, "weights_cached", lambda: False)
    with pytest.raises(Y.DetectorMissing) as exc:
        Y.detect([tmp_path / "page-0001.png"], tmp_path / "out")
    assert "allow_download" in str(exc.value)


def test_a_cached_page_is_not_detected_again(tmp_path, monkeypatch):
    """Minutes of CPU per document, so a lane that re-ran it on every
    assemble is a lane nobody waits for."""
    out = tmp_path / "out"
    out.mkdir()
    png = tmp_path / "page-0001.png"
    png.touch()
    _write(out)
    monkeypatch.setattr(Y, "interpreter",
                        lambda: pytest.fail("should not have been needed"))
    got = Y.detect([png], out)
    assert got == {"status": "cached", "ran": 0, "cached": 1,
                   "out_dir": str(out)}


def test_the_env_var_overrides_the_candidate_search(monkeypatch, tmp_path):
    fake = tmp_path / "python"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv(Y.INTERPRETER_ENV, str(fake))
    assert Y.interpreter() == str(fake)
    monkeypatch.setenv(Y.INTERPRETER_ENV, str(tmp_path / "absent"))
    assert Y.interpreter() is None


def test_describe_says_which_of_the_two_is_missing(monkeypatch):
    monkeypatch.setattr(Y, "interpreter", lambda: None)
    assert "no detector interpreter" in Y.describe()
    monkeypatch.setattr(Y, "interpreter", lambda: "/usr/bin/true")
    monkeypatch.setattr(Y, "weights_cached", lambda: False)
    assert "weights are not in the local cache" in Y.describe()
    monkeypatch.setattr(Y, "weights_cached", lambda: True)
    assert "weights cached" in Y.describe()
    assert Y.available()


def test_the_driver_imports_nothing_from_pdfdrill():
    """It is executed by an interpreter that CANNOT import this package, so an
    import of it would be a failure only reproducible on another machine."""
    import pathlib
    src = (pathlib.Path(Y.__file__).with_name("yolo_driver.py")
           .read_text(encoding="utf-8"))
    for line in src.splitlines():
        line = line.strip()
        if line.startswith(("import ", "from ")):
            assert "pdfdrill" not in line, line
