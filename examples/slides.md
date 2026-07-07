# Example — a slide deck

Slides are visual: text extraction misses layout, figures, and equations rendered
as images. Render and *look*, rather than trusting the text layer.

```bash
pdfdrill size      slides.pdf                     # often few chars/page (figures)
pdfdrill rasterize slides.pdf --pages all --dpi 300   # → slides.pdf.drill/rasterize/
                                                       #   Read each page image
pdfdrill links     slides.pdf                     # links (code/data) hidden in
                                                  #   annotations, no visible anchor
```

For a full deep-zoom viewer over every page (self-contained, offline):

```bash
pdfdrill pyramid slides.pdf                       # 600-DPI DZI pyramid + viewer
pdfdrill inspect slides.pdf                       # DevTools-style page + element view
```

**Why rasterize:** a chart, a diagram, or an equation-as-image is invisible to
`page`/`md`. `rasterize` (Ghostscript ≥400 DPI) gives you the pixels; you Read them.
Don't OCR the slides with your own tool — if you need the text/math typed, that's
`ocr` / `visionocr` / `mathpix`, and `route` will tell you which lane fits.

**Gotcha:** a born-digital deck whose page 1 is a title *figure* still has a text
layer on later pages — `size` samples the first few pages, so it won't mislabel it a
scan.
