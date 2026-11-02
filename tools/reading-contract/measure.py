#!/usr/bin/env python3
"""T-0107 — measure the library's lines.json files, SEPARATED BY PRODUCER.

The population trap this task already records twice (the .tex font census,
and the coordinator's own note): the library holds 5,460 *.lines.json
totalling 6.3 GB, and only a minority are genuine MathPix readings. The rest
are pdfdrill's own glyph-reader output and other readers' look-alikes,
written in the same shape. Counting them together produces a "MathPix
contract" describing our own output.

So every count here is reported per producer, and the producer is taken from
the file, never guessed.

THE FIRST VERSION OF THIS RULE WAS WRONG, and the coordinator's T-0107 review
caught it. It read `source` only at the TOP level and otherwise trusted
`is_printed`/`confidence` on lines as "MathPix markers". Both halves fail:

  * `to_lines_json` (docmodel_six) writes `is_printed: True`, `confidence`,
    `confidence_rate`, `cnt` and `conversion_output` ON PURPOSE — its comment
    says "MathPix's own page keys first, so a consumer written against their
    export reads ours unchanged". So the markers fire on our own output BY
    DESIGN and prove nothing.
  * defect 846 added the top-level `source`; before it, our writer set `source`
    on each PAGE only. 803 pages across 34 documents are in that shape, and the
    old rule filed every one of them under "mathpix". The defect-846 comment in
    docmodel_six records inkdrill hitting this exact failure ("every reading of
    ours looked like MathPix to it"); this measurement repeated it.

The rule now reads, in order:

  1. top-level `source`                     -> reader:<source>
  2. page-level `source` on any page        -> reader:<source> (pre-846/merged)
  3. a writer signature our readers emit and MathPix does not
     (page: px_per_pt, diagrams, fills, links;
      line: gaps, rules, deferred_glyphs, complete, _i)
                                            -> reader:<the signature's owner>
  4. gemma_reader's tell: `furniture_retyped` present, or `image_id` == ""
                                            -> reader:gemma
  5. MathPix proper, split by API vintage:
       page_confidence a dict + real image_id + line layout_confidence
                                            -> mathpix (newer API)
       otherwise                            -> mathpix (classic)
  6. nothing declared                       -> unknown-shape

Note on 4/5: `parse_status`, `fallback_count` and `page_confidence` are
GENUINE MathPix fields of the newer API. A grep says our gemma_reader also
writes those names, but a grep names who CAN write a field, never who DID —
gemma_reader mimics MathPix's shape, as everything here does. The files decide
it: MathPix sets a real `image_id` UUID and a `page_confidence` dict carrying
`method: "prototype_min_v1"`; gemma_reader sets `image_id` to "" ,
`page_confidence` to None, and always adds `furniture_retyped`.

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
evidence = defaultdict(Counter)
#: (producer, rule) -> pages / lines / files, so §1a's "what moved" is a
#: measurement and not a subtraction of two runs.
by_rule_pages = Counter()
by_rule_lines = Counter()
by_rule_files = defaultdict(list)

#: Page-level keys only OUR writers emit, and the writer that emits them.
#: Established by reading the writers on 2026-11-02, not by assumption:
#: docmodel_six.to_lines_json lines 4444-4455.
OURS_PAGE = {"px_per_pt": "pdfminer-docmodel", "diagrams": "pdfminer-docmodel",
             "fills": "pdfminer-docmodel", "links": "pdfminer-docmodel"}
#: Line-level keys only our writers emit (docmodel_six 4485-4524).
OURS_LINE = {"gaps": "pdfminer-docmodel", "rules": "pdfminer-docmodel",
             "deferred_glyphs": "pdfminer-docmodel",
             "complete": "pdfminer-docmodel", "_i": "pdfminer-docmodel"}



def rel(path) -> str:
    """The library-relative path, safe to put in JSON.

    Some library folder names carry bytes that are not valid UTF-8; Python
    surfaces them as lone surrogates, which `json.dumps` accepts and
    `write_text(encoding="utf-8")` then refuses -- leaving a 0-byte
    measured.json and a coverage run that dies on it. Replacing them here
    keeps the name readable and the file writable.
    """
    return (str(path.relative_to(LIB))
            .encode("utf-8", "replace").decode("utf-8"))


def producer_of(doc, pages):
    """Return the producer class, and the evidence that decided it."""
    # 1. the top-level declaration (defect 846 put it there)
    src = doc.get("source") if isinstance(doc, dict) else None
    if src:
        return "reader:%s" % src, "top-level source"
    # 2. a page-level declaration: our pre-846 shape, and the only place a
    #    merged reading can say it carries pages from two readers
    page_srcs = {pg.get("source") for pg in pages
                 if isinstance(pg, dict) and pg.get("source")}
    if len(page_srcs) == 1:
        return "reader:%s" % page_srcs.pop(), "page-level source"
    if len(page_srcs) > 1:
        return "merged:%s" % "+".join(sorted(page_srcs)), "page-level source (several)"
    # 3./4. signatures, page then line
    gemma = False
    for pg in pages:
        if not isinstance(pg, dict):
            continue
        if "furniture_retyped" in pg or pg.get("image_id") == "":
            gemma = True
        for k, owner in OURS_PAGE.items():
            if k in pg:
                return "reader:%s" % owner, "page field %s" % k
        for ln in (pg.get("lines") or [])[:200]:
            if not isinstance(ln, dict):
                continue
            for k, owner in OURS_LINE.items():
                if k in ln:
                    return "reader:%s" % owner, "line field %s" % k
    if gemma:
        return "reader:gemma", 'image_id "" / furniture_retyped'
    # 5. MathPix proper — split by API vintage, because the newer one carries
    #    fields the contract must not attribute to the classic export
    newer = any(isinstance(pg, dict) and isinstance(pg.get("page_confidence"), dict)
                for pg in pages)
    marked = any(("is_printed" in ln or "confidence" in ln)
                 for pg in pages[:3] if isinstance(pg, dict)
                 for ln in (pg.get("lines") or [])[:50] if isinstance(ln, dict))
    if newer:
        return "mathpix-newer", "page_confidence dict"
    if marked:
        return "mathpix-classic", "is_printed/confidence, no reader signature"
    # 6. nothing declared, nothing recognisable
    return "unknown-shape", "no declaration, no marker"

def main() -> None:
    global t0, paths, i, p, doc, pages, prod, why, doc_name, by_id, result
    t0 = time.time()
    paths = sorted(LIB.glob("*/*.lines.json"))
    print("files: %d" % len(paths), flush=True)
    for i, p in enumerate(paths, 1):
        try:
            if p.stat().st_size > MAX_BYTES:
                skipped.append([rel(p), p.stat().st_size])
                continue
            with p.open(encoding="utf-8", errors="replace") as fh:
                doc = json.load(fh)
        except Exception as e:                                   # noqa: BLE001
            unreadable.append([rel(p), "%s: %s" % (type(e).__name__, e)])
            continue
        pages = doc.get("pages") if isinstance(doc, dict) else doc
        if not isinstance(pages, list):
            unreadable.append([rel(p), "no pages list"])
            continue
        prod, why = producer_of(doc, pages)
        evidence[prod][why] += 1
        rule_key = "%s|%s" % (prod, why)
        by_rule_files[rule_key].append(rel(p))
        _np = sum(1 for pg in pages if isinstance(pg, dict))
        _nl = sum(len(pg.get("lines") or []) for pg in pages if isinstance(pg, dict))
        by_rule_pages[rule_key] += _np
        by_rule_lines[rule_key] += _nl
        producers[prod] += 1
        files_by_producer[prod].append(rel(p))
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
        # Per classification rule: how many files, pages and lines each rule
        # accounts for, and which files. §1a reads this directly, so "what
        # moved out of MathPix" is measured, never a subtraction of two runs.
        "by_rule": {k: {"files_n": len(v), "pages": by_rule_pages[k],
                        "lines": by_rule_lines[k],
                        "files": sorted(v) if len(v) <= 200 else sorted(v)[:200],
                        "files_truncated": len(v) > 200}
                    for k, v in sorted(by_rule_files.items())},
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
                # WHY each file landed in this class — the rule is
                # auditable only if it says what it read.
                "classified_by": evidence[prod].most_common(),
            }
            for prod in producers
        },
    }
    # encode first: write_text would create the file and then fail on a bad
    # byte, leaving 0 bytes behind for the next tool to choke on.
    _blob = json.dumps(result, indent=1, ensure_ascii=False).encode("utf-8",
                                                                    "replace")
    (OUT / "measured.json").write_bytes(_blob)
    print("producers:", producers.most_common())
    print("wrote %s in %.0fs" % (OUT / "measured.json", time.time() - t0))


if __name__ == "__main__":
    main()
