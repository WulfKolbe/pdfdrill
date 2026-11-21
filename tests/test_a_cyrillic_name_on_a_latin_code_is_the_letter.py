r"""A Cyrillic glyph NAME on a Latin letter's CODE is the Latin letter.

1805.01788 sets `log` in Linux Libertine italic, and the subset names the `g`
glyph `afii10069.ital` -- the AFII name for Cyrillic `de`, whose italic is
drawn like a Latin g. pdfminer resolves the NAME, so the reading said `loд`.

That is a wrong character, and it cost more than a character. `glyph_latex`
emits a bare letter only when it `isascii()`, so `д` deferred, the maths span
around it deferred with it, and the fraction it sat in was never built:

    page      DCG@k(r) = \sum_{i=1}^{k} \frac{2^{r(i)} - 1}{\log_2(i+1)}
    before    DCG@k $(r$ $) =$ $\sum^{k}$ i=1 2r ${}^{(i}$ ${}^{)} -$ 1loд2 $(i$ $+ 1)$
    after     DCG@k $(r$ $) =$ $\sum^{k}$ i=1 $\frac{2^{r (i )} - 1}{\log_{2} (i + 1)}$

`\log` arrives with it: the operator is only recognisable once its `g` is.

THE GENERAL RULE IS WRONG AND THE CENSUS SAYS SO. "Prefer the character code
to the glyph name" looks obvious and would have been a disaster: across the
ten documents of the inspect set, 620 glyphs decode to a non-Latin character
sitting on a printable ASCII code, and nearly every one is CORRECT -- TeX's
`'` -> U+2019, CMSY's `p` -> U+221A, `2` -> U+2208. Exactly four decode to
Cyrillic, all four this same `д` on cid 103, every one a Latin g.

So the rule is Cyrillic-only, and the risk is stated where it lives: a
genuinely Cyrillic document that put `afii10069` at code 103 through a
/Differences array would be read as `g`. Such a document encodes its text at
the Cyrillic code points, where this never fires.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")


def test_the_libertine_g_is_a_g():
    assert D._spell_glyph("д", "afii10069.ital", 103) == "g"


def test_the_code_decides_which_letter():
    """Not a table of names: the font's own code says which letter it is."""
    assert D._spell_glyph("д", "afii10069.ital", ord("p")) == "p"


def test_a_cyrillic_code_is_left_alone():
    """A Cyrillic character at a Cyrillic code point is Cyrillic text, and
    this is where a real Russian document lives."""
    assert D._spell_glyph("д", "afii10069", 0x434) == "д"


def test_a_cyrillic_glyph_on_a_digit_is_left_alone():
    """Only a LETTER's code names a letter. A digit or a punctuation code is
    where the 620 correct non-Latin decodes sit."""
    assert D._spell_glyph("д", "afii10069", ord("2")) == "д"


@pytest.mark.parametrize("text,cid", [
    ("’", ord("'")),      # TeX's right quote
    ("√", ord("p")),      # CMSY `p` is the radical
    ("∈", ord("2")),      # CMSY `2` is \in
    ("“", ord("\\")),     # LMRoman `\` is the left double quote
    ("−", 0),             # txsys minus
])
def test_the_measured_correct_decodes_are_untouched(text, cid):
    """The five shapes behind the 620. Each one is the font saying something
    true that a code-first rule would have thrown away -- `\\sqrt` read as
    `p`, `\\in` as `2`."""
    assert D._spell_glyph(text, "whatever", cid) == text


def test_the_rule_needs_the_cid_and_defaults_to_doing_nothing():
    """A caller that cannot supply a code gets the old behaviour, not a
    guess: the other construction site composes glyphs that have no cid."""
    assert D._spell_glyph("д", "afii10069.ital") == "д"


def test_a_ligature_is_still_spelled_out():
    """Rule 1 runs first and is unaffected."""
    assert D._spell_glyph("ﬁ", None, ord("g")) == "fi"
