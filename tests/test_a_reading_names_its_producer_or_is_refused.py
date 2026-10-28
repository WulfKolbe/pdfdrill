"""ENGINEERING 2d rule 5: a reading is read because it is identified, not because it is silent.

`_TYPED_GEOMETRY_SOURCES` used to begin with `""`, so a lines.json that
declared no producer passed the geometry gate for declaring nothing. Its own
docstring called that an accident. Measured over the library on 2026-10-28, the
accident covered **1,452 of 1,811 readings** — the figure in the code said 168,
and another docstring in the same file said 1,579.

The owner's decision of 2026-10-28 (option 4a, relayed through
pdfdrill-pdf2mmd2-migration): pdfdrill identifies those readings FROM THEIR
CONTENT at read time and writes nothing into the library. The alternative was to
stamp a `source` onto 1,452 files, i.e. to edit the owner's corpus so a test
would pass.

What the content says, all of it measured before any of it was coded:

* MathPix names a converted PDF with a UUID and builds `image_id` as
  `<pdf_id>-<page>`. 1,450 of the 1,452 undeclared readings carry that shape,
  and **no** reading that declares a source carries it.
* our own writers build `image_id` from the document's stem, so a stem-shaped id
  on an undeclared file means one of our readers wrote it before they declared
  anything. One file in the library.
* an integer `page_width` is a pixel frame, a float is PDF points. The split is
  total: 1,451 of 1,451 parseable undeclared readings are integers, and every
  point-frame reader in the library writes a float. There is deliberately NO
  size threshold — 11 of those readings have a page under 1000 px wide, 9 of
  them long scanned books, so "big enough to be pixels" would refuse real
  MathPix readings.

So the refusals are the readings whose content says nothing: no typed lines, or
a point frame, or nothing parseable at all.
"""
import json

import pytest

from pdfdrill.commands import (_TYPED_GEOMETRY_SOURCES, _detect_lines_source,
                               _is_mathpix_lines, _is_typed_geometry_lines,
                               _lines_json_source, _lines_source)

UUID = "8a29fc03-28d7-4c95-8397-e96f4ec2224d"


def _page(image_id: str, page: int, width=2125, height=2750, kinds=("math",)):
    return {
        "image_id": image_id,
        "page": page,
        "lines": [{"id": f"{image_id}_{i}", "line": i, "type": k,
                   "text": "x^2", "region": {"top_left_x": 10, "top_left_y": 20,
                                             "width": 300, "height": 18}}
                  for i, k in enumerate(kinds)],
        "page_height": height,
        "page_width": width,
    }


def _write(tmp_path, stem, data):
    p = tmp_path / f"{stem}.lines.json"
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return p


# --- what is recognised ----------------------------------------------------

def test_a_mathpix_reading_is_recognised_by_its_uuid(tmp_path):
    p = _write(tmp_path, "doc", {"pages": [_page(f"{UUID}-1", 1)]})
    assert _lines_json_source(p) == ""            # declares nothing
    assert _detect_lines_source(p) == "mathpix"
    assert _is_typed_geometry_lines(p), "the richest input pdfdrill has"
    assert _is_mathpix_lines(p), "a paid reading must stay protected"


def test_our_own_early_output_is_recognised_but_is_not_a_purchase(tmp_path):
    """The defect this fixes, not a new feature.

    `_is_mathpix_lines` read "declares no source" as evidence of a purchase, so
    pdfdrill called a file it had generated itself a bought MathPix reading —
    `texbook-appendix-g-generating-boxes` in the library, measured. A reading
    wrongly believed to be paid is a reading nothing will regenerate.
    """
    p = _write(tmp_path, "doc", {"pages": [_page("doc-1", 1)]})
    assert _detect_lines_source(p) == "mathpix-shaped"
    assert _is_typed_geometry_lines(p), "same geometry contract"
    assert not _is_mathpix_lines(p), "nobody bought this"


def test_mathpix_shaped_needs_no_entry_of_its_own(tmp_path):
    """Both gates test `src == s or src.startswith(s + '-')`, so the prefix
    carries it. Pinned because the alternative — adding a fourth name to the
    tuple — is how that tuple grew the `""` it just lost."""
    assert "mathpix-shaped" not in _TYPED_GEOMETRY_SOURCES
    p = _write(tmp_path, "doc", {"pages": [_page("doc-1", 1)]})
    assert _is_typed_geometry_lines(p)


def test_a_declared_source_still_wins_over_the_content(tmp_path):
    """Detection is the fallback, never an override: a reading that says what it
    is is believed, even when its content looks like something else."""
    data = {"source": "pdfminer-chars", "pages": [_page(f"{UUID}-1", 1)]}
    p = _write(tmp_path, "doc", data)
    assert _lines_source(p) == "pdfminer-chars"
    assert not _is_typed_geometry_lines(p), "points, whatever the ids look like"
    assert not _is_mathpix_lines(p)


def test_the_readers_own_stamp_is_untouched_by_all_this(tmp_path):
    p = _write(tmp_path, "doc", {"source": "pdf2mmd2",
                                 "pages": [_page("doc-1", 1)]})
    assert _lines_source(p) == "pdf2mmd2"
    assert _is_typed_geometry_lines(p)
    assert not _is_mathpix_lines(p)


def test_a_reading_that_names_mathpix_is_treated_as_bought(tmp_path):
    """The one answer this change turns around on purpose.

    The old code read ANY declaration as proof that a reading was NOT a
    purchase — "only MathPix leaves `source` out" — and `tests/test_pagelines`
    pinned it, `source: "mathpix"` included. Measured 2026-10-28: 0 of the
    library's 1,811 readings declare `mathpix` (1,452 declare nothing, 174
    `pdfminer-chars`, 171 `pdfminer-docmodel`, 8 `tesseract`, 3 `visionocr`, one
    each `yolo-geometry`, `pdftotext`, `pdfminer`). So the old rule protected
    nothing that exists, and was one stamp away from switching the four money
    sites off: write `source: "mathpix"` onto a bought reading and it became
    overwritable. A reading that says it was bought is now protected — the cost
    of being wrong is one `.mathpix.bak.json`, the cost of the other direction
    is the reading.
    """
    p = _write(tmp_path, "doc", {"source": "mathpix",
                                 "pages": [_page("doc-1", 1)]})
    assert _lines_source(p) == "mathpix"
    assert _is_mathpix_lines(p)
    assert _is_typed_geometry_lines(p)


# --- what is refused: the loophole, turned around --------------------------

def test_the_empty_source_is_gone_from_the_gate():
    assert "" not in _TYPED_GEOMETRY_SOURCES, (
        "a reading would again be admitted for declaring nothing")


def test_a_point_frame_reading_that_declares_nothing_is_refused(tmp_path):
    """The case built to fail. A float page size is PDF points, so its regions
    are in the wrong frame for every consumer of this gate, and nothing in the
    file says who wrote it."""
    p = _write(tmp_path, "doc", {"pages": [_page("whoever-1", 1, width=612.0,
                                                 height=792.0)]})
    assert _detect_lines_source(p) == ""
    assert not _is_typed_geometry_lines(p)
    assert not _is_mathpix_lines(p)


def test_an_identified_reading_with_no_typed_lines_is_named_but_not_admitted(tmp_path):
    """The two questions, kept apart — and the reason the id is tested FIRST.

    Asking for the line types before the id refused 75 of the library's MathPix
    readings, measured: `_has_mathpix_line_types` looks at the first three pages
    and a book opens with a cover, a title page and a colophon, all plain
    `text`. All 75 carry MathPix's UUID and a pixel frame. So an id identifies
    the PRODUCER on its own, while the line types decide what the reading can
    DO — and the geometry gate still says no here."""
    p = _write(tmp_path, "doc", {"pages": [_page("doc-1", 1, kinds=("text",))]})
    assert _detect_lines_source(p) == "mathpix-shaped"   # who wrote it
    assert not _is_typed_geometry_lines(p)               # what it can do
    assert not _is_mathpix_lines(p)


def test_a_reading_with_neither_an_id_nor_typed_lines_is_refused(tmp_path):
    """With no id to go on, the shape of the reading is the only evidence left,
    and both halves are then required."""
    p = _write(tmp_path, "doc", {"pages": [_page("whoever-1", 1,
                                                 kinds=("text",))]})
    assert _detect_lines_source(p) == ""
    assert not _is_typed_geometry_lines(p)


def test_an_empty_file_is_refused_and_raises_nothing(tmp_path):
    """There is one in the library: `2308.06374/mmd-out/2308.06374.lines.json`,
    0 bytes. It was refused before this change too, by the line-type half."""
    p = tmp_path / "doc.lines.json"
    p.write_text("", encoding="utf-8")
    assert _detect_lines_source(p) == ""
    assert not _is_typed_geometry_lines(p)
    assert not _is_mathpix_lines(p)


def test_a_missing_file_is_refused(tmp_path):
    p = tmp_path / "absent.lines.json"
    assert _lines_source(p) == ""
    assert not _is_typed_geometry_lines(p)
    assert not _is_mathpix_lines(p)


# --- the cheapness contract ------------------------------------------------

def test_only_the_two_ends_of_the_file_are_read(tmp_path):
    """`_lines_json_source` claimed to read 8 KB and read the whole file.

    The library is 4.9 GB of readings, up to 12 MB each, and this probe runs on
    every call that asks what a reading is. A decoy `source` buried in the
    middle proves the head is really the only part consulted — and the same
    decoy proves it the other way for a writer who puts `source` last, which is
    why '' means "declares nothing" and not "unknown".
    """
    filler = [_page("doc-%d" % i, i) for i in range(1, 400)]
    data = {"pages": filler}
    p = _write(tmp_path, "doc", data)
    raw = p.read_text(encoding="utf-8")
    assert len(raw) > 3 * 8192, "fixture too small to prove anything"
    middle = len(raw) // 2
    p.write_text(raw[:middle] + '"source": "nonsense-decoy", ' + raw[middle:],
                 encoding="utf-8")
    assert _lines_json_source(p) == "", "the middle of the file was read"


def test_the_page_size_is_found_in_the_tail_of_a_long_reading(tmp_path):
    """`page_width` sits AFTER its page's lines, so on a long document the first
    one is megabytes in. Measured: 1,451 of the 1,452 undeclared library
    readings carry one in their last 8 KB, the only miss being the 0-byte file.
    """
    pages = [_page(f"{UUID}-{i}", i) for i in range(1, 400)]
    p = _write(tmp_path, "doc", {"pages": pages})
    assert p.stat().st_size > 3 * 8192
    assert _detect_lines_source(p) == "mathpix"
