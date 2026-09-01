"""390-392 — ONE figure-recovery prompt, and the preamble its replies compile in.

Shared deliberately. 391 rescues MathPix crops that have no reference, and 392
measures the same prompt on DaTikZ rows where the author's code is known. If
the two used different prompts, 392's distance distribution would not say
anything about 391's rescues, and saying something about them is the whole
reason 392 exists.
"""
from pdfdrill import prompts

SYSTEM = ("You read an image of a figure from a mathematics or science paper "
          "and return LaTeX/TikZ that reproduces it. Return ONLY code. No "
          "explanation, no commentary, no markdown fence.")

PROMPT = prompts.load("recover-figure")

#: 391 — the fallback preamble, and why it is fixed rather than requested.
#:
#: 337's single compile error was a missing \usepackage line. Asking the model
#: to emit its own preamble makes every reply a chance to reintroduce exactly
#: that, and a reply that draws the figure correctly but forgets
#: \usetikzlibrary{arrows.meta} is scored as a failure of the drawing. A fixed
#: preamble removes the one error we actually observed, and it removes it for
#: every reply at once rather than one prompt revision at a time.
#:
#: The libraries are loaded unconditionally. An unused \usetikzlibrary costs
#: nothing; a missing one costs the row.
PREAMBLE = r"""\documentclass[tikz,border=2pt]{standalone}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{tikz}
\usetikzlibrary{arrows,arrows.meta,positioning,shapes,shapes.geometric,
                shapes.misc,calc,decorations.pathmorphing,
                decorations.markings,decorations.text,patterns,
                patterns.meta,fit,backgrounds,matrix,chains,trees,mindmap,
                intersections,through,angles,quotes,babel,3d,perspective,
                spy,external,plotmarks,datavisualization}
\usepackage{tikz-cd}
\usepackage{circuitikz}
\begin{document}
%s
\end{document}
"""


def wrap(body: str) -> str:
    """A reply into a compilable document.

    A reply that DID emit a full document is passed through untouched — the
    366 lesson, which cost 100 of 100 compiles: wrapping something that
    already has \\documentclass puts a document class inside a document body
    and measures the wrapper instead of the code.
    """
    body = strip_fence(body)
    if "\\documentclass" in body:
        return body
    return PREAMBLE % body


def strip_fence(text: str) -> str:
    """Markdown fences, which the system prompt forbids and models emit anyway."""
    t = text.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
