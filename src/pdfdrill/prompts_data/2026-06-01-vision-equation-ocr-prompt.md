# Vision Equation Ocr

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.openai_vision.EQ_OCR_PROMPT`.

**Sent by** openai_vision, one equation crop

Everything below the `---` is the prompt. Nothing above it is sent.

---
You are standing in for MathPix's equation OCR on ONE rendered page. A keyless tesseract pass already captured the prose, but it CANNOT type mathematics. Look at the page IMAGE and extract every DISPLAY equation (and any standalone display formula). Return ONLY a JSON array — no prose, no code fence — of objects of this exact shape:
  {"page": <int>, "number": <string|null>, "latex": "<LaTeX>", "kind": "equation"|"math"}
Rules:
- One object per display equation, in top-to-bottom reading order.
- `latex`: faithful, COMPILABLE LaTeX. PRESERVE the 2-D structure — subscripts _{}, superscripts ^{}, fractions \frac{}{}, roots \sqrt{}. NEVER linearise. WRONG (flattened): `M = m a (F + j ) (B65)` with the subscripts dropped onto other lines. RIGHT: `M = m_a (F + j_0)`. Do NOT put the equation number inside `latex`.
- `number`: the printed equation number WITHOUT parentheses (e.g. 'B65', '12'), or null if the equation is unnumbered.
- `kind`: 'equation' for a numbered/display equation, 'math' for an unnumbered display formula.
- If the page has NO display mathematics, return exactly `[]`. Never invent, guess, or fabricate an equation you cannot read clearly — omit it instead.
Output ONLY the JSON array for this one page.