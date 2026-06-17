"""
Tests for pdfdrill.llm_delegate — the keyless LLM-delegation fallback.

No real `claude -p` call and no network: the CLI transport is exercised by
monkeypatching subprocess.run; the sandbox transport is a pure filesystem
handshake. Covers runtime detection (incl. overrides), content-hash task
identity, the sandbox defer→answer→ingest round-trip, the NONE error, and the
CLI synchronous path with JSON-envelope parsing.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import llm_delegate as D


def test_detect_runtime_override():
    for name in ("cli", "sandbox", "none"):
        os.environ["PDFDRILL_DELEGATE"] = name
        try:
            assert D.detect_runtime() is D.Runtime(name)
        finally:
            del os.environ["PDFDRILL_DELEGATE"]


def test_detect_runtime_signals(monkeypatch):
    # CLI wins when a claude binary resolves.
    monkeypatch.delenv("PDFDRILL_DELEGATE", raising=False)
    monkeypatch.setattr(D, "_claude_binary", lambda: "/usr/bin/claude")
    monkeypatch.setattr(os, "environ", {"IS_SANDBOX": "yes"})
    assert D.detect_runtime() is D.Runtime.CLI
    # No binary + IS_SANDBOX -> sandbox.
    monkeypatch.setattr(D, "_claude_binary", lambda: None)
    monkeypatch.setattr(os, "environ", {"IS_SANDBOX": "yes"})
    assert D.detect_runtime() is D.Runtime.SANDBOX
    # Nothing -> none.
    monkeypatch.setattr(os, "environ", {})
    assert D.detect_runtime() is D.Runtime.NONE


def test_task_id_is_content_hash():
    a = D.LLMTask("vision", "P")
    b = D.LLMTask("vision", "P")
    c = D.LLMTask("vision", "Q")
    assert a.task_id == b.task_id != c.task_id
    assert len(a.task_id) == 32  # blake2b digest_size=16 -> 32 hex chars


def test_none_runtime_raises():
    try:
        D.delegate_batch([D.LLMTask("bibtex", "x")], runtime=D.Runtime.NONE)
        assert False, "expected DelegateUnavailable"
    except D.DelegateUnavailable:
        pass


def test_sandbox_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        drill = Path(td) / "doc.drill"
        vis = D.LLMTask("vision", "classify", image_path=None)
        bib = D.LLMTask("bibtex", "bibtex for Foo 2020")

        res, deferred = D.delegate_batch([vis, bib], drill_dir=drill,
                                        runtime=D.Runtime.SANDBOX)
        assert res == {} and deferred is not None
        assert len(D.pending_requests(drill)) == 2

        llm = drill / "llm"
        (llm / (vis.task_id + D.RESP_SUFFIX)).write_text(json.dumps(
            {"result": {"selector": "math", "math": "x^2"}}))
        (llm / (bib.task_id + D.RESP_SUFFIX)).write_text(json.dumps(
            {"result": "```bibtex\n@article{foo2020,year={2020}}\n```"}))

        res2, deferred2 = D.delegate_batch([vis, bib], drill_dir=drill,
                                          runtime=D.Runtime.SANDBOX)
        assert deferred2 is None
        assert res2[vis.task_id]["math"] == "x^2"
        assert res2[bib.task_id]["fields"]["year"] == "2020"
        assert D.pending_requests(drill) == []


def test_cli_transport(monkeypatch):
    """CLI path: subprocess.run returns the claude JSON envelope; we parse it."""
    import subprocess

    class _Proc:
        returncode = 0
        stderr = ""
        def __init__(self, result):
            self.stdout = json.dumps({"type": "result", "is_error": False,
                                      "result": result, "session_id": "s1"})

    def fake_run(cmd, **kw):
        # vision prompt references the image; bib does not
        if "--allowedTools" in cmd:
            return _Proc('{"selector": "math", "math": "E=mc^2"}')
        return _Proc("```bibtex\n@book{x, year={1999}}\n```")

    monkeypatch.setattr(D, "_claude_binary", lambda: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "crop.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        vis = D.LLMTask("vision", "classify", image_path=str(img))
        bib = D.LLMTask("bibtex", "bibtex for X")
        res, deferred = D.delegate_batch([vis, bib], runtime=D.Runtime.CLI)
        assert deferred is None
        assert res[vis.task_id]["selector"] == "math"
        assert res[vis.task_id]["math"] == "E=mc^2"
        assert res[bib.task_id]["fields"]["year"] == "1999"


def test_cli_error_envelope(monkeypatch):
    import subprocess

    class _Proc:
        returncode = 0
        stderr = ""
        stdout = json.dumps({"is_error": True, "result": "rate limited"})

    monkeypatch.setattr(D, "_claude_binary", lambda: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Proc())
    try:
        D.delegate(D.LLMTask("bibtex", "x"), runtime=D.Runtime.CLI)
        assert False, "expected error"
    except RuntimeError as e:
        assert "rate limited" in str(e)


_TESTS = [test_detect_runtime_override, test_task_id_is_content_hash,
          test_none_runtime_raises, test_sandbox_roundtrip]
_MP_TESTS = [test_detect_runtime_signals, test_cli_transport,
             test_cli_error_envelope]


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v, raising=True):
            self._u.append((o, n, getattr(o, n, None))); setattr(o, n, v)
        def delenv(self, n, raising=True): os.environ.pop(n, None)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    for fn in _TESTS:
        fn(); print(f"PASS {fn.__name__}")
    for fn in _MP_TESTS:
        mp = _MP()
        try:
            fn(mp); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(_TESTS) + len(_MP_TESTS)} tests passed.")
