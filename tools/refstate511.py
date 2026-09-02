#!/usr/bin/env python3
r"""511 — every object whose refinement is in a state other than verified.

The 33 accepted corrections are the population that can carry a
contradiction, because only a refined object has two records to disagree.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import refine as rf          # noqa: E402

MAXB = 300 * 1024 * 1024


class _O:
    """The shape refinement_state reads, out of raw JSON."""

    def __init__(self, d):
        self.props = d.get("props") or {}
        self.realizations = [_R(r) for r in (d.get("realizations") or [])]


class _R:
    def __init__(self, d):
        self.provenance = d.get("provenance")
        self.props = d.get("props") or {}


if __name__ == "__main__":
    lib = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    tally = collections.Counter()
    bad = []
    docs = 0
    for d in sorted(p for p in lib.iterdir() if p.is_dir()):
        f = d / "model.docmodel.json"
        if not f.is_file() or f.stat().st_size > MAXB:
            continue
        try:
            s = f.read_text(errors="replace")
        except OSError:
            continue
        if rf.REFINED_FIELD not in s:
            continue                       # no refinement anywhere in it
        try:
            m = json.loads(s)
        except ValueError:
            continue
        docs += 1
        for o in m.get("objects", []):
            st = rf.refinement_state(_O(o))
            if st["state"] == rf.NONE:
                continue
            tally[st["state"]] += 1
            if st["state"] != rf.VERIFIED:
                bad.append({"doc": d.name, "obj": o.get("id"),
                            "type": o.get("type"), **st})
        print("\r%d documents with a refinement, %d non-verified"
              % (docs, len(bad)), end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"documents": docs, "by_state": dict(tally), "offenders": bad},
              sys.stdout, indent=1, ensure_ascii=False)
