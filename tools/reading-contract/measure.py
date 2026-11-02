#!/usr/bin/env python3
"""T-0107 — measure the library's lines.json files, SEPARATED BY PRODUCER.

The population trap this task already records twice (the .tex font census,
and the coordinator's own note): the library holds 5,460 *.lines.json
totalling 6.3 GB, and only a minority are genuine MathPix readings. The rest
are pdfdrill's own glyph-reader output and other readers' look-alikes,
written in the same shape. Counting them together produces a "MathPix
contract" describing our own output.

So every count here is reported per producer, and the producer is taken from
the file, never guessed:

  source            the top-level field a non-MathPix writer sets
                    ("pdfminer-chars" for pdfdrill's glyph reader)
  mathpix_markers   is_printed / confidence on lines, which MathPix sets and
                    our readers do not

Read only. Nothing in the library is written.
"""
import json, os, sys, time
from collections import Counter, defaultdict
from pathlib import Path

LIB = Path.home() / "pdfdrill-library"
import sys
#: where the measurement lands; git-ignored by default, and an argument so a
#: reviewer can write it anywhere without editing the script.
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "work/run-files/t0107")
OUT.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 1_200_000_000

producers = Counter()
files_by_producer = defaultdict(list)
type_lines = defaultdict(Counter)        # producer -> type -> lines
type_docs = defaultdict(lambda: defaultdict(set))
line_field_lines = defaultdict(Counter)  # producer -> field -> lines
line_total = Counter()
page_field_pages = defaultdict(Counter)
page_total = Counter()
file_field_files = defaultdict(Counter)
subtypes = defaultdict(Counter)
parent_of = defaultdict(Counter)         # producer -> "parent>child"
unreadable = []
skipped = []

def producer_of(doc, pages):
    src = doc.get("source") if isinstance(doc, dict) else None
    marked = False
    for pg in pages[:3]:
        for ln in (pg.get("lines") or [])[:50]:
            if "is_printed" in ln or "confidence" in ln:
                marked = True
                break
        if marked:
            break
    if src:
        return "reader:%s" % src
    return "mathpix" if marked else "unknown-shape"

t0 = time.time()
paths = sorted(LIB.glob("*/*.lines.json"))
print("files: %d" % len(paths), flush=True)
for i, p in enumerate(paths, 1):
    try:
        if p.stat().st_size > MAX_BYTES:
            skipped.append([str(p.relative_to(LIB)), p.stat().st_size])
            continue
        with p.open(encoding="utf-8", errors="replace") as fh:
            doc = json.load(fh)
    except Exception as e:                                   # noqa: BLE001
        unreadable.append([str(p.relative_to(LIB)), "%s: %s" % (type(e).__name__, e)])
        continue
    pages = doc.get("pages") if isinstance(doc, dict) else doc
    if not isinstance(pages, list):
        unreadable.append([str(p.relative_to(LIB)), "no pages list"])
        continue
    prod = producer_of(doc, pages)
    producers[prod] += 1
    files_by_producer[prod].append(str(p.relative_to(LIB)))
    doc_name = p.parent.name
    if isinstance(doc, dict):
        for k in doc:
            if k != "pages":
                file_field_files[prod][k] += 1
    by_id = {}
    for pg in pages:
        if not isinstance(pg, dict):
            continue
        page_total[prod] += 1
        for k in pg:
            if k != "lines":
                page_field_pages[prod][k] += 1
        for ln in (pg.get("lines") or []):
            if not isinstance(ln, dict):
                continue
            line_total[prod] += 1
            t = ln.get("type") or "<no type>"
            type_lines[prod][t] += 1
            type_docs[prod][t].add(doc_name)
            for k in ln:
                line_field_lines[prod][k] += 1
            st = ln.get("subtype")
            if st:
                subtypes[prod]["%s/%s" % (t, st)] += 1
            if ln.get("id") is not None:
                by_id[ln["id"]] = t
    for pg in pages:
        if not isinstance(pg, dict):
            continue
        for ln in (pg.get("lines") or []):
            if isinstance(ln, dict) and ln.get("parent_id") in by_id:
                parent_of[prod]["%s>%s" % (by_id[ln["parent_id"]],
                                           ln.get("type") or "<no type>")] += 1
    if i % 250 == 0:
        print("  %d/%d  %.0fs" % (i, len(paths), time.time() - t0), flush=True)

result = {
    "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "library": str(LIB),
    "files_found": len(paths),
    "files_skipped_too_big": skipped,
    "files_unreadable": unreadable,
    "producers": producers.most_common(),
    "per_producer": {
        prod: {
            "files_n": producers[prod],
            "pages": page_total[prod],
            "lines": line_total[prod],
            "types": [[t, n, len(type_docs[prod][t])]
                      for t, n in type_lines[prod].most_common()],
            "line_fields": [[k, n, round(100.0 * n / max(1, line_total[prod]), 1)]
                            for k, n in line_field_lines[prod].most_common()],
            "page_fields": [[k, n, round(100.0 * n / max(1, page_total[prod]), 1)]
                            for k, n in page_field_pages[prod].most_common()],
            "file_fields": file_field_files[prod].most_common(),
            "subtypes": subtypes[prod].most_common(),
            "parent_child": parent_of[prod].most_common(),
            # The FILE LIST, for every producer small enough to name. A
            # count cannot be checked; a list can. The two large producers
            # are capped so the record stays readable.
            "files": files_by_producer[prod] if producers[prod] <= 100
                     else files_by_producer[prod][:50],
            "files_truncated": producers[prod] > 100,
        }
        for prod in producers
    },
}
(OUT / "measured.json").write_text(json.dumps(result, indent=1, ensure_ascii=False),
                                   encoding="utf-8")
print("producers:", producers.most_common())
print("wrote %s in %.0fs" % (OUT / "measured.json", time.time() - t0))
