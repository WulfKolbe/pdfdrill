# Vision Selector

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.openai_vision.DEFAULT_PROMPT`.

**Sent by** openai_vision.describe → GPT-4o

THE VISION SELECTOR. Classifies an unresolved crop into one of 16 selectors and fills only that field. See the provenance note below — it is the descendant of the original ChatGPT prompt.

Everything below the `---` is the prompt. Nothing above it is sent.

---
You are given a base64-encoded image crop that an OCR service could NOT resolve and left as a raw image. Identify what it contains and return a JSON object with this structure:

{
  "selector": "text|handwriting|table|math|annotated_math|chemical_equation|chemical_structure|commutative_diagram|gnuplot|tikzpicture|tensor|diagram|chart|photo|logo|empty",
  "text": "verbatim transcription of printed OR handwritten text",
  "table": "LaTeX tabular for a data table",
  "math": "LaTeX math expression",
  "annotated_math": "the mathematics ONLY - the delimiter pair and its contents, e.g. \\left[\\begin{array}{ccc}...\\end{array}\\right]",
  "annotation_overlay": "tikzpicture BODY drawing only what lies OUTSIDE the delimiters - arrows, braces, labels - positioned relative to the node named (M)",
  "mhchem": "mhchem \\ce{...} expression for a chemical formula/equation",
  "chemfig": "chemfig LaTeX code for a 2D molecular structure or reaction scheme",
  "commutative_diagram": "tikz-cd code",
  "gnuplot": "GnuPlot script reproducing a plot",
  "csv_data": "extracted plot data as CSV",
  "tikzpicture": "tikzpicture LaTeX code",
  "tensor": "tensor diagram LaTeX code",
  "description": "concise factual description for diagram/chart/photo/logo"
}

CLASSIFICATION RULES — fill ONLY the field named by selector.
- "text" - printed prose/labels/numbers/addresses. Transcribe verbatim into "text".
- "handwriting" - cursive or hand-printed writing. Transcribe your best reading into "text".
- "table" - rows/columns of text or numbers. Fill "table" with a \begin{tabular}...\end{tabular} reproducing every visible cell, row by row.
- "math" - a math expression. Fill "math" with LaTeX in $$ delimiters.
- "annotated_math" - mathematics inside a DELIMITER PAIR (brackets, parentheses, braces, bars) with text, arrows, braces or labels positioned OUTSIDE that pair: row-operation arrows beside a matrix, an underbrace naming a block, "n columns" over a bracket, a label pointing at one entry. Fill BOTH fields, never one: "annotated_math" with the delimiter pair and its contents alone, and "annotation_overlay" with tikzpicture body code for everything outside it, positioned relative to a node called (M) which will contain the mathematics. Do NOT copy the annotation into the array - an arrow or a word inside a cell is the failure this selector exists to prevent.
- "chemical_equation" - a chemical formula, ion, isotope, or reaction equation written as TEXT on one line (e.g. 2H2 + O2 -> 2H2O, SO4^2-, ^{227}_{90}Th, CrO4^2- <=> Cr2O7^2-). Fill "mhchem" with one \ce{...} expression using mhchem v4 syntax: digits become subscripts automatically, charges as ^2- / ^+, arrows as ->, <-, <=>, states as (s)/(aq)/(g), precipitate v, gas ^, reaction conditions above arrows as ->[\text{...}].
- "chemical_structure" - a DRAWN 2D molecular structure: skeletal/bond-line formula, ring system, Lewis structure, or a reaction scheme whose participants are drawn structures. Fill "chemfig" with chemfig code: bonds - = ~ and angle bonds like -[:30]; rings as *6(...) (e.g. benzene *6(-=-=-=)); branches in parentheses; charges as \oplus/\ominus or ^{+}/^{-} in atom labels; Lewis electron pairs via \charge/\Lewis. For a multi-structure reaction scheme wrap the whole thing in \schemestart ... \schemestop and connect structures with \arrow (reagents above the arrow as \arrow{->[reagent]}). Output only body code (no preamble, no \documentclass).
- "commutative_diagram" - fill "commutative_diagram" with tikz-cd code.
- "gnuplot" - a data plot: fill "csv_data" with every readable data point (CSV, header row, x in column 1) AND "gnuplot" with a complete self-contained script reading 'data.csv'.
- "tikzpicture" - general TikZ-style line drawing. Fill "tikzpicture".
- "tensor" - tensor network diagram. Fill "tensor".
- "diagram" / "chart" / "photo" / "logo" - a picture with no transcribable text. Fill "description".
- "empty" - ONLY for a genuinely blank/featureless area.

ANNOTATION DISAMBIGUATION: a matrix or aligned block with NOTHING outside its delimiters is "math", not "annotated_math". A drawing whose main content is lines and nodes rather than a delimited expression is "tikzpicture". Choose "annotated_math" only when BOTH are present: real mathematics inside delimiters, AND marks outside them.

CHEMISTRY DISAMBIGUATION: element symbols with stoichiometric subscripts, charges, or reaction arrows = "chemical_equation" (NOT "math"); any drawing with bond lines, rings, or wedge/dash bonds = "chemical_structure" (NOT "diagram" or "tikzpicture"). A subscripted variable like x_2 with no element symbols stays "math".

IMPORTANT: faint, low-contrast, light-grey, or cursive content is NOT empty. If you can perceive ANY strokes, glyphs, lines, or marks, classify and extract them (use "handwriting" or "text" for writing, "diagram" otherwise). Reserve "empty" for a truly blank crop.

Return ONLY the JSON object. No markdown fences, no explanation.