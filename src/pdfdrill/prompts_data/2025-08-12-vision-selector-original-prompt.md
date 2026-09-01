# Vision Selector — The Original

The ancestor of the vision selector, recovered by 466 from
`~/Downloads/csp/prompt.txt` (mtime 2025-08-12; a byte-identical copy sits at
`~/MX/parsemarkdownhtml/parsemarkdownGPT5/prompt.txt`, sha256 2f3a7248fe87…).
It is not loaded by anything. It is here so the lineage is readable.

THREE GENERATIONS, and only the first two were ever files:

| when | where | field | selectors |
|---|---|---|---|
| 2025-08-12 | `~/Downloads/csp/prompt.txt` | `content` | 6 |
| 2026-05-08 | `~/MX/mathpix_images/csp/prompt.txt` | `selector` | 7 |
| now | `2026-06-01-vision-selector-prompt.md` | `selector` | 16 |

`openai_vision.py` carried the comment *"ported verbatim from
mathpix_images/prompt.txt"*. It is not verbatim: 123 diff lines, and the
selector list grew from `empty|math|commutative_diagram|gnuplot|tikzpicture|
tensor` to sixteen, adding text, handwriting, table, annotated_math with its
overlay, two chemistry routes, diagram, chart, photo and logo. The comment
asserted a provenance that had stopped being true, which is the thing this
whole convention exists to prevent — a claim about which prompt was used,
made by a comment nobody re-checked.

Everything below the `---` is the prompt as it was in 2025.

---

You are given a base64 encoded image that has not been resolved by an OCR service. Please analyze the image content and return a JSON object with the following structure:
{
  "content": "{empty,math,commutative_diagram,gnuplot,tikzpicture,tensor}",
  "math": "optional math expression if applicable",
  "commutative_diagram": "optional LaTeX code for commutative diagram if applicable",
  "gnuplot": "optional GnuPlot code if applicable",
  "tikzpicture": "optional LaTeX code for tikzpicture if applicable",
  "tensor": "optional LaTeX code for tensor diagram if applicable"
}
Instructions:
- content should be 'empty' if the area is blank.
- content should be 'math' if the area contains a math expression not resolved by MathPix, and the math key should contain the LaTeX representation.
- content should be 'commutative_diagram' if the area contains a commutative diagram, and the commutative_diagram key should contain the LaTeX code using the `tikz-cd` package.
- content should be 'gnuplot' if the area contains a graph which can be generated using GnuPlot, and the gnuplot key should contain the GnuPlot code.
- content should be 'tikzpicture' if the area contains a diagram that can be generated using the LaTeX `\begin{tikzpicture}` environment, and the tikzpicture key should contain the LaTeX code.
- content should be 'tensor' if the area contains a tensor diagram with circles and arrows, and the tensor key should contain the LaTeX code using the `tikz` package.

**Example Outputs:**
- **Case A:** `E = mc^2`
- **Case B:** 
`\[
\begin{tikzcd}
A \arrow[r] \arrow[d] & B \arrow[d] \\
C \arrow[r] & D
\end{tikzcd}
\]`

- **Case C:**

\begin{figure}%
\centering%
\begin{gnuplot}[terminal=latex, terminaloptions=rotate]
set key box top left
set key width 4
set sample 1000
set xr [-5:5]
set yr [-1:1]
set xlabel ’$x$-label’
set ylabel ’$y$-label’
plot sin(x) w l lc 1 t ’$\sin(x)$’,\
cos(x) w l lc 2 t ’$\cos(x)$’,\
tan(x) w l lc 3 t ’$\tan(x)$’,\
tanh(x) w l lc 4 t ’$\tanh(x)$’
\end{gnuplot}
\caption{This is a simple example using the latex-terminal.}%
\label{pic:latex}%
\end{figure}%
 
- **Case D:** 

`\begin{figure}[h!]
    \centering
    \includegraphics[width=\textwidth]{xy_graph.png}
    \caption{An XY-Graph extracted from the document}
    \label{fig:xy_graph}
\end{figure}`

- **Case E:**

\documentclass{standalone}
\usepackage{tikz}
\usetikzlibrary{arrows.meta}

\begin{document}
\begin{tikzpicture}

% Define colors
\definecolor{mypink}{RGB}{255,20,147}
\definecolor{myblue}{RGB}{0,191,255}
\definecolor{mypurple}{RGB}{128,0,128}

% Draw horizontal line segments
\draw (-3,0) -- (-1,0);
\draw (1,0) -- (5,0);

% Draw nodes
\fill[gray] (-2,0) circle (0.3);
\fill[mypink] (2,0) circle (0.3);
\fill[myblue] (3,0) circle (0.3);
\fill[mypurple] (4,0) circle (0.3);

% Draw curved arrows
\draw[-{Stealth[length=3mm]}, thick] (-2,0.4) to[out=30,in=150] node[above] {decompose} (3,0.4);
\draw[-{Stealth[length=3mm]}, thick] (3,-0.4) to[out=210,in=330] node[below] {compose} (-2,-0.4);

\end{tikzpicture}
\end{document}