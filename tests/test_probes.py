"""The three cheap probes run unconditionally and are read from the sidecar.

Measured on a 110-page A4 handbook: pdfinfo 11 ms, `pdfimages -list` 198 ms,
pdftotext 212 ms — 420 ms for all three over the whole document, which is
cheaper than deciding whether to run them.

Numbers in these fixtures are measured, not chosen: 110 pages, and the
form-feed shape is real pdftotext output.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import probes


# ------------------------------------------------------------- page splitting
def test_a_form_feed_terminates_a_page_it_does_not_separate_them():
    """pdftotext ends every page with \\f, including the last — so a naive
    split reports one page too many on every document."""
    assert probes.split_pages("one\ftwo\fthree\f") == ["one", "two", "three"]


def test_a_document_with_no_trailing_form_feed_is_not_truncated():
    assert probes.split_pages("one\ftwo") == ["one", "two"]


def test_a_blank_interior_page_is_still_a_page():
    """A genuinely empty page is real — the duplex blank-side logic depends on
    it — so only the trailing artefact may be dropped."""
    assert probes.split_pages("a\f\fc\f") == ["a", "", "c"]


def test_a_single_page_and_an_empty_document():
    assert probes.split_pages("only\f") == ["only"]
    assert probes.split_pages("") == []
    assert probes.split_pages(None) == []


# ------------------------------------------------------------------- pdfinfo
def test_pdfinfo_values_may_contain_colons():
    text = ("Title:          A: B\n"
            "Producer:       pdfTeX-1.40.25\n"
            "Pages:          110\n"
            "Page size:      595 x 842 pts (A4)\n")
    d = probes.parse_pdfinfo(text)
    assert d["Title"] == "A: B"
    assert d["Producer"] == "pdfTeX-1.40.25"
    assert d["Pages"] == "110"
    assert d["Page size"] == "595 x 842 pts (A4)"


def test_a_key_with_an_empty_value_is_kept():
    """`Producer:` with nothing after it is a fact — the PDF has an empty
    producer, which is not the same as having none."""
    assert probes.parse_pdfinfo("Producer:\n") == {"Producer": ""}


def test_non_key_value_noise_is_ignored():
    assert probes.parse_pdfinfo("garbage line\n\nPages: 3\n") == {"Pages": "3"}


# ------------------------------------------------------- absent vs unattempted
class _SC:
    """Stands for pdfdrill.sidecar.Sidecar — see tests/test_stub_fidelity.py."""

    def __init__(self, ev=None, blob_dir=None):
        self.evidence = dict(ev or {})
        self.blob_dir = blob_dir

    def set_evidence(self, k, v):
        self.evidence[k] = v

    def get_evidence(self, k, default=None):
        return self.evidence.get(k, default)


def test_a_failed_probe_is_recorded_as_None_not_omitted():
    """"we asked and got nothing" and "we never asked" are different, and only
    the second should make a consumer run the tool itself."""
    p = probes.probe_document(Path("/nonexistent/none.pdf"))
    assert set(p) >= {"pdfinfo", "pdfimages_list_raw", "page_text"}
    assert p["pdfinfo"] is None and p["page_text"] is None


def test_is_probed_keys_on_the_record_not_on_the_results():
    """A document with no images is probed and has none."""
    assert probes.is_probed(_SC()) is False
    assert probes.is_probed(_SC({"probe_version": 1})) is True
    assert probes.is_probed(_SC({"page_text": []})) is False


def test_store_then_read_a_page_without_touching_the_pdf(tmp_path):
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": 1, "pdfinfo": {"Pages": "3"},
                      "page_text": ["one", "", "three"], "page_count_text": 3,
                      "pdfimages_list_raw": "page num ...\n"})
    assert probes.page_text(sc, 1) == "one"
    assert probes.page_text(sc, 2) == ""          # a blank page, not a miss
    assert probes.page_text(sc, 3) == "three"
    assert probes.page_text(sc, 4) is None
    assert probes.page_text(sc, 0) is None
    assert sc.get_evidence("page_count_text") == 3


def test_store_omits_a_failed_probe_rather_than_writing_a_null(tmp_path):
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": 1, "pdfinfo": None,
                      "page_text": None, "pdfimages_list_raw": None})
    assert sc.get_evidence("probe_version") == 1
    assert "pdfinfo_fields" not in sc.evidence
    assert probes.page_texts(sc) is None


# ------------------------------------------------------------------ live
@pytest.mark.skipif(not (shutil.which("pdfinfo") and shutil.which("pdftotext")),
                    reason="poppler not installed")
def test_a_real_pdf_is_probed_end_to_end(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    pdf = tmp_path / "d.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)
    p = probes.probe_document(pdf)
    assert p["pdfinfo"]["Pages"] == "3"
    assert p["page_count_text"] == 3           # the split agrees with pdfinfo


# ------------------------------------------------------- consumers read sidecar
def test_accessors_read_the_sidecar_and_do_not_touch_the_pdf(tmp_path):
    """The point of probing at acquisition: a consumer with a sidecar never
    shells out again. The accessors take only the sidecar, so there is no path
    back to the subprocess."""
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": 1,
                      "pdfinfo": {"Pages": "110", "Producer": "pdfTeX"},
                      "page_text": ["a", "b"], "page_count_text": 2,
                      "pdfimages_list_raw": "page num type\n---\n  1 0 image\n"})
    assert probes.pdfinfo_fields(sc) == {"Pages": "110", "Producer": "pdfTeX"}
    assert probes.page_count(sc) == 110
    assert probes.producer(sc) == "pdfTeX"
    assert probes.image_count(sc) == 1


def test_image_count_is_zero_not_negative_for_a_document_with_no_images(tmp_path):
    """`pdfimages -list` prints its two header rows and nothing else. That is a
    measured zero; -1 (the old sentinel) means the tool could not be run."""
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": 1, "pdfimages_list_raw":
                      "page   num  type   width height\n"
                      "--------------------------------\n"})
    assert probes.image_count(sc) == 0
    assert probes.image_count(_SC()) is None       # never probed


def test_accessors_return_None_when_the_probe_failed_rather_than_guessing(tmp_path):
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": 1, "pdfinfo": None,
                      "page_text": None, "pdfimages_list_raw": None})
    assert probes.pdfinfo_fields(sc) is None
    assert probes.page_count(sc) is None
    assert probes.producer(sc) is None


def test_page_count_survives_a_non_numeric_pages_value():
    sc = _SC()
    probes.store(sc, {"probe_version": 1, "pdfinfo": {"Pages": "n/a"}})
    assert probes.page_count(sc) is None


@pytest.mark.skipif(not shutil.which("pdfinfo"), reason="poppler not installed")
def test_ensure_probes_once_and_is_then_a_sidecar_read(tmp_path, monkeypatch):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    pdf = tmp_path / "d.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)
    sc = _SC(blob_dir=tmp_path / 'blob')
    assert probes.ensure(pdf, sc) is True
    calls = []
    monkeypatch.setattr(probes, "_run", lambda *a, **k: calls.append(a) or None)
    assert probes.ensure(pdf, sc) is False         # already probed
    assert calls == []                             # and no subprocess was run


# ------------------------------------------------------------------- wiring
@pytest.mark.skipif(not (shutil.which("pdfinfo") and shutil.which("pdftotext")),
                    reason="poppler not installed")
def test_resolving_a_pdf_argument_probes_it_with_no_command_asked_for(tmp_path):
    """The acceptance criterion: a freshly acquired PDF carries pdfinfo,
    `pdfimages -list` and page-attributed text in its sidecar because it was
    acquired — not because someone ran `size`."""
    from pdfdrill import cli
    from pdfdrill.sidecar import Sidecar

    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    for _ in range(2):
        w.add_blank_page(width=200, height=200)
    pdf = tmp_path / "fresh.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)

    assert cli._pdf([str(pdf)]) == pdf
    sc = Sidecar(pdf)
    assert probes.is_probed(sc)
    assert probes.page_count(sc) == 2
    assert probes.page_text(sc, 1) is not None
    assert probes.image_count(sc) == 0


def test_a_non_pdf_argument_is_not_probed(tmp_path):
    """`markdown`/`latexbook` take .md/.tex. Probing those would record a
    failed pdfinfo and mark them probed, so nothing would ever retry."""
    from pdfdrill import cli
    from pdfdrill.sidecar import Sidecar

    md = tmp_path / "notes.md"
    md.write_text("# hi\n")
    assert cli._pdf([str(md)]) == md
    assert not probes.is_probed(Sidecar(md))


# --------------------------------------------- consumers do not re-run the tool
def _explode(*a, **k):                     # any subprocess here is the bug
    raise AssertionError("consumer re-ran a probe instead of reading the sidecar")


@pytest.mark.skipif(not (shutil.which("pdfinfo") and shutil.which("pdftotext")),
                    reason="poppler not installed")
def test_size_producer_and_image_count_come_from_the_probe(tmp_path, monkeypatch):
    from pdfdrill import commands
    from pdfdrill.sidecar import Sidecar

    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    for _ in range(6):
        w.add_blank_page(width=200, height=200)
    pdf = tmp_path / "probed.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)
    probes.ensure(pdf, Sidecar(pdf))       # as acquisition would have

    monkeypatch.setattr(commands.subprocess, "run", _explode)
    assert commands._pdf_producer(pdf) is not None
    assert commands._pdfimages_count(pdf, Sidecar(pdf)) == 0
    out = commands.cmd_size(pdf)
    assert "6-page PDF" in out and "pypdf" in out


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="poppler not installed")
def test_the_text_layer_probe_reads_stored_page_text(tmp_path, monkeypatch):
    """`_probe_text_layer` sampled the first pages with its own pdftotext runs.
    The stored page text answers the same question — and it is per page, so the
    5-page sample is a slice rather than a second extraction."""
    from pdfdrill import commands

    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": 1,
                      "page_text": [""] + ["body text here"] * 5,
                      "page_count_text": 6})
    monkeypatch.setattr(commands.subprocess, "run", _explode)
    has_text, _n_fonts, first = commands._probe_text_layer(tmp_path / "x.pdf", sc)
    assert first == 0                       # a cover-figure page 1
    assert has_text is True                 # ... in a born-digital document


# --------------------------------------------------- the premise has a page cap
# Measured on the real corpus (6634 PDFs, largest 11232 pages): pdftotext and
# `pdfimages -list` each cost ~2 ms/page, so "420 ms for the whole document" is
# a 110-page fact, not a document-size-independent one. On 1511.08771 the pair
# costs 80 SECONDS and yields 36 MB of text. pdfinfo stays 30 ms at that size.

def test_a_huge_document_still_gets_pdfinfo_but_defers_the_linear_probes(monkeypatch):
    seen = []

    def fake_run(cmd, timeout=120.0):
        seen.append(cmd[0])
        return "Pages: 11232\n" if cmd[0] == "pdfinfo" else "x"

    monkeypatch.setattr(probes, "_run", fake_run)
    p = probes.probe_document(Path("big.pdf"))
    assert seen == ["pdfinfo"]                       # the linear ones never ran
    assert p["pdfinfo"]["Pages"] == "11232"
    assert p["page_text"] is None
    assert p["deferred"] == ["page_text", "pdfimages_list"]


def test_deferred_is_not_the_same_as_failed(monkeypatch, tmp_path):
    """A deferred probe must stay askable. Recording it as a failure would make
    it indistinguishable from "pdftotext is broken here" and nothing would retry."""
    monkeypatch.setattr(probes, "_run", lambda cmd, timeout=120.0:
                        "Pages: 11232\n" if cmd[0] == "pdfinfo" else "x")
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, probes.probe_document(Path("big.pdf")))
    assert sc.get_evidence("probe_deferred") == ["page_text", "pdfimages_list"]
    assert probes.page_count(sc) == 11232
    assert probes.image_count(sc) is None


def test_a_document_under_the_cap_is_probed_in_full(monkeypatch):
    seen = []

    def fake_run(cmd, timeout=120.0):
        seen.append(cmd[0])
        return "Pages: 110\n" if cmd[0] == "pdfinfo" else "a\fb\f"

    monkeypatch.setattr(probes, "_run", fake_run)
    p = probes.probe_document(Path("ok.pdf"))
    assert seen == ["pdfinfo", "pdfimages", "pdftotext"]
    assert p["page_text"] == ["a", "b"] and p["deferred"] == []


def test_the_cap_is_settable_for_a_caller_that_wants_the_whole_thing(monkeypatch):
    monkeypatch.setattr(probes, "_run", lambda cmd, timeout=120.0:
                        "Pages: 900\n" if cmd[0] == "pdfinfo" else "a\f")
    assert probes.probe_document(Path("b.pdf"))["deferred"] != []
    assert probes.probe_document(Path("b.pdf"), page_limit=None)["deferred"] == []


# --------------------------------------------- bulk lives beside, not inside
def test_bulk_probe_output_is_not_stored_in_the_always_read_sidecar(tmp_path):
    """The sidecar is loaded by every command. 36 MB of page text in it would
    cost more than the probe saves — the same argument that keeps
    `pdftotext -bbox-layout` out of the probe set."""
    sc = _SC(blob_dir=tmp_path)
    probes.store(sc, {"probe_version": probes.PROBE_VERSION,
                      "pdfinfo": {"Pages": "3"},
                      "page_text": ["one", "two", "three"], "page_count_text": 3,
                      "pdfimages_list_raw": "h\n-\n r1\n r2\n", "deferred": []})
    blob = "".join(str(v) for v in sc.evidence.values())
    assert "one" not in blob and "two" not in blob
    assert sc.get_evidence("page_count_text") == 3     # the cheap facts stay
    assert sc.get_evidence("image_count") == 2
    assert probes.page_text(sc, 2) == "two"            # ... and the bulk loads
    assert probes.pdfimages_list(sc).startswith("h\n")
