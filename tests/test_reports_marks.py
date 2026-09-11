# tests/test_reports_marks.py — 672: draw inkdrill's formula marks onto a
# copy of the crop; never touch report-crops/ or report-crops-b/.
import json
from pathlib import Path

import pdfdrill.reports.marks as MK
from pdfdrill.commands import _marks_line
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine


REGION = {"top_left_x": 10, "top_left_y": 20, "width": 300, "height": 40}


def _host(page=3, region=None):
    return HostLine(page=page, region=region if region is not None else dict(REGION))


def _real_jpg(path: Path, w=300, h=40):
    """A PIL-openable JPEG that carries real, non-uniform content — a
    plain fill would be BLANK per `MK._is_blank` (672 review, finding 1:
    a uniform-colour crop is exactly the shape a real production crop
    with no rendered content takes, and must be refused, not drawn on).
    A few dark bars give it real stddev while staying trivial to build."""
    from PIL import Image, ImageDraw
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (w, h), color=(255, 255, 255))
    d = ImageDraw.Draw(im)
    for x in range(5, w - 5, max(6, w // 20)):
        d.line([(x, 3), (x, h - 3)], fill=(20, 20, 20), width=1)
    im.save(path, "JPEG", quality=95)


def _blank_jpg(path: Path, w=300, h=40, color=(255, 255, 255)):
    """A uniform crop — exactly the shape of the real blank production
    crops the review found (1510.06699_FO0765/_FO0911, all stddev 0.0)."""
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color=color).save(path, "JPEG", quality=95)


def _mrow(**over):
    base = dict(id="D_FO0001", page=3, host_page=3, math="x+y",
               region=dict(REGION), mark=True, why_no_mark=None,
               rect=[1.0, 2.0, 100.0, 30.0],
               rect_frac=[0.1, 0.1, 0.6, 0.8], y_from="ink")
    base.update(over)
    return base


# --- check_row -------------------------------------------------------

def test_check_row_passes_when_region_host_page_and_math_all_agree():
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host())
    assert MK.check_row(row, _mrow()) is None


def test_check_row_refuses_on_a_region_mismatch():
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host())
    mrow = _mrow(region={"top_left_x": 999, "top_left_y": 20, "width": 300,
                         "height": 40})
    reason = MK.check_row(row, mrow)
    assert reason is not None and "region/host_page" in reason


def test_check_row_refuses_on_a_host_page_mismatch():
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(page=3))
    mrow = _mrow(host_page=9)
    reason = MK.check_row(row, mrow)
    assert reason is not None and "region/host_page" in reason


def test_check_row_refuses_on_a_reading_change():
    """`math` is display_safe(latex), not raw latex — this is what
    inkdrill's own tool parsed back out of \\FitMath{...}."""
    row = FormulaRow(identifier="D_FO0001", latex="z", host_line=_host())
    reason = MK.check_row(row, _mrow(math="x+y"))
    assert reason is not None and "math mismatch" in reason


def test_check_row_refuses_when_our_own_row_has_no_host_line():
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=None)
    reason = MK.check_row(row, _mrow())
    assert reason is not None and "no host line" in reason


# --- apply -------------------------------------------------------------

def test_apply_is_a_no_op_without_a_marks_path():
    rows = {"formula": [FormulaRow(identifier="D_FO0001", latex="x+y",
                                   host_line=_host())],
            "equation": [EquationRow(identifier="D_EQ0001", latex="a")]}
    out, counts = MK.apply(rows, None, "/does/not/matter")
    assert out is rows
    assert counts == {"rows": 1, "marked_in_file": None, "checked": 0,
                      "drawn": 0, "refused": {}}


def test_apply_draws_a_real_crop_and_repoints_the_row_leaving_the_source_untouched(tmp_path):
    doc_dir = tmp_path
    crop = doc_dir / "report-crops" / "D_FO0001.jpg"
    _real_jpg(crop)
    before = crop.read_bytes()
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(),
                     crop=crop)
    rows = {"formula": [row]}
    marks_path = doc_dir / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 1},
        "rows": [_mrow()]}))

    out, counts = MK.apply(rows, marks_path, doc_dir)

    assert counts["drawn"] == 1
    assert counts["checked"] == 1
    assert counts["marked_in_file"] == 1
    assert counts["refused"] == {}
    drawn_row = out["formula"][0]
    assert drawn_row.crop != crop
    assert drawn_row.crop.parent.name == MK.MARKS_DIR
    assert drawn_row.crop.is_file()
    # the SOURCE crop_sha256/crop_gate/655's budget must read is untouched
    assert crop.read_bytes() == before


def test_apply_leaves_a_document_wide_refusal_untouched_and_tallies_it(tmp_path):
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host())
    rows = {"formula": [row]}
    marks_path = tmp_path / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": "stale: D.lines.json changed since the run",
        "counts": None, "rows": []}))

    out, counts = MK.apply(rows, marks_path, tmp_path)

    assert out["formula"][0] is row               # unmoved
    assert counts["drawn"] == 0
    assert list(counts["refused"].values()) == [1]
    assert "stale" in next(iter(counts["refused"]))


def test_apply_counts_a_missing_row_as_refused_not_a_silent_skip(tmp_path):
    row = FormulaRow(identifier="D_FO0002", latex="x+y", host_line=_host())
    rows = {"formula": [row]}
    marks_path = tmp_path / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 0}, "rows": []}))

    out, counts = MK.apply(rows, marks_path, tmp_path)

    assert out["formula"][0] is row
    assert counts["refused"] == {"not offered a mark (no row of this id in "
                                 "the file)": 1}


def test_apply_leaves_an_unmarked_row_alone_without_counting_it_as_refused(tmp_path):
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host())
    rows = {"formula": [row]}
    marks_path = tmp_path / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 0},
        "rows": [_mrow(mark=False, why_no_mark="position not unique",
                       rect=None, rect_frac=None, y_from=None)]}))

    out, counts = MK.apply(rows, marks_path, tmp_path)

    assert out["formula"][0] is row
    assert counts["checked"] == 0
    assert counts["drawn"] == 0
    assert counts["refused"] == {}


def test_apply_refuses_a_row_with_no_crop_to_draw_on(tmp_path):
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(),
                     crop=None)
    rows = {"formula": [row]}
    marks_path = tmp_path / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 1}, "rows": [_mrow()]}))

    out, counts = MK.apply(rows, marks_path, tmp_path)

    assert counts["drawn"] == 0
    assert counts["refused"] == {"no crop to draw on": 1}


def test_apply_refuses_a_blank_crop_instead_of_drawing_on_nothing(tmp_path):
    """672 review, finding 1 — a crop that EXISTS but carries no visible
    content (the real shape of 1510.06699_FO0765/_FO0911 and
    kohlhase-omdoc_FO0045: all `stddev == 0.0`) must be refused, never
    drawn on: a rectangle on a blank crop asserts an evidence claim the
    crop itself does not support."""
    doc_dir = tmp_path
    crop = doc_dir / "report-crops" / "D_FO0001.jpg"
    _blank_jpg(crop)
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(),
                     crop=crop)
    rows = {"formula": [row]}
    marks_path = doc_dir / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 1}, "rows": [_mrow()]}))

    out, counts = MK.apply(rows, marks_path, doc_dir)

    assert counts["drawn"] == 0
    assert counts["refused"] == {"crop has no visible content (blank)": 1}
    assert out["formula"][0] is row                # unmoved, crop untouched


def test_apply_refuses_a_row_whose_marks_entry_has_no_rect_frac(tmp_path):
    """A malformed/hand-edited marks file must not crash the whole
    build — every other failure mode here is a counted refusal, not an
    exception (672 review, minor finding)."""
    doc_dir = tmp_path
    crop = doc_dir / "report-crops" / "D_FO0001.jpg"
    _real_jpg(crop)
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(),
                     crop=crop)
    rows = {"formula": [row]}
    marks_path = doc_dir / "marks.json"
    mrow = _mrow()
    del mrow["rect_frac"]
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 1}, "rows": [mrow]}))

    out, counts = MK.apply(rows, marks_path, doc_dir)

    assert counts["drawn"] == 0
    assert counts["refused"] == {"marks file row is missing rect_frac": 1}
    assert out["formula"][0] is row


def test_apply_only_touches_the_formula_kind():
    eq = EquationRow(identifier="D_EQ0001", latex="a")
    rows = {"equation": [eq], "formula": []}
    out, _counts = MK.apply(rows, None, "/x")
    assert out is rows            # no-op path returns the same dict


def test_apply_threads_the_rungs_own_quality_into_the_draw(tmp_path, monkeypatch):
    """672 review, finding 2 — the quality must follow the CALLER's own
    rung, never a constant: `ensure_crops` chose (0.42, 70) for this
    kind, so the marked file must be saved at quality 70, not
    `DEFAULT_QUALITY`."""
    doc_dir = tmp_path
    crop = doc_dir / "report-crops-b" / "D_FO0001.jpg"
    _real_jpg(crop)
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(),
                     crop=crop)
    rows = {"formula": [row]}
    marks_path = doc_dir / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 1}, "rows": [_mrow()]}))

    seen = {}
    real_draw = MK._draw

    def spy(src, dst, rect_frac, quality=MK.DEFAULT_QUALITY):
        seen["quality"] = quality
        return real_draw(src, dst, rect_frac, quality=quality)

    monkeypatch.setattr(MK, "_draw", spy)
    out, counts = MK.apply(rows, marks_path, doc_dir, rung=(0.42, 70))

    assert counts["drawn"] == 1
    assert seen["quality"] == 70


def test_apply_uses_default_quality_when_the_kind_was_never_scaled(tmp_path, monkeypatch):
    doc_dir = tmp_path
    crop = doc_dir / "report-crops" / "D_FO0001.jpg"
    _real_jpg(crop)
    row = FormulaRow(identifier="D_FO0001", latex="x+y", host_line=_host(),
                     crop=crop)
    rows = {"formula": [row]}
    marks_path = doc_dir / "marks.json"
    marks_path.write_text(json.dumps({
        "refused": None, "counts": {"marked": 1}, "rows": [_mrow()]}))

    seen = {}
    real_draw = MK._draw

    def spy(src, dst, rect_frac, quality=MK.DEFAULT_QUALITY):
        seen["quality"] = quality
        return real_draw(src, dst, rect_frac, quality=quality)

    monkeypatch.setattr(MK, "_draw", spy)
    out, counts = MK.apply(rows, marks_path, doc_dir, rung=None)

    assert counts["drawn"] == 1
    assert seen["quality"] == MK.DEFAULT_QUALITY


def test_a_fixed_high_quality_reencode_measurably_inflates_an_already_scaled_crop():
    """Pins the MEASUREMENT behind finding 2 with a real (non-uniform)
    JPEG re-encoded twice: quality 92 (the old constant) must cost more
    bytes than quality 70 (a real 655 floor rung) for the identical
    marked pixels. Guards against the fix being silently reverted."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src.jpg"
        _real_jpg(src, w=600, h=60)
        dst92 = Path(td) / "q92.jpg"
        dst70 = Path(td) / "q70.jpg"
        assert MK._draw(src, dst92, [0.1, 0.1, 0.9, 0.9], quality=92)
        assert MK._draw(src, dst70, [0.1, 0.1, 0.9, 0.9], quality=70)
        assert dst92.stat().st_size > dst70.stat().st_size


# --- _is_blank -----------------------------------------------------------

def test_is_blank_true_for_a_uniform_crop(tmp_path):
    p = tmp_path / "blank.jpg"
    _blank_jpg(p)
    assert MK._is_blank(p) is True


def test_is_blank_false_for_a_crop_with_real_content(tmp_path):
    p = tmp_path / "content.jpg"
    _real_jpg(p)
    assert MK._is_blank(p) is False


def test_is_blank_false_rather_than_raising_on_an_unreadable_file(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not a jpeg")
    assert MK._is_blank(p) is False


# --- _draw sizes/legibility -------------------------------------------

def test_draw_survives_a_scaled_down_copy_and_stays_an_outline_not_a_fill(tmp_path):
    """rect_frac is size-independent by construction: drawing it on a
    full-size crop and on a scaled-down copy of the SAME crop must land
    the rectangle at the same RELATIVE position in both -- the whole
    reason 655's ladder needs `rect_frac` rather than `rect` (672)."""
    from PIL import Image
    full = tmp_path / "full.jpg"
    _real_jpg(full, w=800, h=100)
    small = tmp_path / "small.jpg"
    with Image.open(full) as im:
        im.resize((int(800 * 0.42), int(100 * 0.42))).save(small, "JPEG", quality=70)

    frac = [0.2, 0.1, 0.8, 0.9]
    dst_full = tmp_path / "marked_full.jpg"
    dst_small = tmp_path / "marked_small.jpg"
    assert MK._draw(full, dst_full, frac)
    assert MK._draw(small, dst_small, frac)

    with Image.open(dst_full) as f, Image.open(dst_small) as s:
        # a pixel at the rectangle's own edge picks up the drawn colour in
        # BOTH -- proves the rectangle tracks the fraction, not a fixed
        # pixel offset that would land wrong once the image is smaller.
        def reddish_near(img, x, y, w=2):
            xs = range(max(0, x - w), x + w + 1)
            return any(img.getpixel((xi, y))[0] > 140 and img.getpixel((xi, y))[1] < 110
                      for xi in xs)

        fw, fh = f.size
        sw, sh = s.size
        assert reddish_near(f, int(frac[0] * fw), fh // 2)
        assert reddish_near(s, int(frac[0] * sw), sh // 2)


def test_draw_line_width_never_falls_below_the_floor_on_a_tiny_crop(tmp_path):
    tiny = tmp_path / "tiny.jpg"
    _real_jpg(tiny, w=40, h=16)
    dst = tmp_path / "tiny_marked.jpg"
    assert MK._draw(tiny, dst, [0.1, 0.1, 0.9, 0.9])
    assert dst.is_file()


def test_draw_returns_false_on_an_unreadable_file(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    dst = tmp_path / "out.jpg"
    assert MK._draw(bad, dst, [0.1, 0.1, 0.9, 0.9]) is False
    assert not dst.exists()


# --- _marks_line (commands.py) -----------------------------------------

def test_marks_line_reports_all_four_things_the_brief_asks_for():
    line = _marks_line({"rows": 10, "marked_in_file": 4, "checked": 4,
                        "drawn": 3, "refused": {"math mismatch": 1}})
    assert "10 formula row(s)" in line
    assert "4 marked in the file" in line
    assert "4 checked" in line
    assert "3 drawn" in line
    assert "math mismatch: 1" in line


def test_marks_line_shows_unknown_marked_count_as_a_question_mark_not_none():
    line = _marks_line({"rows": 5, "marked_in_file": None, "checked": 0,
                        "drawn": 0, "refused": {}})
    assert "? marked in the file" in line
    assert "None" not in line
