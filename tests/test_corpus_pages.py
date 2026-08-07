"""Corpus page sampling — DOCUMENT variety, not page variety.

The library had 1008 rendered pages spread over 35 of 3273 modelled documents:
plenty of pages, almost no documents. A residual-rate measured on that reads as
a property of the corpus when it is really a property of one thesis that
happened to be rendered in full.

So the sampler spends its budget on breadth: a few pages from EVERY document
rather than every page from a few. These tests pin the selection rules, which
are the part that decides whether the corpus is representative.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import corpus_pages as cp


# --------------------------------------------------------------------------
# sample_pages — which pages represent a document
# --------------------------------------------------------------------------

def test_short_documents_are_taken_whole():
    """Nothing to choose from — a 1-page flyer IS its own sample."""
    assert cp.sample_pages(1, 3) == [1]
    assert cp.sample_pages(2, 3) == [1, 2]
    assert cp.sample_pages(3, 3) == [1, 2, 3]


def test_samples_are_spread_across_the_document():
    """Evenly spread, so a sample is not three consecutive front-matter pages."""
    assert cp.sample_pages(12, 3) == [2, 6, 10]
    assert cp.sample_pages(100, 4) == [13, 38, 63, 88]


def test_the_cover_page_is_not_the_sample_of_a_long_document():
    """Page 1 is a title page — it says nothing about how the body extracts.
    Sampling it by default would make every long document look like a cover."""
    for n in (10, 50, 300, 6216):
        assert 1 not in cp.sample_pages(n, 3), n


def test_samples_stay_inside_the_document():
    for n in (1, 2, 5, 9, 17, 250, 6216):
        for k in (1, 3, 5):
            pages = cp.sample_pages(n, k)
            assert pages == sorted(set(pages)), (n, k, pages)
            assert pages, (n, k)
            assert min(pages) >= 1 and max(pages) <= n, (n, k, pages)
            assert len(pages) <= max(k, 0) or len(pages) <= n


def test_sampling_is_deterministic():
    """Re-running the sampler must not shuffle the corpus — a measurement
    compared against last week's is otherwise comparing different pages."""
    assert cp.sample_pages(137, 3) == cp.sample_pages(137, 3) == [23, 69, 114]


def test_no_pages_requested_or_empty_document():
    assert cp.sample_pages(0, 3) == []
    assert cp.sample_pages(10, 0) == []


# --------------------------------------------------------------------------
# resuming — never re-render what is on disk
# --------------------------------------------------------------------------

def test_existing_pages_reads_the_inspector_naming(tmp_path):
    d = tmp_path / "inspect" / "pages"
    d.mkdir(parents=True)
    for name in ("p1.png", "p7.png", "p23.png",   # the pages
                 "page-0007.png",                  # the hardlink twin of p7
                 "notes.txt", "preview.png", "p.png", "px.png",
                 "p12.png.tmp", "p9.jpg"):         # must not read as pages
        (d / name).write_bytes(b"x")
    assert cp.existing_pages(d) == {1, 7, 23}


def test_existing_pages_on_a_document_never_rendered(tmp_path):
    assert cp.existing_pages(tmp_path / "nope") == set()


def test_missing_pages_is_what_still_has_to_be_rendered():
    assert cp.missing_pages([2, 6, 10], {6}) == [2, 10]
    assert cp.missing_pages([2, 6, 10], {2, 6, 10}) == []
    assert cp.missing_pages([2, 6, 10], set()) == [2, 6, 10]


def test_a_fully_rendered_document_is_left_alone():
    """The 35 documents already rendered in full must not be touched: their
    pages are a superset of any sample, so there is nothing to add."""
    wanted = cp.sample_pages(178, 3)
    assert cp.missing_pages(wanted, set(range(1, 179))) == []


# --------------------------------------------------------------------------
# page count discovery
# --------------------------------------------------------------------------

def test_page_count_read_from_the_model_head():
    head = b'{"meta": {"bibkey": "x", "num_pages": 42, "pages": [{"page": 1}]}'
    assert cp.page_count_from_head(head) == 42


def test_page_count_absent_from_the_head_is_none_not_a_guess():
    """A wrong page count silently samples pages that do not exist. Unknown
    must stay unknown so the caller falls back to asking the PDF."""
    assert cp.page_count_from_head(b'{"meta": {"bibkey": "x"}') is None
    assert cp.page_count_from_head(b"") is None
    assert cp.page_count_from_head(b'{"meta": {"num_pages": 0}}') is None


def test_page_count_ignores_a_num_pages_inside_later_content():
    """Only the meta header counts — a `num_pages` string appearing in some
    object's props further down the file is not the document's page count."""
    head = b'{"objects": [{"props": {"text": "see \\"num_pages\\": 999 in the log"}}]'
    assert cp.page_count_from_head(head) is None

    # and with a real meta present, the search must STOP at the meta block:
    # reading on into the objects is how a 3-page paper gets sampled at p999.
    head = (b'{"meta": {"bibkey": "x"}, "objects": '
            b'[{"id": "o1", "props": {"num_pages": 999}}]')
    assert cp.page_count_from_head(head) is None


# --------------------------------------------------------------------------
# planning — the whole decision, before anything is rendered
# --------------------------------------------------------------------------

def _doc(tmp_path, name, num_pages, rendered=()):
    d = tmp_path / name
    d.mkdir()
    (d / f"{name}.pdf").write_bytes(b"%PDF-1.4\n")
    (d / "model.docmodel.json").write_text(
        json.dumps({"meta": {"bibkey": name, "num_pages": num_pages}}))
    if rendered:
        pg = d / "inspect" / "pages"
        pg.mkdir(parents=True)
        for n in rendered:
            (pg / f"p{n}.png").write_bytes(b"x")
    return d


def test_plan_covers_every_modelled_document(tmp_path):
    _doc(tmp_path, "a", 20)
    _doc(tmp_path, "b", 8)
    plan = cp.plan_library(tmp_path, per_doc=3)
    assert {p.bibkey for p in plan} == {"a", "b"}
    assert [p.pages for p in plan if p.bibkey == "b"] == [[1, 4, 7]]


def test_plan_skips_documents_that_already_have_their_sample(tmp_path):
    _doc(tmp_path, "done", 12, rendered=cp.sample_pages(12, 3))
    _doc(tmp_path, "todo", 12)
    plan = cp.plan_library(tmp_path, per_doc=3)
    assert [p.bibkey for p in plan] == ["todo"]


def test_plan_asks_for_only_the_pages_a_partial_document_lacks(tmp_path):
    _doc(tmp_path, "part", 12, rendered=[6])
    plan = cp.plan_library(tmp_path, per_doc=3)
    assert plan[0].pages == [2, 10]


def test_a_directory_without_a_model_is_reported_not_silently_dropped(tmp_path):
    d = tmp_path / "nomodel"
    d.mkdir()
    (d / "nomodel.pdf").write_bytes(b"%PDF-1.4\n")
    plan, skipped = cp.plan_library(tmp_path, per_doc=3, with_skipped=True)
    assert plan == []
    assert skipped == [("nomodel", "no model")]


def test_a_directory_without_a_pdf_is_reported(tmp_path):
    d = tmp_path / "nopdf"
    d.mkdir()
    (d / "model.docmodel.json").write_text(json.dumps({"meta": {"num_pages": 3}}))
    _plan, skipped = cp.plan_library(tmp_path, per_doc=3, with_skipped=True)
    assert skipped == [("nopdf", "no pdf")]


def test_plan_is_capped_by_limit_for_a_trial_run(tmp_path):
    for i in range(5):
        _doc(tmp_path, f"d{i}", 10)
    assert len(cp.plan_library(tmp_path, per_doc=3, limit=2)) == 2


# --------------------------------------------------------------------------
# what the corpus IS, once built
# --------------------------------------------------------------------------

def test_corpus_stats_count_documents_not_hardlinks(tmp_path):
    """The reported size was 2016 pages; on disk it was 1008 images, each
    hardlinked under both naming schemes. Counting the links doubles the
    corpus on paper without adding one page to it."""
    d = _doc(tmp_path, "a", 20, rendered=[2, 6, 10])
    pg = d / "inspect" / "pages"
    for n in (2, 6, 10):                     # the page-NNNN.png twins
        (pg / f"page-{n:04d}.png").write_bytes(b"x")
    _doc(tmp_path, "b", 5)                   # modelled, nothing rendered

    st = cp.corpus_stats(tmp_path)
    assert st["pages"] == 3                  # not 6
    assert st["documents_with_pages"] == 1
    assert st["documents"] == 2


def test_page_count_falls_back_to_the_pdf_when_the_model_head_is_silent(tmp_path):
    """676 of 3273 documents have no `num_pages` in their model header. Handing
    the fallback the DIRECTORY instead of the PDF made every one of them
    'unknown page count' — a fifth of the library dropped from the corpus by a
    wrong argument, with the run still reporting success and a plan that simply
    did not mention them."""
    pytest.importorskip("pypdf")
    if shutil.which("pdfinfo") is None:
        pytest.skip("poppler pdfinfo not installed")
    from pypdf import PdfWriter

    d = tmp_path / "silent"
    d.mkdir()
    (d / "model.docmodel.json").write_text(json.dumps({"meta": {"bibkey": "silent"}}))
    w = PdfWriter()
    for _ in range(9):
        w.add_blank_page(width=300, height=300)
    with open(d / "silent.pdf", "wb") as fh:
        w.write(fh)

    plan, skipped = cp.plan_library(tmp_path, per_doc=3, with_skipped=True)
    assert skipped == [], skipped
    assert [p.page_count for p in plan] == [9]
    assert plan[0].pages == cp.sample_pages(9, 3)


def test_a_document_that_rendered_nothing_is_an_error_not_an_ok(tmp_path,
                                                                monkeypatch):
    """One trial document reported 'ok' having produced zero pages, because the
    run counted documents attempted rather than pages written. A corpus that
    counts empty renders as coverage is worse than a smaller honest one."""
    import pdfdrill.pdf_reading as pr
    monkeypatch.setattr(pr, "rasterize", lambda *a, **k: [])
    plan = cp.DocPlan(bibkey="x", pdf=tmp_path / "x.pdf",
                      pages_dir=tmp_path / "pages", pages=[2], page_count=9,
                      sample=[2])
    rec = cp.render(plan, dpi=400)
    assert rec["rendered"] == []
    assert rec["error"]
