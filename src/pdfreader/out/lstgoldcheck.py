#!/usr/bin/env python3
r"""lstgoldcheck — is the GOLD SET sound? Not: did it produce a file.

781c — A PDF APPEARING IS NOT EVIDENCE THAT THE FILE COMPILED.

The builder's check was "a PDF exists and is over 1000 bytes", and all 307
candidates passed it. LaTeX recovers from nearly everything and prints the
rest of the source, so 96 of those files compiled with ERRORS and 23 pages
did not show the listing at all -- one of them showed its own preamble:

    mathescape=false, texcl=false,
    morekeywords=[1] import, prelude, protected, private, noncomputable, ...

A reader measured against a page like that is measured against nothing, and
nothing in the loop said so. This asks the two questions that would have:

  ERRORS    every `!` line pdflatex printed, not whether a file appeared
  THE PAGE  how much of the rendered text is the listing the file was built
            for. A page that is 3% listing and 97% something else is not a
            question about code.

    python3 lstgoldcheck.py                 # report
    python3 lstgoldcheck.py --install       # and refresh lstgold/pdf/
"""
import argparse
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GOLD = Path(os.environ.get("PDF2MMD_LSTGOLD",
                           Path.home() / "pdfdrill-library" / "lstgold"))
_LST = re.compile(r"\\begin\{lstlisting\}(?:\[([^\]]*)\])?\n(.*?)\\end\{lstlisting\}",
                  re.S)

#: Below this share the page is not the listing. Long captions reach 0.45
#: legitimately (lst-033 carries a 100-word one), so the number FLAGS, it
#: does not convict -- every flagged file is named.
DAMAGED = 0.60


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", s)


def check(path: str, install: bool = False) -> dict:
    f = Path(path)
    d = Path(tempfile.mkdtemp(prefix="gc-", dir="/tmp/claude-1000"))
    try:
        shutil.copy2(f, d)
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-no-shell-escape",
                            "-output-directory", str(d), str(d / f.name)],
                           capture_output=True, text=True, errors="replace",
                           timeout=240)
        errs = sorted({l.strip() for l in r.stdout.split("\n") if l.startswith("!")})
        pdf = d / (f.stem + ".pdf")
        row = {"id": f.stem, "pdf": pdf.exists(), "errors": errs[:6], "ratio": 0.0}
        if not pdf.exists():
            return row
        if install:
            (GOLD / "pdf").mkdir(exist_ok=True)
            shutil.copy2(pdf, GOLD / "pdf" / (f.stem + ".pdf"))
        page = subprocess.run(["pdftotext", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        m = _LST.search(f.read_text(encoding="utf-8", errors="replace"))
        body = _alnum(m.group(2)) if m else ""
        seen = _alnum(page)
        row["ratio"] = (len(body) / len(seen)) if seen else 0.0
        return row
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true",
                    help="refresh lstgold/pdf/ from this compile")
    ap.add_argument("--json", default="")
    A = ap.parse_args()
    files = sorted(glob.glob(str(GOLD / "lst-*.tex")))
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda f: check(f, A.install), files))
    if A.json:
        Path(A.json).write_text(json.dumps(res, indent=1))
    bad = [r for r in res if r["errors"]]
    hurt = [r for r in res if r["ratio"] < DAMAGED]
    print("gold files              %d" % len(res))
    print("  produced a PDF        %d" % sum(1 for r in res if r["pdf"]))
    print("  compiled with ERRORS  %d" % len(bad))
    print("  page is <%d%% listing  %d" % (100 * DAMAGED, len(hurt)))
    for r in sorted(hurt, key=lambda r: r["ratio"]):
        print("      %-10s %.2f   %s" % (r["id"], r["ratio"],
                                         (r["errors"] or ["(no error)"])[0][:46]))
    c = collections.Counter(e[:70] for r in bad for e in r["errors"])
    for k, v in c.most_common(10):
        print("   %3d  %s" % (v, k))


if __name__ == "__main__":
    main()
