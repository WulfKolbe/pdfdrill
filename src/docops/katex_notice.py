r"""531 — the warning every KaTeX-rendered artefact has to carry.

KaTeX renders in a browser with NO PREAMBLE. It cannot use a package, and it
cannot use the document's own macros. MathPix's `tex.zip` declares packages
its output needs, and the corpus says how much that matters:

  * `\bm` — 327 occurrences across 7 documents, the single biggest package
    gap in the corpus and unnamed until 482 measured it.
  * `\Perp` — no package defines it at all; it spans 10 documents and the
    report preamble supplies it with a `\providecommand` (484).
  * 11,088 of 11,624 undefined occurrences are the SOURCE DOCUMENT'S OWN
    macros (482), which no renderer can know without the author's preamble.

So a KaTeX cell is not evidence in either direction. A row that looks wrong
there may be correct, and a row that looks right there may not compile. The
LaTeX report (B) renders through the document's own preamble and is the
surface to judge from.

ONE TEXT, ONE PLACE. Five generators emit KaTeX — formula_report,
comparison_html, distill_reader, docinspect and the corrections page — and a
warning that is retyped in five files is a warning that will say five
different things within a month.
"""

#: the sentence, for a plain-text or Markdown context
KATEX_WARNING_TEXT = (
    "KaTeX renders without a preamble: it cannot use \\usepackage or this "
    "document's own macros. \\bm alone occurs 327 times across the corpus, "
    "\\Perp is defined by no package and spans 10 documents, and 11,088 of "
    "11,624 undefined occurrences are the source document's own macros. "
    "A row that looks wrong here may be correct, and one that looks right "
    "here may not compile. Judge from the LaTeX report."
)

#: the same sentence as a banner, for an HTML page
KATEX_WARNING_HTML = (
    '<div class="katex-caveat" role="note" style="margin:0 0 1rem;'
    'padding:.6rem .8rem;border-left:4px solid #c47f00;background:#fff8e6;'
    'color:#4a3c14;font:13px/1.5 -apple-system,system-ui,sans-serif">'
    '<strong>The rendered column is KaTeX, and KaTeX has no preamble.</strong> '
    'It cannot use <code>\\usepackage</code> or this document&rsquo;s own '
    'macros. Corpus-wide, <code>\\bm</code> occurs 327 times, '
    '<code>\\Perp</code> is defined by no package and spans 10 documents, and '
    '11,088 of 11,624 undefined occurrences are the source document&rsquo;s '
    'own macros. <strong>A row that looks wrong here may be correct, and one '
    'that looks right here may not compile.</strong> The LaTeX report renders '
    'through the document&rsquo;s own preamble and is the surface to judge '
    'from.</div>'
)
