"""
tools/imageserver/mathpix_server.py — the MathPix-free image server.

Regression for the "viewer does not work (but `python3 -m http.server` does)" bug:
the server now serves STATIC files (viewer.html / manifest.json / tiles/*) with
Python's proven SimpleHTTPRequestHandler — correct MIME, CORS, conditional caching
— and only overrides /cropped + /healthz. This builds a real 1-page DZI pyramid
(gs + pyvips) and asserts every route a browser + OpenSeadragon hits. Gated on the
pyramid tools so it skips cleanly where libvips is absent.
"""
import sys, subprocess, time, json
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from pdfdrill import pyramid

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "tools" / "imageserver" / "mathpix_server.py"


def _get(url, headers=None):
    # return r.headers (an HTTPMessage) — its .get() is CASE-INSENSITIVE, so a
    # header sent as "Content-Type" (our _send) or "Content-type" (stdlib static)
    # both resolve. A plain dict() would be case-sensitive and miss one of them.
    try:
        r = urlopen(Request(url, headers=headers or {}), timeout=5)
        return r.status, r.headers, r.read()
    except HTTPError as e:
        return e.code, e.headers, e.read()


def test_server_serves_viewer_tiles_and_crop():
    ok, _ = pyramid.tools_available()
    if not ok:
        print("  (skip: gs/pyvips not available)"); return
    import tempfile, socket
    from pypdf import PdfWriter
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "x.pdf"
        w = PdfWriter(); w.add_blank_page(width=612, height=792)
        with open(pdf, "wb") as f:
            w.write(f)
        viewer = d / "viewer"
        pyramid.build_pyramid(pdf, viewer, dpi=150, pages=[1])
        # copy the real viewer.html in (mirrors cmd_pyramid)
        import shutil
        shutil.copy(REPO / "tools" / "imageserver" / "viewer.html", viewer / "viewer.html")

        # a free port
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--root", str(viewer),
             "--tiles", str(viewer / "tiles"), "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            up = False
            for _ in range(60):
                try:
                    if _get(base + "/healthz")[0] == 200:
                        up = True; break
                except Exception:
                    pass
                time.sleep(0.2)
            assert up, "server did not come up"

            # viewer.html: 200 text/html, no-cache, CORS (the static path = SimpleHTTPRequestHandler)
            st, h, body = _get(base + "/viewer.html")
            assert st == 200 and "text/html" in h.get("Content-type", "")
            assert h.get("Cache-Control") == "no-cache"
            assert h.get("Access-Control-Allow-Origin") == "*"
            assert b"manifest.json" in body  # the generic viewer reads the manifest

            # manifest.json: 200 application/json, valid, 1 page
            st, h, body = _get(base + "/manifest.json")
            assert st == 200 and len(json.loads(body)) == 1

            # .dzi tile-source: 200 application/xml (the MIME fix), max-age (immutable)
            st, h, body = _get(base + "/tiles/page01.dzi")
            assert st == 200 and h.get("Content-type") == "application/xml"
            assert "max-age" in (h.get("Cache-Control") or "") and b"<Image" in body

            # a real tile: 200 image/jpeg
            mani = json.loads(_get(base + "/manifest.json")[2])
            lvl = mani[0]["levels"] - 1
            st, h, body = _get(base + f"/tiles/page01_files/{lvl}/0_0.jpg")
            assert st == 200 and "image/jpeg" in h.get("Content-type", "") and body[:2] == b"\xff\xd8"

            # /cropped still works (a region assembled from the pyramid)
            st, h, body = _get(base + "/cropped/page01.jpg?top_left_x=5&top_left_y=5&width=60&height=40")
            assert st == 200 and "image/jpeg" in h.get("Content-type", "") and body[:2] == b"\xff\xd8"

            # / redirects to the viewer
            st, h, _ = _get(base + "/")
            assert st in (200, 302)   # urllib follows 302 → 200; either is fine
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except Exception: proc.kill()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
