"""
pdfdrill pyramid (src/pdfdrill/pyramid.py): build a local 600-DPI DZI pyramid
(gs render + pyvips dzsave) — the MathPix-free image source. The dzsave step
needs pyvips/libvips; the manifest math + graceful degradation are tested here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pyramid


def test_manifest_entry_levels():
    e = pyramid._manifest_entry(3, "page03", 4800, 6200)
    assert e["page"] == 3 and e["dzi"] == "tiles/page03.dzi"
    assert e["width"] == 4800 and e["height"] == 6200
    # levels = ceil(log2(max(w,h))) + 1  → ceil(log2(6200))=13, +1 = 14
    assert e["levels"] == 14


def test_tools_available_reports_missing_pyvips():
    ok, msg = pyramid.tools_available()
    if pyramid._have_pyvips() and __import__("pdfdrill.pdf_reading",
            fromlist=["gs_binary"]).gs_binary():
        assert ok and msg == ""
    else:
        assert not ok and "pyramid build needs" in msg


def test_cmd_pyramid_graceful_without_tools(monkeypatch=None):
    """When pyvips/libvips is absent, `pdfdrill pyramid` returns a clear install
    message — never a traceback."""
    import tempfile
    from pdfdrill import commands, pyramid as P
    # force "tools unavailable" regardless of the host
    real = P.tools_available
    P.tools_available = lambda: (False, "pyramid build needs pyvips (system libvips-tools).")
    try:
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
            out = commands.cmd_pyramid(pdf)
            assert "Pyramid not built" in out and "pyvips" in out
    finally:
        P.tools_available = real


def test_real_pyramid_build_and_crop():
    """END-TO-END (gated on gs + pyvips): build a real DZI pyramid from a pypdf PDF
    and crop a region from it with eqcrop. Skips cleanly where the tools are absent."""
    ok, _ = pyramid.tools_available()
    if not ok:
        print("  (skip: gs/pyvips not available)"); return
    import tempfile
    from pypdf import PdfWriter
    from pdfdrill import eqcrop
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        w = PdfWriter(); w.add_blank_page(width=612, height=792)
        with open(pdf, "wb") as f:
            w.write(f)
        out = Path(d) / "viewer"
        res = pyramid.build_pyramid(pdf, out, dpi=150, pages=[1])
        assert res["pages"] == 1
        e = res["manifest"][0]
        assert e["dzi"] == "tiles/page01.dzi" and e["width"] > 0 and e["height"] > 0
        assert (out / "manifest.json").exists()
        assert (out / "tiles" / "page01.dzi").exists()
        # the deepest level holds the full render → eqcrop reads a region from it
        files = out / "tiles" / "page01_files"
        assert files.is_dir() and any(files.iterdir())
        pyr = eqcrop.Pyramid(str(out / "tiles" / "page01.dzi"))
        crop = pyr.crop(10, 10, 100, 60)               # a small region
        assert crop is not None and crop.width > 0 and crop.height > 0


def test_streaming_build_flat_disk_and_progress():
    """Big-doc fix (211-page Axe manual): build ONE page at a time — render →
    dzsave → delete the page PNG — so temp disk stays ~1 page instead of the
    whole doc, and a build.json progress marker {done,total} exists DURING the
    build and is gone after. Gated on gs+pyvips."""
    ok, _ = pyramid.tools_available()
    if not ok:
        print("  (skip: gs/pyvips not available)"); return
    import json, tempfile
    from pypdf import PdfWriter
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        w = PdfWriter()
        for _ in range(3):
            w.add_blank_page(width=612, height=792)
        with open(pdf, "wb") as f:
            w.write(f)
        out = Path(d) / "viewer"

        seen = {"max_pngs": 0, "progress_seen": False}
        real_dzsave = pyramid._dzsave_page
        def spy(img_path, tiles_dir, name, **kw):
            pngs = list((out / "_render").glob("*.png")) if (out / "_render").exists() else []
            seen["max_pngs"] = max(seen["max_pngs"], len(pngs))
            bj = out / "build.json"
            if bj.exists():
                prog = json.loads(bj.read_text())
                assert set(prog) >= {"done", "total"} and prog["total"] == 3
                seen["progress_seen"] = True
            return real_dzsave(img_path, tiles_dir, name, **kw)
        pyramid._dzsave_page = spy
        try:
            res = pyramid.build_pyramid(pdf, out, dpi=150)
        finally:
            pyramid._dzsave_page = real_dzsave

        assert res["pages"] == 3
        assert seen["max_pngs"] <= 1, f"disk not flat: {seen['max_pngs']} PNGs at once"
        assert seen["progress_seen"], "build.json progress marker never appeared"
        assert not (out / "build.json").exists(), "progress marker must be removed"
        assert not (out / "_render").exists(), "temp render dir must be removed"
        assert (out / "manifest.json").exists()


def test_concurrent_build_lock_and_clear_page_error():
    """Two-builds clash fix (the Axe crash): a FRESH build.json is a LOCK — a
    second build_pyramid refuses with an in-progress error instead of racing
    the first (each build's cleanup was wiping the other's temp render). And a
    page gs renders nothing for raises a CLEAR error naming the page, not a
    bare 'list index out of range'."""
    import json, tempfile, time
    from pdfdrill import pyramid as P
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "viewer"
        out.mkdir(parents=True)
        # a fresh lock from "another" build
        (out / "build.json").write_text(json.dumps({"done": 3, "total": 9,
                                                    "dpi": 600}))
        try:
            P.build_pyramid(Path(d) / "x.pdf", out, dpi=150)
            assert False, "expected the in-progress lock to refuse"
        except RuntimeError as e:
            assert "in progress" in str(e) and "3/9" in str(e)
        # the lock file must survive the refusal (it belongs to the OTHER build)
        assert (out / "build.json").exists()

        # a STALE lock (dead build) does not block — but this stub PDF makes gs
        # fail, so we only assert the lock was cleared for a fresh attempt path
        old = time.time() - 600
        import os
        os.utime(out / "build.json", (old, old))
        ok, _ = P.tools_available()
        if not ok:
            print("  (skip stale-lock path: gs/pyvips not available)"); return
        (Path(d) / "x.pdf").write_bytes(b"%PDF-1.4")   # stub: render will fail
        try:
            P.build_pyramid(Path(d) / "x.pdf", out, dpi=150)
        except Exception as e:
            assert "in progress" not in str(e)          # stale lock did NOT block


def test_missing_page_render_is_a_clear_error():
    """rasterize returning nothing for a page must raise a named-page error."""
    ok, _ = pyramid.tools_available()
    if not ok:
        print("  (skip: gs/pyvips not available)"); return
    import tempfile
    from pypdf import PdfWriter
    from pdfdrill import pdf_reading
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        w = PdfWriter(); w.add_blank_page(width=612, height=792)
        with open(pdf, "wb") as f:
            w.write(f)
        real = pdf_reading.rasterize
        pdf_reading.rasterize = lambda *a, **k: []       # gs "produced nothing"
        try:
            pyramid.build_pyramid(pdf, Path(d) / "viewer", dpi=150)
            assert False, "expected a clear error"
        except RuntimeError as e:
            assert "page 1" in str(e) and "no image" in str(e)
        finally:
            pdf_reading.rasterize = real


def test_cmd_pyramid_offline_writes_server_free_bundle():
    """--offline on the MAIN gs command: after the build, the doc's viewer/ also
    carries viewer_offline.html + the vendored OSD (the server-free bundle) —
    and a repeat call on an existing pyramid can add the bundle without a
    rebuild. Gated on gs+pyvips."""
    ok, _ = pyramid.tools_available()
    if not ok:
        print("  (skip: gs/pyvips not available)"); return
    import tempfile
    from pypdf import PdfWriter
    from pdfdrill import commands
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        w = PdfWriter(); w.add_blank_page(width=612, height=792)
        with open(pdf, "wb") as f:
            w.write(f)
        out = commands.cmd_pyramid(pdf, dpi=150, offline=True)
        viewer = Sidecar(pdf).blob_dir / "viewer"
        assert (viewer / "viewer_offline.html").exists(), out
        assert (viewer / "openseadragon.min.js").exists(), out
        assert "viewer_offline.html" in out           # the prose names the bundle
        # idempotent add-on: pyramid exists, offline re-requested → bundle stays
        out2 = commands.cmd_pyramid(pdf, dpi=150, offline=True)
        assert (viewer / "viewer_offline.html").exists()
        assert "already built" in out2.lower()



def test_imageserve_argv_without_pyramid():
    """`pdfdrill imageserve` returns a clear 'run pyramid first' message when the
    doc has no <drill>/viewer/manifest.json — never launches a server."""
    import tempfile
    from pdfdrill import commands
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        argv, url, err = commands._imageserve_argv(pdf, sc, 8000, None)
        assert argv is None and "pyramid" in err and "imageserve" not in err.lower()[:5]
        assert "run `pdfdrill pyramid" in err


def test_imageserve_argv_built_when_pyramid_present():
    """With a built pyramid the argv targets mathpix_server.py over the viewer dir,
    passes the gs --pyramid-dpi from the sidecar, and adds --lines when present."""
    import json as _json, tempfile, sys as _sys
    from pdfdrill import commands
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        viewer = sc.blob_dir / "viewer"; (viewer / "tiles").mkdir(parents=True)
        (viewer / "manifest.json").write_text("[]", encoding="utf-8")
        sc.set_evidence("pyramid", {"dpi": 600})
        lines = pdf.parent / "x.lines.json"; lines.write_text("{}", encoding="utf-8")
        argv, url, err = commands._imageserve_argv(pdf, sc, 8123, None)
        assert err == "" and argv is not None
        assert argv[0] == _sys.executable and argv[1].endswith("mathpix_server.py")
        assert "--root" in argv and str(viewer) in argv
        assert "--pyramid-dpi" in argv and "600" in argv
        assert "--port" in argv and "8123" in argv
        assert "--lines" in argv and str(lines) in argv
        assert url == "http://localhost:8123/viewer.html"


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
