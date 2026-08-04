"""
docinspect (vendored DevTools-style docmodel inspector) + `pdfdrill inspect`.

The tool builds a self-contained inspector HTML over a model.docmodel.json:
an ELEMENTS tree + INSPECTOR pane, every DocObject hooked by id so the page
box and the tree stay linked. These tests exercise the reusable
`build_from_paths` core (no gs / no network) and the `cmd_inspect` wiring
(writes <bibkey>.inspect.html into the drill dir, returns its path), degrading
gracefully when there are no page images (embed with missing PNGs → empty src,
the tree still works).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect


def _model():
    """A minimal docmodel dict in the real Document.to_dict() shape: meta.pages,
    a mathpix_lines stream with an ordered anchor list + a payload map, and
    objects whose realizations reference an anchor range (start/end)."""
    return {
        "meta": {"bibkey": "demo", "num_pages": 1, "title": "Demo Doc",
                 "pages": [{"page": 1, "page_width": 1000, "page_height": 1400}]},
        "streams": {
            "mathpix_lines": {
                "anchors": ["a_para", "a_eq"],
                "payload": {
                    "a_para": {"region": {"top_left_x": 100, "top_left_y": 200,
                                          "width": 800, "height": 60},
                               "text": "Hello world.", "_page": 1},
                    "a_eq": {"region": {"top_left_x": 120, "top_left_y": 400,
                                        "width": 300, "height": 80},
                             "text": "x^2", "_page": 1},
                },
            }
        },
        "objects": [
            {"id": "pg1", "type": "Page", "props": {"page": 1}, "realizations": []},
            {"id": "p1", "type": "Paragraph",
             "props": {"text": "Hello world.", "page": 1, "flow_index": 1},
             "realizations": [{"stream": "mathpix_lines", "start": "a_para",
                               "end": "a_para"}]},
            {"id": "f1", "type": "Formula",
             "props": {"latex": "x^2", "page": 1, "flow_index": 2},
             "realizations": [{"stream": "mathpix_lines", "start": "a_eq",
                               "end": "a_eq"}]},
        ],
        "alignments": [],
    }


def test_build_from_paths_produces_inspector_html():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        mp.write_text(json.dumps(_model()))
        html, n_pages, n_el, mode = docinspect.build_from_paths(str(mp), embed=True)
        assert "<html" in html.lower() and "</html>" in html.lower()
        # the two non-Page elements are hooked into the payload by id
        assert '"p1"' in html and '"f1"' in html
        assert "x^2" in html                     # formula latex reaches the client
        assert n_el == 2                          # Paragraph + Formula (Page excluded)
        assert n_pages == 1
        # embed with no PNG on disk → graceful empty src, HTML still built
        assert mode == "embed"


def test_cmd_inspect_writes_html_and_returns_path(monkeypatch):
    """cmd_inspect on a drill dir that already has a model (no gs needed):
    with images unavailable it still writes <bibkey>.inspect.html and reports
    the path (the drillui-clickable artifact)."""
    from pdfdrill.commands import cmd_inspect
    from pdfdrill import commands as C
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "demo.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        drill = Path(d) / "demo.pdf.drill"
        drill.mkdir()
        (drill / "model.docmodel.json").write_text(json.dumps(_model()))
        # pretend the model is fresh/built so cmd_inspect doesn't try to rebuild
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        # no page images → embed degrades to boxes-only, still an artifact
        out = cmd_inspect(pdf, embed=True, images=False)
        html_path = drill / "demo.inspect.html"
        assert html_path.exists(), out
        assert "inspect.html" in out and "element" in out.lower()


if __name__ == "__main__":
    import types
    class MP:
        def setattr(self, o, n, v): setattr(o, n, v)
        def setenv(self, *a): pass
        def delenv(self, *a, **k): pass
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            import inspect as _i
            t(MP()) if _i.signature(t).parameters else t()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")


def test_inspect_no_meta_pages_derives_from_objects():
    """Sandbox root cause: the LaTeX-source model species has NO meta['pages'],
    so docinspect crashed with KeyError('pages') and `inspect` returned the
    cryptic 'inspect failed: pages' that made the agent improvise. It must derive
    the page list from the objects' page props instead."""
    import json as _j, tempfile as _t
    from pathlib import Path as _P
    m = _model()
    del m["meta"]["pages"]                          # the latex-source species
    with _t.TemporaryDirectory() as d:
        mp = _P(d) / "model.docmodel.json"
        mp.write_text(_j.dumps(m))
        html, n_pages, n_el, mode = docinspect.build_from_paths(str(mp), embed=True)
        assert "<html" in html.lower()              # no crash
        assert '"p1"' in html and '"f1"' in html    # elements still present
        assert n_pages == 1                          # derived page 1 from the objects


def test_page_filter_restricts_elements_and_pages():
    """`inspect --pages` must shrink the WHOLE inspector (elements + embedded page
    images), not just which pages get rasterized — else a big doc always emits the
    full (14 MB) HTML that chokes a reverse-proxy/drillui load."""
    import json as _j, tempfile as _t
    from pathlib import Path as _P
    m = _model()
    # add a second page + an element on it
    m["meta"]["pages"].append({"page": 2, "page_width": 1000, "page_height": 1400})
    m["meta"]["num_pages"] = 2
    m["streams"]["mathpix_lines"]["anchors"].append("a_p2")
    m["streams"]["mathpix_lines"]["payload"]["a_p2"] = {
        "region": {"top_left_x": 50, "top_left_y": 50, "width": 400, "height": 40},
        "text": "Second page para.", "_page": 2}
    m["objects"] += [
        {"id": "pg2", "type": "Page", "props": {"page": 2}, "realizations": []},
        {"id": "p2only", "type": "Paragraph",
         "props": {"text": "Second page para.", "page": 2, "flow_index": 3},
         "realizations": [{"stream": "mathpix_lines", "start": "a_p2", "end": "a_p2"}]},
    ]
    with _t.TemporaryDirectory() as d:
        mp = _P(d) / "model.docmodel.json"
        mp.write_text(_j.dumps(m))
        # no filter → both pages, both elements
        _h, n_pages_all, n_el_all, _m = docinspect.build_from_paths(str(mp), embed=True)
        assert n_pages_all == 2 and '"p2only"' in _h
        # filter to page 1 → page 2 element dropped, only 1 page
        html, n_pages, n_el, _m = docinspect.build_from_paths(
            str(mp), embed=True, page_filter={1})
        assert n_pages == 1 and n_el < n_el_all
        assert '"p1"' in html and '"p2only"' not in html


# --- P4a: the inspect HTML GENERATOR (build_inspector_html) — was untested -----
def test_generator_embeds_elements_bbox_latex():
    """The client payload must carry each element by id/type/bbox + the formula
    LaTeX (what the tree, inspector and KaTeX reflow read)."""
    html = docinspect.build_inspector_html(_model(), pages={}, title="T")
    assert "f1" in html and "Formula" in html and "x^2" in html
    assert "p1" in html and "Hello world" in html      # paragraph reaches the client
    assert "pages_meta" in html                         # page geometry embedded
    assert "bbox" in html


def test_generator_crop_uses_region_faithfully_no_padding():
    """Regression guard for the char-leak investigation: the client crop draws the
    EXACT bbox — no additive padding/rounding that would leak neighbouring glyphs.
    (The leak is region-side/DRILLPDFse, NOT the generator — keep it that way.)"""
    html = docinspect.build_inspector_html(_model(), pages={}, title="T")
    assert "cropFromPage" in html
    assert "drawImage(im, b.x*sx,b.y*sy,b.w*sx,b.h*sy" in html   # faithful rect
    assert "b.x*sx+" not in html and "+pad" not in html          # no additive leak


def test_generator_reflow_and_tree_scaffolding():
    html = docinspect.build_inspector_html(_model(), pages={}, title="Demo Doc")
    assert "reflow" in html.lower()                    # the reading-order reflow tab
    assert "Demo Doc" in html                          # title threaded through
    assert "<html" in html.lower() and "</html>" in html.lower()


def test_generator_geometryless_model_still_renders():
    m = _model()
    del m["meta"]["pages"]                             # the LaTeX-source species
    html = docinspect.build_inspector_html(m, pages={}, title="T")
    assert "<html" in html.lower()
    assert "f1" in html and "p1" in html               # elements still in the payload


def test_copy_rectangles_button_and_non_secure_fallback():
    """A "copy all rectangles" control that also works over plain HTTP.

    drillui serves this page from `http://<host>:8787`, which is NOT a secure
    context, so `navigator.clipboard` is undefined there — the whole feature
    would be dead exactly where it is used. The execCommand fallback is the path
    that actually runs; the async API is the bonus for https/localhost.
    """
    html = docinspect.build_inspector_html(_model(), pages={}, title="demo")

    assert 'id="copyRects"' in html, "no copy control in the toolbar"
    assert "execCommand" in html, \
        "no fallback — clipboard would be dead over plain http, which is how " \
        "drillui serves this page"
    assert "isSecureContext" in html, "must not call the async API blindly"
    # the payload the button copies is built from the elements' own boxes
    assert "function rectRows" in html


def test_every_boxed_element_is_in_the_copy_payload():
    """The control says ALL rectangles, so it must not inherit the page filter
    or the current selection."""
    html = docinspect.build_inspector_html(_model(), pages={}, title="demo")
    body = html[html.index("function rectRows"):][:600]
    assert "DATA.elements" in body, body[:200]
    assert "filter" in body and "bbox" in body      # only elements that HAVE a box
    assert "pageSel" not in body, "must not be limited to the visible page"


def test_copy_content_is_type_aware():
    """The rectangle is rarely what you want — the thing inside it is, and what
    that IS depends on the type. Math must yield LaTeX, a figure the image, a
    table its source, prose its text."""
    html = docinspect.build_inspector_html(_model(), pages={}, title="demo")
    assert 'id="copyContent"' in html
    body = html[html.index("function elementContent"):][:900]
    assert "e.latex" in body, "math must copy as LaTeX"
    assert "latex_code" in body and "raw_text" in body, "table source before cell text"
    assert "cropBlob" in body, "a figure must copy as the image"
    assert "e.text" in body, "prose must copy as text"


def test_image_copy_degrades_to_a_download_on_plain_http():
    """`navigator.clipboard.write` needs a secure context, which drillui's
    http://<host>:<port> is not, and an image cannot go through execCommand. So
    the fallback hands over the FILE rather than failing silently."""
    html = docinspect.build_inspector_html(_model(), pages={}, title="demo")
    body = html[html.index("function copyImage"):][:700]
    assert "isSecureContext" in body and "ClipboardItem" in body
    assert "a.download" in body, "no download fallback — dead over plain http"
    assert "revokeObjectURL" in body, "object URL leaked"


def test_copy_button_is_bound_to_the_rendered_element():
    """No hidden global selection state: the inspector passes the element it is
    rendering, so the button cannot act on a stale one."""
    html = docinspect.build_inspector_html(_model(), pages={}, title="demo")
    assert "copyElementContent(e, cb)" in html
