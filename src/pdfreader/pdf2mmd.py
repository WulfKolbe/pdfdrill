#!/usr/bin/env python3
"""pdf2mmd.py — convert a born-digital PDF to Markdown with LaTeX injected.

The driver behind `pdf2mmd.sh`. Builds the docmodel once and projects it to
every output, so the formats cannot disagree with each other.

OUTPUTS (into --out)
  <stem>.md            Markdown, LaTeX inline, crop links where maths defers
  <stem>.tex           the same content as LaTeX
  <stem>.lines.json    Mathpix-shaped geometry
  <stem>.fonts.md      the type-size evidence behind the heading levels
  <stem>.report.txt    what projected, what did not, and why

REFUSES a page whose glyphs are all invisible (Tr 3/7). That is a scanner's OCR
layer over a raster: its positions are good and its identities are another
tool's guess, so projecting it would produce confident nonsense. Use MathPix
for those.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import docmodel_six as docmodel
import provenance
import docpack
import equations as eqmod                                            # noqa: E402
import project_mmd as mmd                                  # noqa: E402


def parse_pages(spec: str | None, total: int):
    if not spec or spec == "all":
        return range(0, total)
    if "-" in spec:
        a, b = spec.split("-", 1)
        return range(int(a) - 1, int(b))
    n = int(spec)
    return range(n - 1, n)


def page_count(pdf: str) -> int:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    with open(pdf, "rb") as fh:
        return sum(1 for _ in PDFPage.create_pages(PDFDocument(PDFParser(fh))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="all", help="N, N-M, or all")
    ap.add_argument("--out", default=".", help="output folder")
    ap.add_argument("--doc-id", help="id used in crop URLs (default: stem)")
    ap.add_argument("--image-base", default="http://localhost:8000",
                    help="origin serving /cropped/... (inspectserver.py)")
    ap.add_argument("--separator", default="---",
                    help="page separator; 'ff' for a pdftotext form feed, "
                         "'' for none")
    ap.add_argument("--no-crops", action="store_true",
                    help="leave unprojected maths as a comment, not an image")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.exists(args.pdf):
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.pdf))[0]
    doc_id = args.doc_id or stem
    sep = {"ff": "\f", "": ""}.get(args.separator, f"\n{args.separator}\n")

    def say(*a):
        if not args.quiet:
            print(*a, file=sys.stderr)

    total = page_count(args.pdf)
    rng = parse_pages(args.pages, total)
    say(f"{stem}: {total} pages, converting {len(rng)} "
        f"({rng.start + 1}-{rng.stop})")

    t0 = time.time()
    pages = docmodel.build(args.pdf, rng)
    say(f"  docmodel built in {time.time() - t0:.1f}s")

    ocr = [p.page for p in pages if p.invisible]
    if ocr:
        say(f"  ! {len(ocr)} page(s) are an OCR layer (Tr 3) and were not "
            f"projected: {ocr[:8]}")

    # ---- statistics, gathered from the model rather than from the output
    stats = collections.Counter()
    why: collections.Counter = collections.Counter()
    for p in pages:
        for ln in p.lines:
            stats["lines"] += 1
            for sp in ln.spans:
                stats["glyphs"] += len(sp.glyphs)
                if sp.kind != "math":
                    continue
                stats["math_spans"] += 1
                if docmodel.span_latex(sp) is not None:
                    stats["projected"] += 1
                else:
                    why[docmodel.span_reason(sp)] += 1

    base = os.path.join(args.out, stem)
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(mmd.to_markdown(pages, doc_id=doc_id, base=args.image_base,
                                 page_separator=sep,
                                 crop_deferred=not args.no_crops))
    with open(base + ".tex", "w", encoding="utf-8") as fh:
        fh.write(mmd.to_latex(pages, doc_id=doc_id, base=args.image_base))
    with open(base + ".lines.json", "w", encoding="utf-8") as fh:
        json.dump(docmodel.to_lines_json(pages, doc_id=stem), fh, indent=1)
    # The pdfdrill docmodel: meta / streams / objects / alignments, with
    # objects pointing into the stream by anchor range rather than carrying
    # text of their own.
    # The equation evidence table: one row per equation, with the LaTeX, the
    # crop region and what is known about how complete each is.
    with open(base + ".equations.json", "w", encoding="utf-8") as fh:
        _eq = eqmod.to_json(pages, bibkey=stem)
        _eq["produced_by"] = provenance.identity()      # 785
        json.dump(_eq, fh, indent=1)
    with open(os.path.join(os.path.dirname(base), "model.docmodel.json"),
              "w", encoding="utf-8") as fh:
        json.dump(docpack.to_docmodel(pages, bibkey=stem,
                                      source_path=os.path.abspath(args.pdf)),
                  fh, indent=1)
    with open(base + ".fonts.md", "w", encoding="utf-8") as fh:
        fh.write(mmd.font_report(pages))

    m = stats["math_spans"]
    pct = 100.0 * stats["projected"] / m if m else 0.0
    lines = [
        # 785 — WHO PRODUCED THIS. The report recorded everything about the
        # document and nothing about the reader, so when two installs existed
        # on one machine (a checkout at 784 and a standalone copy frozen days
        # earlier) their results could only be told apart by file mtime, which
        # is evidence about the filesystem and not about the code. 347 GB of
        # output had to be dated rather than identified.
        provenance.built_line(),
        "",
        f"document      {stem}",
        f"pages         {rng.start + 1}-{rng.stop} of {total}",
        f"glyphs        {stats['glyphs']}",
        f"lines         {stats['lines']}",
        f"maths spans   {m}",
        f"  projected   {stats['projected']} ({pct:.1f}%)",
        f"  deferred    {m - stats['projected']}",
        "",
        "deferrals by reason (each is a crop link in the Markdown, with its "
        "node id):",
    ]
    for k, v in why.most_common():
        lines.append(f"  {v:6d}  {100.0 * v / m if m else 0:5.1f}%  {k}")
    if ocr:
        lines += ["", f"OCR-layer pages skipped: {ocr}"]

    # 733 -- A PDF THIS READER CANNOT READ MUST NOT LOOK LIKE A SUCCESS.
    #
    # `~/Gemma4/test.pdf` produced `glyphs 0, lines 0`, an exit status of 0
    # and no message at all; the `.tex` was `\documentclass{article}` around a
    # bare `\newpage`, and xelatex answered "No pages of output" -- which
    # reads as a LaTeX fault rather than as "nothing was extracted". Found by
    # running PDFs from outside the corpus.
    #
    # Zero glyphs is not a hard case, it is a DIFFERENT KIND OF DOCUMENT: no
    # text layer, so the page is an image and belongs to OCR, not to a glyph
    # reader. Named, and the status says so.
    empty = stats["glyphs"] == 0
    if empty:
        lines += ["",
                  "NO TEXT WAS READ.",
                  "  This PDF has no text layer on the pages requested: every",
                  "  glyph count is zero, so there is nothing for a glyph",
                  "  reader to project. The page is an image (a scan, or a",
                  "  figure exported as a whole) and needs OCR instead.",
                  "  Exit status 2."]
    report = "\n".join(lines) + "\n"
    with open(base + ".report.txt", "w", encoding="utf-8") as fh:
        fh.write(report)

    if not args.quiet:
        print(report, file=sys.stderr)
        say(f"  wrote {base}.md/.tex/.lines.json/.fonts.md/.report.txt"
            f", model.docmodel.json and {base}.equations.json")
    if empty:
        print("pdf2mmd: NO TEXT WAS READ from %s -- no text layer on pages "
              "%d-%d; this is a scan or an image-only page and needs OCR."
              % (args.pdf, rng.start + 1, rng.stop), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
