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


#: 389 — the engine order, and why there are two.
#:
#: xelatex first, because a model carries raw Unicode and pdflatex cannot set
#: it. But a DaTikZ row is not our projection — it is an author's own
#: standalone document, and 3 of the first 100 begin
#: \usepackage[utf8]{inputenc}, which is a hard error under xetex:
#: "inputenc is not designed for xetex or luatex". pdflatex compiles those
#: without complaint.
#:
#: This is 348's rule for regions applied to the render path: try the
#: preamble the document asks for, fall back on failure. A single-engine
#: renderer reports an author's preamble choice as a compile failure, and the
#: report then shows "did not compile" for a document that compiles fine —
#: a measurement of our engine choice presented as a property of the row.
ENGINES = ("xelatex", "pdflatex")


def _run(engine, tex, work, timeout):
    """(pdf or None, first '!' line from the log)."""
    r = subprocess.run(
        [engine, "-interaction=nonstopmode", "-halt-on-error",
         "-output-directory", str(work), str(tex)],
        capture_output=True, text=True, timeout=timeout)
    pdf = work / (tex.stem + ".pdf")
    if pdf.is_file():
        return pdf, ""
    log = work / (tex.stem + ".log")
    err = ""
    if log.is_file():
        for line in log.read_text(errors="replace").splitlines():
            if line.startswith("!"):
                err = line[:110]
                break
    return None, err or "no pdf (rc=%d)" % r.returncode


def compile_one(tex: pathlib.Path, work: pathlib.Path, timeout: int = 120):
    work.mkdir(parents=True, exist_ok=True)
    pdf, err, used = None, "", ""
    for engine in ENGINES:
        # A failed run leaves the PREVIOUS engine's pdf behind, and the next
        # engine would then be credited with it. Remove it before each try.
        stale = work / (tex.stem + ".pdf")
        if stale.is_file():
            stale.unlink()
        pdf, err = _run(engine, tex, work, timeout)
        if pdf is not None:
            used = engine
            break
    if pdf is None:
        return None, err, ""
    png = work / (tex.stem + ".png")
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
                    "-r150", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                    "-sOutputFile=" + str(png), str(pdf)],
                   capture_output=True, timeout=timeout)
    return (png if png.is_file() else None), "", used


def main() -> int:
    man = json.loads((FIX / "manifest.json").read_text())
    rows = man["rows"]
    OUT.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        png, err, engine = compile_one(FIX / r["tex"], OUT)
        if png:
            r["rendered"] = str(png.relative_to(FIX))
            r["engine"] = engine
            ok.append(r)
        else:
            r["compile_error"] = err
            failed.append(r)
        if i % 20 == 0:
            print("  ... %d/%d  %.0fs" % (i, len(rows), time.time() - t0), flush=True)
    (ROOT / "out" / "365.json").write_text(json.dumps(
        {"compiled": len(ok), "failed": len(failed),
         "rows": ok, "failures": failed}, indent=1, ensure_ascii=False))
    import collections
    by = collections.Counter(r.get("engine", "?") for r in ok)
    print("compiled %d of %d (%.0f%%), failed %d"
          % (len(ok), len(rows), 100.0 * len(ok) / max(1, len(rows)), len(failed)))
    print("  by engine: " + ", ".join("%s %d" % (k, v)
                                      for k, v in by.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
