"""The drop-zone server, exercised over real HTTP (no mocked handlers)."""

from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pdfdrill.scandrill.server import JobStore, make_server


def _png(blank: bool = False, size=(400, 560)) -> bytes:
    arr = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    if not blank:
        arr[80:300, 60:340] = 30
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def live(tmp_path: Path):
    allowed = tmp_path / "allowed"
    secret = tmp_path / "secret"
    allowed.mkdir(); secret.mkdir()
    (allowed / "ref.png").write_bytes(_png())
    (secret / "id_rsa").write_text("KEY")
    (secret / "private.png").write_bytes(_png())

    store = JobStore("j1", tmp_path / "job", "2026-07-16T10:00:00+02:00",
                     "de-DE", [allowed])
    httpd = make_server(store, port=0)          # port 0 = let the OS pick
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", store, allowed, secret
    httpd.shutdown()
    httpd.server_close()


def _post(url, body: bytes, ctype: str):
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _multipart(files, boundary="Bd"):
    parts = []
    for name, data in files:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n".encode()
            + data + b"\r\n")
    return (f"multipart/form-data; boundary={boundary}",
            b"".join(parts) + f"--{boundary}--\r\n".encode())


def test_drop_zone_serves(live):
    base, store, _a, _s = live
    code, body = _get(base + "/")
    assert code == 200
    assert b"drop page images here" in body
    assert b"j1" in body, "the page must be bound to the job"


def test_upload_roundtrip_over_http(live):
    base, store, _a, _s = live
    ctype, body = _multipart([("one.png", _png()), ("two.png", _png(blank=True))])
    code, js = _post(f"{base}/job/j1/pages", body, ctype)
    assert code == 200
    assert js["added"] == [1, 2] and js["errors"] == []

    code, raw = _get(f"{base}/job/j1/manifest")
    m = json.loads(raw)
    assert [p["src"] for p in m["pages"]] == ["raw/p0001_one.png", "raw/p0002_two.png"]
    assert m["pages"][0]["status"] == "pending"
    assert m["pages"][1]["status"] == "removed_blank", "blank detected on upload"
    # the manifest was persisted, not just held in memory
    assert store.manifest_path.exists()
    assert json.loads(store.manifest_path.read_text())["pages"]


def test_paths_mode_references_without_copying(live):
    base, store, allowed, _s = live
    body = f"file://{allowed / 'ref.png'}".encode()
    code, js = _post(f"{base}/job/j1/paths", body, "text/uri-list")
    assert code == 200 and js["added"] == [1]
    page = store.manifest.pages[0]
    assert Path(page.src) == (allowed / "ref.png").resolve()
    assert not (store.job_dir / "raw").exists(), "reference mode must not copy"


def test_paths_mode_refuses_outside_root_over_http(live):
    base, store, _a, secret = live
    body = f"file://{secret / 'private.png'}".encode()
    code, js = _post(f"{base}/job/j1/paths", body, "text/uri-list")
    assert code == 200                       # partial success is reported, not thrown
    assert js["added"] == []
    assert len(js["errors"]) == 1 and "outside the allowed roots" in js["errors"][0]
    assert store.manifest.pages == []


def test_upload_with_traversal_filename_stays_in_job_dir(live):
    base, store, _a, _s = live
    ctype, body = _multipart([("../../../evil.png", _png())])
    code, js = _post(f"{base}/job/j1/pages", body, ctype)
    assert code == 200 and js["added"] == [1]
    written = store.job_dir / store.manifest.pages[0].src
    assert written.resolve().parent == (store.job_dir / "raw").resolve()


def test_thumb_serves_the_page_image(live):
    base, store, _a, _s = live
    ctype, body = _multipart([("one.png", _png())])
    _post(f"{base}/job/j1/pages", body, ctype)
    code, data = _get(f"{base}/job/j1/thumb/1")
    assert code == 200 and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumb_404s_for_unknown_page(live):
    base, *_ = live
    code, _ = _get(f"{base}/job/j1/thumb/99")
    assert code == 404


def test_unknown_job_is_404(live):
    base, *_ = live
    code, _ = _get(f"{base}/job/other/manifest")
    assert code == 404


def test_empty_post_rejected(live):
    base, *_ = live
    code, js = _post(f"{base}/job/j1/pages", b"", "multipart/form-data; boundary=B")
    assert code == 400


def test_non_multipart_post_rejected(live):
    base, *_ = live
    code, js = _post(f"{base}/job/j1/pages", b"{}", "application/json")
    assert code == 400 and "multipart" in js["error"]
