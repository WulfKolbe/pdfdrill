#!/usr/bin/env python3
"""311b — convert inkdrill's existing measurements for the 311 scope.

Stage one of the ink pass: the documents that already hold inkdrill's
report.compare.tsv need only `inkconvert`, which reads a TSV and writes
report.ink.json. Seconds each, no rendering, nothing external.

`inkconvert` ASSERTS the pairing between the TSV's rows and report.tex's
identifiers. Where 295 rebuilt the report after inkdrill measured it, that
assertion can fail — and a refusal is the correct outcome, not an error to
work around: the measurement describes a report that no longer exists.
Refusals are recorded with their reason rather than retried.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = pathlib.Path.home() / "pdfdrill-library"
OUT = ROOT / "out" / "311b.jsonl"


def scope():
    names = json.loads((ROOT / "out" / "311.scope.json").read_text())
    out = []
    for n in names:
        d = LIB / n
        if not d.is_dir():
            continue
        if (d / "report.ink.json").is_file():
            continue
        if not (d / "report.compare.tsv").is_file():
            continue
        pdfs = [p for p in d.glob("*.pdf") if p.name != "report.pdf"]
        if pdfs:
            out.append((n, pdfs[0]))
    return out


def main():
    done = set()
    if OUT.is_file():
        for ln in OUT.read_text(errors="replace").splitlines():
            try:
                done.add(json.loads(ln)["doc"])
            except Exception:
                pass
    todo = [(n, p) for n, p in scope() if n not in done]
    print("scope: %d documents need inkconvert" % len(todo), flush=True)
    env = dict(os.environ, PDFDRILL_NO_PREFLIGHT="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"))
    fh = OUT.open("a", encoding="utf-8")
    for i, (name, pdf) in enumerate(todo, 1):
        t0 = time.time()
        rec = {"doc": name}
        try:
            p = subprocess.run([sys.executable, "-m", "pdfdrill", "inkconvert",
                                str(pdf)], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=600)
            out = (p.stdout or "").strip()
            rec["rc"] = p.returncode
            rec["tail"] = out.split("\n")[-2][:200] if len(out.split("\n")) > 1 \
                else out[:200]
            low = out.lower()
            if "refusing to convert" in low:
                rec["outcome"] = "refused"
            elif "already exists" in low:
                rec["outcome"] = "already"
            elif "report.ink.json:" in low:
                rec["outcome"] = "converted"
            elif "no report.compare.tsv" in low:
                rec["outcome"] = "no_tsv"
            elif "documentbusy" in low or "DocumentBusy" in (p.stderr or ""):
                rec["outcome"] = "locked"
            else:
                rec["outcome"] = "other"
                rec["stderr"] = (p.stderr or "")[-200:]
        except subprocess.TimeoutExpired:
            rec["outcome"] = "timeout"
        rec["seconds"] = round(time.time() - t0, 1)
        rec["ink_exists"] = (pdf.parent / "report.ink.json").is_file()
        # a lock refusal is a statement about another process, not about this
        # document; leave it out so a later pass retries it
        if rec["outcome"] != "locked":
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
        print("[%3d/%3d] %-40s %-10s %.1fs" % (i, len(todo), name[:40],
                                               rec["outcome"], rec["seconds"]),
              flush=True)
    fh.close()
    print("PASS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
