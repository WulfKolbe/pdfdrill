# Escalate

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.commands._ESCALATE_PROMPT`.

**Sent by** commands, the escalation route

Everything below the `---` is the prompt. Nothing above it is sent.

---
These equations were FLAGGED for review (low confidence or disagreement). For each, open the image at `cdn_url` and transcribe ONLY the mathematics as a single LaTeX string (no surrounding $; \begin{aligned} for multi-line). Return JSON list of {eq_id, latex}. A reading that corroborates the existing one will resolve the flag.