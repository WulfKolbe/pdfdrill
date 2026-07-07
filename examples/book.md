# Example — a large born-digital book

A 500–2000-page born-digital book (produced by LaTeX / Word / a publisher tool).
pdfdrill reads its own text layer keylessly (pdfplumber → lines.json), and the book
commands recover printed structure.

```bash
pdfdrill size     book.pdf           # confirms a text layer (born-digital)
pdfdrill ls       ~/library          # shallow-scan a FOLDER: pdfinfo per file,
                                      #   table led by PRODUCER (the triage signal)
pdfdrill identifiers book.pdf         # ISBN/ISSN/DOI + author on the front matter
pdfdrill booktoc  book.pdf           # printed TOC → PDF page (front-matter offset
                                      #   solved); greppable book.toc.txt
```

Navigate by the printed TOC, then extract only what you need:

```bash
grep -i "chapter 7" book.pdf.drill/book.toc.txt     # → its PDF page
pdfdrill page      book.pdf 143                      # that page's text
pdfdrill rasterize book.pdf --pages 143 --dpi 400    # or read the page image
pdfdrill model     book.pdf                          # full model (born-digital route)
pdfdrill context   book.pdf "define the metric tensor" --max-tokens 1200
```

**Why not the whole thing:** building/serving a 2000-page model is heavy. Reach for
the cheapest sufficient rung first — `ls` (folder), `booktoc` (navigation),
`identifiers` (front matter) — before the full `model`. The `.chars.json` pdfplumber
dump (600–800 MB on a huge book) lives in `book.pdf.drill/` and is a regenerable
intermediate.

**Gotcha:** a scanned book (no text layer) is a different lane — `route` sends it to
Gemma (≤20 pages) or MathPix (larger); there is no keyless math for a scan.
