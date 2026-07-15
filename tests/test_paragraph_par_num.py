"""
Tesseract lines carry the TSV layout hierarchy (block_num/par_num) — the
enriched keyless OCR path (PDFDRILLocr) preserves it verbatim into the
mathpix_lines stream. ParagraphProcessor must split paragraphs when that
group changes; without it, a tesseract-built model collapses each page into
ONE giant Paragraph (seen on scan_20260715170757.pdf: 80 lines -> 1 object).
MathPix lines carry no par_num, so their grouping is unchanged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.base_module import ModuleConfig


def _mod():
    return ParagraphProcessor(
        ModuleConfig(title="ParagraphProcessor",
                     classname="ParagraphProcessor", proc_order=13), "T")


def _line(i, text, block=None, par=None):
    l = {"id": f"l{i}", "type": "text", "text": text, "text_display": text}
    if block is not None:
        l["block_num"] = block
        l["par_num"] = par
    return l


def test_tesseract_par_num_splits_paragraphs():
    doc = Document()
    ingest_lines_json(doc, {"source": "tesseract", "pages": [{
        "page": 1, "image_id": None, "lines": [
            _line(0, "Sehr geehrter Herr Kolbe,", block=1, par=1),
            _line(1, "wir informieren Sie hiermit.", block=1, par=1),
            _line(2, "Ihr Fahrzeug ist betroffen.", block=1, par=2),
            _line(3, "Bitte vereinbaren Sie einen Termin.", block=1, par=2),
            _line(4, "Mit freundlichen Grüßen", block=2, par=1),
        ]}]})
    _mod().process_document(doc)
    paras = [o.props["text"] for o in doc.objects_of_type("Paragraph")]
    assert len(paras) == 3
    assert paras[0].endswith("hiermit.")
    assert paras[1].startswith("Ihr Fahrzeug")
    assert paras[2] == "Mit freundlichen Grüßen"


def test_mathpix_lines_without_par_num_unchanged():
    doc = Document()
    ingest_lines_json(doc, {"pages": [{
        "page": 1, "image_id": "i", "lines": [
            _line(0, "First line of prose."),
            _line(1, "Second line, same paragraph."),
            _line(2, "Third line, still the same."),
        ]}]})
    _mod().process_document(doc)
    paras = doc.objects_of_type("Paragraph")
    assert len(paras) == 1
    assert paras[0].props["num_lines"] == 3
