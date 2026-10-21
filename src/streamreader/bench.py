# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""pdf2mmd2-bench — run the readers over a corpus list and compare.

For every document: time each warm-up reader, compare its reading with the
document's MathPix export, and optionally hold the result against a stored
baseline. Output goes to --out, never into the corpus.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import bboxlayout, compare, glyphs, runner, warmup

COMMANDS = {"text": warmup.command, "bbox": bboxlayout.command,
            "tsv": bboxlayout.command_tsv}
# Metrics where a lower value than the baseline's is a regression ...
HIGHER_IS_BETTER = ("word_share_mean", "word_share_min", "pages_ge_95",
                    "page_size_equal", "located", "glyph_agreement_mean",
                    "type_hits", "line_purity", "line_coverage",
                    "reading_order", "math_display_f1", "math_inline_f1")
# ... and where a higher one is.
LOWER_IS_BETTER = ("unmapped", "unassigned", "type_false")
SHARE_TOLERANCE = 0.005
SLOWDOWN_LIMIT = 2.0


def read_corpus(path: Path) -> list[str]:
    docs = []
    for raw in Path(path).read_text("utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            docs.append(line)
    return docs


def find_reference(folder: Path, stem: str) -> Path | None:
    """The MathPix export of a document: the backup pdfdrill keeps when a
    free reading displaced it, else a lines.json that names no `source`."""
    for name in (f"{stem}.lines.mathpix.bak.json", f"{stem}.lines.json"):
        path = Path(folder) / name
        if not path.is_file():
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(8192)
        if '"image_id"' in head and not re.search(r'"source"\s*:', head):
            return path
    return None


def _best(fn, repeats: int):
    best, value = None, None
    for _ in range(repeats):
        t = time.perf_counter()
        value = fn()
        dt = time.perf_counter() - t
        best = dt if best is None else min(best, dt)
    return best, value


def measure(root: Path, doc: str, out_dir: Path, repeats: int = 3,
            refine: bool = False) -> dict:
    folder = Path(root) / doc
    pdf = folder / f"{doc}.pdf"
    if not pdf.is_file():
        return {"doc": doc, "error": f"no {doc}/{doc}.pdf in the corpus"}
    ref_path = find_reference(folder, doc)
    ref = json.loads(ref_path.read_text("utf-8")) if ref_path else None
    try:
        total = runner.page_count(pdf)
        readers = {}
        for name, command in COMMANDS.items():
            raw, _ = _best(lambda: subprocess.run(
                command(pdf, 1, total), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL), repeats)
            dest = Path(out_dir) / doc / name
            runs = [runner.run(pdf, dest, jobs=1, reader=name)
                    for _ in range(repeats)]
            ours = json.loads(runs[-1]["lines_json"].read_text("utf-8"))
            readers[name] = compare.summary(ours, ref)
            readers[name]["seconds"] = {
                "pdftotext": round(raw, 4),
                "read": round(min(r["seconds"]["warmup"] for r in runs), 4),
                "assemble": round(min(r["seconds"]["assemble"]
                                      for r in runs), 4),
            }
        if refine and not glyphs.missing_features():
            # pdfminer is timed once: it is slow, and its noise is small
            # beside its cost
            run = runner.run(pdf, Path(out_dir) / doc / "refine", jobs=1,
                             refine=True)
            ours = json.loads(run["lines_json"].read_text("utf-8"))
            r = compare.summary(ours, ref)
            agree = [p["agreement"] for p in run["refine_pages"]]
            r.update(
                glyphs=run["refine"]["glyphs"],
                rules=run["refine"]["rules"],
                unassigned=run["refine"]["unassigned"],
                glyph_agreement_mean=round(sum(agree) / len(agree), 4),
                glyph_agreement_min=min(agree),
                page_errors=len(run["refine"]["errors"]),
                seconds={"pdftotext": readers["tsv"]["seconds"]["pdftotext"],
                         "read": round(run["seconds"]["warmup"], 4),
                         "refine": round(run["seconds"]["refine"], 4),
                         "assemble": round(run["seconds"]["assemble"], 4)})
            readers["refine"] = r
    except (warmup.WarmupError, runner.OverwriteError, OSError,
            ValueError) as e:
        return {"doc": doc, "error": str(e)}
    return {"doc": doc, "pages": total,
            "reference": ref_path.name if ref_path else None,
            "readers": readers}


def check(result: dict, baseline: dict) -> list[str]:
    """Every way `result` is worse than `baseline`, one sentence each."""
    problems: list[str] = []
    read_now: dict[str, float] = {}
    read_then: dict[str, float] = {}
    for doc, then in baseline["docs"].items():
        if "readers" not in then:
            continue
        now = result["docs"].get(doc)
        if now is None:
            problems.append(f"{doc}: missing from this run")
            continue
        if "error" in now:
            problems.append(f"{doc}: {now['error']}")
            continue
        for reader, b in then["readers"].items():
            n = now["readers"].get(reader)
            if n is None:
                problems.append(f"{doc}/{reader}: reader missing from this run")
                continue
            if n["pages"] != b["pages"]:
                problems.append(f"{doc}/{reader}: pages {n['pages']}, "
                                f"baseline {b['pages']}")
            for key in HIGHER_IS_BETTER + LOWER_IS_BETTER:
                old, new = b.get(key), n.get(key)
                if old is None:
                    continue
                slack = SHARE_TOLERANCE if isinstance(old, float) else 0
                worse = (new is None
                         or (key in HIGHER_IS_BETTER and new < old - slack)
                         or (key in LOWER_IS_BETTER and new > old + slack))
                if worse:
                    problems.append(f"{doc}/{reader}: {key} {new}, "
                                    f"baseline {old}")
            read_now[reader] = read_now.get(reader, 0) + n["seconds"]["read"]
            read_then[reader] = (read_then.get(reader, 0)
                                 + b["seconds"]["read"])
    for reader, then_s in read_then.items():
        if read_now[reader] > SLOWDOWN_LIMIT * then_s:
            problems.append(f"{reader}: read time {read_now[reader]:.3f} s "
                            f"over the corpus, baseline {then_s:.3f} s")
    return problems


def _version(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return "absent"
    lines = (p.stdout + p.stderr).strip().splitlines()
    return lines[0] if lines else ""


def _table(docs: dict) -> str:
    head = (f"{'document':<34} {'reader':<6} {'pages':>5} {'lines':>6} "
            f"{'ms/pg':>6} {'words':>6} {'min':>5} {'>=.95':>9} "
            f"{'pure':>5} {'cover':>5} {'order':>5} "
            f"{'located':>12} {'font':>5} {'U+FFFD':>6} {'glyph=':>6} "
            f"{'typed ok/bad':>12} {'math d/i F1':>11}")
    rows = [head, "-" * len(head)]
    for doc, res in docs.items():
        if "error" in res:
            rows.append(f"{doc[:34]:<34} ERROR {res['error']}")
            continue
        for reader, r in res["readers"].items():
            def cell(key, fmt="{}"):
                return "-" if r.get(key) is None else fmt.format(r[key])
            ge = (f"{r['pages_ge_95']}/{r['prose_pages']}"
                  if r.get("prose_pages") is not None else "-")
            loc = (f"{r['located']}/{r['locatable']}"
                   if r.get("located") is not None else "-")
            typed = (f"{r['type_hits']}/{r['type_false']}"
                     if r.get("type_hits") is not None else "-")
            rows.append(
                f"{doc[:34]:<34} {reader:<6} {r['pages']:>5} {r['lines']:>6} "
                f"{1000 * (r['seconds']['read'] + r['seconds'].get('refine', 0)) / max(1, r['pages']):>6.2f} "
                f"{cell('word_share_mean', '{:.3f}'):>6} "
                f"{cell('word_share_min', '{:.2f}'):>5} {ge:>9} "
                f"{cell('line_purity', '{:.2f}'):>5} "
                f"{cell('line_coverage', '{:.2f}'):>5} "
                f"{cell('reading_order', '{:.2f}'):>5} {loc:>12} "
                f"{cell('font_ratio_median', '{:.2f}'):>5} "
                f"{r['unmapped']:>6} "
                f"{cell('glyph_agreement_mean', '{:.3f}'):>6} "
                f"{typed:>12} "
                f"{cell('math_display_f1', '{:.2f}'):>5}/"
                f"{cell('math_inline_f1', '{:.2f}'):<5}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pdf2mmd2-bench", description=__doc__)
    ap.add_argument("--corpus", default="bench/corpus.txt",
                    help="file with one corpus folder name per line")
    ap.add_argument("--root", default=str(Path.home() / "pdfdrill-library"))
    ap.add_argument("--out", default="out/bench")
    ap.add_argument("--baseline", default="bench/baseline.json")
    ap.add_argument("--repeats", type=int, default=3,
                    help="timing repeats; the fastest counts")
    ap.add_argument("--no-refine", action="store_true",
                    help="skip the pdfminer refinement pass")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if anything is worse than the baseline")
    ap.add_argument("--update-baseline", action="store_true",
                    help="store this run as the new baseline")
    args = ap.parse_args(argv)

    root, out = Path(args.root), Path(args.out)
    if not root.is_dir():
        print(f"pdf2mmd2-bench: no corpus at {root}", file=sys.stderr)
        return 2
    if root.resolve() in [out.resolve(), *out.resolve().parents]:
        print(f"pdf2mmd2-bench: --out {out} is inside the corpus; "
              f"refusing to write there", file=sys.stderr)
        return 2
    result = {
        "meta": {
            "date": datetime.date.today().isoformat(),
            "cpus": os.cpu_count(),
            "pdftotext": _version(["pdftotext", "-v"]),
            "pdfminer": ("absent" if glyphs.missing_features()
                         else __import__("pdfminer").__version__),
            "repeats": args.repeats,
        },
        "docs": {doc: measure(root, doc, out, repeats=args.repeats,
                              refine=not args.no_refine)
                 for doc in read_corpus(Path(args.corpus))},
    }
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=1, ensure_ascii=False)
    (out / "results.json").write_text(text, "utf-8")
    print(_table(result["docs"]))
    baseline = Path(args.baseline)
    if args.update_baseline:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(text, "utf-8")
        print(f"\nbaseline written to {baseline}")
    if args.check:
        if not baseline.is_file():
            print(f"pdf2mmd2-bench: no baseline at {baseline}",
                  file=sys.stderr)
            return 2
        problems = check(result, json.loads(baseline.read_text("utf-8")))
        if problems:
            print(f"\n{len(problems)} regression(s) against {baseline}:")
            for p in problems:
                print(f"  {p}")
            return 1
        print(f"\nno regression against {baseline}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
