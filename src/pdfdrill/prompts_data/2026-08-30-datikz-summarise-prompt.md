# Datikz Summarise

Runtime prompt, moved out of Python by 466. Before the move it was
`tools/datikz_summarise.py:PROMPT`.

**Sent by** tools/datikz_summarise.py

Everything below the `---` is the prompt. Nothing above it is sent.

---
Summarise this TikZ picture in one sentence, under 20 words.
State the kind — one of: plot, commutative diagram, graph or network, geometric figure, circuit, tree, flowchart, table-like grid, illustration, other.
Then the elements that dominate it — axes, nodes, arrows, curves, labels, shading, coordinates.
Describe what is drawn. Do not describe the code, do not name TikZ libraries, do not begin with "This figure".

%s