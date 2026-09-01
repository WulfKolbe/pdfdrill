# Vision Selector — The 2026-05 Revision

The middle generation, recovered by 466 from `~/MX/mathpix_images/csp/prompt.txt`
(mtime 2026-05-08, sha256 2c49cd71c3ef…). Not loaded by anything; kept so the
step between [the original](2025-08-12-vision-selector-original-prompt.md) and
the current selector is readable rather than inferred.

What changed from the original: the JSON field `content` became `selector`,
and `csv_data` joined `gnuplot`.

---

You are given a base64 encoded image that has not been resolved by an OCR service.
Analyze the image content and return a JSON object with this structure:

{
  "selector": "empty|math|commutative_diagram|gnuplot|tikzpicture|tensor",
  "math": "optional LaTeX math expression",
  "commutative_diagram": "optional tikz-cd code",
  "gnuplot": "optional GnuPlot rendering commands",
  "csv_data": "optional extracted plot data as CSV",
  "tikzpicture": "optional tikzpicture LaTeX code",
  "tensor": "optional tensor diagram LaTeX code"
}

---

CLASSIFICATION RULES

- "empty" — blank area. All other fields empty.
- "math" — unresolved math expression. Fill "math" with LaTeX in $$ delimiters.
- "commutative_diagram" — commutative diagram. Fill "commutative_diagram" with
  tikz-cd code (no \begin{document}...\end{document}).
- "gnuplot" — data plot / graph. See GNUPPLOT RULES below.
- "tikzpicture" — general TikZ diagram. Fill "tikzpicture".
- "tensor" — tensor network diagram with circles and arrows. Fill "tensor".

---

GNUPPLOT RULES (CRITICAL — read carefully)

When selector is "gnuplot", the image contains a data plot. You must do TWO things:

1. EXTRACT THE DATA — Read every visible data point from the plot and write it
   as CSV in the "csv_data" field. The first row is a header. The first column
   is the independent variable (x-axis). Subsequent columns are the dependent
   variables, one per legend entry, named exactly as they appear in the legend.
   Use comma as delimiter. Do not add extra spaces. Example:

   fraction,Blue,Red,Green
   0.15,0.055,0.050,0.045
   0.16,0.050,0.045,0.040
   ...

   Estimate values as precisely as possible from the plot. If the plot has
   error bars, extract the center value. If values are hard to read, give your
   best estimate — do not skip or leave gaps.

2. GENERATE THE GNUPLOT SCRIPT — Write a COMPLETE, self-contained GnuPlot
   script in the "gnuplot" field that reads the CSV file "data.csv" and
   reproduces the plot. The script MUST include:

   - set terminal pngcairo enhanced size 800,600
   - set output '<descriptive_name>.png'
   - set title matching the original plot title (if visible)
   - set xlabel / set ylabel matching the original axis labels
   - set key at the same position as the original (top right, top left, etc.)
   - set grid
   - set style data linespoints
   - One plot clause per series, matching the ORIGINAL colors, line widths,
     point types, and dash patterns shown in the legend.
   - Use lc rgb '#rrggbb' or named colors matching what you see.
   - Use pt (point type) and lw (line width) matching the original.
   - Use proper line continuation (backslash at end of each line except last).

   IMPORTANT: The "gnuplot" field must contain ONLY the GnuPlot commands.
   Do NOT wrap it in \begin{gnuplot}...\end{gnuplot} or any LaTeX environment.
   Do NOT include \documentclass or \begin{document}.

---

EXAMPLES

Case A (math):
{"selector":"math","math":"$$E = mc^2$$","commutative_diagram":"","gnuplot":"","csv_data":"","tikzpicture":"","tensor":""}

Case B (commutative_diagram):
{"selector":"commutative_diagram","math":"","commutative_diagram":"\\begin{tikzcd}\nA \\arrow[r] \\arrow[d] & B \\arrow[d] \\\\\nC \\arrow[r] & D\n\\end{tikzcd}","gnuplot":"","csv_data":"","tikzpicture":"","tensor":""}

Case C (tikzpicture):
{"selector":"tikzpicture","math":"","commutative_diagram":"","gnuplot":"","csv_data":"","tikzpicture":"\\begin{tikzpicture}\n\\fill[gray] (0,0) circle (0.3);\n\\draw[->] (0,0) -- (2,0);\n\\end{tikzpicture}","tensor":""}

Case D (tensor):
{"selector":"tensor","math":"","commutative_diagram":"","gnuplot":"","csv_data":"","tikzpicture":"","tensor":"\\begin{tikzpicture}\n\\fill[black] (0,0) circle (0.2);\n\\fill[black] (0,-1) circle (0.2);\n\\draw[thick] (0,0) -- (4,0);\n\\end{tikzpicture}"}

Case E (empty):
{"selector":"empty","math":"","commutative_diagram":"","gnuplot":"","csv_data":"","tikzpicture":"","tensor":""}

Case F (gnuplot — this is the format you MUST follow for data plots):
{"selector":"gnuplot","math":"","commutative_diagram":"","gnuplot":"set terminal pngcairo enhanced size 800,600\nset output 'bhattacharyya_plot.png'\nset title 'Bhattacharyya Distance vs. Fraction of Samples'\nset xlabel 'Fraction of Samples'\nset ylabel 'Bhattacharyya Distance'\nset key top right\nset grid\nset style data linespoints\nplot 'data.csv' using 1:2 with linespoints lc rgb 'blue' lw 2 pt 7 title 'Blue', \\\n     '' using 1:3 with linespoints lc rgb 'red' lw 2 pt 7 title 'Red', \\\n     '' using 1:4 with linespoints lc rgb 'green' lw 2 pt 7 title 'Green'","csv_data":"fraction,Blue,Red,Green\n0.15,0.055,0.050,0.045\n0.16,0.050,0.045,0.040\n0.17,0.045,0.040,0.035\n0.18,0.040,0.035,0.030\n0.19,0.035,0.030,0.025\n0.20,0.030,0.025,0.020","tikzpicture":"","tensor":""}

---

Return ONLY the JSON object. No markdown fences, no explanation.
