#!/usr/bin/env python3
"""710 — re-measure the WHOLE library after 709b moved geometry_sha256.

709b changes `row` and the source-cell escaping, both of which decide where
text falls on the page. `report_tex.geometry_signature` is a hash over the
AST of the functions that lay out the report, and `row` is one of them, so
every stamp on disk (329543be18ef...) now disagrees with the code that would
build the report (6cc2aeeb4701...). `inkreport.fresh_ink`'s sixth content
question sees that and refuses to resume — correctly. Every stored
measurement is stale BY DESIGN, and this re-measures them.

Ordering matters and is the lesson of 708/709: `report.ink.json` is removed
before the measure step. Without that, `fresh_ink` can resume and the step
returns rc=0 having done nothing — a rework that reports success and changes
no number. (Here the geometry question would catch it anyway; the removal is
belt and braces, and it makes the run independent of that one check.)

Usage: remeasure_710.py <lane> <slug>...
"""
import collections
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LIB = Path("/home/wkolbe/pdfdrill-library")
REPO = Path("/home/wkolbe/MX/PDFDRILL")
ENV = {**os.environ, "PYTHONPATH": str(REPO / "src"),
       "PDFDRILL_NO_PREFLIGHT": "1", "PYTHONDONTWRITEBYTECODE": "1"}

lane = sys.argv[1]
# 710 — SLUGS COME FROM A FILE, ONE PER LINE, NEVER FROM THE SHELL.
# `remeasure_710.py 1 $(cat lane1.txt)` word-splits: 18 of this library's
# folder names contain spaces ("Numerical Linear Algebra and Matrix
# Factorizations (Tom Lyche) (Z-Library)", "main (2)"), so 87 lines arrived
# as 118 arguments and the lanes spent their time skipping fragments like
# "0049". Nothing was damaged -- unresolvable names are skipped -- but
# nothing was measured either, and the logs looked busy while doing it.
if sys.argv[2] == "--from-file":
    slugs = [ln.rstrip("\n") for ln in
             Path(sys.argv[3]).read_text(encoding="utf-8").splitlines() if ln.strip()]
else:
    slugs = sys.argv[2:]
failed, empty, classes = [], [], collections.Counter()
t_start = time.time()

for n, slug in enumerate(slugs, 1):
    doc = LIB / slug
    pdf = doc / (slug + ".pdf")
    if not pdf.is_file():
        # The author's PDF, never one we generated. 703's lesson: a batch
        # that globs *.pdf in a document folder drills report.pdf,
        # residuals.pdf and evidence-*.pdf -- 288 of 506 entries, on a run
        # the user caught. `datikz-fixture` carries a stored measurement and
        # NO pdf at all; it is skipped by name here rather than failing a lane.
        cands = [p for p in doc.glob("*.pdf")
                 if p.name not in ("report.pdf", "residuals.pdf")
                 and not p.name.startswith("evidence-")]
        if not cands:
            print("%-40s no author PDF — skipped" % slug[:40], flush=True)
            empty.append(slug)
            continue
        if len(cands) > 1:
            print("%-40s AMBIGUOUS (%d pdfs) — skipped: %s"
                  % (slug[:40], len(cands), [p.name for p in cands][:3]), flush=True)
            failed.append((slug, "ambiguous-pdf"))
            continue
        pdf = cands[0]
    ink = doc / "report.ink.json"
    if ink.is_file():
        ink.unlink()
    ok = True
    for name, args in [("measure", ["residuals", str(pdf), "--measure", "--pdf"]),
                       ("evidence", ["evidence", str(pdf), "--all-kinds", "--pdf"]),
                       ("report", ["report", str(pdf)])]:
        t0 = time.time()
        p = subprocess.run([sys.executable, "-m", "pdfdrill", *args],
                           capture_output=True, text=True, env=ENV, cwd=str(REPO))
        if p.returncode != 0:
            tail = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-1:]
            print("%-40s %-9s rc=%d %6.1fs | %s"
                  % (slug[:40], name, p.returncode, time.time() - t0,
                     (tail[0] if tail else "")[:90]), flush=True)
            failed.append((slug, name))
            ok = False
            break
    if not ok:
        continue
    if not ink.is_file():
        # no equation rows to measure: an EMPTY population, not a failure.
        # inkdrill's own warning: an all-zero pair scores distance 0 and reads
        # CLEAN -- "a clean score from a comparison that did not happen".
        empty.append(slug)
        print("%-40s (no measurable rows)  [%d/%d]" % (slug[:40], n, len(slugs)), flush=True)
        continue
    try:
        rows = json.loads(ink.read_text()).get("rows", [])
    except (OSError, ValueError) as exc:
        failed.append((slug, "readback"))
        print("%-40s READBACK %s" % (slug[:40], exc), flush=True)
        continue
    c = collections.Counter(r.get("flag") for r in rows)
    classes.update(c)
    print("%-40s %3d rows %-46s [%d/%d  %.0fs]"
          % (slug[:40], len(rows), dict(c), n, len(slugs), time.time() - t_start),
          flush=True)

print("\n===== lane %s: %d documents, %d failed, %d with no measurable rows, %.0f min"
      % (lane, len(slugs), len(failed), len(empty), (time.time() - t_start) / 60), flush=True)
for s, step in failed:
    print("   FAILED %s at %s" % (s, step), flush=True)
print("classes: %s" % dict(classes), flush=True)
json.dump({"lane": lane, "classes": dict(classes), "failed": failed,
           "empty": empty, "documents": len(slugs),
           "seconds": round(time.time() - t_start)},
          open(str(LIB / "out" / ("710_%s.json" % lane)), "w"), indent=1)
