#!/usr/bin/env python3
"""corpusrun — run pdf2mmd over every document of the library, in parallel.

    python3 corpusrun.py OUTDIR            convert what is not already there
    python3 corpusrun.py OUTDIR --force    convert everything again
    python3 corpusrun.py OUTDIR --install  and copy the result into the
                                           library beside each PDF

`--install` is what makes the sweep and the table see new output: they read
`<doc>/pdf2mmd/page.md`, never a scratch directory. Nothing else writes
there, so a run you have not installed cannot change a measurement by
accident.

    $PDF2MMD_LIBRARY   default ~/pdfdrill-library
    $PDF2MMD_CODE      default the parent of this folder
"""
import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LIB = Path(os.environ.get("PDF2MMD_LIBRARY", Path.home() / "pdfdrill-library"))
CODE = Path(os.environ.get("PDF2MMD_CODE", Path(__file__).resolve().parent.parent))
PY = CODE / ".pdfmm-venv" / "bin" / "python"
if not PY.is_file():
    PY = Path(sys.executable)


def one(slug: str, out: Path, force: bool):
    d = out / slug
    if not force and (d / (slug + ".md")).is_file():
        return slug, 0
    p = subprocess.run([str(PY), "pdf2mmd.py", str(LIB / slug / (slug + ".pdf")),
                        "--out", str(d), "--quiet"],
                       capture_output=True, text=True, cwd=str(CODE), timeout=1800)
    return slug, p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--jobs", type=int, default=10)
    A = ap.parse_args()
    out = Path(A.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    docs = sorted(x.name for x in LIB.glob("wzlxjtu-*") if x.is_dir())
    bad = 0
    with ThreadPoolExecutor(max_workers=A.jobs) as ex:
        futs = [ex.submit(one, s, out, A.force) for s in docs]
        for i, f in enumerate(as_completed(futs), 1):
            slug, rc = f.result()
            # 2 is "no text layer", which is a verdict, not a failure
            if rc not in (0, 2):
                bad += 1
                print("   FAIL %s rc=%s" % (slug, rc))
            if i % 25 == 0:
                print("   %d/%d" % (i, len(docs)), flush=True)
    print("converted %d documents, %d failures" % (len(docs), bad))

    if A.install:
        n = 0
        for d in sorted(out.glob("wzlxjtu-*")):
            dst = LIB / d.name / "pdf2mmd"
            if not dst.is_dir():
                continue
            for f in d.iterdir():
                # the library calls them `page.*`; the run calls them `<slug>.*`
                tgt = (dst / f.name if f.suffix == ".tex"
                       or f.name == "model.docmodel.json"
                       else dst / f.name.replace(d.name, "page", 1))
                shutil.copy2(f, tgt)
            n += 1
        print("installed %d documents into %s" % (n, LIB))


if __name__ == "__main__":
    main()
