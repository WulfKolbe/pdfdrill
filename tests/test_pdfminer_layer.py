"""
pdfminer_layer (src/pdfdrill/pdfminer_layer.py): the pdfminer leg of the merge.
MathPix flattens all local formatting; pdfminer's LTChar carries per-glyph
fontname / size / CTM / color, so this layer recovers the RICH signal MathPix
drops — font CHANGES (bold/italic emphasis runs) and SIZE changes (headings,
footnotes, sub/superscripts) — and precise CTM-chain geometry.

Pure core tested here (no PDF needed): font-style classification, run-grouping
of same-style adjacent chars, dominant (body) style, and emphasis spans (the
runs that deviate from the body font — the local formatting MathPix loses).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pdfminer_layer as pm


def test_font_style_strips_subset_prefix_and_reads_bold_italic():
    # TeX Computer Modern
    assert pm.font_style("CMBX10") == {"family": "cmbx", "bold": True,
                                       "italic": False, "mono": False}
    assert pm.font_style("CMTI10")["italic"] is True
    assert pm.font_style("CMTT10")["mono"] is True
    # real-world with a 6-letter subset prefix
    assert pm.font_style("ABCDEF+Arial-BoldMT")["bold"] is True
    assert pm.font_style("XYZQWE+NimbusRomNo9L-RegularItalic")["italic"] is True
    # plain roman is neither
    s = pm.font_style("AAAAAA+CMR10")
    assert s["bold"] is False and s["italic"] is False


def _char(text, font, size, page=1, x0=0.0, top=0.0, w=5.0, h=10.0, color="black"):
    return {"text": text, "font": font, "size": size, "page": page,
            "x0": x0, "top": top, "x1": x0 + w, "bottom": top + h, "color": color,
            **pm.font_style(font)}


def test_font_runs_group_adjacent_same_style_and_split_on_change():
    """A word set bold inside body text becomes its own run — the local
    formatting MathPix would have flattened into one plain string."""
    line = "The result is important."
    chars = []
    x = 0.0
    for ch in "The result is ":
        chars.append(_char(ch, "CMR10", 10.0, x0=x)); x += 5
    for ch in "important":
        chars.append(_char(ch, "CMBX10", 10.0, x0=x)); x += 5
    for ch in ".":
        chars.append(_char(ch, "CMR10", 10.0, x0=x)); x += 5
    runs = pm.font_runs(chars)
    assert [r["text"] for r in runs] == ["The result is ", "important", "."]
    assert runs[1]["bold"] is True and runs[0]["bold"] is False
    # the bold run carries a region (union bbox, MathPix top-left convention)
    r = runs[1]["region"]
    assert set(r) == {"top_left_x", "top_left_y", "width", "height"}
    assert r["width"] > 0 and r["height"] > 0


def test_dominant_style_is_the_body_font_by_char_count():
    chars = [_char("x", "CMR10", 10.0) for _ in range(20)]
    chars += [_char("y", "CMBX12", 12.0) for _ in range(3)]     # a few heading chars
    dom = pm.dominant_style(chars)
    assert dom["font"] == "CMR10" and dom["size"] == 10.0


def test_emphasis_spans_are_runs_deviating_from_body():
    body = {"font": "CMR10", "size": 10.0}
    runs = [
        {"text": "plain ", "font": "CMR10", "size": 10.0, "bold": False,
         "italic": False, "mono": False},
        {"text": "EMPH", "font": "CMTI10", "size": 10.0, "bold": False,
         "italic": True, "mono": False},
        {"text": " and a ", "font": "CMR10", "size": 10.0, "bold": False,
         "italic": False, "mono": False},
        {"text": "Heading", "font": "CMBX12", "size": 12.0, "bold": True,
         "italic": False, "mono": False},
    ]
    spans = pm.emphasis_spans(runs, body)
    kinds = {s["text"]: s["kind"] for s in spans}
    assert kinds == {"EMPH": "italic", "Heading": "bold+larger"}


def test_attach_page_emphasis_to_page_objects():
    from docmodel.core import Document, DocObject
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Page", id="pg1", props={"page_number": 1}))
    doc.add(DocObject(type="Page", id="pg2", props={"page_number": 2}))
    spans = [
        {"page": 1, "text": "Introduction", "kind": "bold+larger",
         "font": "CMBX12", "size": 12.0, "region": {"top_left_x": 5}},
        {"page": 1, "text": "key term", "kind": "italic", "font": "CMTI10",
         "size": 10.0, "region": {"top_left_x": 8}},
    ]
    n = pm.attach_page_emphasis(doc, spans)
    assert n == 1                                        # only page 1 had spans
    fe = doc.objects["pg1"].props["font_emphasis"]
    assert [x["text"] for x in fe] == ["Introduction", "key term"]
    assert "font_emphasis" not in doc.objects["pg2"].props
    # idempotent (re-attach same spans → same result)
    assert pm.attach_page_emphasis(doc, spans) == 1


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
