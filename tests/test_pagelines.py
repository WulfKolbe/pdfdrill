"""896 — a reading delivered as one file per page.

`~/pdf2mmd2` writes its reading twice: as `<stem>.lines.json`, and as
`<stem>.lines/page-NNNN.json`, one file per page. The per-page file is exactly
one `pages[]` element, so `pdfdrill.pagelines` folds the folder back into an
ordinary lines.json at the one place the CLI already resolves a document, and
nothing downstream changes.

THE FIXTURES ARE pdf2mmd2's OWN OUTPUT, never hand-written here. The format
belongs to the producer: a page file invented in this file would test our
agreement with ourselves, and the splitter that writes the MathPix twins
(`pdf2mmd2-mathpix-pages`) is where the second reader's spelling is defined.
So these tests read `~/pdf2mmd2/out/*/<name>.lines/` and skip when it is
absent — the same gate `test_docmodel_six.py` uses for its corpus PDFs.

The two tests that need no page CONTENT (numeric ordering, the empty folder)
do run everywhere: an empty file named `page-0010.json` carries no format.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pdfdrill import pagelines

PDF2MMD2_OUT = Path.home() / "pdf2mmd2" / "out"


def _a_real_page_folder() -> "tuple[str, Path] | None":
    """(document name, `<name>.lines/`) of a pdf2mmd2 reading on this machine,
    preferring one that also has the MathPix twins beside it."""
    if not PDF2MMD2_OUT.is_dir():
        return None
    found = []
    for d in sorted(PDF2MMD2_OUT.rglob("*.lines")):
        if not d.is_dir():
            continue
        name = d.name[: -len(".lines")]
        if pagelines.page_files(d):
            found.append((len(pagelines.twin_files(d)), name, d))
    if not found:
        return None
    found.sort(key=lambda t: -t[0])           # twins first
    return found[0][1], found[0][2]


_REAL = _a_real_page_folder()
needs_real = pytest.mark.skipif(
    _REAL is None,
    reason=f"no pdf2mmd2 per-page reading under {PDF2MMD2_OUT}")


@pytest.fixture
def doc(tmp_path):
    """A document folder holding pdf2mmd2's real page files, copied verbatim.

    No PDF is created: `assemble` derives its paths from the name and never
    opens the document. The fixture therefore exercises exactly the folder
    pdf2mmd2 produces.
    """
    assert _REAL is not None
    name, src = _REAL
    folder = tmp_path / name
    folder.mkdir()
    shutil.copytree(src, folder / f"{name}.lines")
    return folder / f"{name}.pdf"             # the path, not a file


# --- what the folder is ----------------------------------------------------

def test_numeric_order_not_lexicographic(tmp_path):
    """`sorted(glob())` puts page-10 before page-9 the moment the producer
    stops zero-padding to a fixed width. The padding is a property of today's
    writer, not of the format, so the order comes from the number."""
    d = tmp_path / "x.lines"
    d.mkdir()
    for n in ("page-9.json", "page-10.json", "page-0002.json"):
        (d / n).touch()
    assert [n for n, _ in pagelines.page_files(d)] == [2, 9, 10]


def test_a_second_readers_twin_is_never_a_page_of_this_document(tmp_path):
    """`page-0003.mathpix.json` is MathPix's reading of page 3, written beside
    ours for comparison. One lines.json holding both readers' lines would be a
    document no measurement could attribute, so the twins are counted and
    excluded. A glob cannot make this distinction; the anchored number can."""
    d = tmp_path / "x.lines"
    d.mkdir()
    (d / "page-0001.json").touch()
    (d / "page-0001.mathpix.json").touch()
    (d / "page-0002.mathpix.json").touch()
    assert [n for n, _ in pagelines.page_files(d)] == [1]
    assert [n for n, _ in pagelines.twin_files(d)] == [1, 2]


def test_no_page_folder_is_a_no_op(tmp_path):
    assert pagelines.assemble(tmp_path / "nothing.pdf") is None
    (tmp_path / "nothing.lines").mkdir()
    assert pagelines.assemble(tmp_path / "nothing.pdf") is None


# --- the assembled document ------------------------------------------------

@needs_real
def test_every_page_survives_verbatim(doc):
    """The assembled `pages[i]` IS the i-th page file, unchanged. This is the
    whole claim of the format: there is nothing to translate."""
    rep = pagelines.assemble(doc)
    assert rep is not None and rep["wrote"], rep
    built = json.loads(pagelines.lines_json(doc).read_text(encoding="utf-8"))
    files = pagelines.page_files(pagelines.lines_dir(doc))
    assert len(built["pages"]) == len(files)
    for (num, path), page in zip(files, built["pages"]):
        assert page == json.loads(path.read_text(encoding="utf-8"))
        assert page["page"] == num


@needs_real
def test_it_stays_a_mathpix_shaped_reading(doc):
    """`commands._is_mathpix_lines` answers the planner's `lines:mathpix`
    prerequisite, which `inspect` depends on. Stamping provenance into the file
    would break that chain and make `inspect --ensure` name a paid step, so the
    assembled file carries exactly what the page files carry — no more."""
    from pdfdrill.commands import _is_mathpix_lines, _lines_json_source
    pagelines.assemble(doc)
    lp = pagelines.lines_json(doc)
    assert _lines_json_source(lp) == ""
    assert _is_mathpix_lines(lp) is True


@needs_real
def test_a_reading_we_did_not_write_is_left_untouched(doc):
    """pdf2mmd2 makes this refusal in the other direction, and for the same
    reason: in a library folder the `<stem>.lines.json` may be a paid MathPix
    conversion. A page folder dropped in beside it must not cost it."""
    lp = pagelines.lines_json(doc)
    lp.write_text('{"pages": [], "not": "ours"}', encoding="utf-8")
    before = lp.read_bytes()
    rep = pagelines.assemble(doc)
    assert rep is not None and rep["wrote"] is False
    assert "did not write" in rep["why"]
    assert lp.read_bytes() == before


@needs_real
def test_assembling_twice_does_not_rewrite(doc):
    first = pagelines.assemble(doc)
    assert first["wrote"] is True
    second = pagelines.assemble(doc)
    assert second["wrote"] is False
    assert "current" in second["why"]


@needs_real
def test_a_rewritten_page_is_picked_up(doc):
    """pdf2mmd2 re-runs and rewrites one page; the assembled reading must
    follow. The test only touches the file's mtime — its content is still
    pdf2mmd2's."""
    pagelines.assemble(doc)
    num, path = pagelines.page_files(pagelines.lines_dir(doc))[0]
    path.touch()
    again = pagelines.assemble(doc)
    assert again["wrote"] is True


# --- what it refuses to do -------------------------------------------------

@needs_real
def test_a_filename_that_disagrees_with_its_page_field_is_refused(doc):
    """Two independent statements of the same fact, and the format gives us
    both. When they disagree neither is used: this repo has already paid once
    for treating a label as a key — a document diffed by `EQnnnn` reported 25
    of 37 rows changed when, keyed on position, 30 of 36 were unchanged."""
    d = pagelines.lines_dir(doc)
    num, path = pagelines.page_files(d)[0]
    shutil.copyfile(path, d / f"page-{num + 900:04d}.json")   # same `page`
    with pytest.raises(pagelines.PageLinesError) as e:
        pagelines.assemble(doc)
    assert str(num) in str(e.value)
    assert not pagelines.lines_json(doc).exists()      # nothing written


@needs_real
def test_a_gap_is_reported_not_filled(doc):
    d = pagelines.lines_dir(doc)
    files = pagelines.page_files(d)
    if len(files) < 3:
        pytest.skip("needs a reading of at least three pages")
    missing = files[1][0]
    files[1][1].unlink()
    rep = pagelines.assemble(doc)
    assert rep["gaps"] == [missing]
    assert rep["pages"] == len(files) - 1
    built = json.loads(pagelines.lines_json(doc).read_text(encoding="utf-8"))
    assert [p["page"] for p in built["pages"]] == [
        n for n, _ in pagelines.page_files(d)]
    assert missing not in [p["page"] for p in built["pages"]]


# --- the statement for the producer ---------------------------------------

@needs_real
def test_a_field_pdfdrill_reads_and_no_line_carries_is_named(doc):
    """The report is for pdf2mmd2's CLI, so it must name the field AND what
    reads it — a producer cannot act on "something is missing".

    The list is `docmodel.type_contract.CLAIMED_FIELDS`, not a list written
    here: the contract already names every MathPix field a module consumes and
    is held to the corpus by its own test. `parent_id` must NOT appear — it is
    in IGNORED_FIELDS, verified redundant over 500 documents (1,122,695 of
    1,122,695 parents list the child back), and asking a producer for a value
    nothing reads is noise.
    """
    from docmodel.type_contract import CLAIMED_FIELDS, IGNORED_FIELDS
    rep = pagelines.assemble(doc)
    miss = rep["missing_fields"]
    assert set(miss) <= set(CLAIMED_FIELDS)
    assert set(miss).isdisjoint(IGNORED_FIELDS)
    for field, why in miss.items():
        assert why == CLAIMED_FIELDS[field]
        assert why                            # a bare name is not a statement
    text = pagelines.report_text(rep)
    for field in miss:
        assert field in text
    # The fields every reading must carry — present, so never reported.
    for always in ("id", "type", "text", "region"):
        assert always not in miss, text


@needs_real
def test_the_report_names_the_twins_without_reading_them(doc):
    rep = pagelines.assemble(doc)
    d = pagelines.lines_dir(doc)
    assert rep["twins"] == len(pagelines.twin_files(d))
    if rep["twins"]:
        assert "second reader" in pagelines.report_text(rep)


# --- the CLI's two ends ----------------------------------------------------

def test_a_folder_holding_a_reading_but_no_pdf_says_which(tmp_path, monkeypatch):
    """`~/pdf2mmd2/out/<name>/` is a reading with no document in it. Without
    this the directory itself travelled on AS the PDF, and every later step
    reported the consequence — pdfinfo cannot open it, no reading is found —
    instead of the one fact that explains it."""
    from pdfdrill import cli
    folder = tmp_path / "1306.1660"
    (folder / "1306.1660.lines").mkdir(parents=True)
    (folder / "1306.1660.lines" / "page-0001.json").touch()
    monkeypatch.setattr("pdfdrill.config.library_root", lambda: tmp_path / "lib")
    with pytest.raises(FileNotFoundError) as e:
        cli._pdf([str(folder)])
    said = str(e.value)
    assert "no PDF" in said
    assert "1 page file(s) in 1306.1660.lines/" in said
    assert "1306.1660.pdf" in said            # names what to put there


def test_a_plan_is_computed_against_the_document_not_the_token(tmp_path):
    """896 — `--ensure` planned against the raw argument. drillui adds
    `--ensure` to every command and names documents by folder or bare name, so
    this was every drillui invocation."""
    from pdfdrill import cli
    folder = tmp_path / "paper"
    folder.mkdir()
    pdf = folder / "paper.pdf"
    pdf.touch()
    assert cli.plan_target(str(folder)) == pdf
    assert cli.plan_target(str(folder) + "/") == pdf
    # a full path is already the document
    assert cli.plan_target(str(pdf)) == pdf
    # an unresolvable token plans as it used to, rather than raising
    assert cli.plan_target("nothing-here-at-all") == Path("nothing-here-at-all")
    # a URL / bare arXiv id is NEVER acquired to compute a plan
    assert cli.plan_target("https://arxiv.org/abs/2508.19773") == \
        Path("https://arxiv.org/abs/2508.19773")


def test_the_library_name_resolves_for_planning(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    (lib / "1306.1660").mkdir(parents=True)
    pdf = lib / "1306.1660" / "1306.1660.pdf"
    pdf.touch()
    monkeypatch.setattr("pdfdrill.config.library_root", lambda: lib)
    from pdfdrill import cli
    assert cli.plan_target("1306.1660") == pdf


# --- 897: a reading may say who produced it --------------------------------

def _lines(source: "str | None", page_source: "str | None" = None,
           types=("page_info", "math")) -> dict:
    """A minimal reading, for the two DETECTORS only — no page geometry is
    asserted against it. The shape (which types count, where `source` may sit)
    is the contract under test, not pdf2mmd2's output, so it belongs here."""
    pg = {"page": 1, "page_width": 2125, "page_height": 2750,
          "lines": [{"id": "a", "type": t, "text": ""} for t in types]}
    if page_source is not None:
        pg["source"] = page_source
    doc = {"pages": [pg]}
    if source is not None:
        doc["source"] = source
    return doc


def _write(tmp_path, doc) -> Path:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")            # mtime must precede the reading
    lp = tmp_path / "x.lines.json"
    lp.write_text(json.dumps(doc), encoding="utf-8")
    return pdf


def test_a_declared_reader_still_carries_typed_geometry(tmp_path):
    """The prerequisite `inspect` depends on asks whether a typed,
    geometry-bearing reading EXISTS — not whether it was bought. While the two
    questions shared one detector, declaring a producer made `--ensure` name a
    paid step that could not have helped."""
    from pdfdrill.commands import _is_typed_geometry_lines, _is_mathpix_lines
    for src in ("pdf2mmd2", "pdf2mmd2-tsv", "pdfminer-docmodel", "mathpix"):
        pdf = _write(tmp_path, _lines(src))
        assert _is_typed_geometry_lines(tmp_path / "x.lines.json") is True, src
        # and the money question still answers NO for everything but MathPix's
        # own undeclared export
        assert _is_mathpix_lines(tmp_path / "x.lines.json") is False, src
    pdf = _write(tmp_path, _lines(None))      # MathPix declares nothing
    assert _is_mathpix_lines(tmp_path / "x.lines.json") is True
    assert _is_typed_geometry_lines(tmp_path / "x.lines.json") is True


def test_a_text_only_reader_is_not_typed_geometry(tmp_path):
    """`pdfminer-chars` is the case that has to be argued: 37 of its 153
    readings in this library DO carry `math` lines in their first three pages,
    so the line-type test alone would admit them. They are keyless and
    text-only by construction and their regions are PDF POINTS, so admitting
    them would hand a consumer coordinates in the wrong frame."""
    from pdfdrill.commands import _is_typed_geometry_lines
    for src in ("pdfminer-chars", "tesseract", "pdfplumber-chars", "visionocr"):
        _write(tmp_path, _lines(src, types=("math",)))
        assert _is_typed_geometry_lines(tmp_path / "x.lines.json") is False, src


def test_a_declared_reading_satisfies_the_prerequisite(tmp_path):
    from pdfdrill import planner
    from pdfdrill.sidecar import Sidecar
    pdf = _write(tmp_path, _lines("pdf2mmd2"))
    assert planner.detect("lines:typed-geometry", Sidecar(pdf), pdf, tmp_path / "model.docmodel.json") is True


def test_the_prerequisite_is_unsatisfied_without_a_reading(tmp_path):
    from pdfdrill import planner
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "y.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert planner.detect("lines:typed-geometry", Sidecar(pdf), pdf, tmp_path / "model.docmodel.json") is False


# --- 897: where a reading is allowed to declare itself ---------------------

def test_a_source_on_the_pages_counts_as_declared():
    """168 of this library's 1,747 readings declare `pdfminer-docmodel` on
    every PAGE and have `pages` as their only top-level key. Each built a model
    saying `meta.source = "mathpix"` — our own glyph reader's output recorded
    as the paid reader's."""
    from docmodel.main import declared_source
    assert declared_source(_lines(None, page_source="pdfminer-docmodel")) == \
        "pdfminer-docmodel"
    assert declared_source(_lines("mathpix", page_source="x")) == "mathpix"
    assert declared_source(_lines(None)) == ""


def test_pages_that_disagree_name_no_producer():
    """The per-page key is the only place a MERGED reading can say its pages
    came from two readers. So disagreement is meaningful, and picking one of
    them would be a guess recorded as provenance."""
    from docmodel.main import declared_source
    doc = {"pages": [{"source": "mathpix", "lines": []},
                     {"source": "pdf2mmd2", "lines": []}]}
    assert declared_source(doc) == ""


@needs_real
def test_a_source_the_pages_agree_on_is_lifted_to_the_top(doc):
    """pdf2mmd2's reading is per page by construction, so a `source` it adds
    arrives per page and nothing appears at the top. Lifting it makes
    `declared_source` and the 8 KB head-read in `_lines_json_source` right by
    construction rather than by key ordering."""
    from pdfdrill.commands import _lines_json_source, _is_typed_geometry_lines
    d = pagelines.lines_dir(doc)
    for _, path in pagelines.page_files(d):
        pg = json.loads(path.read_text(encoding="utf-8"))
        pg["source"] = "pdf2mmd2"             # the change being requested
        path.write_text(json.dumps(pg), encoding="utf-8")
    rep = pagelines.assemble(doc)
    assert rep["source"] == "pdf2mmd2"
    lp = pagelines.lines_json(doc)
    built = json.loads(lp.read_text(encoding="utf-8"))
    assert built["source"] == "pdf2mmd2"
    assert _lines_json_source(lp) == "pdf2mmd2"       # the head-read sees it
    assert _is_typed_geometry_lines(lp) is True       # inspect still chains
    assert "pdf2mmd2" in pagelines.report_text(rep)


@needs_real
def test_nothing_is_invented_while_the_producer_declares_nothing(doc):
    rep = pagelines.assemble(doc)
    assert rep["source"] == ""
    built = json.loads(pagelines.lines_json(doc).read_text(encoding="utf-8"))
    assert "source" not in built


# --- 897: declaring a producer must not change the coordinate frame --------

def test_a_declared_page_pixel_reader_keeps_its_frame():
    """`image_ref` had two cases — "mathpix" and everything-else-is-points — so
    the moment a reading declared a producer its crops were requested in the
    wrong unit. pdf2mmd2 writes MathPix's frame: on 1306.1660 page 3 its
    page_width/page_height are 2125x2750, byte-identical to MathPix's own twin
    (8.5in and 11in at 250 dpi). A region at y=1400 PIXELS asked for as y=1400
    POINTS is off the bottom of the page."""
    from docmodel.mathpix import image_ref, is_local_crop
    region = {"top_left_x": 222, "top_left_y": 1400, "width": 718, "height": 26}
    mp = image_ref("img", region, "mathpix")
    assert mp.startswith("https://cdn.mathpix.com/")      # MathPix hosts it
    for src in ("pdf2mmd2", "pdf2mmd2-tsv"):
        u = image_ref("img", region, src)
        assert u.startswith("/cropped/"), u               # no CDN image exists
        assert "units=" not in u, u    # the server then uses the page dims
        assert is_local_crop(u)
    pt = image_ref("img", region, "pdfminer-docmodel")
    assert "units=pt" in pt                               # points, unchanged
    assert is_local_crop(pt)


def test_the_region_numbers_are_never_rewritten():
    """Whichever frame it is, the four numbers reach the crop server verbatim.
    A unit is declared, never converted here."""
    from docmodel.mathpix import image_ref
    region = {"top_left_x": 222, "top_left_y": 1400, "width": 718, "height": 26}
    for src in ("mathpix", "pdf2mmd2", "pdfminer-docmodel"):
        u = image_ref("img", region, src)
        for k, v in region.items():
            assert f"{k}={v}" in u, (src, k, u)
