"""
NLP must run CPU-only by default. On an AMD-APU / integrated-GPU machine the
ROCm torch build would otherwise run Stanza on the very GPU driving X11 — a
Stanza GPU allocation there crashed the display to a black screen (Solus/Beelink
Ryzen). nlp_stanza hides every GPU from torch BEFORE it is imported, unless the
user opts in with PDFDRILL_NLP_GPU=1.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docops import nlp_stanza as N


def test_hides_gpu_by_default(monkeypatch):
    for v in N._GPU_HIDE_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("PDFDRILL_NLP_GPU", raising=False)
    forced = N._hide_gpu_from_torch()
    assert forced is True
    for v in N._GPU_HIDE_VARS:                       # every GPU hidden from torch
        assert os.environ.get(v) == ""


def test_opt_in_keeps_gpu(monkeypatch):
    for v in N._GPU_HIDE_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("PDFDRILL_NLP_GPU", "1")
    forced = N._hide_gpu_from_torch()
    assert forced is False
    for v in N._GPU_HIDE_VARS:                       # untouched — user wants GPU
        assert os.environ.get(v) is None


def test_pipeline_kwargs_force_cpu(monkeypatch):
    monkeypatch.delenv("PDFDRILL_NLP_GPU", raising=False)
    kw = N._pipeline_kwargs("en", "tokenize", cpu=True)
    assert kw.get("device") == "cpu"
    kw2 = N._pipeline_kwargs("en", "tokenize", cpu=False)
    assert "device" not in kw2


if __name__ == "__main__":
    import inspect
    class MP:
        def __init__(self): self._u=[]
        def setenv(self,k,v): self._u.append((k,os.environ.get(k))); os.environ[k]=v
        def delenv(self,k,raising=True): self._u.append((k,os.environ.get(k))); os.environ.pop(k,None)
        def undo(self):
            for k,v in reversed(self._u):
                if v is None: os.environ.pop(k,None)
                else: os.environ[k]=v
    tests=[(k,v) for k,v in list(globals().items()) if k.startswith("test_")]
    failed=[]
    for name,t in tests:
        mp=MP()
        try: t(mp); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
        finally: mp.undo()
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
