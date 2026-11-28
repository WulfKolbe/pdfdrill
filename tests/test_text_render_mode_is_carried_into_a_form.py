r"""`3 Tr` set before a form XObject's `Do` holds inside the form.

lib:025faeafae2f p153 (T-0174's finding) sets `3 Tr` and draws its whole OCR
layer through one form; pdfminer starts a form with a fresh text state and
reported the layer visible. The build's interpreter carries the render mode.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")


def _pdf(path, tr_outside):
    form = b"BT /F1 12 Tf 72 700 Td (Hello) Tj ET"
    page = (b"q " + tr_outside + b" /Fm1 Do Q")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /XObject << /Fm1 5 0 R >> /Font << /F1 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(page) + page + b"\nendstream",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] "
        b"/Resources << /Font << /F1 6 0 R >> >> /Length %d >>\nstream\n" % len(form)
        + form + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(out)
    return str(path)


def _modes(pdf):
    from pdfminer.layout import LTChar

    def walk(o):
        if isinstance(o, LTChar):
            yield o
        elif hasattr(o, "__iter__"):
            for x in o:
                yield from walk(x)
    lay, _seen = next(iter(dm._pages_with_order(pdf, None)))
    return [getattr(c, "invisible", None) for c in walk(lay)]


def test_tr3_before_a_form_makes_its_text_invisible(tmp_path):
    assert _modes(_pdf(tmp_path / "a.pdf", b"3 Tr")) == [True] * 5


def test_without_tr_the_form_text_stays_visible(tmp_path):
    assert _modes(_pdf(tmp_path / "b.pdf", b"")) == [False] * 5
