# Recover Figure

Runtime prompt, moved out of Python by 466. Before the move it was
`tools/recover_prompt.py:PROMPT`.

**Sent by** tools/recover_prompt.py

Everything below the `---` is the prompt. Nothing above it is sent.

---
The image is a figure from a paper.

Reproduce it as closely as you can in TikZ/pgfplots.

Return ONLY the body: \begin{tikzpicture} ... \end{tikzpicture}, or a
\begin{axis} inside one. Do not write \documentclass, \usepackage or
\begin{document} — a preamble is already supplied and yours would collide
with it. Do not use \includegraphics: draw the content, do not embed it.

Match the STRUCTURE first — the number of nodes, edges, axes, curves and
labels, and their arrangement. Exact colours and font sizes matter less than
getting the right things in the right places.

If part of the figure is illegible, draw what you can see and leave the rest
out rather than inventing content.