r"""THE RATCHET. The board's model counts, measured in the suite, pinned.

Audit 2026-11-19, proposal 2: pdfdrill's own suite had no ratchet, so every
regression in the model build had to be found by rebuilding the corpus and
reading a report. These counts now fail the suite instead.

WHAT IS MEASURED. `pagecheck`'s MODEL checks, on a model this test builds
through the real pipeline -- `docmodel.main.run` followed by the three
cleanup steps `cmd_model` runs after it (`clean_heading_residuals`,
`extract_footnote_paragraphs`, `flag_document`), which is exactly what
`pdfdrill model` writes:

  * `overlap_model` -- two of our leaf boxes overlapping by more than half
    the smaller one;
  * `merged` -- one of our units holding lines of several MathPix units;
  * `split`  -- one MathPix unit's lines landing in several of ours;
  * `matched` -- one MathPix unit, one of ours, nothing else in it.

  * `box_text_model` -- the PDF text-layer words inside one of our boxes,
    against that unit's own text, failing over a CER of 0.25.

`box_text_model` reads PINNED WORD BOXES, not the PDF: one `p<N>.bbox.html`
per fixture page, the output of `pdftotext -bbox-layout -cropbox -f N -l N`,
which `pagecheck --words` reads in place of `--pdf` (drillgroup deab8a0).
That keeps three third-party PDFs out of a public repository -- 2312.11532's
alone is 20 MB, over this repo's own commit limit -- and it was VERIFIED
equal to the PDF route rather than assumed: same word count and same
`box_text_model` on all three pages (1157/476/730 words, 2/0/11 failures).

THE FIXTURES ARE WHOLE REAL PAGES, one per document, chosen because each
carries a NON-ZERO count of every kind -- a ratchet pinned at zero on a page
with no findings cannot move and measures nothing. Whole pages, because
`_body_edges` is keyed by page, so a whole-page slice has exactly the
statistics the page has in the full document; a part-page slice does not, and
that has produced a lying fixture twice (see
`test_the_reading_says_where_a_paragraph_starts`).

    document          page   reading                 MathPix reference
    0864               3     Gemma4 2957de8, yolo    the document's own
    1805.01788         8     Gemma4 2957de8, yolo    MathPix lines.json
    2312.11532         6     Gemma4 2957de8, yolo

HOW TO USE IT. A count may IMPROVE, never worsen, and an improvement is
pinned in the same commit that causes it -- so the assertion is EQUALITY and
the message says which direction moved. Lowering a baseline because a change
made it worse is the one thing this file exists to prevent; the number is
there to be argued with in a commit message, not edited quietly.

BASELINE: 73188fe9 (2026-11-20), after e653b8db / e518e375 / 1175259b moved
merged and split across the whole ten-document set.

AND IT CAN FAIL, which was verified rather than assumed. With the reading's
block marker disabled in memory (`_begins_a_sentence` forced to False, so
the rule e518e375 and 1175259b built stops firing), two of the three
documents move and would be reported as WORSE:

    0864 p3        merged 0 -> 2, split 3 -> 2, matched 12 -> 11
    2312.11532 p6  merged 0 -> 3, split 2 -> 1, matched  7 ->  5
    1805.01788 p8  unmoved -- its own counts come from other rules

Note the shape of it: `split` FALLS while `merged` rises and `matched`
falls. A ratchet on `split` alone would have called that an improvement,
which is why all four counts are pinned together and `matched` is pinned in
the opposite direction.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: document -> (page, {count: pinned value})
BASELINE = {
    "0864":       (3, {"overlap_model": 1, "box_text_model": 2, "merged": 0,
                       "split": 3, "matched": 12}),
    "1805.01788": (8, {"overlap_model": 4, "box_text_model": 0, "merged": 1,
                       "split": 5, "matched": 7}),
    "2312.11532": (6, {"overlap_model": 7, "box_text_model": 11, "merged": 0,
                       "split": 2, "matched": 7}),
}

#: THE MODEL AGAINST THE READING'S OWN PARAGRAPH RULE, on the same page and
#: the same MathPix reference. `reading_matched` is how many MathPix units
#: `pagecheck`'s own rule matches when it builds units straight from the
#: reading (a column's run of text lines, cut at every `text_display`
#: paragraph start); `matched` above is how many OUR model matches. The GAP
#: is what may not grow -- see
#: `test_the_model_does_not_fall_further_behind_the_reading` for why it is
#: not required to be zero.
READING_MATCHED = {"0864": 13, "1805.01788": 7, "2312.11532": 7}

#: which direction is better, per count
BETTER_WHEN_LOWER = {"overlap_model": True, "box_text_model": True,
                     "merged": True, "split": True, "matched": False}


def _build(lines_path: Path, bibkey: str, out_dir: Path) -> dict:
    """The model `pdfdrill model` writes, built in process."""
    from docmodel import main as dmain
    from docmodel.core import Document
    from pdfdrill import env_balance as eb
    from pdfdrill import heading_cleanup as hc

    out = dmain.run(str(lines_path), dmain.DEFAULT_CONFIG_PATH, bibkey,
                    str(out_dir / "model.docmodel.json"), [])
    doc = Document.from_dict(out)
    for step in (hc.clean_heading_residuals, hc.extract_footnote_paragraphs,
                 eb.flag_document):
        step(doc)
    return doc.to_dict()


def _counts(key: str, page: int, out_dir: Path) -> dict:
    import _pagecheck_pinned as pc

    lines_path = FIXTURES / f"ratchet-{key}.lines.json"
    mp_path = FIXTURES / f"ratchet-{key}.mathpix.json"
    model = _build(lines_path, key, out_dir)
    units = pc.model_units(model).get(page) or []
    mp_pages = json.loads(mp_path.read_text("utf-8"))["pages"]
    mp_page = next((p for p in mp_pages if p.get("page") == page), None)
    assert mp_page is not None, f"no MathPix page {page} in the fixture"
    mp_units = pc.line_units(mp_page)
    assert mp_units, "the MathPix fixture states no units — fixture is broken"
    our_page = next(p for p in json.loads(lines_path.read_text("utf-8"))["pages"]
                    if p.get("page") == page)
    tl = pc.text_layer(None, page, words=str(FIXTURES / f"words-{key}"))
    assert tl and tl[2], (
        f"no pinned word boxes for {key} p{page} — "
        f"fixtures/words-{key}/p{page}.bbox.html is missing or empty")
    got = {"overlap_model": len(pc.check_overlap(units)),
           "box_text_model": len(pc.check_box_text(
               units, tl, float(our_page.get("page_width") or 0),
               float(our_page.get("page_height") or 0))),
           "merged": 0, "split": 0, "matched": 0}
    for row in pc.check_paragraphs(mp_units, units)["text"]:
        if row["status"] in got:
            got[row["status"]] += 1
    return got


@pytest.mark.parametrize("key", sorted(BASELINE))
def test_the_board_counts_only_improve(key, tmp_path):
    page, pinned = BASELINE[key]
    got = _counts(key, page, tmp_path)
    worse, better = [], []
    for name, want in sorted(pinned.items()):
        have = got[name]
        if have == want:
            continue
        lower_is_better = BETTER_WHEN_LOWER[name]
        if (have > want) == lower_is_better:
            worse.append(f"{name} {want} -> {have}")
        else:
            better.append(f"{name} {want} -> {have}")
    assert not worse, (
        f"{key} p{page}: the board got WORSE: {', '.join(worse)}. "
        "Find the cause and fix it; do not move the baseline to match.")
    assert not better, (
        f"{key} p{page}: the board IMPROVED: {', '.join(better)}. "
        "Pin the new numbers in BASELINE in the same commit, and say in the "
        "commit message what moved them.")


@pytest.mark.parametrize("key", sorted(BASELINE))
def test_the_model_does_not_fall_further_behind_the_reading(key, tmp_path):
    r"""The model may not match FEWER MathPix units than the reading's own
    paragraph rule does -- by more than it already does.

    Proposed as a flat invariant (model matched >= reading matched) and
    measured instead, on the inspect set built at Gemma4 809a542. It is NOT
    an invariant, for two reasons found by measuring, and the ratchet is on
    the GAP so it starts green and still catches the model falling behind.

    FIRST, THE TWO SIDES DO NOT MEASURE THE SAME THING. `model_units` ends
    with `if b is None or page is None: continue` -- an object with NO BOX is
    dropped from the model side entirely -- while `line_units` builds the
    reading's units from the page's line list and never needs a box. So a
    record the reading states with no `region` still forms a reading unit and
    cannot form one of ours. pdfdrill cannot invent the box (D-11), so that
    part of the gap is not ours to close.

    It is most of the gap. Region-less leaf text records, yolo against
    inklines on 809a542: lib:5a5c76391c9c 9 -> 18, lib:d68e0271bd4d
    864 -> 904, 1805.01788 28 -> 69. That is exactly the arm asymmetry the
    coordinator asked about -- lib:5a5c76391c9c and lib:d68e0271bd4d pass on
    yolo and fail on inklines while THE TEXT IS IDENTICAL between arms (448
    and 17,000 text records either way, same block markers, same subtypes).
    Only the geometry differs, and on lib:5a5c76391c9c p9 the section header
    "4.2 Experimental Result" has a region in yolo and `region: None` in
    inklines, so the unit goes straight to `missing`. Two more on the same
    document are a region in the WRONG COLUMN ("2 Related work", p3:
    (470, 1941) against (1083, 1016)) and boxes of 6x16 and 4x9 pixels for
    full caption lines -- one in each arm, so neither detector owns the
    defect.

    Restricting the comparison to pages whose every leaf text record HAS a
    plausible box makes lib:d68e0271bd4d pass on BOTH arms (796 >= 753 and
    681 >= 657) and 2312.11532, 0864 and lib:008d43e5db48 pass too.

    SECOND, IT DOES NOT RESCUE ALL OF THEM, so there is another cause: on
    clean pages BH3 is still 242 against 282 and lib:c9daf79960c3 1250
    against 1283. The reading rule is close to MathPix's OWN segmentation --
    both come from a reading of the same page -- so comparing it to MathPix
    is nearly self-referential, while our model also builds Sections,
    ListItems, Footnotes and Tables, and every line one of those claims
    leaves the paragraph pool. That can only lower `matched` against
    MathPix's text units, and it is not a defect by itself. On
    lib:008d43e5db48 our model BEATS the reading rule, 1385 against 1138, so
    it is not uniformly behind either.

    WHAT THIS PINS, therefore: the gap per page, which may not grow. A flat
    invariant would have been red on five rows the day it was written, and a
    red line is a TODO, not a ratchet.
    """
    page, pinned = BASELINE[key]
    import _pagecheck_pinned as pc

    lines = json.loads(
        (FIXTURES / f"ratchet-{key}.lines.json").read_text("utf-8"))
    mp = json.loads(
        (FIXTURES / f"ratchet-{key}.mathpix.json").read_text("utf-8"))
    our_page = next(p for p in lines["pages"] if p.get("page") == page)
    mp_page = next(p for p in mp["pages"] if p.get("page") == page)
    reading_units = pc.line_units(our_page)
    mp_units = pc.line_units(mp_page)
    reading_matched = sum(
        1 for r in pc.check_paragraphs(mp_units, reading_units)["text"]
        if r["status"] == "matched")
    assert reading_matched == READING_MATCHED[key], (
        f"{key} p{page}: the READING's own matched count moved "
        f"{READING_MATCHED[key]} -> {reading_matched}. The reading is a "
        "pinned fixture, so this means the fixture or the pinned pagecheck "
        "changed, not the model.")
    model_matched = _counts(key, page, tmp_path)["matched"]
    gap = reading_matched - model_matched
    pinned_gap = READING_MATCHED[key] - pinned["matched"]
    assert gap <= pinned_gap, (
        f"{key} p{page}: the model fell further behind the reading's own "
        f"paragraph rule: gap {pinned_gap} -> {gap} "
        f"(reading {reading_matched}, model {model_matched}).")
    assert gap == pinned_gap, (
        f"{key} p{page}: the model CAUGHT UP: gap {pinned_gap} -> {gap}. "
        "Pin the new `matched` in BASELINE in the same commit.")


def test_every_pinned_count_can_actually_move():
    """A ratchet pinned at zero on a page with no findings is decoration.
    Every document must pin at least one NON-zero failure count, or the
    fixture was chosen badly and a regression could not show up in it."""
    for key, (page, pinned) in BASELINE.items():
        failures = {k: v for k, v in pinned.items() if BETTER_WHEN_LOWER[k]}
        assert any(v > 0 for v in failures.values()), (
            f"{key} p{page} pins only zeros for the failure counts "
            f"({failures}) — pick a page that has findings")
        assert pinned["matched"] > 0, (
            f"{key} p{page} matches nothing, so `matched` cannot fall")


def test_the_pinned_pagecheck_is_the_whole_script():
    """The vendored copy is a PIN, not a fork. If it has been edited down to
    the few functions used here, a later re-pin silently changes what the
    ratchet measures."""
    import _pagecheck_pinned as pc
    for fn in ("model_units", "line_units", "check_overlap",
               "check_paragraphs", "summarise_paragraphs", "check_box_text",
               "check_columns", "check_margin", "main"):
        assert hasattr(pc, fn), f"the pinned pagecheck lost {fn}()"
