# pdf2mmd — running it on your own PDFs

Everything is in this folder. Nothing needs installing: the interpreter and
its patched pdfminer live in `.pdfmm-venv/`, and the launcher finds them.

## Run it

    ~/Downloads/pdf2mmd/pdf2mmd paper.pdf              # whole document
    ~/Downloads/pdf2mmd/pdf2mmd paper.pdf 1-6          # just those pages
    ~/Downloads/pdf2mmd/pdf2mmd paper.pdf all out/     # and where to put it
    ~/Downloads/pdf2mmd/pdf2mmd -c paper.pdf 1-6       # also compile the .tex

Works from any directory. Output goes to a folder named after the PDF unless
you name one.

Put it on your PATH if you like:

    ln -s ~/Downloads/pdf2mmd/pdf2mmd ~/.local/bin/pdf2mmd

## What you get

    <stem>.md              Markdown, LaTeX inline, `$$` for displays.
                           Equation numbers appear as `\tag{3}`, because
                           Markdown has no numbering of its own.
    <stem>.tex             the same reading as LaTeX, with a preamble
                           DERIVED from the fonts the document used --
                           amssymb only if it needs it, dsfont only if the
                           document sets a double-struck symbol, and so on.
                           Equation numbers are NOT written: `\begin{equation}`
                           prints them itself.
    <stem>.report.txt      what projected, what did not, and why.  READ THIS.
    <stem>.lines.json      the geometry, in MathPix's shape.
    <stem>.fonts.md        the type sizes behind the heading levels.
    <stem>.equations.json  one row per equation, with its crop region.
    model.docmodel.json    the full document model.

With `-c` you also get `<stem>.pdf` — a proof copy. The `\includegraphics`
lines are commented out in it, because a crop link points at a server that
is not running; the uncommented original is kept as `<stem>.withcrops.tex`.

## Exit status

    0   converted
    2   NO TEXT WAS READ.  The PDF has no text layer on those pages: it is a
        scan, or the page is one image.  This reader works from glyphs and
        cannot help; that document needs OCR.
    1   usage error, or the conversion failed

## What it refuses, and why that is the point

Mathematics it cannot assemble is NOT guessed. The span is left out and a
crop link to that exact rectangle is written instead, with the reason beside
it (`fraction`, `script-or-multi-baseline`, `unmapped-glyph:<name>`). The
report totals them. A wrong `\frac` is worse than a picture of the right
one, because nothing marks it as wrong.

A page whose glyphs are all invisible (`Tr 3`) is refused outright: that is a
scanner's OCR layer over a raster, and projecting it would produce confident
nonsense.

## Seeing the crops

    ~/Downloads/pdf2mmd/pdf2mmd.sh paper.pdf 1-6 out/

does the same conversion AND renders the page images the crop links resolve
against; `SERVE=1` in front of it starts the little server afterwards.

## If the LaTeX will not compile

Compile with **xelatex**, not pdflatex — the output carries real Unicode.
`-c` already does. The preamble names anything it could not place:

    % WARNING: commands with no known package: ...
    % WARNING: no translation for, and no font here sets: U+2ADF ...
    % WARNING: 1 private-use codepoint(s) removed ...

Those lines are the reader telling you what it was unsure of. They are not
noise.
