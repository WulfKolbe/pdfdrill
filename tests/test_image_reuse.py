"""Image PLACEMENTS are not distinct XObjects, and resolution is per placement.

Every fixture number here is a MEASURED one, not a chosen one — the audit's
"right level, wrong magnitude" failure came from fixtures whose dimensions were
invented, so a 14:1 ratio stood in for a real 250:1 and the filter under test
excluded the class it existed to compare against.

Measured, and used verbatim below:
  Infineon handbook   228 placements, x-ppi 96-551, 109 of 228 exceed 400 dpi
                      object 9: one logo, 109 placements, 551x242
                      obj 9 is 200 ppi on page 1 and 551 on pages 2+
  2310.08579 mosaic   492 placements, x-ppi 251-2340, 465 of 492 exceed 400
  Gewasserkundebuch    40 placements, x-ppi 145-1200,   3 of  40 exceed 400
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.image_reuse import (effective_ppi, format_summary, object_key,
                                  summarize)


def _placements(obj, n, ppi, w=551, h=242, start_page=1):
    return [{"page": start_page + i, "object_id": obj, "x_ppi": ppi,
             "width": w, "height": h} for i in range(n)]


# ------------------------------------------------------------------ identity
def test_the_object_key_is_page_independent():
    a = {"page": 1, "object_id": "9 0"}
    b = {"page": 77, "object_id": "9 0"}
    assert object_key(a) == object_key(b) == "9 0"


def test_the_key_is_built_from_obj_and_gen_when_not_preformatted():
    assert object_key({"obj": 9, "gen": 0}) == "9 0"
    assert object_key({"obj": 12}) == "12 0"
    assert object_key({"object_id": 9}) == "9 0"


def test_a_placement_with_no_object_id_is_not_silently_merged():
    """Unidentified placements must not all collapse into one 'object'."""
    assert object_key({"page": 3}) is None
    s = summarize([{"page": 1}, {"page": 2}], render_dpi=400)
    assert s["distinct"] == 0 and s["unidentified"] == 2


# ------------------------------------------------------- the two numbers
def test_one_logo_on_109_pages_is_one_object_and_109_placements():
    """The measured handbook case: `images` reported 213 where there are far
    fewer distinct ones."""
    recs = _placements("9 0", 109, 551)
    s = summarize(recs, render_dpi=400)
    assert s["placements"] == 109
    assert s["distinct"] == 1
    assert s["reused_objects"] == 1
    assert s["most_reused"][0] == {"object": "9 0", "placements": 109,
                                   "dims": "551x242"}


def test_resolution_is_per_placement_not_per_object():
    """obj 9 is 200 ppi on page 1 and 551 on pages 2+ — same image, different
    CTM. Collapsing to one number per object loses the deciding fact."""
    recs = [{"page": 1, "object_id": "9 0", "x_ppi": 200, "width": 551, "height": 242}]
    recs += _placements("9 0", 108, 551, start_page=2)
    s = summarize(recs, render_dpi=400)
    assert s["distinct"] == 1
    assert s["ppi_min"] == 200 and s["ppi_max"] == 551
    assert s["above_render_dpi"] == 108        # page 1 does not, the rest do


# ------------------------------------------- the number that decides the read
def test_the_handbook_splits_almost_evenly_so_no_blanket_policy_works():
    recs = _placements("9 0", 109, 551) + _placements("11 0", 119, 96)
    s = summarize(recs, render_dpi=400)
    assert s["placements"] == 228
    assert s["above_render_dpi"] == 109        # 48% — measured
    assert 0 < s["above_render_dpi"] < s["placements"]


def test_the_mosaic_is_almost_entirely_above_the_render():
    recs = _placements("2 0", 465, 2340, w=4000, h=3000) + \
           _placements("3 0", 27, 251, w=500, h=400)
    s = summarize(recs, render_dpi=400)
    assert s["placements"] == 492 and s["above_render_dpi"] == 465
    assert s["ppi_max"] == 2340


def test_the_gewasserkundebuch_is_almost_entirely_below():
    recs = _placements("4 0", 37, 145) + _placements("5 0", 3, 1200)
    s = summarize(recs, render_dpi=400)
    assert s["placements"] == 40 and s["above_render_dpi"] == 3


def test_a_missing_ppi_is_not_counted_either_way():
    """`pdfimages` does not always print x-ppi; absent must not read as 0."""
    recs = [{"page": 1, "object_id": "9 0"}, {"page": 2, "object_id": "9 0",
                                              "x_ppi": 800}]
    s = summarize(recs, render_dpi=400)
    assert s["ppi_known"] == 1 and s["above_render_dpi"] == 1
    assert effective_ppi({"x_ppi": 0}) is None
    assert effective_ppi({"x_ppi": "n/a"}) is None


# ------------------------------------------------------------------- output
def test_the_summary_states_both_numbers_and_the_decision():
    recs = _placements("9 0", 109, 551) + _placements("11 0", 119, 96)
    text = "\n".join(format_summary(summarize(recs, render_dpi=400)))
    assert "228 image placement(s)" in text
    assert "2 distinct XObject(s)" in text
    assert "obj 9 0 x109" in text
    assert "109 of 228 exceed the 400 dpi render" in text


def test_no_images_says_so_without_dividing_by_zero():
    s = summarize([], render_dpi=400)
    assert s["placements"] == 0 and s["distinct"] == 0
    assert format_summary(s)
