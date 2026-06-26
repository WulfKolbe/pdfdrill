"""
Tests for graceful sandbox-accessibility handling (pdfdrill.net) and the
command-level behaviour when an outbound host is blocked.
"""
import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import net


def _httperror(code, body=b"", reason="Forbidden"):
    return urllib.error.HTTPError("https://api.x.com/e", code, reason, {},
                                  io.BytesIO(body))


def test_urlerror_becomes_networkblocked(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("Network is unreachable")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        net.urlopen("https://api.mathpix.com/v3/pdf", host="api.mathpix.com")
        assert False, "expected NetworkBlocked"
    except net.NetworkBlocked as e:
        assert "api.mathpix.com" in str(e)
        assert "blocked or unreachable" in str(e)
        assert "offline routes" in str(e)


def test_oserror_becomes_networkblocked(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    try:
        net.urlopen("https://api.openai.com/v1/chat", host="api.openai.com")
        assert False
    except net.NetworkBlocked as e:
        assert "api.openai.com" in str(e)


def test_real_http_status_propagates(monkeypatch):
    # A genuine 401 from the host is NOT a block — it must pass through.
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(_httperror(401, b"bad key", "Unauthorized")))
    try:
        net.urlopen("https://api.openai.com", host="api.openai.com")
        assert False
    except net.NetworkBlocked:
        assert False, "401 should propagate, not become NetworkBlocked"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_proxy_block_http_becomes_networkblocked(monkeypatch):
    # An egress proxy returning 403 with a block-hint body IS a block.
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            _httperror(403, b"host not allowed by sandbox proxy")))
    try:
        net.urlopen("https://api.perplexity.ai", host="api.perplexity.ai")
        assert False
    except net.NetworkBlocked as e:
        assert "api.perplexity.ai" in str(e)


# ---- command-level: blocked host -> graceful message, no traceback ----

def _model_with_eq(tmp: Path):
    from docmodel.core import Document, DocObject
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import MODEL_BUILT
    pdf = tmp / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    doc = Document()
    doc.add(DocObject(type="Equation", props={
        "cdn_url": "https://cdn.mathpix.com/cropped/x-1.jpg?height=1&width=1&top_left_y=0&top_left_x=0",
        "latex": "x"}))
    sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
    sc.add_fact(MODEL_BUILT); sc.save()
    return pdf


def test_cmd_snip_blocked_returns_message(monkeypatch):
    from pdfdrill import commands
    from pdfdrill import mathpix_snip
    monkeypatch.setattr(mathpix_snip, "snip_result",
                        lambda *a, **k: (_ for _ in ()).throw(net.NetworkBlocked("BLOCKED-MSG api.mathpix.com")))
    with tempfile.TemporaryDirectory() as d:
        pdf = _model_with_eq(Path(d))
        out = commands.cmd_snip(pdf)
        assert "BLOCKED-MSG" in out          # graceful: returns the message


def test_cmd_vision_blocked_returns_message(monkeypatch):
    from pdfdrill import commands, openai_vision
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    monkeypatch.setattr(openai_vision, "analyze_image",
                        lambda *a, **k: (_ for _ in ()).throw(net.NetworkBlocked("BLOCKED-MSG api.openai.com")))
    with tempfile.TemporaryDirectory() as d:
        pdf = _model_with_eq(Path(d))
        out = commands.cmd_vision(pdf)
        assert "BLOCKED-MSG" in out


def test_urlopen_attaches_browser_user_agent(monkeypatch):
    captured = {}

    def fake(req, *a, **k):
        captured["is_request"] = isinstance(req, urllib.request.Request)
        captured["ua"] = req.get_header("User-agent") if captured["is_request"] else None
        class _R:
            def read(self, *a): return b""
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _R()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    net.urlopen("https://aclanthology.org/2020.emnlp-main.434.pdf", timeout=5)
    # a bare string URL is wrapped in a Request carrying a browser UA (anti-bot)
    assert captured["is_request"] is True
    assert captured["ua"] and "Mozilla" in captured["ua"]


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    fns = [test_urlerror_becomes_networkblocked, test_oserror_becomes_networkblocked,
           test_real_http_status_propagates, test_proxy_block_http_becomes_networkblocked,
           test_urlopen_attaches_browser_user_agent,
           test_cmd_snip_blocked_returns_message, test_cmd_vision_blocked_returns_message]
    for fn in fns:
        mp = _MP()
        try:
            fn(mp); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(fns)} tests passed.")
