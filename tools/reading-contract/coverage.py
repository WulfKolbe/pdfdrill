#!/usr/bin/env python3
"""T-0107 item 4 — for each measured MathPix type, WHO READS IT.

Grep-based and deliberately crude: it reports the modules that mention the
type name as a string literal. A mention is evidence that something looks at
the type, not proof that the type is handled correctly -- so the contract
says "read by <modules>" or "no reader found", and the coverage TEST (which
is the gate) only requires that every type is either claimed by a module or
listed as dropped with a reason.
"""
import json, re, subprocess
from pathlib import Path

import sys
#: run from the repository root; the measurement directory is an argument.
ROOT = Path.cwd()
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "work/run-files/t0107")
m = json.loads((OUT / "measured.json").read_text(encoding="utf-8"))
#: MathPix is measured in two API-vintage classes; coverage is about the
#: VOCABULARY, so it runs over their union. (It read a single "mathpix" class
#: until the coordinator's review of 7a6dc1dc showed that class held 34 files
#: of ours -- which is also why `caption`, `equation`, `formula` and
#: `rotated_text` are no longer in this list: no MathPix file carries them.)
_pp = m["per_producer"]
types = sorted({t for cls in ("mathpix-classic", "mathpix-newer")
                for t, n, d in _pp.get(cls, {}).get("types", [])})

rows = []
for t in types:
    if t.startswith("<"):
        continue
    try:
        res = subprocess.run(
            ["grep", "-rl", '"%s"' % t, "src/"],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        hits = [l for l in res.stdout.splitlines() if l.endswith(".py")]
        res2 = subprocess.run(
            ["grep", "-rl", "'%s'" % t, "src/"],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        hits += [l for l in res2.stdout.splitlines() if l.endswith(".py")]
    except subprocess.TimeoutExpired:
        hits = ["<grep timed out>"]
    hits = sorted(set(hits))
    rows.append({"type": t, "readers": hits})

(OUT / "coverage.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
unread = [r["type"] for r in rows if not r["readers"]]
print("types: %d   with at least one reader: %d   with none: %d"
      % (len(rows), len(rows) - len(unread), len(unread)))
print("no reader found:", unread)
for r in rows:
    print("  %-30s %s" % (r["type"], ", ".join(
        p.replace("src/", "") for p in r["readers"][:4]) or "-- none --"))
