"""The report surface, redrawn (spec 2026-09-06-evidence-residuals-design).

Evidence = every LaTeX/image line of the document, one file per kind, for
lookup. Residuals = the open points only, sorted worst first. Both render
from the same row model, so HTML and PDF of one kind cannot disagree.
"""
KINDS = ("equation", "formula", "table", "image")
COLUMNS = ("Identifier", "Page", "Conf.", "LaTeX source", "Rendered", "Image")
