"""Metadata control, and the refusal where the OCR graft used to be.

The graft is gone (`docs/LANES.md`): a text layer on a scan makes `pdfdrill
route` read it as born-digital and send it to the text-layer lane instead of one
that can read it. Its tests went with it — they asserted that grafting left the
image stream byte-identical, which is no longer a thing that can happen. What
remains here is the metadata half, plus one test that `assemble` REFUSES the
flag rather than ignoring it.
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



# ---- the graft is refused, not ignored -----------------------------------------

def test_assemble_refuses_the_ocr_flag(job):
    """A caller that still passes `ocr=True` is told WHY, not quietly obliged.

    Ignoring the flag would hand back a PDF without the text layer and no reason
    for it; raising names the misroute and the command that reads a scan.
    """
    tmp, raw, m = job
    with pytest.raises(ValueError) as e:
        assemble(m, tmp / "out.pdf", job_dir=raw, ocr=True)
    msg = str(e.value)
    assert "born-digital" in msg, msg
    assert "gemmaocr" in msg, msg


def test_assemble_without_the_flag_still_writes_a_pdf(job):
    tmp, raw, m = job
    out = assemble(m, tmp / "plain.pdf", job_dir=raw)
    assert out.exists() and out.stat().st_size > 0
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 2
