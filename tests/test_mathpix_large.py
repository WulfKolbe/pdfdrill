"""
Large-file handling for the MathPix upload (the 463 MB / 175-page edge case).

Two guards, both pure-testable:
  * upload_preflight(size, pages) → refuse over MathPix's limit, warn when large,
    so the toolkit gives a clear message + OCR route instead of OOM / a doomed
    multipart POST.
  * the STREAMING multipart body (written to a temp file, never 2× the PDF in
    RAM) must be byte-identical to the in-memory encode_multipart_formdata — so we
    can trust streaming for huge files without breaking the working upload format.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import mathpix_client as mc

MB = 1024 * 1024


def test_preflight_refuses_oversize():
    ok, level, msg = mc.upload_preflight(600 * MB)
    assert ok is False and level == "refuse"
    assert "MB" in msg and ("ocr" in msg.lower() or "split" in msg.lower())


def test_preflight_warns_large_but_allowed():
    ok, level, msg = mc.upload_preflight(200 * MB, pages=175)
    assert ok is True and level == "warn" and msg


def test_preflight_ok_for_small():
    ok, level, _ = mc.upload_preflight(2 * MB, pages=6)
    assert ok is True and level == "ok"


def test_streaming_multipart_matches_inmemory():
    # the streamed body (to a temp file) must equal the in-memory encoding
    import json
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake body \x00\x01\x02 end")
        boundary = "TESTBOUNDARY123"
        ct, length, body_path = mc._stream_multipart(
            Path(d) / "body.bin", json.dumps(mc.CONVERSION_OPTIONS), str(pdf), boundary)
        streamed = Path(body_path).read_bytes()
        ct2, inmem = mc.encode_multipart_formdata(
            fields=[("options_json", json.dumps(mc.CONVERSION_OPTIONS))],
            files=[("file", "x.pdf", pdf.read_bytes())], boundary=boundary)
        assert streamed == inmem
        assert length == len(streamed)
        assert "multipart/form-data" in ct


if __name__ == "__main__":
    for fn in (test_preflight_refuses_oversize, test_preflight_warns_large_but_allowed,
               test_preflight_ok_for_small, test_streaming_multipart_matches_inmemory):
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
