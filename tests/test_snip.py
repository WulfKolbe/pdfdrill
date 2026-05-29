"""
Unit tests for the MathPix Snip client (pdfdrill.mathpix_snip).

No network: payload building and response extraction are pure, and the one
network function is exercised with urllib.request.urlopen monkeypatched.
"""
import io
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import mathpix_snip as ms


def test_to_src_passes_through_url_and_datauri():
    assert ms.to_src("https://cdn.mathpix.com/cropped/x.jpg?height=1") \
        == "https://cdn.mathpix.com/cropped/x.jpg?height=1"
    assert ms.to_src("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"


def test_to_src_encodes_local_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "snippet.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n fake bytes")
        src = ms.to_src(str(p))
        assert src.startswith("data:image/png;base64,")
        assert len(src) > len("data:image/png;base64,")


def test_build_payload_sets_line_data_and_latex_options():
    pl = ms.build_payload("https://x/y.png", formats=("text", "data"))
    assert pl["src"] == "https://x/y.png"
    assert pl["include_line_data"] is True
    assert pl["data_options"] == {"include_latex": True}
    assert pl["math_inline_delimiters"] == ["$", "$"]
    assert pl["rm_spaces"] is True


def test_best_latex_prefers_latex_styled():
    resp = {"latex_styled": "x^2 + 1", "text": "$x^{2}+1$",
            "data": [{"type": "latex", "value": "WRONG"}]}
    assert ms.best_latex(resp) == "x^2 + 1"


def test_best_latex_from_data_array():
    resp = {"text": "$a+b$", "data": [{"type": "latex", "value": "a + b"}]}
    assert ms.best_latex(resp) == "a + b"


def test_best_latex_strips_delimiters_from_text():
    assert ms.best_latex({"text": "\\( f(x) \\)"}) == "f(x)"
    assert ms.best_latex({"text": "$$E=mc^2$$"}) == "E=mc^2"


def test_line_candidates_extraction():
    resp = {"line_data": [{
        "type": "math",
        "cnt": [[49, 332], [49, 0], [774, 0], [774, 332]],
        "included": True,
        "is_handwritten": True,
        "text": "\\( f(x)=\\left\\{...\\right. \\)",
        "confidence": 1,
    }]}
    lines = ms.line_candidates(resp)
    assert len(lines) == 1
    assert lines[0]["type"] == "math"
    assert lines[0]["confidence"] == 1
    assert lines[0]["cnt"][0] == [49, 332]


def test_snip_posts_expected_payload(monkeypatch):
    captured = {}

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp(json.dumps({"latex_styled": "y = x", "confidence": 0.97}).encode())

    os.environ["MATHPIX_APP_ID"] = "test_id"
    os.environ["MATHPIX_APP_KEY"] = "test_key"
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    out = ms.snip_result("https://cdn.mathpix.com/cropped/x.jpg")
    assert captured["url"].endswith("/v3/text")
    assert captured["method"] == "POST"
    assert captured["body"]["include_line_data"] is True
    assert out["latex"] == "y = x"
    assert out["confidence"] == 0.97


if __name__ == "__main__":
    import types

    class _MP:
        """Minimal monkeypatch shim so this file runs without pytest."""
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)

    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, fn in tests:
        mp = _MP()
        try:
            if "monkeypatch" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                fn(mp)
            else:
                fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name)
            print(f"ERROR {name}: {e!r}")
        finally:
            mp.undo()
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
