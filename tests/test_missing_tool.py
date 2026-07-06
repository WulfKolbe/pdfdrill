"""
A missing core system tool (poppler's pdfinfo) must degrade to a clear, actionable
message — not the raw '[Errno 2] No such file or directory: pdfinfo' the CoCalc
test hit. cmd_size is the level-0 entry most commands chain, so it's the guard
point.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_size_reports_missing_poppler_cleanly(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        def boom(cmd, *a, **k):
            raise FileNotFoundError(2, "No such file or directory", "pdfinfo")
        monkeypatch.setattr(C.subprocess, "run", boom)
        out = C.cmd_size(pdf)
        assert "poppler" in out.lower() and "install" in out.lower()
        assert "Errno 2" not in out and "Traceback" not in out
        assert "doctor" in out.lower()             # steers to the prereq check


def test_missing_tool_msg_helper():
    msg = C._missing_tool_msg("pdfinfo", "poppler-utils")
    assert "pdfinfo" in msg and "poppler-utils" in msg and "install" in msg.lower()


if __name__ == "__main__":
    import inspect
    class MP:
        def setattr(self, o, n, v): setattr(o, n, v)
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(MP()) if inspect.signature(t).parameters else t()
            print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
