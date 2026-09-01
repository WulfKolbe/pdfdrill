#!/usr/bin/env python3
"""466 — bundle docs/prompts/ into the package, the way skillsync bundles the SKILL.

`docs/prompts/` is canonical: it is where a prompt is edited and where its
history is readable. But an installed wheel has no project root to search
upward to (the same reason `scandrill.toml` travels with the package), so the
files are copied into `src/pdfdrill/prompts_data/` and declared as
package-data.

    python3 tools/promptsync.py bundle    copy canonical -> bundled
    python3 tools/promptsync.py check     fail on drift (what CI runs)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "prompts"
DST = ROOT / "src" / "pdfdrill" / "prompts_data"
SUFFIX = "-prompt.md"


def _files(d: Path) -> dict:
    return {p.name: p.read_bytes() for p in sorted(d.glob("*" + SUFFIX))} \
        if d.is_dir() else {}


def bundle() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    src, dst = _files(SRC), _files(DST)
    for name in set(dst) - set(src):
        (DST / name).unlink()
    n = 0
    for name, body in src.items():
        if dst.get(name) != body:
            (DST / name).write_bytes(body)
            n += 1
    print("bundled %d prompt file(s) (%d changed) %s -> %s"
          % (len(src), n, SRC.relative_to(ROOT), DST.relative_to(ROOT)))
    return 0


def check() -> int:
    src, dst = _files(SRC), _files(DST)
    if src == dst:
        print("✓ prompts: canonical ↔ bundled in sync (%d files)" % len(src))
        return 0
    for name in sorted(set(src) | set(dst)):
        if name not in dst:
            print("  MISSING from bundle: %s" % name)
        elif name not in src:
            print("  STALE in bundle:     %s" % name)
        elif src[name] != dst[name]:
            print("  DIFFERS:             %s" % name)
    print("run: python3 tools/promptsync.py bundle")
    return 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    raise SystemExit({"bundle": bundle, "check": check}[action]())
