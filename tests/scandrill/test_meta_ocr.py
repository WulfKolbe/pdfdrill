"""Metadata control + the OCR text-layer graft.

The load-bearing assertion: grafting a searchable text layer must leave the image
stream BYTE-IDENTICAL. If that ever regresses, we have quietly traded the whole
point of the project (a lossless projection of ingest.json) for searchability.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pikepdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from pdfdrill.scandrill.assemble import assemble
from pdfdrill.scandrill.manifest import Manifest, Page
from pdfdrill.scandrill.meta import DocMeta, _pdf_date, stamp
from pdfdrill.scandrill import ocr as ocr_mod

needs_tess = pytest.mark.skipif(not ocr_mod.have_tesseract(),
                                reason="tesseract not installed")


_TTF = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _text_page(msg: str, size=(1200, 400)) -> Image.Image:
    """A page with text large enough to OCR reliably.

    PIL's default bitmap font is ~10 px — far harder than a real 300 dpi scan,
    and tesseract genuinely misreads digits at that size (8→6). Use a scalable
    face at a realistic size so the test exercises the plumbing, not tesseract's
    limits on unrealistic input.
    """
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(_TTF, 64)
    except OSError:                      # no scalable face: fall back
        font = ImageFont.load_default()
    d.text((60, 150), msg, fill="black", font=font)
    return im


@pytest.fixture
def job(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _text_page("SCANDRILL probe 12345").save(raw / "p1.png")
    _text_page("second page 67890").save(raw / "p2.jpg", quality=92)
    m = Manifest(job="metajob", created="2026-07-15T14:30:12+02:00", lang="de-DE")
    m.add(Page(seq=0, src="p1.png"))
    m.add(Page(seq=0, src="p2.jpg"))
    return tmp_path, raw, m


# ---- metadata -------------------------------------------------------------------

def test_docmeta_from_manifest_projects_the_job(job):
    _t, _raw, m = job
    meta = DocMeta.from_manifest(m)
    assert meta.title == "metajob"
    assert meta.lang == "de-DE"
    assert meta.created == "2026-07-15T14:30:12+02:00"


def test_pdf_date_conversion():
    assert _pdf_date("2026-07-15T14:30:12+02:00") == "D:20260715143012+02'00'"
    assert _pdf_date(None) is None
    assert _pdf_date("not a date") is None


def test_docinfo_and_xmp_agree(job):
    """Both metadata stores must carry the same values, or readers disagree."""
    tmp_path, raw, m = job
    meta = DocMeta(title="Rechnung 2026", author="Wulf Kolbe", subject="Scan",
                   keywords="invoice;2026", creator="SCANDRILL test",
                   created="2026-07-15T14:30:12+02:00", lang="de-DE")
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, meta=meta)

    with pikepdf.open(out) as pdf:
        di = pdf.docinfo
        assert str(di["/Title"]) == "Rechnung 2026"
        assert str(di["/Author"]) == "Wulf Kolbe"
        assert str(di["/Subject"]) == "Scan"
        assert str(di["/Keywords"]) == "invoice;2026"
        assert str(di["/CreationDate"]) == "D:20260715143012+02'00'"
        assert "SCANDRILL" in str(di["/Producer"])

        xmp = pdf.open_metadata()
        assert xmp["dc:title"] == "Rechnung 2026"
        assert xmp["dc:creator"] == ["Wulf Kolbe"]      # dc:creator is a list
        assert xmp["dc:description"] == "Scan"
        assert "SCANDRILL" in xmp["pdf:Producer"]
        assert str(pdf.Root.Lang) == "de-DE"


def test_pikepdf_does_not_hijack_the_producer(job):
    """set_pikepdf_as_editor=False — otherwise pikepdf stamps itself."""
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw,
                   meta=DocMeta(producer="SCANDRILL 9.9"))
    with pikepdf.open(out) as pdf:
        assert str(pdf.docinfo["/Producer"]) == "SCANDRILL 9.9"
        assert "pikepdf" not in pdf.open_metadata()["pdf:Producer"].lower()


def test_page_labels_configurable(job):
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw,
                   meta=DocMeta(label_style="r", label_start=3, label_prefix="A-"))
    with pikepdf.open(out) as pdf:
        d = pdf.Root.PageLabels.Nums[1]
        assert str(d.S) == "/r" and int(d.St) == 3 and str(d.P) == "A-"


def test_lang_default_still_stamped(job):
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, title="plain")
    with pikepdf.open(out) as pdf:
        assert str(pdf.Root.Lang) == "de-DE"
        assert str(pdf.docinfo["/Title"]) == "plain"


# ---- OCR ------------------------------------------------------------------------

def test_lang_mapping():
    assert ocr_mod.tesseract_lang("de-DE") == "deu"
    assert ocr_mod.tesseract_lang("en-GB") == "eng"
    assert ocr_mod.tesseract_lang("deu") == "deu"      # already 3-letter
    assert ocr_mod.tesseract_lang("xx-YY") == "eng"    # unknown -> eng
    assert ocr_mod.tesseract_lang("") == "eng"


@needs_tess
def test_ocr_graft_keeps_image_streams_byte_identical(job):
    """THE test. Adding searchability must not re-encode a single pixel."""
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, title="pre-ocr")

    def raw_streams(p):
        with pikepdf.open(p) as pdf:
            got = []
            for page in pdf.pages:
                obj = page.images[next(iter(page.images))]
                got.append((obj.read_raw_bytes(), str(obj.get("/Filter"))))
            return got

    before = raw_streams(out)
    n = ocr_mod.graft_text_layer(out, [raw / "p1.png", raw / "p2.jpg"], lang="eng")
    after = raw_streams(out)

    assert n == 2
    assert before == after, "grafting the text layer rewrote an image stream"
    # and the JPEG page is still verbatim DCT
    assert after[1][1] == "/DCTDecode"
    assert after[1][0] == (raw / "p2.jpg").read_bytes()


@needs_tess
def test_ocr_makes_text_extractable(job):
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, ocr=True, ocr_lang="eng")
    import fitz
    d = fitz.open(out)
    text = " ".join(pg.get_text() for pg in d).replace("\n", " ")
    assert "12345" in text
    assert "67890" in text


@needs_tess
def test_ocr_preserves_metadata(job):
    """The graft must not cost us the metadata we just stamped."""
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, ocr=True, ocr_lang="eng",
                   meta=DocMeta(title="Searchable", author="WK", lang="de-DE"))
    with pikepdf.open(out) as pdf:
        assert str(pdf.docinfo["/Title"]) == "Searchable"
        assert str(pdf.Root.Lang) == "de-DE"
        assert pdf.open_metadata()["dc:creator"] == ["WK"]


@needs_tess
def test_graft_rejects_page_image_mismatch(job):
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw)
    with pytest.raises(ocr_mod.OcrError, match="mismatch"):
        ocr_mod.graft_text_layer(out, [raw / "p1.png"], lang="eng")   # 2 pages, 1 image


@needs_tess
def test_text_only_pdf_embeds_no_image(tmp_path: Path):
    """textonly_pdf=1 is the whole safety property — assert it really holds."""
    img = tmp_path / "x.png"
    _text_page("no image here 55555").save(img)
    layer = ocr_mod.text_only_pdf(img, tmp_path / "layer.pdf", lang="eng")
    with pikepdf.open(layer) as pdf:
        assert len(list(pdf.pages[0].images)) == 0, "text-only layer carries an image!"


def test_ghostscript_pdfocr_is_absent_here():
    """Documents WHY we don't use gs pdfocr8/24/32: this build lacks them (and
    they rasterize anyway). If a future gs gains them, this test fails loudly and
    the decision gets revisited on purpose rather than by accident."""
    p = subprocess.run(["gs", "-h"], capture_output=True, text=True, timeout=30)
    devices = p.stdout
    assert "pdfocr8" not in devices, (
        "gs now ships pdfocr8 — revisit docs/PROPOSAL-ASSEMBLY.md. It still "
        "rasterizes (pdfocr8 is grayscale), so the graft is likely still right."
    )


@needs_tess
def test_ocr_refuses_a_missing_language_pack(job):
    """Better to fail than to OCR German as English and graft a plausible-looking
    wrong text layer."""
    tmp_path, raw, m = job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw)
    with pytest.raises(ocr_mod.OcrError, match="not installed"):
        ocr_mod.graft_text_layer(out, [raw / "p1.png", raw / "p2.jpg"],
                                 lang="xxx_not_a_lang")


@needs_tess
def test_available_langs_reports_installed_packs():
    langs = ocr_mod.available_langs()
    assert "eng" in langs and "deu" in langs
