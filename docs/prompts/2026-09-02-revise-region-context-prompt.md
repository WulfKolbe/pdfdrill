# Revise Region With Context

Runtime prompt (487). The context-carrying counterpart of
[`revise-region`](2026-09-01-revise-region-prompt.md), which 448 measured and
which carries the crop and the existing reading alone.

**Sent by** `tools/ctx507.py` → MiniMax-m3 (Novita), arm B.

Substituted with `.replace`, NOT `.format` — 448 learned that
`\usetikzlibrary{arrows.meta, positioning}` inside a body reads as a format
placeholder and raises `KeyError('arrows')`. Placeholders: `{conf}`,
`{latex}`, `{context}`.

`{context}` is assembled by `pdfdrill.reccontext` and is EMPTY when nothing is
known — 488 measured that an abstract exists in 67% of documents and not in
johnston at all, and that a section path exists for 74% of book math objects
under 506's gate. A field that is unknown is omitted; none is ever rendered
as a placeholder, because "section: (unknown)" teaches the model that the
section is called unknown.

Everything below the `---` is the prompt. Nothing above it is sent.

---

The image is a crop of ONE region of a printed page. It may be an equation, a
complete float, a table, or a fragment of running text — do not assume it is
mathematics.

An OCR reader has already transcribed it, at confidence {conf}, as:

{latex}

{context}

Return the LaTeX that reproduces WHAT THE CROP SHOWS, and nothing else.

Rules, in order of precedence:

1. The crop is the evidence. Where the crop and the existing reading disagree,
   the crop wins. Where the crop is illegible, keep the existing reading
   rather than inventing a replacement.
2. Reproduce only what is inside the crop. Do not add a wrapper, a caption, a
   label, or an environment that is not visible.
3. Keep the existing reading's alphabet unless the crop shows otherwise. A
   script letter and a calligraphic one are different glyphs, and the
   difference is visible: the script forms carry a swash or a crossing
   stroke.
4. If the existing reading is already correct, return it unchanged. Returning
   the input is a valid answer and is preferred to a rewrite that changes
   nothing but the spelling.
5. Return the LaTeX body only — no `$`, no `\[`, no `\begin{document}`, no
   explanation, no commentary, no code fence.
