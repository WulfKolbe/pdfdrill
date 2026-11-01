"""T-0088 — a region an eqlist writes as an identity must be ON the page it names.

Found by gemma4-ba on 2026-10-28, cutting crops for the Gemma4 corpus run:
283,785 display formulas were cut and 164 were not, because the region named a
rectangle that is not on the page. 21 documents.
~/Gemma4/work/corpus-run/bad-regions-20261028/bad_regions.tsv is the list.

MEASURED CAUSE (this session, 2026-11-01), because the fix depends on it:

* The coordinates are already wrong IN THE READING, before any list is built.
  Raab page 8 is 362.835 x 272.126 pt. `Raab.equations.json` EQ0002 sits at
  (487, 221) px, which is on the page; EQ0003 -- the very next row, the same
  `\\int` glyph, the same font -- sits at (7043, -6459). The glyph record
  underneath it gives `rect_pt` [2028.372, 2121.442, ...]: y = 2121 pt on a
  272 pt page.
* pdfminer ITSELF produces that. `extract_pages` reports the page's own bbox
  as (0, 0, 362.83, 272.13) and then hands back glyphs with x1 up to 2336.63
  and y1 up to 2147.10. The additive glyph-identity patch is not involved --
  it carries `cid`, `glyphname` and `render_mode`, not geometry.
* poppler disagrees, on every document sampled. `pdftotext -bbox` on the same
  Raab page 8 puts every glyph at y <= 270.3 and x <= 339.5, inside the page;
  likewise 2307.13528v2 p1, Science of Yoga p78, Solar Hybrid p164, Week_14
  p12, Florence Lin p218. So the PDFs are not carrying off-page content: our
  reading is misplacing it.
* It is NOT the page-size fallback that `page_size_for` was written for: on
  all 164 rows the page size the list recorded equals the PDF's own.
* It is NOT a rotation. `pdfinfo` reports rot 0, and MediaBox == CropBox on
  every page sampled. gemma4-ba's "fits swapped" label (20 rows) is arithmetic
  coincidence, not evidence: those rows overflow ONE axis by 30-215 pt on
  pages whose height exceeds their width by more, so "it would fit if you
  swapped W and H" is true of almost any modest overflow on a portrait page.
  Week_14 is genuinely landscape (725.67 x 272.13 pt) and is recorded as
  landscape. T-0088's deliverable 3 is conditional -- "read in the page's real
  orientation IF the cause is a rotation" -- and the condition is not met, so
  swapping those 20 would move 20 correct-as-recorded rows to a second wrong
  place.

Hence what this file pins: the list cannot repair the reading, and it must not
pass the damage on as an identity. It refuses the row and says why.

AND THE EXISTING CHECK HAS NO LOWER BOUND, which is how the first row in
gemma4-ba's list survived it. `validate()` tested only `top_left_x + width >
page` / `top_left_y + height > page`. 1-s2.0-S2405896315004644-main EQ0041 is
at top_left_x -1008, width 861 -- so x1 is -147, which is not greater than the
page width, and y is entirely in range. A region wholly off the LEFT of the
page passed a check written to catch regions off the RIGHT.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import eqlist as EL                                # noqa: E402

PDF = b"%PDF-1.7 not-a-real-pdf\n%%EOF\n"

#: Raab's real page, in points. The regions below are in `EL.PX_PER_PT`.
W_PT, H_PT = 362.835, 272.126
W_PX, H_PX = W_PT * EL.PX_PER_PT, H_PT * EL.PX_PER_PT


def _eq(label, page, x, y, w=100, h=20, latex="x", kind="display"):
    return {"identifier": label, "ident": f"eq_{label}", "page": page,
            "kind": kind, "confidence": 1.0, "structural_ok": True,
            "latex": latex, "spans": 1, "projected": 1, "deferred": [],
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": h}}


def _library(tmp_path, eqs, *, pages=True):
    """A one-document library whose reading carries a per-page size map."""
    root = tmp_path / "lib"
    (root / "doc").mkdir(parents=True)
    d = root / "doc"
    (d / "doc.pdf").write_bytes(PDF)
    body = {"bibkey": "doc", "counts": {"total": len(eqs)}, "equations": eqs}
    if pages:
        body["pages"] = {str(p): {"width_pt": W_PT, "height_pt": H_PT}
                         for p in range(1, 10)}
    (d / "doc.equations.json").write_text(json.dumps(body), encoding="utf-8")
    (d / "doc.drill.json").write_text(json.dumps(
        {"evidence": {"producer": "pdfTeX-1.40.10", "pages": 9}}),
        encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# The predicate. It has to have a LOWER bound, which is the half that was
# missing.
# --------------------------------------------------------------------------

def test_a_negative_x_origin_is_a_fault_even_when_x1_is_on_the_page():
    """1-s2.0-S2405896315004644-main EQ0041, verbatim from gemma4-ba's list:
    top_left_x -1008, width 861 on a 2067 px page. x1 = -147, so every
    upper-bound test passes and the region is still nowhere near the page."""
    why = EL.region_fault({"top_left_x": -1008, "top_left_y": 2047,
                           "width": 861, "height": 77}, 595.276, 793.701)
    assert why, "a region 1008 px left of the page must be a fault"
    assert "left" in why.lower() or "x" in why.lower(), why


def test_a_negative_y_origin_is_a_fault():
    """Raab EQ0003: top_left_y -6459."""
    why = EL.region_fault({"top_left_x": 7043, "top_left_y": -6459,
                           "width": 21, "height": 38}, W_PT, H_PT)
    assert why, "a region above the page must be a fault"


def test_a_region_on_the_page_is_not_a_fault():
    """Raab EQ0002, the good row on the same page as EQ0003."""
    assert EL.region_fault({"top_left_x": 487, "top_left_y": 221,
                            "width": 21, "height": 38}, W_PT, H_PT) is None


def test_a_region_is_not_judged_without_a_page_size():
    """A reading built before the per-page map existed must not be convicted
    on a page size nobody recorded. `page_size_for` returns (0, 0) there."""
    assert EL.region_fault({"top_left_x": -500, "top_left_y": 0,
                            "width": 10, "height": 10}, 0, 0) is None


def test_the_fault_names_the_edge_it_crossed():
    """A reason a reader can act on, not a boolean. L3: listed, never silent."""
    right = EL.region_fault({"top_left_x": W_PX + 10, "top_left_y": 10,
                             "width": 50, "height": 10}, W_PT, H_PT)
    below = EL.region_fault({"top_left_x": 10, "top_left_y": H_PX + 10,
                             "width": 50, "height": 10}, W_PT, H_PT)
    assert right and below and right != below, (right, below)


# --------------------------------------------------------------------------
# The builder. A faulty region is not written as an identity.
# --------------------------------------------------------------------------

def test_the_builder_does_not_write_a_bad_region_as_an_identity(tmp_path):
    good = _eq("EQ0002", 8, 487, 221, w=21, h=38)
    bad = _eq("EQ0003", 8, 7043, -6459, w=21, h=38)
    data = EL.build(_library(tmp_path, [good, bad]), name="t")
    keys = [(r["identity"]["page"], r["identity"]["region"]) for r in data["rows"]]
    assert keys == [(8, good["region"])], (
        "the off-page row must not reach `rows`: %r" % (keys,))


def test_every_refused_row_is_listed_with_its_cause(tmp_path):
    """164 -> 0 written as identities, and 164 listed. A row that vanishes
    without a reason is the failure class this project keeps paying for."""
    bad = _eq("EQ0003", 8, 7043, -6459, w=21, h=38)
    data = EL.build(_library(tmp_path, [_eq("EQ0002", 8, 487, 221), bad]),
                    name="t")
    refused = data.get("refused_regions")
    assert refused, "the artefact must carry the refused rows"
    assert len(refused) == 1, refused
    r = refused[0]
    assert r["document"] == "doc" and r["label"] == "EQ0003", r
    assert r["page"] == 8 and r["region"] == bad["region"], r
    assert r.get("reason"), "a refusal without a reason is a silent drop"
    assert data["counts"].get("refused_region") == 1, data["counts"]


def test_the_counts_do_not_include_a_refused_row(tmp_path):
    """`counts.rows` is read as the row population. A refused row counted in
    it makes the list claim rows it does not contain."""
    data = EL.build(_library(tmp_path, [_eq("EQ0002", 8, 487, 221),
                                        _eq("EQ0003", 8, 7043, -6459)]),
                    name="t")
    assert data["counts"]["rows"] == len(data["rows"]) == 1, data["counts"]


def test_a_valid_row_is_byte_identical_to_what_it_was(tmp_path):
    """T-0088's gate: rows with valid regions unchanged. The refusal must be
    a filter, not a rewrite."""
    good = _eq("EQ0002", 8, 487, 221, w=21, h=38)
    alone = EL.build(_library(tmp_path / "a", [good]), name="t")["rows"]
    beside = EL.build(_library(tmp_path / "b",
                               [good, _eq("EQ0003", 8, 7043, -6459)]),
                      name="t")["rows"]
    assert json.dumps(alone, sort_keys=True) == json.dumps(beside, sort_keys=True)


def test_validate_finds_no_region_outside_the_page_after_the_gate(tmp_path):
    """The artefact asserts the property, so the artefact tests it."""
    data = EL.build(_library(tmp_path, [_eq("EQ0002", 8, 487, 221),
                                        _eq("EQ0003", 8, 7043, -6459),
                                        _eq("EQ0041", 3, -1008, 2047, w=861, h=77)]),
                    name="t")
    problems = [p for p in EL.validate(data) if "past the page" in p]
    assert not problems, problems


def test_the_refusal_is_not_silent_in_the_summary(tmp_path):
    """A per-row field in a 280,000-row list is read by whoever already
    suspects something, which is never the person reading the summary."""
    data = EL.build(_library(tmp_path, [_eq("EQ0002", 8, 487, 221),
                                        _eq("EQ0003", 8, 7043, -6459)]),
                    name="t")
    assert data.get("refused_regions_by_reason"), (
        "the artefact must carry the refusals grouped by cause")
    assert sum(data["refused_regions_by_reason"].values()) == 1


def test_the_command_says_it_refused_something(tmp_path):
    """THE ARTEFACT CARRYING IT IS NOT ENOUGH. The first acceptance run of
    this gate printed `eqlist: 845 row(s) across 2 document(s)` for a library
    whose two documents had just had 385 rows refused, and said nothing else:
    the refusals were in the file and absent from the summary, which is the
    one thing a reader actually reads."""
    from pdfdrill import commands as C
    lib = _library(tmp_path, [_eq("EQ0002", 8, 487, 221),
                              _eq("EQ0003", 8, 7043, -6459)])
    text = C.cmd_eqlist(library=lib, out=tmp_path / "out", name="t")
    assert "REFUSED" in text, text
    assert "origin right of the page; origin above the page" in text, text


def test_a_refusal_carries_how_far_outside_the_page_it_reached(tmp_path):
    """The refused rows are TWO populations and the cause alone cannot tell
    them apart. Measured over the library: of 221 rows that merely extend past
    the right edge, 92 do so by under 10 pt -- pdfminer's rectangle is the font
    line box by height and the ADVANCE width, so a glyph at the right margin
    legitimately reaches past it -- while 87 exceed 50 pt, up to 5,225 pt. Both
    are refused; the amount is recorded so that line can be moved from data."""
    big = _eq("EQ0003", 8, 7043, -6459, w=21, h=38)
    small = _eq("EQ0099", 8, int(W_PX) - 10, 20, w=30, h=10)
    data = EL.build(_library(tmp_path, [big, small]), name="t")
    by_label = {r["label"]: r for r in data["refused_regions"]}
    assert set(by_label) == {"EQ0003", "EQ0099"}, by_label
    assert by_label["EQ0099"]["overflow_pt"] < 10, by_label["EQ0099"]
    assert by_label["EQ0003"]["overflow_pt"] > 100, by_label["EQ0003"]


def test_overflow_is_zero_for_a_region_on_the_page():
    assert EL.region_overflow_pt({"top_left_x": 487, "top_left_y": 221,
                                  "width": 21, "height": 38},
                                 W_PT, H_PT) == 0.0


def test_a_valid_row_keeps_its_number_when_a_refused_row_precedes_it(tmp_path):
    """THE DISCRIMINATING CASE, and the one the first implementation failed.

    T-0088's gate is that rows with valid regions are byte-identical before
    and after. Counting `no` over WRITTEN rows satisfies that only when every
    refusal happens to come last. On Raab the refusals are interleaved with
    good rows, so a contiguous count shifts `no` on 838 surviving rows and
    every one of them differs from the list built before the gate existed.
    `no` is therefore the ordinal over the CHOSEN rows and a refusal leaves a
    gap."""
    bad = _eq("EQ0001", 8, 7043, -6459, w=21, h=38)
    good = _eq("EQ0002", 8, 487, 221, w=21, h=38)
    rows = EL.build(_library(tmp_path, [bad, good]), name="t")["rows"]
    assert len(rows) == 1
    assert rows[0]["no"] == 2, (
        "the surviving row was second in the reading and must stay no=2, "
        "not be renumbered to 1: got %r" % (rows[0]["no"],))


def test_the_document_entry_counts_the_rows_actually_written(tmp_path):
    """`rows_listed` is what the measuring side marks against. It must be the
    written count even though `no` is not."""
    data = EL.build(_library(tmp_path, [_eq("EQ0001", 8, 7043, -6459),
                                        _eq("EQ0002", 8, 487, 221)]),
                    name="t")
    assert data["documents"][0]["rows_listed"] == 1, data["documents"][0]
    assert data["documents"][0]["rows_in_document"] == 2
