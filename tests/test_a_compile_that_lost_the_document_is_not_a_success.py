r"""`latex --compile` may not report success for a PDF that lost the document.

T-0156 class G (pdfdrill-58's craft-libs findings, base 0be8abcf): over eight
e-prints from the library, `pdfdrill latex <pdf> --compile` exited 0 on 8 of 8
while producing **no PDF on 7**, and printed `compiled ✓` on the eighth —
2602.11699v3 — whose PDF is ONE page holding 0.3% of the paper's words.

A false success is red under group rule 7 (reporting stays honest). The same
defect was fixed for `glyphlines` under T-0153: "a reader that failed exits
non-zero. This returned a plain string, so the process exited 0 and a caller
that checks the status went on with no reading."

THE THRESHOLD IS MEASURED, not chosen. Re-measured today on the audit's own
copies, counting the `.tex`'s words with commands, comments and maths stripped
against `pdftotext` on the PDF beside it:

    2602.11699v3   the PDF that printed ✓      25 of 7369 words   0.0034
    1909.00741     compiled here for calibration
                   (xelatex exit 1, 344 errors, 24 pages)      6695 of 7014   0.9545

A complete compile scores 0.95 and the fragment 0.0034 — two orders of
magnitude apart — so half the words separates them with nothing tuned. It is
not a quality bar: a document that compiles with errors but renders is a
success, and `_COMPILE_MIN_SHARE` exists only to catch a PDF that is not the
document at all.

(Also measured, and NOT changed here: `-halt-on-error` is why 7 of 8 produced
no PDF. Without it 1909.00741 yields that 95%-complete 24-page PDF. Reported
separately — it widens what compiles, which is a different decision from
refusing to lie about what did.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

C = pytest.importorskip("pdfdrill.commands")


def test_a_tex_file_s_words_exclude_markup():
    """Commands, comments and maths are not the document's words."""
    tex = ("% a comment\n"
           "\\documentclass{article}\\begin{document}\n"
           "Hello brave new world $x^2 + \\alpha$ and more.\n"
           "\\end{document}\n")
    # Six: Hello brave new world and more. `article` and `document` are the
    # arguments of structural commands — markup, not words, and the first
    # version of this counted them, flattering every share it computed.
    assert C._tex_text_words(tex) == 6


def test_a_fragment_is_not_a_compiled_document():
    """2602.11699v3's real numbers: 25 words out of 7369."""
    assert C._compile_is_complete(25, 7369) is False


def test_a_document_that_compiled_with_errors_is_a_success():
    """1909.00741's real numbers: 6695 of 7014, from a run with 344 errors."""
    assert C._compile_is_complete(6695, 7014) is True


def test_exactly_the_threshold_passes():
    assert C._compile_is_complete(50, 100) is True


def test_an_empty_source_cannot_be_judged():
    """No words to compare against: do not invent a verdict either way."""
    assert C._compile_is_complete(0, 0) is True
