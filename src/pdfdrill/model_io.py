"""
model_io — one chokepoint for loading/saving the docmodel, with a packed cache.

The `model.docmodel.json` is large (tens of MB; ~75% is per-character anchor +
`{"codepoint":…}` dicts that most commands never read). `docpack` stores the
same model losslessly in ~30% of the bytes (≈9% gz). This module is the single
place the toolchain reads/writes the model, so the packed sidecar
`model.docpack.json` is always available:

  * `save_model(path, doc)`   — writes the canonical `.docmodel.json` (so any
    direct reader / older code still works) AND the packed `.docpack.json`.
  * `load_model(path)`        — returns a full `Document` (prefers the packed
    sidecar when fresh; identical result either way — `unpack(pack(m)) == m`).

The packed sidecar is also what the lazy `DocGraph` read-path consumes (the
real per-call speed win for the LLM-facing read-only commands — a full
`Document.from_dict` stays ~1.9s regardless of file size because it expands the
char dicts, while `DocGraph` over the packed model loads in ~0.2s and never
expands them). `packed_path(path)` exposes the sidecar location for that path.

Lossless and back-compatible: an existing `.docmodel.json` with no sidecar
loads exactly as before; the sidecar is (re)written on the next save.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import docpack


def packed_path(model_path) -> Path:
    """The `.docpack.json` sidecar next to a `model.docmodel.json`."""
    p = Path(model_path)
    return p.with_name(p.name.replace(".docmodel.json", ".docpack.json"))


def _fresh(packed: Path, plain: Path) -> bool:
    """True if the packed sidecar exists and is at least as new as the plain
    model (so an out-of-band write to `.docmodel.json` is never read stale)."""
    if not packed.exists():
        return False
    if not plain.exists():
        return True
    return packed.stat().st_mtime >= plain.stat().st_mtime - 1e-6


def load_model(model_path):
    """Load the model as a `Document` (packed sidecar preferred when fresh)."""
    from docmodel.core import Document
    plain = Path(model_path)
    packed = packed_path(plain)
    if _fresh(packed, plain):
        try:
            data = docpack.unpack(json.loads(packed.read_text(encoding="utf-8")))
            return Document.from_dict(data)
        except Exception:
            pass                                   # corrupt sidecar -> fall back
    return Document.from_dict(json.loads(plain.read_text(encoding="utf-8")))


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` atomically: to a temp file in the same directory,
    then os.replace (atomic on POSIX). A process killed mid-write (e.g. a huge
    model hitting a timeout) then leaves EITHER the old file or nothing — never a
    truncated JSON that poisons every later read. The temp is cleaned on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)                      # atomic rename
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def save_model(model_path, doc, *, packed: bool = True) -> None:
    """Write the canonical model + (by default) the packed sidecar in sync.
    Both writes are ATOMIC so a killed process never leaves a truncated JSON."""
    plain = Path(model_path)
    plain.parent.mkdir(parents=True, exist_ok=True)
    data = doc.to_dict()
    _atomic_write(plain, json.dumps(data, indent=2, ensure_ascii=False))
    sidecar = packed_path(plain)
    if packed:
        try:
            _atomic_write(sidecar, json.dumps(docpack.pack(data), ensure_ascii=False))
        except Exception:
            if sidecar.exists():                   # never leave a stale sidecar
                sidecar.unlink()
    elif sidecar.exists():
        sidecar.unlink()


def load_docgraph(model_path):
    """The lazy read-path view (DocGraph) over the packed sidecar — the fast
    per-call loader for read-only commands. Falls back to packing the plain
    model on the fly if no sidecar exists yet."""
    from .docgraph import DocGraph
    packed = packed_path(model_path)
    if _fresh(packed, Path(model_path)):           # mtime-guarded, like load_model
        return DocGraph.load(str(packed))
    return DocGraph.load(str(model_path))          # sidecar absent OR stale (e.g.
    #                          a command saved the .docmodel.json via json.dump)
