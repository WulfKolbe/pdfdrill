"""Front-matter LaTeX commands are not prose — unwrap them.

A merged model keeps the author's LaTeX for the title page verbatim, so a
paragraph's text reads

    \\title{
    Correlation in the Hubbard Model
    }

    Bachelor's Thesis

Every projector then shows the command: the inspector renders it as literal
text, llmtext feeds it to a model as if it were a sentence, and the markdown
carries it into the reader's document. The BRACED CONTENT is the prose; the
command is markup that was never meant to be read.

Applied to the translation and its `_source` twin alike, so a bilingual document
does not end up clean in one language and marked up in the other.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.heading_cleanup import unwrap_frontmatter_commands, clean_frontmatter


def u(s):
    return unwrap_frontmatter_commands(s)


def test_title_and_author_keep_their_content():
    assert u("\\title{\nCorrelation in the Hubbard Model\n} \n\nBachelor's Thesis") \
        == "Correlation in the Hubbard Model\n\nBachelor's Thesis"
    assert u("\\author{\nUniversity of Cologne  \\\\ Institute for Theoretical Physics\n}") \
        == "University of Cologne\nInstitute for Theoretical Physics"


def test_a_line_break_command_becomes_a_line_break():
    assert u("Alpha \\\\ Beta") == "Alpha\nBeta"


def test_layout_only_commands_disappear():
    for cmd in ("\\maketitle", "\\newpage", "\\clearpage", "\\bigskip",
                "\\vspace{2cm}", "\\hfill", "\\noindent"):
        assert u("Before " + cmd + " After") == "Before After", cmd


def test_nested_braces_inside_the_argument_survive():
    assert u("\\title{A \\emph{very} good title}") == "A \\emph{very} good title"


def test_an_unbalanced_command_is_left_alone():
    """Half-unwrapping would silently truncate the text. Leave it visible."""
    bad = "\\title{Correlation in the Hubbard Model"
    assert u(bad) == bad


def test_ordinary_prose_and_math_are_untouched():
    for s in ("A normal sentence.", "Energy \\(E = mc^2\\) is conserved.",
              "The \\emph{Hubbard} model.", ""):
        assert u(s) == s


def test_a_paragraph_of_pure_markup_collapses_to_nothing():
    assert u("\\maketitle") == ""


class _Obj:
    def __init__(self, type_, **props):
        self.type = type_
        self.props = dict(props)


class _Doc:
    def __init__(self, objs):
        self.objects = {str(i): o for i, o in enumerate(objs)}


def test_clean_frontmatter_cleans_both_languages():
    """A bilingual document must not come out clean in one language and marked
    up in the other — the switch would then look like it changed the content."""
    d = _Doc([_Obj("Paragraph",
                   text="\\title{\nCorrelation in the Hubbard Model\n}",
                   text_source="\\title{\nKorrelation im Hubbard Modell\n}")])
    assert clean_frontmatter(d) == 1
    p = d.objects["0"]
    assert p.props["text"] == "Correlation in the Hubbard Model"
    assert p.props["text_source"] == "Korrelation im Hubbard Modell"


def test_clean_frontmatter_is_idempotent():
    d = _Doc([_Obj("Paragraph", text="\\title{X}")])
    assert clean_frontmatter(d) == 1
    assert clean_frontmatter(d) == 0
    assert d.objects["0"].props["text"] == "X"


def test_clean_frontmatter_leaves_math_objects_alone():
    """Uses a field the cleaner DOES process (`text`) on a type it must not, so
    the type filter is what the assertion rests on — an earlier version used
    `latex`, which the field list never touches, and so passed either way."""
    d = _Doc([_Obj("Equation", latex="\\title{not prose}", text="\\title{x}"),
              _Obj("Formula", text="\\author{y}"),
              _Obj("Link", text="\\maketitle")])
    assert clean_frontmatter(d) == 0
    assert d.objects["0"].props["latex"] == "\\title{not prose}"
    assert d.objects["0"].props["text"] == "\\title{x}"
    assert d.objects["1"].props["text"] == "\\author{y}"
    assert d.objects["2"].props["text"] == "\\maketitle"


def test_a_figure_caption_is_cleaned_like_any_other_prose():
    """Captions are translated, so they must be cleaned too — otherwise a
    caption keeps its `\\\\` line breaks in both languages."""
    d = _Doc([_Obj("Diagram", caption="Heisenberg chain \\\\ seven sites",
                   caption_source="Heisenberg-Kette \\\\ sieben Plätze")])
    assert clean_frontmatter(d) == 1
    p = d.objects["0"]
    assert p.props["caption"] == "Heisenberg chain\nseven sites"
    assert p.props["caption_source"] == "Heisenberg-Kette\nsieben Plätze"
