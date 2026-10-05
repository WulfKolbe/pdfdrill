r"""880 — text the typesetter generated, not text the author wrote.

MathPix cannot tell a bibliography entry from a paragraph: 298 of them across
the four readings this library holds, all typed `text`. Our own reader does
the same independently — 70 `text` and 4 `footnote` on one document. The
instruction was not to emulate the error but to carry a property MathPix has
no equivalent for.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfreader import generated_text as G                      # noqa: E402


# --------------------------------------------------------------------------
# What is generated, by shape.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expect", [
    ("3.2 Introduction . . . . . . . . . . . 14", "toc_entry"),
    ("Appendix A  Notation …………… 101", "toc_entry"),
    ("[7] D. Knuth, The TeXbook, Addison-Wesley, 1984.", "bib_entry"),
    ("[Knu84] D. Knuth, The TeXbook.", "bib_entry"),
    ("(iv) Consider a conjugate net with the first form", "list_label"),
    ("12", "page_number"),
    ("xiv", "page_number"),
])
def test_a_typesetter_shape_is_recognised(text, expect):
    assert G.generated_by(text) == expect


@pytest.mark.parametrize("text", [
    "The result follows from [7] and the lemma above.",   # a citation IN prose
    "1. " ,                                              # a bare counter, no content
    "We consider the case n = 3.",
    "",
])
def test_prose_is_left_alone(text):
    """An unmarked line is NOT a claim that it is prose — it is the absence of
    evidence that it is not. Marking a citation inside a sentence as a
    bibliography entry would be the same class of error as MathPix's, pointing
    the other way."""
    assert G.generated_by(text) is None


def test_a_sentence_opening_with_a_number_is_not_a_list_label():
    """`1. ` is a real list counter and also how a sentence can start. The
    length floor is what separates them: a real item carries content."""
    assert G.generated_by("1. x") is None
    assert G.generated_by("1. Consider the conjugate net") == "list_label"


# --------------------------------------------------------------------------
# What is generated, by the heading above it.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("heading,expect", [
    ("References", "bib_entry"), ("Bibliography", "bib_entry"),
    ("Glossary", "glossary_entry"), ("Abbreviations", "glossary_entry"),
    ("List of Symbols", "symbol_entry"), ("Notation", "symbol_entry"),
    ("Nomenclature", "symbol_entry"),
    ("Contents", "toc_entry"), ("Table of Contents", "toc_entry"),
    ("Results", None), ("Introduction", None),
])
def test_a_generating_heading_scopes_the_body(heading, expect):
    """A glossary entry has NO shape of its own — it is a short line, like any
    other short line. The heading above it is the only reliable signal, which
    is why the two mechanisms are complementary rather than redundant."""
    assert G.section_generator(heading) == expect


# --------------------------------------------------------------------------
# The LaTeX of generated text is the command, not the expansion.
# --------------------------------------------------------------------------

def test_every_generator_has_a_command():
    for g in G.GENERATORS:
        assert g in G.GENERATOR_LATEX, g
        assert G.GENERATOR_LATEX[g].startswith("\\"), g


def test_the_command_is_the_generator_not_the_text():
    r"""THE POINT OF THE WHOLE PROPERTY. A table of contents round-trips as
    `\tableofcontents`, never as the expanded entries: re-typeset and LaTeX
    rebuilds them from the counters with the NEW layout's page numbers.
    Emitting the expansion as source freezes this build's page numbers into
    the document, and they are wrong the first time anything above them
    changes length."""
    assert G.GENERATOR_LATEX["toc_entry"] == r"\tableofcontents"
    assert G.GENERATOR_LATEX["bib_entry"] == r"\bibliography{}"
    assert G.GENERATOR_LATEX["glossary_entry"] == r"\printglossary"
    assert G.GENERATOR_LATEX["symbol_entry"] == r"\printnomenclature"
    # and nothing here is a rendered line
    for cmd in G.GENERATOR_LATEX.values():
        assert "...." not in cmd and not cmd.strip().endswith(".")


def test_the_generator_set_does_not_grow_silently():
    """A consumer switches on these exhaustively."""
    assert set(G.GENERATORS) == {
        "toc_entry", "bib_entry", "glossary_entry", "symbol_entry",
        "list_label", "page_number", "equation_number"}


# --------------------------------------------------------------------------
# It is a property, not a type.
# --------------------------------------------------------------------------

def test_it_is_carried_beside_the_mathpix_type_not_instead_of_it():
    """The `type` field belongs to MathPix: every consumer in `src/docmodel/`
    keys off their vocabulary, so a type they have never seen is a line those
    consumers DROP. Being better than the reference must not mean being
    incompatible with it."""
    from pdfreader import docmodel_six as dm
    import inspect
    src = inspect.getsource(dm._mark_generated_text)
    assert 'rec["generated"]' in src
    assert 'rec["type"] =' not in src, "the type must not be overwritten"
