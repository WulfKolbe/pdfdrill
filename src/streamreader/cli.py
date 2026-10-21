# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""pdf2mmd2 <pdf> — write MathPix lines.json page structures."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import pageimage, refine, runner, warmup


def _pages(spec: str | None) -> tuple[int | None, int | None]:
    if not spec or spec == "all":
        return None, None
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a), int(b)
    return int(spec), int(spec)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pdf2mmd2", description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="all", help="N, N-M, or all")
    ap.add_argument("--out", help="output folder (default: ./<stem>/)")
    ap.add_argument("--jobs", type=int, help="parallel workers (default: CPUs)")
    ap.add_argument("--images", action="store_true",
                    help="also render each page to pages/<image_id>.jpg")
    ap.add_argument("--warmup", choices=sorted(runner.READERS), default=None,
                    help="glyphs: lines from the page's own glyphs (default "
                         "with --refine; no pdftotext); tsv: text with "
                         "geometry from pdftotext -tsv (default without); "
                         "bbox: the same from -bbox-layout; text: pdftotext "
                         "-layout, geometry zero")
    ap.add_argument("--refine", action="store_true",
                    help="after the warm-up, patch the lines from the "
                         "page's glyphs (patched pdfminer; slower)")
    ap.add_argument("--compact", action="store_true",
                    help="write the JSON on one line instead of one key "
                         "per row")
    ap.add_argument("--timings", action="store_true",
                    help="print one JSON record of stage timings to stderr")
    args = ap.parse_args(argv)

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"pdf2mmd2: no such file: {pdf}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path.cwd() / pdf.stem
    try:
        first, last = _pages(args.pages)
        res = runner.run(pdf, out, first=first, last=last, jobs=args.jobs,
                         images=args.images, reader=args.warmup,
                         refine=args.refine, pretty=not args.compact)
    except (runner.RangeError, runner.OverwriteError, warmup.WarmupError,
            refine.RefineError,
            pageimage.RenderError,
            ValueError) as e:
        print(f"pdf2mmd2: {e}", file=sys.stderr)
        return 2
    if args.timings:
        rec = {"pdf": pdf.name, "pages": res["pages"], "lines": res["lines"],
               "seconds": res["seconds"]}
        if "refine" in res:
            rec["refine"] = res["refine"]
        print(json.dumps(rec), file=sys.stderr)
    print(res["lines_json"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
