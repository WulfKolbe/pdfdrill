r"""What a reading says, with the markup it says it in removed.

Gate line 3 of every reading change is "zero content characters lost", and the
counter behind it was wrong three times in one day — each time reporting a loss
that was a GAIN in structure, and each time caught only by listing the
characters instead of trusting the total:

    1. a command that STANDS FOR a character
       `α0 = 12` -> `\alpha_{0} = \frac{1}{2}`     8 "lost" Greek letters
       (θ ϕ ω Λ α), which had become `\theta`, `\omega`, `\alpha` BECAUSE the
       terms now assemble. Stripping `\[A-Za-z]+` threw the character away
       with the command.

    2. a structural command's ARGUMENT
       `\documentclass{article}\begin{document}` contributed the words
       `article` and `document`, so an almost-empty preamble scored words it
       does not carry.

    3. an ENVIRONMENT NAME
       `\begin{array}{c}` -> `\begin{smallmatrix}`  60 "lost" letters of
       "array" plus the `{c}` spec, against "smallmatrix"'s letters gained.

A total is not evidence until the characters behind it have been named. This
module exists so the fourth variant fails a test instead of a board run.

The command-to-character bridge is `mathgold.floor.LATEX_UNICODE`, whose 64
entries were each chosen by MEASURING what the text layer emits for that
construct — never a mapping invented here.
"""
from __future__ import annotations

import collections
import re

from .floor import LATEX_UNICODE

#: `\begin{env}` / `\end{env}`, with an `array`-style column spec.
_ENV = re.compile(r"\\(?:begin|end)\{[^{}]*\}(?:\{[^{}]*\})?")
#: a command whose braced argument is structure, not words.
_STRUCTURAL = re.compile(
    r"\\(?:documentclass|usepackage|label|ref|eqref|cref|autoref|cite[a-z]*|"
    r"input|include|includegraphics|bibliography|bibliographystyle|"
    r"newcommand|renewcommand|definecolor|geometry|hypersetup|setlength|"
    r"pagestyle)\*?(?:\[[^\]]*\])*(?:\{[^{}]*\})*")
_CMD = re.compile(r"\\[A-Za-z]+")


def content_chars(text: str) -> "collections.Counter[str]":
    r"""The alphanumeric characters a reading CARRIES, markup excluded.

    A command that stands for a character resolves to it, so `\alpha` counts
    the one `α` it sets; every other command, and the arguments that are
    structure rather than words, count nothing.
    """
    text = _ENV.sub(" ", text)
    text = _STRUCTURAL.sub(" ", text)
    text = _CMD.sub(lambda m: LATEX_UNICODE.get(m.group(0), " "), text)
    return collections.Counter(c for c in text if c.isalnum())


def content_delta(before: str, after: str) -> "tuple[int, int]":
    """`(lost, gained)` content characters from `before` to `after`."""
    a, b = content_chars(before), content_chars(after)
    lost = sum(max(0, a[c] - b.get(c, 0)) for c in a)
    gained = sum(max(0, b[c] - a.get(c, 0)) for c in b)
    return lost, gained
