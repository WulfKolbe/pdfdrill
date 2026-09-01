# Refine Propose Crop

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.refine.PROPOSE_PROMPT_C`.

**Sent by** refine.propose_one, CROP arm (variant C)

`.format(conf=…, latex=…)`. The arm 444 and 454 ran: the crop plus the existing reading.

Everything below the `---` is the prompt. Nothing above it is sent.

---
The image is a crop of one printed equation from a scanned page.

An OCR service read it as the LaTeX below, with confidence {conf}. That reading
may be right, or may have lost or merged rows, dropped cells from an aligned
table, or run two columns of the page together.

Correct it AGAINST THE IMAGE. Rules:
  - return the LaTeX body only, no $ or \[ delimiters and no code fence
  - keep every environment balanced
  - if it is a table of numbers, every row must have the same number of cells
  - prefer the existing reading where the image does not contradict it

THE OCR'S READING:
{latex}
