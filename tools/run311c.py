#!/usr/bin/env python3
"""311c — measure the ink for the 311 scope, cheapest document first.

Ordered by report page count ASCENDING and resumable per document, because the
cost is dominated by a handful of books: five reports hold 3,641 of the 7,242
pages. Cheapest-first means most documents are done early and the run can be
stopped at any point having finished the many rather than one of the few.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
LIB = pathlib.Path.home() / "pdfdrill-library"
OUT = ROOT / "out" / "311c.jsonl"
WORK = pathlib.Path("/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/"
                    "ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da/scratchpad/w311c")


def main():
    from pdfdrill import inkmeasure as im
    from pdfdrill import doclock
    need = json.loads((ROOT / "out" / "311.need.json").read_text())
    need.sort(key=lambda r: r["pages"])
    done = set()
    if OUT.is_file():
        for ln in OUT.read_text(errors="replace").splitlines():
            try:
                done.add(json.loads(ln)["doc"])
            except Exception:
                pass
    todo = [r for r in need if r["doc"] not in done]
    print("scope: %d documents, %d report pages"
          % (len(todo), sum(r["pages"] for r in todo)), flush=True)
    fh = OUT.open("a", encoding="utf-8")
    env = dict(os.environ, PDFDRILL_NO_PREFLIGHT="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"))
    for i, r in enumerate(todo, 1):
        d = LIB / r["doc"]
        rep, tsv = d / "report.pdf", d / "report.compare.tsv"
        rec = {"doc": r["doc"], "pages": r["pages"]}
        t0 = time.time()
        if tsv.is_file():
            rec["outcome"] = "already"
        else:
            try:
                pdfs = [p for p in d.glob("*.pdf") if p.name != "report.pdf"]
                with doclock.hold(pdfs[0] if pdfs else rep, "inkmeasure"):
                    rows = im.measure(rep, WORK / r["doc"][:40])
                    tsv.write_text(im.to_tsv(rows), encoding="utf-8")
                rec.update(outcome="measured", rows=len(rows))
            except doclock.DocumentBusy:
                rec["outcome"] = "locked"
            except Exception as exc:
                rec.update(outcome="refused",
                           error="%s: %s" % (type(exc).__name__, str(exc)[:150]))
        if rec["outcome"] in ("measured", "already"):
            p = subprocess.run([sys.executable, "-m", "pdfdrill", "inkconvert",
                                str([q for q in d.glob("*.pdf")
                                     if q.name != "report.pdf"][0])],
                               cwd=ROOT, env=env, capture_output=True,
                               text=True, timeout=900)
            low = (p.stdout or "").lower()
            rec["convert"] = ("converted" if "report.ink.json:" in low else
                              "refused" if "refusing" in low else
                              "already" if "already exists" in low else "other")
        rec["seconds"] = round(time.time() - t0, 1)
        if rec["outcome"] != "locked":            # retry a lock on a later pass
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
        print("[%3d/%3d] %-38s %3dp %-9s %-9s %.0fs"
              % (i, len(todo), r["doc"][:38], r["pages"], rec["outcome"],
                 rec.get("convert", "-"), rec["seconds"]), flush=True)
    fh.close()
    print("PASS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
