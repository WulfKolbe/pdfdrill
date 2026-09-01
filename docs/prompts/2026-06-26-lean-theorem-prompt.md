# Lean Theorem

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.lean_export.LEAN_THEOREM_PROMPT`.

**Sent by** lean_export

Everything below the `---` is the prompt. Nothing above it is sent.

---
Translate this mathematical statement from a research paper into a Lean 4 (Mathlib) declaration.

Output ONLY Lean 4 code (a fenced ```lean block is fine), no commentary:
- a `theorem {name} ... : ... := by sorry` (leave the proof as `sorry`)
- declare reasonable variables/hypotheses; prefer Mathlib names; invent nothing
- if the statement is too informal to formalise precisely, give your best-effort
  signature and add a `-- INFORMAL:` comment line with the original wording.

{kind}{number_part}{label_part}
LaTeX statement:
{statement}
