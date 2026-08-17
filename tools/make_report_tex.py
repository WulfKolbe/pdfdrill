#!/usr/bin/env python3
"""Shim — the generator moved INTO the command surface (audit A2/A4: a new
capability is a layer in the manifest, not a tool nothing can sequence).

Use `pdfdrill reporttex <pdf>`; the implementation is
src/pdfdrill/report_tex.py. This file only keeps the old invocation
(`python3 tools/make_report_tex.py <tiddlers.json> [...]`) working.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import main  # noqa: E402

if __name__ == "__main__":
    main()
