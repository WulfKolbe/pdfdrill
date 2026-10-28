# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""pdf2mmd2-mathpix-pages — a MathPix lines.json as one file per page.

Writes `page-NNNN.mathpix.json` next to pdf2mmd2's own `page-NNNN.json`,
in the same layout, so the two readings of a page sit beside each other in
a file list and open side by side in an editor.

The source is a lines.json path, or a folder name of the library: then its
MathPix export is found the way the benchmark finds it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench, mathpix


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdf2mmd2-mathpix-pages", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="MathPix lines.json, or a library "
                                   "folder name")
    ap.add_argument("--root", default=str(Path.home() / "pdfdrill-library"))
    ap.add_argument("--out", help="folder for the page files (default: "
                                  "out/<name>/<name>.lines)")
    args = ap.parse_args(argv)

    root = Path(args.root)
    source = Path(args.source)
    if source.is_file():
        name = source.name.split(".lines")[0]
    else:
        name = args.source
        found = bench.find_reference(root / name, name)
        if found is None:
            print(f"pdf2mmd2-mathpix-pages: no MathPix lines.json for "
                  f"{name!r} under {root}", file=sys.stderr)
            return 2
        source = found
    out = Path(args.out) if args.out else Path("out") / name / f"{name}.lines"
    if root.resolve() in [out.resolve(), *out.resolve().parents]:
        print(f"pdf2mmd2-mathpix-pages: --out {out} is inside the library; "
              f"refusing to write there", file=sys.stderr)
        return 2
    pages = json.loads(source.read_text("utf-8"))["pages"]
    out.mkdir(parents=True, exist_ok=True)
    for pg in pages:
        (out / f"page-{pg['page']:04d}.mathpix.json").write_text(
            mathpix.pretty(pg, 2), "utf-8")
    print(f"{source.name}: {len(pages)} pages -> "
          f"{out.resolve()}/page-NNNN.mathpix.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
