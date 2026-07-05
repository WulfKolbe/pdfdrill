"""
PDFDRILL_OFFLINE=1 — the central offline switch: net.urlopen refuses ALL outbound
network up front (raising NetworkBlocked), so every paid/keyed route degrades
gracefully with NO spend, regardless of env- or file-based creds. This is what
makes the test harness's keyless mode safe.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import net


def test_offline_refuses_before_any_request(monkeypatch):
    monkeypatch.setenv("PDFDRILL_OFFLINE", "1")
    # would explode if it actually tried to open a socket; the gate must fire first
    called = []
    monkeypatch.setattr(net.urllib.request, "urlopen",
                        lambda *a, **k: called.append(1))
    try:
        net.urlopen("https://api.mathpix.com/v3/pdf", timeout=5)
        assert False, "expected NetworkBlocked"
    except net.NetworkBlocked as e:
        assert "offline" in str(e).lower()
    assert not called                              # never reached the real urlopen


def test_online_when_unset(monkeypatch):
    monkeypatch.delenv("PDFDRILL_OFFLINE", raising=False)
    seen = []
    class FakeResp:
        status = 200
        def read(self, *a): return b"ok"
    monkeypatch.setattr(net.urllib.request, "urlopen",
                        lambda *a, **k: seen.append(1) or FakeResp())
    r = net.urlopen("https://example.com/x", timeout=5)
    assert seen and r.status == 200                # gate does NOT fire


if __name__ == "__main__":
    import inspect
    class MP:
        def __init__(self): self._u=[]
        def setenv(self,k,v): import os; os.environ[k]=v
        def delenv(self,k,raising=True): import os; os.environ.pop(k,None)
        def setattr(self,o,n,v): self._u.append((o,n,getattr(o,n,None))); setattr(o,n,v)
        def undo(self):
            for o,n,v in reversed(self._u): setattr(o,n,v)
    tests=[(k,v) for k,v in list(globals().items()) if k.startswith("test_")]
    failed=[]
    for name,t in tests:
        mp=MP()
        try: t(mp); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
        finally: mp.undo()
    import os
    os.environ.pop("PDFDRILL_OFFLINE", None)
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
