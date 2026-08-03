"""The LIVE born-digital dumper must carry the font, and must resolve (cid:N).

Two defects, one cause: `_pdfminer_char_dump` built each char from only
x0/x1/y0/y1/text and dropped everything else pdfminer knows.

1. No `fontname` reached `chars_to_lines`, so its math-font test always saw
   (False, False) and typed every line as prose — on the very route that CAN see
   math. The pdfplumber FALLBACK does pass the font, so testing that path shows
   math typing working while the path that actually runs types nothing. Verifying
   the fallback and reporting the live route as fixed is exactly the mistake this
   test exists to prevent.

2. pdfminer emits `(cid:N)` for glyphs it cannot map to Unicode, and those are
   overwhelmingly the LaTeX MATH fonts — so the literal text `L(cid:0)x(cid:1)`
   lands in the model and the tiddlers. A resolver (`_CID_MAP`/`_resolve_cid`)
   already existed but was stranded in `nodes/ingest_pdfplumber.py`, the ingest
   path that no longer runs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pdfdrill
from pdfdrill import commands
from pdfdrill.cid_glyphs import resolve_cid


def _patch_pm(monkeypatch, fake):
    """Substitute the pdfminer layer.

    `from . import pdfminer_layer` reads the ATTRIBUTE off the `pdfdrill`
    package, so patching sys.modules alone works only until some other test has
    imported the real module — after that the attribute already exists and the
    patch is silently ignored, which is how this passed alone and failed in the
    suite. Patch both.
    """
    monkeypatch.setitem(sys.modules, "pdfdrill.pdfminer_layer", fake)
    monkeypatch.setattr(pdfdrill, "pdfminer_layer", fake, raising=False)


def test_resolver_maps_math_font_cids():
    assert resolve_cid("(cid:0)", "LMMathExtension10-Regular") == "("
    assert resolve_cid("(cid:1)", "CMEX10") == ")"
    assert resolve_cid("plain", "CMR10") == "plain"          # untouched
    assert resolve_cid("(cid:9999)", "CMEX10") == "(cid:9999)"   # unknown kept


def test_pdfminer_dump_carries_fontname_and_resolves_cids(monkeypatch):
    """The dump is the seam; if it drops the font, everything downstream is blind."""
    recs = [{"page": 1, "text": "x", "font": "LMMathItalic10-Regular",
             "x0": 10.0, "x1": 16.0, "top": 100.0, "bottom": 110.0},
            {"page": 1, "text": "(cid:0)", "font": "LMMathExtension10-Regular",
             "x0": 16.0, "x1": 22.0, "top": 100.0, "bottom": 110.0}]

    class _PM:
        @staticmethod
        def available():
            return True

        @staticmethod
        def char_records(_p):
            return recs

        @staticmethod
        def page_dims(_p):
            return {1: (612.0, 792.0)}

    _patch_pm(monkeypatch, _PM)
    out = commands._pdfminer_char_dump(Path("x.pdf"))
    chars = out["pages"][0]["chars"]
    assert chars[0].get("fontname") == "LMMathItalic10-Regular", \
        "the live dumper must pass the font through"
    assert chars[1]["text"] == "(", "(cid:N) must be resolved at the dump seam"


def test_live_dump_shape_still_feeds_chars_to_lines(monkeypatch):
    """End-to-end on the LIVE dumper: a math-font line comes out typed `math`."""
    recs = [{"page": 1, "text": ch, "font": "LMMathItalic10-Regular",
             "x0": 10.0 + 7 * i, "x1": 16.0 + 7 * i, "top": 100.0, "bottom": 110.0}
            for i, ch in enumerate("y=ax+b")]

    class _PM:
        available = staticmethod(lambda: True)
        char_records = staticmethod(lambda _p: recs)
        page_dims = staticmethod(lambda _p: {1: (612.0, 792.0)})

    _patch_pm(monkeypatch, _PM)
    from pdfdrill.chars_to_lines import chars_to_lines_json
    out = chars_to_lines_json(commands._pdfminer_char_dump(Path("x.pdf")))
    types = [l.get("type") for p in out["pages"] for l in p["lines"]]
    assert "math" in types, f"live route typed {types}"
