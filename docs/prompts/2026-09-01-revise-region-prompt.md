# Revise Region

Runtime prompt, moved out of Python by 466. Before the move it was
`tools/prompt448.py:PROMPT`.

**Sent by** tools/prompt448.py → MiniMax-m3

448's revision prompt. Substituted with `.replace`, NOT `.format`: `\usetikzlibrary{arrows.meta, positioning}` inside the body reads as a format placeholder and raises KeyError('arrows').

Everything below the `---` is the prompt. Nothing above it is sent.

---
The image is a crop of ONE region of a printed page. It may be an
equation, a TikZ-style diagram, a table, or a mixture — do not assume it is
mathematics.

An OCR service read that region as the LaTeX below, with confidence {conf}.

Return LaTeX that reproduces WHAT THE IMAGE SHOWS.

REMOVE ANYTHING THE IMAGE DOES NOT SHOW. The reading may carry wrappers or
environments the crop cannot contain — a float, a caption, a list closer, a
section command. If it is not visible in the image, it is damage from the
segmentation and does not belong in your answer. Correcting structure is part
of the task, not a liberty.

Keep what the image does show, and keep it exactly: every string as printed,
every row and cell of a table, every node and edge of a diagram.

If the region is a DIAGRAM, give TikZ and be specific:
  - every label string as printed, and its font size if it differs
  - node positions and the direction of every arrow
  - line styles that carry meaning (dashed, dotted, double)
  - assume \usetikzlibrary{arrows.meta, positioning} is loaded and use it

If the region is a TABLE, give a tabular whose every row has the same number
of cells.

If the region is an EQUATION, give the body only — no $ or \[ delimiters —
with every environment balanced.

THE OCR'S READING:
{latex}
