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


def _html():
    return docinspect.build_inspector_html(_model(), pages={}, title="demo")


def test_no_copy_buttons_in_the_chrome():
    """Copying is a native habit — right-click and Ctrl+C — not extra buttons."""
    html = _html()
    assert 'id="copyRects"' not in html
    assert 'id="copyContent"' not in html


def test_right_click_opens_a_menu_on_every_hooked_node():
    """`attachHooks` is where a page box and a tree row both get their handlers,
    so hooking there means the menu works from either place."""
    html = _html()
    hooks = html[html.index("function attachHooks"):][:600]
    assert "contextmenu" in hooks and "openMenu(e" in hooks
    assert "preventDefault" in hooks, "the browser menu must be suppressed"


def test_menu_entries_are_type_aware():
    html = _html()
    body = html[html.index("function copyActions"):][:2200]
    assert "Copy math (LaTeX)" in body and "e.latex" in body
    assert "Copy table (LaTeX)" in body and "latex_code" in body
    assert "Save image (PNG file)" in body and "cropBlob" in body
    assert "Copy text" in body
    assert "Copy rectangle" in body and "Copy ALL rectangles" in body


def test_ctrl_c_copies_the_selected_element():
    html = _html()
    body = html[html.index('document.addEventListener("keydown"'):][:900]
    assert "ctrlKey" in body and "metaKey" in body
    assert "selId" in body and "byId" in body
    assert "acts[0]" in body, "Ctrl+C must run the SAME action the menu lists first"


def test_ctrl_c_yields_to_a_real_text_selection():
    """Hijacking Ctrl+C while prose is highlighted would break exactly the
    browser behaviour this is meant to match."""
    body = _html()
    body = body[body.index('document.addEventListener("keydown"'):][:900]
    assert "getSelection" in body
    # the guard must BAIL OUT (return) right after reading the selection —
    # `split("getSelection")[1]` would only span the 11 characters between the
    # two occurrences of the name, which is why it must be sliced by index.
    after = body[body.rindex("getSelection"):][:160]
    assert "return;" in after, after


def test_image_copy_still_degrades_to_a_download_on_plain_http():
    """drillui serves over http://<host>:<port>, which is not a secure context:
    `navigator.clipboard.write` is unavailable and an image cannot go through
    execCommand, so the crop must arrive as a file instead of failing."""
    body = _html()
    ci = body[body.index("function copyImage"):][:500]
    assert "isSecureContext" in ci and "ClipboardItem" in ci
    # the fallback is saveBlob, which is where the download lives now
    assert "saveBlob" in ci
    sb = body[body.index("function saveBlob"):][:400]
    assert "a.download" in sb and "revokeObjectURL" in sb


def test_image_actions_only_on_real_images():
    """Every element has a rectangle; only a picture has an IMAGE.

    Offering "copy image" on a paragraph produced a crop of some prose — not an
    image of anything — and buried the action that matters under one that never
    does. The entry is gated on the type, not on having a box.
    """
    body = _html()
    body = body[body.index("function copyActions"):][:1800]
    assert "_IMAGEY_TYPES.has(e.type)" in body, \
        "image entries must be gated on the type, not on having a rectangle"


def test_a_png_file_is_offered_before_a_clipboard_bitmap():
    """A web page CANNOT put a file on the clipboard.

    The Async Clipboard API carries image/png as bitmap DATA — there is no file
    flavour — so pasting yields pixels, never a .png. A download is the only way
    to hand over an actual file, so it must lead; the bitmap copy is offered
    only where the API exists at all (a secure context).
    """
    body = _html()
    acts = body[body.index("function copyActions"):][:1800]
    i_save = acts.index("Save image (PNG file)")
    i_copy = acts.find("Copy image (bitmap)")
    assert i_copy == -1 or i_save < i_copy, "the file action must come first"
    assert "isSecureContext" in acts, \
        "the bitmap entry must not be shown where the API cannot work"


def test_saved_image_has_a_recognisable_filename():
    """`obj_d93357848b3b.png` in a download folder is unusable."""
    body = _html()
    fn = body[body.index("function imageName"):][:500]
    assert "DATA.bibkey" in fn and "e.page" in fn and "e.type" in fn


def test_save_and_copy_are_separate_paths():
    body = _html()
    assert "function saveBlob" in body
    sb = body[body.index("function saveBlob"):][:400]
    assert "a.download" in sb and "revokeObjectURL" in sb


def test_a_picture_leads_with_its_image_not_its_caption():
    """Ctrl+C runs the FIRST entry, so on a figure it must copy the figure.

    The caption came first, which meant pointing at a diagram and pressing
    Ctrl+C copied the words underneath it instead of the thing being pointed at.
    """
    body = _html()
    acts = body[body.index("function copyActions"):][:2400]
    # Locate the picture branch itself rather than counting characters — an
    # earlier `} else {` elsewhere in the function made an index comparison
    # match the wrong block.
    start = acts.index("_IMAGEY_TYPES.has(e.type)")
    branch = acts[start:]
    end = branch.index("} else {")
    picture, prose = branch[:end], branch[end:]

    assert picture.index("Save image (PNG file)") < picture.index("Copy caption"), \
        "the image action must precede the caption for a picture"
    assert "Copy text" not in picture, "prose must not be offered on a picture"
    assert "Copy text" in prose, "…and must still be offered on everything else"
