"""
Unit tests for the MathPix client (pdfdrill.mathpix_client).

No network is touched: the cached/idempotent path is exercised directly, and
the upload function is monkeypatched to a tripwire that fails the test if
called when outputs already exist.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import mathpix_client as mc


def test_base_name_strips_pdf_case_insensitive():
    assert mc.base_name("/a/b/Paper.PDF") == "/a/b/Paper"
    assert mc.base_name("/a/b/paper.pdf") == "/a/b/paper"
    assert mc.base_name("/a/b/noext") == "/a/b/noext"


def test_expected_outputs_naming():
    out = mc.expected_outputs("/x/doc.pdf", formats=("lines.json", "md"))
    assert out == {"lines.json": "/x/doc.lines.json", "md": "/x/doc.md"}


def test_encode_multipart_formdata_shape():
    ctype, body = mc.encode_multipart_formdata(
        fields=[("options_json", '{"k":1}')],
        files=[("file", "doc.pdf", b"%PDF-1.7 bytes")],
    )
    assert ctype.startswith("multipart/form-data; boundary=")
    boundary = ctype.split("boundary=")[1]
    assert boundary.encode() in body
    assert b'name="options_json"' in body
    assert b'name="file"; filename="doc.pdf"' in body
    assert b"%PDF-1.7 bytes" in body
    assert body.rstrip().endswith(f"--{boundary}--".encode())


def test_fetch_mathpix_cached_skips_network():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.7")
        # Pre-create all expected outputs so the cache path triggers.
        for ext in mc.DEFAULT_FORMATS:
            (Path(d) / f"paper.{ext}").write_text("x")

        original = mc.upload_pdf

        def _boom(*a, **k):
            raise AssertionError("upload_pdf must not be called when cached")

        mc.upload_pdf = _boom
        try:
            res = mc.fetch_mathpix(str(pdf), force=False, log=lambda m: None)
        finally:
            mc.upload_pdf = original

        assert res["status"] == "cached"
        assert res["pdf_id"] is None
        assert set(res["files"]) == set(mc.DEFAULT_FORMATS)
        assert all(os.path.exists(p) for p in res["files"].values())


def test_fetch_mathpix_missing_file_raises():
    try:
        mc.fetch_mathpix("/no/such/file.pdf", log=lambda m: None)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
