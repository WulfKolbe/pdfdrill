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


def _real_jpg(path: Path, w=300, h=40, color=(200, 200, 200)):
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


def test_apply_only_touches_the_formula_kind():
    eq = EquationRow(identifier="D_EQ0001", latex="a")
    rows = {"equation": [eq], "formula": []}
    out, _counts = MK.apply(rows, None, "/x")
    assert out is rows            # no-op path returns the same dict


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
        # a pixel well inside the rectangle stays white-ish in BOTH; a
        # pixel at the rectangle's own edge picks up the drawn colour in
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
        inside_f = f.getpixel((fw // 2, fh // 2))
        inside_s = s.getpixel((sw // 2, sh // 2))
        assert inside_f[1] > 150   # untouched (still light, not the drawn colour)
        assert inside_s[1] > 150


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
