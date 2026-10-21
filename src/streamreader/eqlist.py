# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Our display equations held against the equation lists, one by one.

`~/pdfdrill-library/eqlists` lists display equations across the corpus:
where each one stands on its page (250-dpi pixels), MathPix's LaTeX for it,
pdfdrill's and psred's own readings, and a crop of the page. This tool
reads the same pages with pdf2mmd2 and writes, for every listed equation,
what we have at that place:

  found    one `math` line of ours on the box
  split    several `math` lines of ours inside the box
  merged   one `math` line of ours, much larger than the box
  partial  one `math` line of ours covering little of the box
  missed   no `math` line of ours there

and how close our LaTeX is to MathPix's, in formula tokens. pdfdrill's
and psred's readings of the same rows are scored the same way.

Output goes to --out (never into the library):
  records.jsonl   one row per equation
  summary.json    counts and scores, per document and pooled
  table.html      the rows, worst first, with the crop beside them;
                  a missed row shows the lines we have there and the
                  test that dropped the display
  table-<status>.html   the same for the rows of one status
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import signal
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import bboxlayout, compare, glyphs, refine
from .modules import formulas

FOUND_IOU = 0.5      # as the lists' own join against MathPix
INSIDE = 0.5         # share of a line of ours that must lie in the box
MERGED = 2.0         # our line this many times the box's area: a merge
READERS = ("ours", "pdfdrill", "psred")
DOC_SECONDS = 600
PIECE_PAGES = 100           # listed pages one worker reads in one go


# ---------------------------------------------------------------- the lists

def _strip(latex: str | None) -> str:
    s = (latex or "").strip()
    if s.startswith("\\[") and s.endswith("\\]"):
        s = s[2:-2].strip()
    return s


def load_rows(lists: Path) -> dict[str, list[dict]]:
    """{document: [row]} from the MathPix-joined list, each row with the
    other readers' LaTeX for the same label where the lists have it."""
    lists = Path(lists)
    csv.field_size_limit(1 << 30)

    def table(name, delimiter=","):
        path = lists / name
        if not path.is_file():
            return []
        with open(path, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f, delimiter=delimiter)

    pdfdrill = {(r["document"], r["label"]): r["latex"]
                for r in table("corpus-display.rows.csv")}
    psred = {(r["document"], r["label"]): _strip(r["psred_latex"])
             for r in table("grade-a.psred.tsv", "\t")
             if r.get("psred_latex")}
    out: dict[str, list[dict]] = {}
    for r in table("corpus-display-mathpix.rows.csv"):
        key = (r["document"], r["label"])
        out.setdefault(r["document"], []).append(dict(
            document=r["document"], label=r["label"], page=int(r["page"]),
            box=tuple(int(r[k]) for k in ("px_x", "px_y", "px_w", "px_h")),
            number=r.get("number") or None, pdf=r["pdf_path"],
            mathpix=r["latex"], pdfdrill=pdfdrill.get(key),
            psred=psred.get(key),
            crop=str(lists / f"{r['document']}-crops"
                     / f"{r['document']}-{r['label']}.jpg")))
    return out


def pick(docs: list[str], count: int | None, named: list[str]) -> list[str]:
    """The named documents, or `count` spread evenly through the list -
    its first documents would be one decade and one layout."""
    if named:
        return [d for d in named if d in set(docs)]
    if not count or count >= len(docs):
        return list(docs)
    return [docs[i * len(docs) // count] for i in range(count)]


# ------------------------------------------------------------- one equation

def _rect(ln: dict) -> tuple[int, int, int, int]:
    r = ln["region"]
    return (r["top_left_x"], r["top_left_y"],
            r["top_left_x"] + r["width"], r["top_left_y"] + r["height"])


def _area(b) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _cut(a, b) -> int:
    return _area((max(a[0], b[0]), max(a[1], b[1]),
                  min(a[2], b[2]), min(a[3], b[3])))


def place(box: tuple[int, int, int, int], page: dict) -> dict:
    """What we have at `box` (x, y, width, height) on `page`."""
    truth = (box[0], box[1], box[0] + box[2], box[1] + box[3])
    there, maths, texts = [], [], []
    for ln in page["lines"]:
        if "children_ids" in ln:
            continue
        b = _rect(ln)
        cut = _cut(truth, b)
        if not cut or not _area(b):
            continue
        if ln["type"] != "math":
            if cut >= INSIDE * _area(b):
                there.append(ln["type"])
                texts.append((b[1], b[0], ln.get("text", "")))
            continue
        if cut >= INSIDE * _area(b) or cut >= INSIDE * _area(truth):
            maths.append((b, ln))
    if not maths:
        return dict(status="missed", latex="", iou=0.0, pieces=0,
                    there=sorted(set(there)),
                    text_there="\n".join(t for _, _, t in sorted(texts)))
    maths.sort(key=lambda t: (t[0][1], t[0][0]))
    hull = (min(b[0] for b, _ in maths), min(b[1] for b, _ in maths),
            max(b[2] for b, _ in maths), max(b[3] for b, _ in maths))
    cut = _cut(truth, hull)
    iou = cut / (_area(truth) + _area(hull) - cut)
    if len(maths) > 1:
        status = "split"
    elif iou >= FOUND_IOU:
        status = "found"
    elif _area(hull) >= MERGED * _area(truth):
        status = "merged"
    else:
        status = "partial"
    return dict(status=status, iou=round(iou, 3), pieces=len(maths),
                latex=" \\\\ ".join(_strip(ln["text"]) for _, ln in maths),
                there=sorted(set(there)))


# the tests that take a row of formulas for the cells of a table
_TABLE_TESTS = ("row-prose", "row-stacked", "walled", "cells")


def why(box: tuple[int, int, int, int], trace: list) -> str:
    """Which tests of the formula module dropped the display at `box`
    (`formulas.TRACE`): the table test that took its lines for cells and
    the test that dropped the band covering most of the box, joined by
    ' + ' when both did. '' when no candidate stood there."""
    truth = (box[0], box[1], box[0] + box[2], box[1] + box[3])
    hits = [(_cut(truth, b), reason) for b, reason in trace
            if _cut(truth, b)]
    table = next((t for t in _TABLE_TESTS if any(r == t for _, r in hits)),
                 None)
    band = max((h for h in hits if h[1] not in _TABLE_TESTS), default=None)
    return " + ".join(r for r in (table, band and band[1]) if r)


_END = {".", ",", ";", ":"}


def _tokens(latex: str) -> list[str]:
    t = compare.math_tokens(latex or "")
    while t and t[-1] in _END:
        t.pop()
    return t


def score(latex: str, reference: str) -> dict:
    """Token agreement of a reading with the reference: F1 over the bag
    of tokens, and whether the token sequences are the same."""
    a, b = _tokens(latex), _tokens(reference)
    f1 = compare._f1(compare._overlap(a, b), len(a), len(b))
    return dict(f1=0.0 if f1 is None else f1, same=bool(b) and a == b)


# ------------------------------------------------------------- one document

class _Timeout(Exception):
    pass


def _alarm(_signum, _frame):
    raise _Timeout()


def read_document(rows: list[dict]) -> list[dict]:
    """Records for one document's rows. Runs in a worker process."""
    pdf = Path(rows[0]["pdf"])
    doc = rows[0]["document"]
    wanted = sorted({r["page"] for r in rows})
    pages: dict[int, dict] = {}
    traces: dict[int, list] = {}
    error = None
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(DOC_SECONDS)
    t = time.perf_counter()
    try:
        first, last = wanted[0], wanted[-1]
        warm = {p["page"]: p
                for p in bboxlayout.read_pages_tsv(pdf, first, last, doc)}
        for rec in glyphs.read_pages(pdf, first, last, only=set(wanted)):
            page = warm.get(rec.page)
            if page is not None and rec.page in wanted:
                formulas.TRACE = traces[rec.page] = []
                refine.refine_page(page, rec)
                pages[rec.page] = page
    except _Timeout:
        error = f"timeout after {DOC_SECONDS} s"
    except Exception as e:                               # noqa: BLE001
        error = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        signal.alarm(0)
        formulas.TRACE = None           # the next caller in this process starts clean
    seconds = time.perf_counter() - t
    out = []
    for r in rows:
        page = pages.get(r["page"])
        got = (place(r["box"], page) if page is not None else
               dict(status="unread", latex="", iou=0.0, pieces=0, there=[]))
        rec = dict(document=doc, label=r["label"], page=r["page"],
                   box=list(r["box"]), number=r["number"],
                   status=got["status"], iou=got["iou"],
                   pieces=got["pieces"], there=got["there"],
                   mathpix=r["mathpix"], ours=got["latex"],
                   pdfdrill=r["pdfdrill"], psred=r["psred"], crop=r["crop"])
        if got["status"] == "missed":
            rec["text_there"] = got.get("text_there", "")
            rec["why"] = why(r["box"], traces.get(r["page"], []))
        for reader in READERS:
            if rec[reader] is not None:
                s = score(rec[reader], r["mathpix"])
                rec[f"f1_{reader}"], rec[f"same_{reader}"] = s["f1"], s["same"]
        if error and page is None:
            rec["error"] = error
        out.append(rec)
    if out:
        out[0]["seconds"] = round(seconds, 2)
        out[0]["pages_read"] = len(pages)
    return out


def pieces(rows: list[dict], size: int) -> list[list[dict]]:
    """The rows of one document in pieces of at most `size` listed pages,
    in page order; the rows of a page stay together."""
    wanted = sorted({r["page"] for r in rows})
    if len(wanted) <= size:
        return [rows]
    part = {p: n // size for n, p in enumerate(wanted)}
    out: list[list[dict]] = [[] for _ in range(part[wanted[-1]] + 1)]
    for r in rows:
        out[part[r["page"]]].append(r)
    return out


def work(rows: dict[str, list[dict]], docs: list[str],
         size: int) -> list[tuple[str, int, list[dict]]]:
    """(document, piece number, rows) for every piece, most pages first:
    the long pieces start at once and the short ones fill the gaps."""
    out = [(d, n, part) for d in docs
           for n, part in enumerate(pieces(rows[d], size))]
    out.sort(key=lambda w: -len({r["page"] for r in w[2]}))
    return out


def gathered(rows: list[dict], read: list[list[dict]]) -> list[dict]:
    """The records of a document's pieces as `read_document` gives them
    for the whole: in the order of its rows, seconds and pages summed."""
    seconds = sum(recs[0].pop("seconds", 0) for recs in read if recs)
    pages = sum(recs[0].pop("pages_read", 0) for recs in read if recs)
    by_label = {r["label"]: r for recs in read for r in recs}
    out = [by_label[r["label"]] for r in rows]
    if out:
        first = out[0]
        out[0] = dict(first, seconds=round(seconds, 2), pages_read=pages)
    return out


# ------------------------------------------------------------------ summary

def summarise(records: list[dict]) -> dict:
    readers = {}
    for reader in READERS:
        have = [r for r in records if r.get(reader) is not None]
        scores = [score(r[reader], r["mathpix"]) for r in have]
        readers[reader] = dict(
            rows=len(have),
            same=sum(s["same"] for s in scores),
            f1_mean=round(sum(s["f1"] for s in scores) / len(scores), 4)
            if scores else None)
    return dict(equations=len(records),
                status=dict(sorted(Counter(r["status"]
                                           for r in records).items())),
                missed_why=dict(Counter(
                    r.get("why") or "no candidate" for r in records
                    if r["status"] == "missed").most_common()),
                readers=readers)


def _both(records: list[dict], a: str, b: str) -> dict:
    """The two readers on the rows both have read."""
    rows = [r for r in records
            if r.get(a) is not None and r.get(b) is not None]
    if not rows:
        return dict(rows=0)
    fa = [score(r[a], r["mathpix"]) for r in rows]
    fb = [score(r[b], r["mathpix"]) for r in rows]
    return dict(rows=len(rows),
                **{f"f1_{a}": round(sum(s["f1"] for s in fa) / len(rows), 4),
                   f"f1_{b}": round(sum(s["f1"] for s in fb) / len(rows), 4),
                   f"same_{a}": sum(s["same"] for s in fa),
                   f"same_{b}": sum(s["same"] for s in fb),
                   f"{a}_better": sum(x["f1"] > y["f1"]
                                      for x, y in zip(fa, fb)),
                   f"{b}_better": sum(y["f1"] > x["f1"]
                                      for x, y in zip(fa, fb))})


def write_table(records: list[dict], path: Path, limit: int) -> None:
    """The rows, worst of ours first, crop in the last column."""
    rows = sorted(records, key=lambda r: (r.get("f1_ours", 0.0),
                                          r["document"], r["label"]))[:limit]
    e = html.escape
    out = ["<!doctype html><meta charset='utf-8'><title>eqlist</title>",
           "<style>body{font:13px sans-serif}table{border-collapse:collapse}"
           "td,th{border:1px solid #999;padding:4px;vertical-align:top}"
           "code{white-space:pre-wrap;word-break:break-all}"
           "img{max-width:480px}td.c{max-width:360px}code.t{color:#777}</style>",
           f"<p>{len(rows)} of {len(records)} equations, worst first</p>",
           "<table><tr><th>document<br>label, page</th><th>status</th>"
           "<th>F1</th><th>ours</th><th>MathPix</th><th>pdfdrill</th>"
           "<th>psred</th><th>page</th></tr>"]
    for r in rows:
        f1 = " / ".join("-" if f"f1_{k}" not in r else f"{r[f'f1_{k}']:.2f}"
                        for k in READERS)
        cells = "".join(f"<td class='c'><code>{e(r.get(k) or '')}</code></td>"
                        for k in ("mathpix", "pdfdrill", "psred"))
        if r["status"] == "missed":
            # no display of ours: the lines we have there, and the test
            # that dropped the candidate
            ours = (f"<td class='c'><i>dropped: {e(r.get('why') or 'no candidate')}"
                    f"</i><br><code class='t'>{e(r.get('text_there') or '')}"
                    "</code></td>")
        else:
            ours = f"<td class='c'><code>{e(r.get('ours') or '')}</code></td>"
        cells = ours + cells
        out.append(
            f"<tr><td>{e(r['document'])}<br>{r['label']}, p{r['page']}</td>"
            f"<td>{r['status']}<br>{e(' '.join(r['there']))}</td>"
            f"<td>{f1}</td>{cells}"
            f"<td><img loading='lazy' src='file://{e(r['crop'])}'></td></tr>")
    out.append("</table>")
    path.write_text("\n".join(out), "utf-8")


# ---------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdf2mmd2-eqlist", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="*", help="documents of the list; "
                    "default: --count spread through it")
    ap.add_argument("--lists",
                    default=str(Path.home() / "pdfdrill-library/eqlists"))
    ap.add_argument("--count", type=int, default=40,
                    help="documents to take when none is named; 0 = all")
    ap.add_argument("--out", default="out/eqlist")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--table-rows", type=int, default=2000)
    args = ap.parse_args(argv)
    lists, out = Path(args.lists), Path(args.out)
    library = lists.resolve().parent
    if library in [out.resolve(), *out.resolve().parents]:
        print(f"pdf2mmd2-eqlist: --out {out} is inside the library",
              file=sys.stderr)
        return 2
    refine.require_pdfminer()
    rows = load_rows(lists)
    docs = pick(sorted(rows), args.count, args.docs)
    if not docs:
        print("pdf2mmd2-eqlist: no such document in the list",
              file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    records, per_doc = [], {}
    t = time.perf_counter()
    todo = work(rows, docs, PIECE_PAGES)
    read: dict[str, dict[int, list[dict]]] = {d: {} for d in docs}
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for (d, n, _), recs in zip(todo, pool.map(
                read_document, [part for _, _, part in todo])):
            read[d][n] = recs
        for d in docs:
            recs = gathered(rows[d], [read[d][n] for n in sorted(read[d])])
            records += recs
            s = summarise(recs)
            s["seconds"] = recs[0].get("seconds")
            s["pages"] = recs[0].get("pages_read")
            s["error"] = next((r["error"] for r in recs if "error" in r),
                              None)
            per_doc[recs[0]["document"]] = s
            print(f"{recs[0]['document']}: {s['equations']} equations "
                  f"{s['status']} F1 {s['readers']['ours']['f1_mean']}"
                  + (f" [{s['error']}]" if s["error"] else ""), flush=True)
    total = summarise(records)
    total["documents"] = len(docs)
    total["seconds"] = round(time.perf_counter() - t, 1)
    total["on_rows_both_read"] = {
        other: _both(records, "ours", other) for other in READERS[1:]}
    with open(out / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "summary.json").write_text(json.dumps(
        dict(ALL=total, documents=per_doc), indent=1, ensure_ascii=False))
    write_table(records, out / "table.html", args.table_rows)
    for status in sorted({r["status"] for r in records}):
        write_table([r for r in records if r["status"] == status],
                    out / f"table-{status}.html", args.table_rows)
    print(json.dumps(total, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
