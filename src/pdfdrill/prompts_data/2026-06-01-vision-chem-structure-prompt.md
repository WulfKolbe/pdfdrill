# Vision Chem Structure

Runtime prompt, moved out of Python by 466. Before the move it was
`pdfdrill.openai_vision.CHEM_STRUCTURE_PROMPT`.

**Sent by** openai_vision, chemical structures

Reconstruct a drawn 2D structure or reaction scheme as chemfig.

Everything below the `---` is the prompt. Nothing above it is sent.

---
This image is a CHEMICAL STRUCTURE or REACTION SCHEME that OCR could not resolve. Reconstruct it as faithful chemfig LaTeX code:
- skeletal/bond-line formulas with chemfig bond syntax (- single, = double, ~ triple, angled bonds -[:30], branches in parentheses);
- ring systems with the *n(...) ring syntax (benzene: *6(-=-=-=), fused rings by chaining);
- preserve every heteroatom, charge (\oplus / ^{+}), wedge/dash stereo bonds (< / <:), and substituent label exactly as drawn;
- if the image is a reaction scheme with several drawn structures, wrap everything in \schemestart ... \schemestop and connect the structures with \arrow, placing reagents/conditions above the arrow as \arrow{->[\chemname{}{reagent}]} or ->[text];
- if instead the content is only a line formula / reaction EQUATION in plain text (no drawn bonds), return selector "chemical_equation" with an mhchem \ce{...} expression in "mhchem".
Return a JSON object: {"selector":"chemical_structure","chemfig":"\\chemfig{...}"} (or the chemical_equation/mhchem pair) with ONLY that field filled. Body code only — no preamble. No markdown fences, no explanation.