# Llm Generic

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.commands._LLM_PROMPT`.

**Sent by** commands, the generic LLM route

Everything below the `---` is the prompt. Nothing above it is sent.

---
For each entry below, open the image at `cdn_url` and transcribe ONLY the mathematics as a single LaTeX string (no surrounding $ or \[ \]; use \begin{aligned}...\end{aligned} for multi-line). Return a JSON list of {"eq_id": <unchanged>, "latex": <your LaTeX>}. Keep eq_id exactly as given.