"""pdf2mmd2 — the reader's installed front door, and where its output says who wrote it.

Deliberately NOT part of `src/streamreader/`. Every module in that package is
byte-identical to pdf2mmd2 at 5190249 and `tests/test_streamreader_provenance.py`
holds it there, so pdfdrill-side behaviour cannot live inside it. This file is
the pdfdrill side of the reader: it runs the reader unchanged, then writes the
one key the reader's own format has no field for.

ENGINEERING 2d (owner, 2026-10-27): "there should be strict separation between
tools that generate lines.json like data and pdfdrill… pdf2mmd2, glyphdrill and
Gemma should produce lines.json formated output and not interfere with docmodel
data". So the stamp happens here, on the reader's side, and touches no docmodel.

WHY THE STAMP IS THE WHOLE POINT, and WHICH FLAG IT TAKES. Measured on
1702.06385 (9 pages, 170 maths objects, every one carrying the author's LaTeX)
through this entry point and then `pdfdrill model`, each arm a fresh directory:

    lines.json beside the PDF                 lines   maths boxed   matched+interp
    none — pdfdrill reads the PDF itself          —     30 of 170       45 + 62
    `pdf2mmd2 <pdf>`            (warmup tsv)   1029     31 of 170       56 + 59
    `pdf2mmd2 <pdf> --refine`  (glyph route)    955     40 of 170       65 + 68

So the stamp is worth +10 placed formulas WITH `--refine`, and +1 without: the
default warm-up reads poppler's text layer, which is the same ink pdfdrill
already reads for itself, while `--refine` patches the lines from the page's own
glyphs (33471 glyphs, 0 unassigned, agreement_min 0.9106, 0.6 s for 9 pages).
The reader's own default is NOT changed here — a front door that quietly passes
a flag the caller did not type is a worse defect than a slow default — but any
pdfdrill layer that comes to run this reader should pass `--refine`, and this
measurement is the reason.

An earlier note of mine quoted the 40 without naming `--refine`, from a roll-up
whose `total_pages` key I had written by hand; the reader writes `source` and
`pages` and nothing else. The number survived re-measurement, the condition had
been left out.

WHERE THE FILE LANDS, and why that is not changed here either. `cli` defaults
`--out` to `./<stem>/`, and pdfdrill looks for `<stem>.lines.json` BESIDE the
PDF. Those agree whenever the document sits in a folder named after it, which is
the library's own layout (`<name>/<name>.pdf`) — measured both ways:

    cd <library>   pdf2mmd2 1702.06385/1702.06385.pdf  -> 1702.06385/1702.06385.lines.json
                                                          beside the PDF, no copy
    cd <tmp>       pdf2mmd2 1702.06385.pdf             -> 1702.06385/1702.06385.lines.json
                                                          one level down from the PDF

So the mismatch is an artifact of standing next to a loose PDF, not of the
reader. The default is left alone for the same reason `--refine` is not
injected: the caller's `--out` is the caller's. The fix is not a cleverer
default but a pdfdrill layer that runs the reader and names the path itself;
until then a loose PDF takes `--out .`.

The reader writes `{"pages": [...]}` and nothing else (`runner.py:180`), so its
file declares no source at all. It used to clear `inspect`'s geometry
prerequisite through the `""` entry in `commands._TYPED_GEOMETRY_SOURCES` —
which that tuple's own docstring called an accident — and a reader that is read
only by accident is not integrated. That entry is now closed (2d rule 5,
2026-10-28): an undeclared reading is admitted only when
`commands._detect_lines_source` RECOGNISES it.

An unstamped reading of this reader's still gets in, measured: its `image_id` is
`<stem>-<page>`, which the detector reads as `mathpix-shaped` — ours, typed, in
a pixel frame. So the stamp is not what keeps the reader readable; it is what
makes the file say WHICH reader, instead of leaving pdfdrill to infer the one
fact the detector can see. `mathpix-shaped` is the honest name for a guess;
`pdf2mmd2` is the producer.

The value is exactly `pdf2mmd2`, which both gates already name
(`docmodel.mathpix._PAGE_PIXEL_SOURCES`, `commands._TYPED_GEOMETRY_SOURCES`),
and which `_is_mathpix_lines` still answers no to — four money-spending call
sites depend on that one staying strict. A variant carrying the commit
(`pdf2mmd2-5190249`) would also pass both gates, since each tests
`src == s or src.startswith(s + "-")`; it is not used, because the two call
sites above compare by equality today and a prefixed value would read as a
different source to anything that does the same.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

from streamreader import cli, mathpix

#: What this reader declares itself to be. Both source gates name it verbatim.
SOURCE = "pdf2mmd2"


def stamp(lines_json: Path, source: str = SOURCE) -> bool:
    """Declare `source` as the file's first top-level key. True if it changed.

    Rewriting is atomic and keeps the shape the reader chose: `--compact` is one
    line, the default is one key per row down to the line objects
    (`mathpix.pretty`, depth 4). Re-dumping in the other shape would rewrite
    every row of a file whose diff is supposed to be a single added line.
    """
    raw = lines_json.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"{lines_json}: top level is {type(data).__name__}, not an object")
    if data.get("source") == source:
        return False
    stamped = {"source": source}
    stamped.update({k: v for k, v in data.items() if k != "source"})
    text = (mathpix.pretty(stamped, 4) if raw.startswith("{\n")
            else json.dumps(stamped, ensure_ascii=False))
    tmp = lines_json.with_name(lines_json.name + ".stamp.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, lines_json)
    return True


def main(argv: "list[str] | None" = None) -> int:
    """Run the reader, then stamp what it wrote.

    The reader's stdout is one line: the path it wrote. It is captured so the
    path can be stamped, then written through unchanged — including argparse's
    `--help`, which leaves by `SystemExit` and would otherwise be swallowed by
    the redirect (the defect `eqreport`/`eqlist` already have).
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = cli.main(argv)
    except SystemExit:
        sys.stdout.write(buf.getvalue())
        raise
    captured = buf.getvalue()
    sys.stdout.write(captured)
    if rc != 0:
        return rc
    lines = [ln.strip() for ln in captured.splitlines() if ln.strip()]
    if not lines:
        print("pdf2mmd2: the reader printed no lines.json path; nothing stamped",
              file=sys.stderr)
        return 1
    target = Path(lines[-1])
    try:
        stamp(target)
    except (OSError, ValueError) as exc:
        print(f"pdf2mmd2: {target} was written but declares no source: {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
