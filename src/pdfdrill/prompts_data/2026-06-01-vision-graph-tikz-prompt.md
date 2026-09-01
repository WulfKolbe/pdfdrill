# Vision Graph Tikz

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.openai_vision.GRAPH_TIKZ_PROMPT`.

**Sent by** openai_vision, graph/subgraph crops

Reconstruct a vertices-and-edges diagram as standalone TikZ.

Everything below the `---` is the prompt. Nothing above it is sent.

---
This image is a GRAPH or SUBGRAPH diagram (vertices and edges) that OCR could not resolve. Reconstruct it as a faithful, standalone TikZ picture:
- place every vertex (node) in roughly its observed position;
- draw every edge between the correct vertices;
- preserve colour/emphasis (e.g. a red or highlighted complete-bipartite subgraph) using the matching TikZ colour;
- transcribe any vertex/edge labels you can read.
Return a JSON object: {"selector":"tikzpicture","tikzpicture":"\\begin{tikzpicture} ... \\end{tikzpicture}"} with ONLY the tikzpicture field filled. No markdown fences, no explanation.