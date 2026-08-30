#!/usr/bin/env python3
"""365 — a report over 364's fixture: our compile against the dataset's render.

BOTH COLUMNS ARE RENDERS OF THE SAME CODE. Neither is a scan of a printed
page, so this is a renderer-versus-renderer floor, not a reading comparison —
the TikZ equivalent of the 208-expression rasteriser measurement. A difference
here is our LaTeX installation against theirs: missing packages, library
versions, font substitution. It says nothing about OCR.
"""
import json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = pathlib.Path.home() / "pdfdrill-library" / "datikz-fixture"
OUT = FIX / "rendered"


def compile_one(tex: pathlib.Path, work: pathlib.Path, timeout: int = 120):
    work.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
         "-output-directory", str(work), str(tex)],
        capture_output=True, text=True, timeout=timeout)
    pdf = work / (tex.stem + ".pdf")
    if not pdf.is_file():
        log = work / (tex.stem + ".log")
        err = ""
        if log.is_file():
            for line in log.read_text(errors="replace").splitlines():
                if line.startswith("!"):
                    err = line[:110]
                    break
        return None, err or "no pdf (rc=%d)" % r.returncode
    png = work / (tex.stem + ".png")
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
                    "-r150", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                    "-sOutputFile=" + str(png), str(pdf)],
                   capture_output=True, timeout=timeout)
    return (png if png.is_file() else None), ""


def main() -> int:
    man = json.loads((FIX / "manifest.json").read_text())
    rows = man["rows"]
    OUT.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        png, err = compile_one(FIX / r["tex"], OUT)
        if png:
            r["rendered"] = str(png.relative_to(FIX))
            ok.append(r)
        else:
            r["compile_error"] = err
            failed.append(r)
        if i % 20 == 0:
            print("  ... %d/%d  %.0fs" % (i, len(rows), time.time() - t0), flush=True)
    (ROOT / "out" / "365.json").write_text(json.dumps(
        {"compiled": len(ok), "failed": len(failed),
         "rows": ok, "failures": failed}, indent=1, ensure_ascii=False))
    print("compiled %d of %d (%.0f%%), failed %d"
          % (len(ok), len(rows), 100.0 * len(ok) / max(1, len(rows)), len(failed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
