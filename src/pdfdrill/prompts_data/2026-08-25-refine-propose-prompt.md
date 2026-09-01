# Refine Propose

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.refine.PROPOSE_PROMPT`.

**Sent by** refine.propose_one, TEXT arm

`.format(conf=…, latex=…)`. Used when there is no crop.

Everything below the `---` is the prompt. Nothing above it is sent.

---
This LaTeX came from OCR of a printed equation and its confidence is {conf}.
It may have lost or merged rows, dropped cells from an aligned table, or run two
columns of the page together.

Return a corrected LaTeX body for the SAME equation. Rules:
  - return the body only, with no $ or \[ delimiters and no code fence
  - keep every environment balanced
  - if it is a table of numbers, every row must have the same number of cells
  - do not invent content you cannot see in the source below

SOURCE:
{latex}
