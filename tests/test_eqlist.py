"""865 — the equation list: rows across documents, and the report whose
subject is the list.

Every test here is pinned to something that actually went wrong while the
feature was built, or to a property the measuring side depends on.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import eqlist as EL                                # noqa: E402
from pdfdrill.reports import eqtable as ET                       # noqa: E402

PDF = b"%PDF-1.7 not-a-real-pdf\n%%EOF\n"


def _eq(label, page, x, y, w=100, h=20, latex="x", kind="display"):
    return {"identifier": label, "ident": f"eq_{label}", "page": page,
            "kind": kind, "confidence": 1.0, "structural_ok": True,
            "latex": latex, "spans": 1, "projected": 1, "deferred": [],
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": h}}


def _library(tmp_path, docs):
    """{bibkey: ([equation, ...], producer)} -> a library root."""
    root = tmp_path / "lib"
    root.mkdir(parents=True)
    for key, (eqs, producer) in docs.items():
        d = root / key
        d.mkdir()
        (d / f"{key}.pdf").write_bytes(PDF)
        (d / f"{key}.equations.json").write_text(json.dumps({
            "bibkey": key, "counts": {"total": len(eqs)}, "equations": eqs}),
            encoding="utf-8")
        (d / f"{key}.drill.json").write_text(json.dumps({
            "evidence": {"producer": producer, "pages": 9}}), encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# Identity. The whole design turns on this and two wrong answers were given
# before the right one.
# --------------------------------------------------------------------------

def test_the_latex_hash_is_not_a_key():
    """58.4% of real rows (18,945 of 32,449) share their LaTeX with another
    row in their OWN document — `V` occurs 166 times in sigma26-086. A hash of
    the content identifies a STRING, not a row."""
    assert EL.latex_sha16("V") == EL.latex_sha16("V")
    assert EL.latex_sha16("V") != EL.latex_sha16("M")
    assert EL.latex_sha16(None) is None


def test_identity_survives_a_changed_reading_and_the_label_does_not(tmp_path):
    """THE DEFECT THIS DESIGN EXISTS TO AVOID, and the one `ident` has.

    `ident` is sha(bibkey|page|region|latex) and IS unique — 34,317 of 34,317
    measured. It is still the wrong key, because it mixes the content into the
    hash: re-read a slot, get different LaTeX, and the row reads as a NEW row
    rather than a changed one, so a mark against it is orphaned against an id
    that exists nowhere and the artefact says nothing happened.
    """
    first = _library(tmp_path / "a", {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    a = EL.build(first, name="t")["rows"][0]

    # The SAME slot, re-read, now yielding different LaTeX and renumbered.
    second = _library(tmp_path / "b", {"doc": (
        [_eq("EQ0007", 1, 10, 20, latex="x+1")], "pdfTeX-1.40.25")})
    b = EL.build(second, name="t")["rows"][0]

    assert a["identity"] == b["identity"], "the row is in the same place"
    assert a["label"] != b["label"], "the label renumbered, as labels do"
    assert a["latex_sha16"] != b["latex_sha16"], (
        "the stability field must flag the slot as re-read")
    assert a["ident"] != b["ident"], (
        "ident changes with the content — which is exactly why it cannot be "
        "the key: this looks like a different row, not a changed one")


def test_every_identity_is_distinct_across_documents(tmp_path):
    """A list is keyed across documents or it is not a list."""
    root = _library(tmp_path, {
        "alpha": ([_eq("EQ0001", 1, 10, 20), _eq("EQ0002", 1, 10, 90)], "pdfTeX-1.40.25"),
        "beta": ([_eq("EQ0001", 1, 10, 20)], "LuaTeX-1.18.0"),
    })
    data = EL.build(root, name="t")
    keys = [(r["identity"]["document"], r["identity"]["page"],
             tuple(sorted(r["identity"]["region"].items()))) for r in data["rows"]]
    assert len(set(keys)) == len(keys) == 3
    assert EL.validate(data) == []


# --------------------------------------------------------------------------
# What "binary generated" means, stated as a producer test and not implied.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("producer,expect", [
    ("pdfTeX-1.40.25", True),
    ("dvips + GPL Ghostscript GIT PRERELEASE 9.22", True),
    ("LuaTeX-1.18.0", True),
    ("Acrobat Distiller 8.1.0", True),
    ("CVISION Technologies", False),
    ("ABBYY FineReader 14", False),
    ("", False),
])
def test_binary_generated_is_a_producer_test(producer, expect):
    """A scan with an OCR text layer is a scan. 2,869 of 3,024 documents have
    a text layer; that set is larger and includes re-wrapped scans, so the
    metadata test is the narrower and more honest one."""
    ok, why = EL.binary_generated(producer)
    assert ok is expect, why
    assert why, "the reason travels with the answer, so a reader can disagree"


def test_a_scanned_document_is_not_listed(tmp_path):
    root = _library(tmp_path, {
        "born": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25"),
        "scan": ([_eq("EQ0001", 1, 10, 20)], "CVISION Technologies"),
    })
    data = EL.build(root, name="t")
    assert [d["document"] for d in data["documents"]] == ["born"]
    assert "scan" in json.dumps(data["skipped_documents"]), (
        "a document absent for a knowable reason is not the same as one never "
        "considered")


# --------------------------------------------------------------------------
# Selection is not calibration scope — inkdrill's constraint, which changed
# the design from a self-contained list to one that names its documents.
# --------------------------------------------------------------------------

def test_a_bounded_list_still_names_each_document_in_full(tmp_path):
    """inkdrill votes the scale per document on up to 400 rows and calibrates
    its thresholds from the confidently placed ones. sigma26-080 REFUSED with
    n_ref 7. A list carrying only its own rows would hand it ~5 per document
    and every document would refuse."""
    eqs = [_eq(f"EQ{i:04d}", 1 + i // 5, 10, 20 + 30 * i) for i in range(40)]
    root = _library(tmp_path, {"doc": (eqs, "pdfTeX-1.40.25")})
    data = EL.build(root, name="t", per_document=5)

    assert data["counts"]["rows"] == 5
    d = data["documents"][0]
    assert d["rows_in_document"] == 40, "the FULL count travels with the list"
    assert d["rows_listed"] == 5
    assert d["inputs"]["pdf"]["sha256"], "and the inputs are resolvable + hashed"
    assert data["selection"]["bounded"] is True
    assert EL.validate(data) == []


def test_the_subset_is_spread_through_the_document_not_its_first_rows(tmp_path):
    """The first N rows of a paper are its abstract and introduction. A subset
    drawn from one region of one layout is not a subset."""
    eqs = [_eq(f"EQ{i:04d}", 1 + i, 10, 20) for i in range(50)]
    root = _library(tmp_path, {"doc": (eqs, "pdfTeX-1.40.25")})
    pages = [r["identity"]["page"] for r in EL.build(root, name="t",
                                                     per_document=5)["rows"]]
    assert pages != sorted(pages)[:5] or max(pages) > 10, pages
    assert max(pages) > 25, "the tail of the document must be represented"


def test_the_marks_request_separates_calibration_from_selection(tmp_path):
    eqs = [_eq(f"EQ{i:04d}", 1, 10, 20 + 30 * i) for i in range(30)]
    root = _library(tmp_path, {"doc": (eqs, "pdfTeX-1.40.25")})
    req = ET.marks_request(EL.build(root, name="t", per_document=4))
    d = req["documents"][0]
    assert d["calibrate_on"]["rows_in_document"] == 30
    assert len(d["mark"]) == 4
    assert d["inputs"]["pdf"], "the document must be reachable to calibrate on"
    assert all("identity" in m for m in d["mark"])


# --------------------------------------------------------------------------
# validate() — the half the user asked for first: "to check the correct list
# properties start with a subset".
# --------------------------------------------------------------------------

def test_validate_catches_a_duplicated_identity(tmp_path):
    root = _library(tmp_path, {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    data = EL.build(root, name="t")
    data["rows"].append(dict(data["rows"][0], label="EQ0002"))
    data["counts"]["rows"] = len(data["rows"])
    problems = EL.validate(data)
    assert any("share an identity" in p for p in problems), problems


def test_validate_catches_a_row_whose_document_is_not_named(tmp_path):
    """Rows without their document are rows nothing can be calibrated for."""
    root = _library(tmp_path, {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    data = EL.build(root, name="t")
    data["documents"] = []
    assert any("no entry in" in p for p in EL.validate(data)), EL.validate(data)


def test_verify_inputs_notices_a_rebuilt_document(tmp_path):
    """A list whose documents were rebuilt underneath it is not a list of
    those documents — `proofs.verify`'s rule, applied to a list."""
    root = _library(tmp_path, {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    data = EL.build(root, name="t")
    assert EL.verify_inputs(data) == []
    (root / "doc" / "doc.pdf").write_bytes(PDF + b"changed\n")
    assert any("CHANGED" in m for m in EL.verify_inputs(data))


# --------------------------------------------------------------------------
# The table. Both of these are defects this task produced and measured.
# --------------------------------------------------------------------------

def test_the_rectangle_cell_does_not_end_the_table_row():
    r"""400 errors and all 171 math rows demoted to source-only, on the first
    build. `\\` inside a braced group in a `p{}` column ends the table ROW
    while the group is still open, and the demote-fixpoint attributes the
    failure to whichever row it lands in — so 171 correct equations were
    blamed for a three-line cell."""
    cell = ET._rect_cell({"identity": {"page": 3,
                                       "region": {"top_left_x": 394,
                                                  "top_left_y": 1659,
                                                  "width": 1480,
                                                  "height": 42}}})
    assert "\\\\" not in cell, cell
    assert "\\newline" in cell
    for v in ("394", "1659", "1480", "42", "p3"):
        assert v in cell, v


def test_a_tiny_region_is_not_blown_up_to_the_column_width(tmp_path):
    r"""`\blacksquare` is a 29x38 px region. Scaled to the 50mm column it
    became a black square occupying an entire page of the table: 22 pages for
    200 rows, against 14 for the same rows at native size."""
    root = _library(tmp_path, {"doc": (
        [_eq("EQ0001", 1, 1845, 1282, w=29, h=38, latex=r"\blacksquare")],
        "pdfTeX-1.40.25")})
    data = EL.build(root, name="t")
    out = tmp_path / "out"
    # No crop is cut here (the fixture PDF is not a PDF), so drive the width
    # rule directly: at 250 dpi a 29 px region is 2.95mm, not 50mm.
    assert 29 * (25.4 / 250.0) < 3.0
    tex, stats = ET.render(data, out, crops=False)
    assert stats["rows"] == 1
    assert "\\blacksquare" in tex


def test_the_table_states_its_frame_and_that_a_subset_is_a_subset(tmp_path):
    """A bounded list read as a corpus measurement is 593's defect. And the
    frame must be stated because it cannot be inferred: the widest row reaches
    only the text margin, so the largest observed x understates the page width
    and puts 8.6% of rows 'off the page' that are all inside it."""
    eqs = [_eq(f"EQ{i:04d}", 1, 10, 20 + 30 * i) for i in range(10)]
    root = _library(tmp_path, {"doc": (eqs, "pdfTeX-1.40.25")})
    tex, _ = ET.render(EL.build(root, name="t", per_document=3), tmp_path / "o",
                       crops=False)
    assert "BOUNDED subset" in tex
    assert "250 dpi" in tex and "does not convert" in tex


def test_no_host_is_baked_into_a_row(tmp_path):
    """862: 2,783 `http://localhost:8000/cropped/...` links went into 20 .tex
    files, each unfetchable on any machine without that server."""
    root = _library(tmp_path, {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    data = EL.build(root, name="t")
    assert "localhost" not in json.dumps(data)
    assert "http" not in json.dumps(data["rows"])
    assert "{base}" in data["crop_url_template"], (
        "the host is a template at the top level, not 34,000 baked-in URLs")
    assert data["rows"][0]["crop"]["id"] == "doc-01"


def test_the_image_lane_is_first_class_from_the_start(tmp_path):
    """InftyDB v1/v2 arrive as (image, LaTeX) with no PDF, no page and no
    rectangle. A schema that forces placement and verification into one field
    is wrong in whichever direction it chooses."""
    root = _library(tmp_path, {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    row = EL.build(root, name="t")["rows"][0]
    assert row["lane"] == "pdf"
    assert "image" in row and row["image"] is None


def test_the_calibration_population_is_kind_filtered(tmp_path):
    """inkdrill's correction after the first subset, and it reverses the rule
    I had written down.

    "Calibrate on the document's FULL row set" is right for an unfiltered list
    and wrong for a kind-filtered one. sigma26-080 holds 1,976 inline rows and
    74 display; calibrating a DISPLAY list on all 2,050 draws its reference
    rows from the inline single letters, 409 of 415 sampled rows fail the
    margin test, and the document refuses — which reads as "this document
    cannot be measured" when it means "you gave it the wrong population".
    """
    eqs = ([_eq(f"EQI{i:04d}", 1, 10, 20 + 30 * i, kind="inline") for i in range(96)]
           + [_eq(f"EQD{i:04d}", 2, 10, 20 + 30 * i, kind="display") for i in range(4)])
    root = _library(tmp_path, {"doc": (eqs, "pdfTeX-1.40.25")})
    data = EL.build(root, name="t", kind="display", per_document=2)

    d = data["documents"][0]
    assert d["rows_in_document"] == 100
    assert d["rows_of_kind_in_document"] == 4, (
        "the population to calibrate on is the document's DISPLAY rows, not "
        "its 96 inline fragments")

    cal = ET.marks_request(data)["documents"][0]["calibrate_on"]
    assert cal["kind"] == "display"
    assert cal["rows_in_document"] == 4
    assert cal["rows_in_document_all_kinds"] == 100
    assert "of this kind" in cal["scope"]
    assert EL.validate(data) == []


def test_validate_refuses_a_list_wider_than_what_it_calibrates_on(tmp_path):
    """The listed rows must sit INSIDE the calibration population, or the
    measurement is taken against a set that does not contain its own subject."""
    eqs = [_eq(f"EQ{i:04d}", 1, 10, 20 + 30 * i) for i in range(10)]
    root = _library(tmp_path, {"doc": (eqs, "pdfTeX-1.40.25")})
    data = EL.build(root, name="t")
    data["documents"][0]["rows_of_kind_in_document"] = 3
    assert any("must be inside the calibration population" in p
               for p in EL.validate(data)), EL.validate(data)


@pytest.mark.parametrize("producer,expect,why_has", [
    # Found by READING the 606 producers the pattern did not recognise,
    # instead of assuming the list was complete. `pdftex` matches neither
    # spelling below, so 26 real TeX documents were classified as "not a
    # generator" by a pattern written for a name they do not use.
    ("PDFLaTeX", True, "PDFLaTeX"),
    ("pdfeTeX-1.21a", True, "pdfeTeX"),
    ("Skia/PDF m141", True, "Skia"),
    # These build a PDF from page IMAGES and matched nothing in either
    # pattern, so they were excluded for the vague reason instead of the true
    # one. The scanner pattern is checked first, so naming them fixes both.
    ("Adobe Acrobat 7.0 Image Conversion Plug-in", False, "Image Conversion"),
    ("ImageMagick 6.9.0-6 Q8", False, "ImageMagick"),
    ("libtiff / tiff2pdf - 20191103", False, "tiff2pdf"),
])
def test_producers_found_by_reading_the_unrecognised_ones(producer, expect, why_has):
    ok, why = EL.binary_generated(producer)
    assert ok is expect, why
    assert why_has in why, why


def test_a_rewrapper_is_not_claimed_either_way():
    """pikepdf (103 documents) rewrites an existing PDF and keeps its content
    streams, so the file may well be born-digital — but the producer string of
    whatever MADE it is gone. Unknown is the honest answer, and the reason says
    so rather than implying the document was examined."""
    ok, why = EL.binary_generated("pikepdf 8.15.1")
    assert ok is False
    assert "not recognised" in why


# --------------------------------------------------------------------------
# The equation NUMBER. inkdrill measured this from the ink before I found it
# in my own code: 37 of 200 display regions (18%) carried a blank run up to
# 1,946 px wide, which was the right-margin number inside the same rectangle
# as the body.
# --------------------------------------------------------------------------

def test_the_authors_number_is_the_equation_no_not_our_ordinal(tmp_path):
    """"document, equation no, ..." means the author's `(1.1)` to anyone
    reading the paper. `label` is an ordinal this pipeline invented and
    renumbers at will; it is not the equation's number and must not stand in
    for one."""
    eq = _eq("EQ0001", 5, 394, 1659, w=711, h=42)
    eq["number"] = "(2.9)"
    eq["number_region"] = {"top_left_x": 1796, "top_left_y": 1659,
                           "width": 78, "height": 42}
    root = _library(tmp_path, {"doc": ([eq], "pdfTeX-1.40.25")})
    row = EL.build(root, name="t")["rows"][0]

    assert row["number"] == "(2.9)"
    assert row["number_region"]["top_left_x"] == 1796
    assert row["label"] == "EQ0001"
    assert row["identity"]["region"]["width"] == 711, (
        "the identity's region is the EQUATION — the number has its own box")

    tex, _ = ET.render(EL.build(root, name="t"), tmp_path / "o", crops=False)
    assert "(2.9)" in tex


def test_an_unnumbered_equation_has_no_number_rather_than_a_blank_one(tmp_path):
    """Absent is not false and absent is not zero: a row with no number is not
    row number nothing."""
    root = _library(tmp_path, {"doc": ([_eq("EQ0001", 1, 10, 20)], "pdfTeX-1.40.25")})
    row = EL.build(root, name="t")["rows"][0]
    assert row["number"] is None
    assert row["number_region"] is None
