"""I-B) drop/upload producer.

The security tests come first and are the reason this module exists: a multipart
`filename` is arbitrary client input, and a dropped URI can name any path on the
box. Both are guarded; these prove it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pdfdrill.scandrill.manifest import Manifest, PENDING, REMOVED_BLANK
from pdfdrill.scandrill.producers import upload as up


def _png_bytes(blank: bool = False, size=(400, 560)) -> bytes:
    import io
    arr = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    if not blank:
        arr[80:300, 60:340] = 30
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def roots(tmp_path: Path):
    allowed = tmp_path / "allowed"
    secret = tmp_path / "secret"
    allowed.mkdir()
    secret.mkdir()
    (allowed / "a.png").write_bytes(_png_bytes())
    (allowed / "b.png").write_bytes(_png_bytes())
    (secret / "private.png").write_bytes(_png_bytes())
    (secret / "id_rsa").write_text("PRIVATE KEY")
    return tmp_path, allowed, secret


def _manifest() -> Manifest:
    return Manifest(job="drop", created="2026-07-16T10:00:00+02:00")


# ---- path safety ----------------------------------------------------------------

def test_under_root_accepts_inside(roots):
    _t, allowed, _s = roots
    under = up.under_root(allowed, allowed / "a.png")
    assert under is not None and under.name == "a.png"


def test_under_root_rejects_traversal(roots):
    _t, allowed, secret = roots
    assert up.under_root(allowed, allowed / ".." / "secret" / "id_rsa") is None
    assert up.under_root(allowed, secret / "id_rsa") is None
    assert up.under_root(allowed, "/etc/passwd") is None


def test_under_root_rejects_symlink_escape(roots, tmp_path):
    """A symlink inside the root pointing out of it must not smuggle a path
    through — hence resolving both sides before comparing."""
    _t, allowed, secret = roots
    link = allowed / "escape"
    link.symlink_to(secret)
    assert up.under_root(allowed, link / "id_rsa") is None


def test_under_root_rejects_root_relative_traversal(roots):
    _t, allowed, _s = roots
    assert up.under_root(allowed, "../secret/id_rsa") is None


def test_safe_resolve_tries_each_root(roots):
    _t, allowed, secret = roots
    assert up.safe_resolve([secret, allowed], allowed / "a.png") is not None
    assert up.safe_resolve([allowed], secret / "private.png") is None


@pytest.mark.parametrize("evil,expected", [
    ("../../etc/passwd", "passwd"),
    ("..\\..\\windows\\system32\\cfg", "cfg"),
    ("/absolute/path/x.png", "x.png"),
    ("....//....//x.png", "x.png"),
    (".ssh", "ssh"),
    ("..", "page"),
    ("", "page"),
    ("nor\x00mal.png", "normal.png"),
])
def test_safe_filename_neutralises_traversal(evil, expected):
    assert up.safe_filename(evil) == expected


def test_safe_filename_truncates_absurd_length():
    name = "a" * 500 + ".png"
    got = up.safe_filename(name)
    assert len(got) <= up.MAX_NAME_LEN and got.endswith(".png")


# ---- text/uri-list --------------------------------------------------------------

def test_parse_uri_list_handles_file_uris_comments_and_encoding():
    payload = (
        "# a comment\r\n"
        "file:///home/wk/Mein%20Scan.png\r\n"
        "\r\n"
        "file://localhost/home/wk/b.png\r\n"
        "https://example.com/evil.png\r\n"
        "/plain/path/c.png\r\n"
    )
    assert up.parse_uri_list(payload) == [
        "/home/wk/Mein Scan.png", "/home/wk/b.png", "/plain/path/c.png",
    ]


def test_parse_uri_list_drops_remote_host_file_uri():
    assert up.parse_uri_list("file://otherbox/etc/passwd") == []


# ---- reference mode -------------------------------------------------------------

def test_add_reference_does_not_copy(roots):
    _t, allowed, _s = roots
    m = _manifest()
    pg = up.add_reference(m, allowed / "a.png", roots=[allowed])
    assert Path(pg.src).is_absolute()
    assert Path(pg.src) == (allowed / "a.png").resolve()
    assert pg.origin["mode"] == "reference"
    assert pg.sha256 and pg.status == PENDING
    assert list(allowed.iterdir()) != []          # original untouched


def test_add_reference_refuses_outside_roots(roots):
    _t, allowed, secret = roots
    m = _manifest()
    with pytest.raises(up.UploadError, match="outside the allowed roots"):
        up.add_reference(m, secret / "private.png", roots=[allowed])
    assert m.pages == []


def test_add_reference_refuses_non_image(roots):
    _t, allowed, _s = roots
    (allowed / "notes.txt").write_text("hi")
    m = _manifest()
    with pytest.raises(up.UploadError, match="not an image"):
        up.add_reference(m, allowed / "notes.txt", roots=[allowed])


def test_add_reference_refuses_directory(roots):
    _t, allowed, _s = roots
    m = _manifest()
    with pytest.raises(up.UploadError, match="not a file"):
        up.add_reference(m, allowed, roots=[allowed])


def test_add_drop_ingests_the_good_and_reports_the_bad(roots):
    _t, allowed, secret = roots
    m = _manifest()
    payload = "\n".join([
        f"file://{allowed / 'a.png'}",
        f"file://{secret / 'id_rsa'}",      # outside roots
        f"file://{allowed / 'b.png'}",
    ])
    pages, errors = up.add_drop(m, payload, roots=[allowed])
    assert len(pages) == 2, "one bad entry must not sink the whole drop"
    assert len(errors) == 1 and "outside the allowed roots" in errors[0]
    assert [p.seq for p in pages] == [1, 2]


# ---- upload mode ----------------------------------------------------------------

def test_add_upload_writes_into_raw_and_ingests(tmp_path: Path):
    m = _manifest()
    pg = up.add_upload(m, "scan.png", _png_bytes(), job_dir=tmp_path)
    assert pg.src == "raw/p0001_scan.png"
    assert (tmp_path / pg.src).exists()
    assert pg.origin == {"kind": "drop", "mode": "upload", "filename": "scan.png"}
    assert pg.width == 400 and pg.sha256


def test_add_upload_stores_traversal_name_safely(tmp_path: Path):
    m = _manifest()
    pg = up.add_upload(m, "../../../etc/passwd.png", _png_bytes(), job_dir=tmp_path)
    written = tmp_path / pg.src
    assert written.exists()
    assert written.parent == tmp_path / "raw", "escaped the job dir!"
    assert "passwd.png" in written.name and ".." not in written.name


def test_add_upload_does_not_collide_on_repeated_names(tmp_path: Path):
    m = _manifest()
    a = up.add_upload(m, "scan.png", _png_bytes(), job_dir=tmp_path)
    b = up.add_upload(m, "scan.png", _png_bytes(blank=True), job_dir=tmp_path)
    assert a.src != b.src, "second drop of the same name overwrote the first"
    assert (tmp_path / a.src).exists() and (tmp_path / b.src).exists()


def test_add_upload_detects_blank(tmp_path: Path):
    m = _manifest()
    pg = up.add_upload(m, "blank.png", _png_bytes(blank=True), job_dir=tmp_path)
    assert pg.status == REMOVED_BLANK


def test_add_upload_rejects_empty_and_non_image(tmp_path: Path):
    m = _manifest()
    with pytest.raises(up.UploadError, match="empty"):
        up.add_upload(m, "x.png", b"", job_dir=tmp_path)
    with pytest.raises(up.UploadError, match="not an image"):
        up.add_upload(m, "x.exe", b"MZ...", job_dir=tmp_path)


def test_add_upload_rejects_oversize(tmp_path: Path):
    m = _manifest()
    with pytest.raises(up.UploadError, match="too large"):
        up.add_upload(m, "big.png", b"x" * 100, job_dir=tmp_path, max_bytes=10)


def test_add_upload_cleans_up_on_ingest_failure(tmp_path: Path):
    """Bytes that aren't really an image must not leave a file behind."""
    m = _manifest()
    with pytest.raises(Exception):
        up.add_upload(m, "lies.png", b"this is not a PNG", job_dir=tmp_path)
    assert list((tmp_path / "raw").iterdir()) == []
    assert m.pages == []


# ---- multipart ------------------------------------------------------------------

def _multipart(files: list[tuple[str, bytes]], boundary="XbdyX") -> tuple[str, bytes]:
    parts = []
    for name, data in files:
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: image/png\r\n\r\n".encode() + data + b"\r\n"
        )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", body


def test_parse_multipart_extracts_files():
    png = _png_bytes()
    ctype, body = _multipart([("a.png", png), ("b.png", png)])
    got = up.parse_multipart(ctype, body)
    assert [n for n, _ in got] == ["a.png", "b.png"]
    assert got[0][1] == png, "multipart payload corrupted (binary-safety)"


def test_parse_multipart_rejects_wrong_content_type():
    with pytest.raises(up.UploadError, match="expected multipart"):
        up.parse_multipart("application/json", b"{}")


def test_parse_multipart_ignores_non_file_fields():
    body = (b"--B\r\nContent-Disposition: form-data; name=\"job\"\r\n\r\nx\r\n"
            b"--B--\r\n")
    assert up.parse_multipart("multipart/form-data; boundary=B", body) == []
