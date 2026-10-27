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

import pytest

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
        html, n_pages, n_el, mode, _n_img = docinspect.build_from_paths(str(mp), embed=True)
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


# ---------------------------------------------------------------------------
#  THE INSPECTOR THAT SHIPPED WITHOUT ITS PAGES (ser7, 2026-10-22)
#
#  `BH1org.inspect.html` came out at 7,272,092 bytes instead of 56,137,806 —
#  the complete element tree over 319 BLANK pages — and `pdfdrill inspect`
#  called that a success at exit 0, with the only warning in a parenthesis
#  inside a success sentence. Two defects, one cause: `_inspect_pages_dir`
#  asked Ghostscript for permission BEFORE it looked at the folder it
#  maintains. `rasterize` calls `_require_gs()` as its first act, so on a
#  machine without gs the RuntimeError fired before the directory was ever
#  read, and 319 correct p{N}.png on disk were all discarded. The same
#  blindness runs the other way on a machine that HAS gs: every run
#  re-rendered all 319 pages (481 MB of PNG, 32 s) over byte-identical
#  renders. The docstring said "reusing any already present" the whole time,
#  which is why nobody checked: it had retired the question.
#
#  And a count printed next to a file must be a count OF that file — 40
#  rendered pages of 319 read exactly like 319 of 319, because the note fired
#  only when `pages_dir` was None and nothing ever counted the images.
# ---------------------------------------------------------------------------

def _two_page_model():
    m = _model()
    m["meta"]["num_pages"] = 2
    m["meta"]["pages"].append({"page": 2, "page_width": 1000, "page_height": 1400})
    m["objects"].append({"id": "pg2", "type": "Page", "props": {"page": 2},
                         "realizations": []})
    return m


def _doc_with_renders(d: Path, model: dict, rendered: "list[int]", *,
                      n_pages: int = 1, dpi: int = 400,
                      manifest: bool = True) -> Path:
    """A drill dir holding `model` and a p{N}.png for each page in `rendered`.

    The PNGs are written after the PDF so they are NEWER than it, which is what
    `_pages_on_disk` requires — a render older than the document it came from
    is a stale render.
    """
    from PIL import Image
    from pdfdrill.sidecar import Sidecar
    pdf = d / "demo.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    drill = d / "demo.pdf.drill"
    pages = drill / "inspect" / "pages"
    pages.mkdir(parents=True)
    (drill / "model.docmodel.json").write_text(json.dumps(model))
    for n in rendered:
        Image.new("RGB", (100, 140), (255, 255, 255)).save(pages / f"p{n}.png")
    if manifest:
        (pages / "manifest.json").write_text(json.dumps(
            {"document": "demo", "dpi": dpi, "pages": len(rendered)}))
    # the page count `_inspect_pages_dir` enumerates; pdfinfo cannot answer for
    # an 8-byte stub, and a real document carries it from the probe.
    sc = Sidecar(pdf)
    sc.set_evidence("pages", n_pages)
    sc.save()
    return pdf


def _no_gs(monkeypatch):
    """Ghostscript absent: `rasterize` raises exactly as `_require_gs` does."""
    from pdfdrill import pdf_reading
    def boom(*a, **k):
        raise RuntimeError("Ghostscript (gs) is required for rasterization")
    monkeypatch.setattr(pdf_reading, "rasterize", boom)


def _spy_rasterize(monkeypatch, made=()):
    """Record every rasterize call; return `made` as the rendered files."""
    from pdfdrill import pdf_reading
    calls = []
    def spy(pdf, out_dir, *, pages=None, dpi=400, **k):
        calls.append(pages)
        return list(made)
    monkeypatch.setattr(pdf_reading, "rasterize", spy)
    return calls


def test_pages_already_rendered_are_not_rendered_again(monkeypatch):
    """STEP 1. Every requested page is on disk, so gs is never asked at all —
    and the images reach the HTML."""
    pytest.importorskip("PIL")
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _model(), [1], n_pages=1)
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        calls = _spy_rasterize(monkeypatch)
        out = cmd_inspect(pdf, embed=True, images=True)
        assert calls == [], f"gs was asked for {calls} although page 1 was on disk"
        html = (Path(d) / "demo.pdf.drill" / "demo.inspect.html").read_text(
            encoding="utf-8")
        assert "data:image/jpeg;base64" in html, out


def test_renders_on_disk_survive_a_missing_ghostscript(monkeypatch):
    """STEP 1, the ser7 case. gs is gone and one of the two pages is already
    rendered: the render is USED (not discarded), and the shortfall is named."""
    pytest.importorskip("PIL")
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _two_page_model(), [1], n_pages=2)
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        _no_gs(monkeypatch)
        out = cmd_inspect(pdf, embed=True, images=True)
        html = (Path(d) / "demo.pdf.drill" / "demo.inspect.html").read_text(
            encoding="utf-8")
        assert html.count("data:image/jpeg;base64") == 1, \
            "the page render on disk was discarded because gs was absent"
        assert "1 of 2" in out, out
        assert getattr(out, "exit_code", 0) == 0, "a partial build is not a failure"


def test_an_inspector_with_no_page_images_at_all_fails_loudly(monkeypatch):
    """STEP 2. Zero images over a model that HAS page geometry is a failed
    build: exit 3 (a thing reported and not run), the count, and the one fix."""
    pytest.importorskip("PIL")
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    from pdfdrill.cli import EXIT_LANE_NOT_RUN
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _model(), [], n_pages=1)
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        _no_gs(monkeypatch)
        out = cmd_inspect(pdf, embed=True, images=True)
        assert getattr(out, "exit_code", 0) == EXIT_LANE_NOT_RUN, \
            f"a boxes-only build reported success: {out!r}"
        assert "0 of 1" in out and "hostscript" in out, out
        # the artifact is still written — the tree is usable, it is just blind
        assert (Path(d) / "demo.pdf.drill" / "demo.inspect.html").exists()


def test_no_images_was_asked_for_and_is_not_a_failure(monkeypatch):
    """STEP 2 must not fire on `--no-images`: boxes-only was the REQUEST."""
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _model(), [], n_pages=1, manifest=False)
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        out = cmd_inspect(pdf, embed=True, images=False)
        assert getattr(out, "exit_code", 0) == 0, out
        assert "boxes-only" in out, out


def test_a_partial_render_names_its_count(monkeypatch):
    """STEP 2. gs runs and comes back with fewer pages than were asked for —
    the shortfall is in the prose, where before there was no note at all."""
    pytest.importorskip("PIL")
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _two_page_model(), [1], n_pages=2)
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        _spy_rasterize(monkeypatch)            # page 2 renders to nothing
        out = cmd_inspect(pdf, embed=True, images=True)
        assert "1 of 2" in out, out


def test_reuse_needs_the_manifest_to_name_the_dpi(monkeypatch):
    """STEP 1's one refusal. `prepare_pages` scales a render by
    embed_dpi/src_dpi, so a page reused at the WRONG DPI is embedded at the
    wrong size and its boxes land beside the ink — worse than no image.
    manifest.json is the only record of what the folder was rendered at, so
    without it the pages are re-rendered rather than guessed at."""
    pytest.importorskip("PIL")
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _model(), [1], n_pages=1, manifest=False)
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        calls = _spy_rasterize(monkeypatch)
        cmd_inspect(pdf, embed=True, images=True)
        assert calls, "a render of unrecorded DPI was reused instead of rebuilt"


def test_a_render_from_another_document_is_not_reused(monkeypatch):
    """819e, held: the manifest names the document its pages came from."""
    pytest.importorskip("PIL")
    from pdfdrill import commands as C
    from pdfdrill.commands import cmd_inspect
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc_with_renders(Path(d), _model(), [1], n_pages=1)
        pages = Path(d) / "demo.pdf.drill" / "inspect" / "pages"
        (pages / "manifest.json").write_text(json.dumps(
            {"document": "someone-elses-book", "dpi": 400, "pages": 1}))
        monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
        calls = _spy_rasterize(monkeypatch)
        cmd_inspect(pdf, embed=True, images=True)
        assert calls, "another document's page images were served as this one's"



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
        html, n_pages, n_el, mode, _n_img = docinspect.build_from_paths(str(mp), embed=True)
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
        _h, n_pages_all, n_el_all, _m, _n_img = docinspect.build_from_paths(str(mp), embed=True)
        assert n_pages_all == 2 and '"p2only"' in _h
        # filter to page 1 → page 2 element dropped, only 1 page
        html, n_pages, n_el, _m, _n_img = docinspect.build_from_paths(
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


def test_a_page_offers_its_image_not_just_coordinates():
    """Ctrl+C on a page returned {"type":"Page","x":243,...} — coordinates for
    something the user was pointing at as a picture. A page's content IS the
    rendered bitmap, so it belongs with the image types."""
    body = _html()
    types = body[body.index("const _IMAGEY_TYPES"):][:300]
    assert '"Page"' in types


def test_smaller_boxes_are_painted_last_so_clicks_hit_them():
    """A later sibling paints on top. A page-sized box appended after a figure
    covered it and swallowed the click, which is how a click on a diagram
    selected the Page instead."""
    body = _html()
    rp = body[body.index("function renderPage"):][:1200]
    assert ".sort(" in rp and "bbox.w*b.bbox.h" in rp.replace(" ", ""), rp[:400]


def test_button_era_helpers_are_gone():
    """`elementContent`/`copyElementContent` served the removed buttons; leaving
    them invites a future caller to use a code path nothing exercises."""
    body = _html()
    assert "function elementContent" not in body
    assert "function copyElementContent" not in body


def test_elements_without_a_page_are_still_listed():
    """The tree grouped ONLY by page, so any element with `page: null` was
    silently dropped from it.

    On arXiv 2604.11744 that was 101 of 131 elements — 28 Equations, 23 Formulas,
    28 Paragraphs — because a LaTeX-source model carries no page geometry until
    `geometry` attaches it. The inspector looked empty while the model was
    perfectly healthy, so re-running `mathpix --force`, `injectlatex` and
    `inspect` could not possibly help: the data was never the problem.

    They have no box to draw, but their CONTENT is exactly what the inspector is
    for — selecting one must still show its record and copy its LaTeX.
    """
    html = _html()
    tree = html[html.index("function buildTree"):][:2600]
    assert "e.page == null" in tree or "e.page===null" in tree or "unplaced" in tree, \
        "no branch for page-less elements — they vanish from the tree"


def test_the_unplaced_group_is_labelled_not_disguised_as_a_page():
    html = _html()
    tree = html[html.index("function buildTree"):][:2600]
    assert "no page" in tree.lower(), \
        "an element with no page must not be shown as belonging to one"


# --------------------------------------------------------------------------- #
#  The headline count must be a count OF THE FILE it is printed beside.
#
#  Found by an auditing session (finding J). `build_from_paths` counted two
#  different populations in its two branches: the unfiltered one took the
#  MODEL's objects minus the Pages (so the Document counted as an element),
#  while the page's own `DATA.elements` is `collect_elements` — Document and
#  Citation dropped, the Page containers kept. Measured on hilbert1902:
#  "133 elements" printed over a payload of 142 records, and 132 things
#  actually in the tree.
# --------------------------------------------------------------------------- #

def _model_with_a_document():
    m = _model()
    m["objects"].insert(0, {"id": "doc", "type": "Document",
                            "props": {"title": "Demo Doc"}, "realizations": []})
    m["objects"].append({"id": "c1", "type": "Citation",
                         "props": {"page": 1}, "realizations": []})
    return m


def _payload(html: str) -> dict:
    """The DATA the page actually ships."""
    i = html.index("const DATA")
    j = html.index("{", i)
    depth = 0
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[j:k + 1])
    raise AssertionError("no DATA object in the inspector html")


def test_the_reported_count_matches_the_payload_the_page_ships():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        mp.write_text(json.dumps(_model_with_a_document()))
        html, n_pages, n_el, _m, _n_img = docinspect.build_from_paths(str(mp), embed=True)
        data = _payload(html)
        in_tree = [e for e in data["elements"] if e.get("type") != "Page"]
        assert n_el == len(in_tree), (
            f"the headline says {n_el} elements and the page holds "
            f"{len(in_tree)}: " + repr(sorted(
                {e.get('type') for e in data['elements']})))
        assert n_el == 2, "Paragraph + Formula — not the Document, not the Pages"


def test_the_document_object_is_not_an_element():
    """It is the model's root. It has no page, no box and no row, so counting
    it inflated every number this command printed by one."""
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        mp.write_text(json.dumps(_model_with_a_document()))
        html, _p, n_el, _m, _n_img = docinspect.build_from_paths(str(mp), embed=True)
        types = {e.get("type") for e in _payload(html)["elements"]}
        assert "Document" not in types
        assert n_el == 2


def test_a_page_filtered_count_matches_its_payload_too():
    """The branch that was already right must stay tied to the same list."""
    m = _model_with_a_document()
    m["meta"]["num_pages"] = 2
    m["meta"]["pages"].append({"page": 2, "page_width": 1000, "page_height": 1400})
    m["objects"].append({"id": "pg2", "type": "Page", "props": {"page": 2},
                         "realizations": []})
    m["objects"].append({"id": "p2", "type": "Paragraph",
                         "props": {"text": "Second page.", "page": 2,
                                   "flow_index": 3},
                         "realizations": []})
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        mp.write_text(json.dumps(m))
        html, _p, n_el, _mode, _n_img = docinspect.build_from_paths(
            str(mp), embed=True, page_filter={1})
        in_tree = [e for e in _payload(html)["elements"]
                   if e.get("type") != "Page"]
        assert n_el == len(in_tree) == 2, (n_el, len(in_tree))
