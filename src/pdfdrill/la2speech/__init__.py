"""
la2speech — LaTeX in, TTS-ready plain text out (vendored).

Ported from the standalone `~/la2speech` project so pdfdrill owns every
integration detail and no code lives outside this repo (the same move made for
SCANDRILL). Unchanged apart from the two intra-package imports.

The Python side is vendored; the SPEECH ENGINE is not. `SRESpeechBackend` drives
the npm `speech-rule-engine` (the engine inside MathJax) as a long-lived node
process over NDJSON — 9.6 MB of JavaScript that belongs in an install step, not
in git, exactly like poppler or tesseract. `pdfdrill doctor` reports whether it
is present; `src/pdfdrill/la2speech/setup.sh` installs it.

Public API used by `pdfdrill speak`:

    from pdfdrill.la2speech import SRESpeechBackend, LatexSpeaker
    with SRESpeechBackend(sre_dir, domain="clearspeak") as be:
        sp = LatexSpeaker(be)
        sp.speak_math(r"\\int_0^\\infty e^{-x^2}\\,dx")
        sp.errors            # per-fragment failures, accumulated not raised
"""
from .latex2speech import (SRESpeechBackend, LatexSpeaker,      # noqa: F401
                           normalize_whitespace)

__all__ = ["SRESpeechBackend", "LatexSpeaker", "normalize_whitespace"]


# Vendored from ~/la2speech at b7e420c ("clean_math: multi-letter style alphabets
# become \text{}"). Changes are limited to imports: sibling modules are now
# addressed as package-relative (`from . import latexproject`), including the
# function-level imports inside latex2speech/projections/tiddlerpipe. The
# upstream test suite lives at tests/la2speech/ and is driven by
# tests/test_la2speech_vendored.py.
