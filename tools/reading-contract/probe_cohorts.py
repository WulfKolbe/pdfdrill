#!/usr/bin/env python3
"""Who really wrote the pages my first measurement filed under "mathpix"?

Two cohorts, named by the coordinator's T-0107 review:
  A  803 pages carrying px_per_pt / source / diagrams / fills / links
  B  3,411 pages carrying parse_status / fallback_count / page_confidence

For each, report the page-level `source` value actually present and the
document it came from. Read only.
"""
import json, sys, time
from collections import Counter, defaultdict
from pathlib import Path

LIB = Path.home() / "pdfdrill-library"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "work/run-files/t0107")
MAX_BYTES = 1_200_000_000
SIG_A = {"px_per_pt", "diagrams", "fills", "links"}
SIG_B = {"parse_status", "fallback_count", "page_confidence"}

a_src = Counter(); b_src = Counter()
a_files = defaultdict(set); b_files = defaultdict(set)
a_pages = 0; b_pages = 0
b_status = Counter(); b_top = Counter()
a_top = Counter()
t0 = time.time()
paths = sorted(LIB.glob("*/*.lines.json"))
for i, p in enumerate(paths, 1):
    try:
        if p.stat().st_size > MAX_BYTES:
            continue
        doc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:                                        # noqa: BLE001
        continue
    pages = doc.get("pages") if isinstance(doc, dict) else doc
    if not isinstance(pages, list):
        continue
    top = (doc.get("source") if isinstance(doc, dict) else None) or "<none>"
    for pg in pages:
        if not isinstance(pg, dict):
            continue
        keys = set(pg)
        if keys & SIG_A:
            a_pages += 1
            a_src["page=%s top=%s" % (pg.get("source"), top)] += 1
            a_top[top] += 1
            a_files["page=%s top=%s" % (pg.get("source"), top)].add(p.parent.name)
        if keys & SIG_B:
            b_pages += 1
            b_src["page=%s top=%s" % (pg.get("source"), top)] += 1
            b_top[top] += 1
            b_status[str(pg.get("parse_status"))] += 1
            b_files["page=%s top=%s" % (pg.get("source"), top)].add(p.parent.name)
    if i % 500 == 0:
        print("  %d/%d %.0fs" % (i, len(paths), time.time() - t0), flush=True)

res = {
 "cohort_A_px_per_pt": {"pages": a_pages, "page_source": a_src.most_common(),
                        "top_level_source": a_top.most_common(),
                        "docs_n": {k: len(v) for k, v in a_files.items()},
                        "docs": {k: sorted(v)[:60] for k, v in a_files.items()}},
 "cohort_B_parse_status": {"pages": b_pages, "page_source": b_src.most_common(),
                        "top_level_source": b_top.most_common(),
                        "parse_status_values": b_status.most_common(),
                        "docs_n": {k: len(v) for k, v in b_files.items()},
                        "docs": {k: sorted(v)[:60] for k, v in b_files.items()}},
}
(OUT / "cohorts.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps(res, indent=1, ensure_ascii=False)[:3000])
print("wrote %s in %.0fs" % (OUT / "cohorts.json", time.time() - t0))
