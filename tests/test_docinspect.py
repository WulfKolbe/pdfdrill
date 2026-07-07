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
