r"""MathPix's delimiters become each projection's own math form.

The defect this pins: math that stays in a body text (a sidenote, a list
item, a footnote, a caption, a heading) never passes through the
`<$latex .../>` widget that every projection converts FROM, so it reached
the wiki as literal `\(...\)` --- 24,419 prose sites across the 20
published documents.
"""
import re

import pytest

from docops import mathdelims as md

INLINE = r"we set \(x^{2}\) below"
DISPLAY = r"and \[ a = b \] follows"


def test_inline_becomes_the_widget_the_rest_of_the_pipeline_reads():
    assert md.to_tiddlywiki(INLINE) == (
        'we set <$latex text="x^{2}" displayMode="false"/> below')


def test_display_is_marked_as_display():
    assert md.to_tiddlywiki(DISPLAY) == (
        'and <$latex text="a = b" displayMode="true"/> follows')


def test_markdown_matches_what_okf_makes_of_the_widget():
    """The two routes to Markdown must agree.

    `okf._self_widgets_to_markdown` turns the widget into `$body$` /
    `$$ body $$`. A body converted directly here has to land on the same
    string, or the same formula reads differently depending on whether it
    happened to become an object.
    """
    from docops.projectors.okf import _self_widgets_to_markdown
    via_widget = _self_widgets_to_markdown(md.to_tiddlywiki(INLINE), {})
    assert via_widget == md.to_markdown(INLINE) == r"we set $x^{2}$ below"
    via_widget_d = _self_widgets_to_markdown(md.to_tiddlywiki(DISPLAY), {})
    assert via_widget_d == md.to_markdown(DISPLAY) == r"and $$ a = b $$ follows"


def test_plain_keeps_the_body_and_drops_the_delimiters():
    assert md.to_plain(INLINE) == "we set x^{2} below"


@pytest.mark.parametrize("policy", sorted(md.POLICIES))
def test_a_latex_source_body_is_never_touched(policy):
    r"""A Table's `raw_text` tabular is source, not prose.

    Rewriting `\(x\)` inside `\begin{tabular}` breaks the tabular, and those
    bodies go to the SVG route (docs/layers/RECLASSIFY.md) where the raw
    LaTeX is what is compiled.
    """
    src = r"\begin{tabular}{|l|}\hline \(x\) \\ \hline\end{tabular}"
    assert md.render(src, policy) == src


@pytest.mark.parametrize("policy", sorted(md.POLICIES))
def test_a_body_with_no_math_is_returned_unchanged(policy):
    assert md.render("plain prose, no math", policy) == "plain prose, no math"


@pytest.mark.parametrize("policy", sorted(md.POLICIES))
def test_conversion_is_idempotent(policy):
    once = md.render(INLINE + " " + DISPLAY, policy)
    assert md.render(once, policy) == once


def test_an_unknown_policy_raises_and_names_the_ones_that_exist():
    with pytest.raises(ValueError) as e:
        md.render(INLINE, "katex")
    assert "katex" in str(e.value) and "tiddlywiki" in str(e.value)


# ---------------------------------------------------------- attribute quoting

def test_a_body_containing_a_double_quote_is_left_in_mathpix_delimiters():
    r"""No escape character exists inside a TiddlyWiki attribute, and the
    reader downstream (`okf._attr_value`) parses only the double-quoted
    form --- so switching quote style would render in the wiki and arrive
    in Markdown with the quotes attached. 74 bodies in 1,428,984."""
    src = r'we set \(\text{"q"}\) here'
    assert md.to_tiddlywiki(src) == src
    assert md.unconvertible(src) == [r'\text{"q"}']


def test_a_body_with_only_a_single_quote_is_still_converted():
    """The control: only the double quote is the problem."""
    out = md.to_tiddlywiki(r"\(f'\)")
    assert out == '<$latex text="f\'" displayMode="false"/>'
    assert md.unconvertible(r"\(f'\)") == []


def test_every_emitted_attribute_survives_the_markdown_reader():
    """The property that matters: whatever this module emits, the value
    read back out by okf is the body that went in."""
    from docops.projectors.okf import _ATTR_RE, _attr_value
    for body in [r"x^{2}", r"f'", r"\alpha > \beta", r"a b c"]:
        widget = md.to_tiddlywiki("\\(" + body + "\\)")
        assert widget.startswith("<$latex "), body
        attrs = dict(_ATTR_RE.findall(widget[len("<$latex "):]))
        assert _attr_value(attrs["text"], {}) == body, body


def test_markdown_converts_what_the_widget_route_has_to_refuse():
    r"""Dollars have no quoting problem, so the Markdown policy is not
    limited by the widget's attribute syntax."""
    assert md.to_markdown(r'\(\text{"q"}\)') == r'$\text{"q"}$'


# ------------------------------------------------------------------ edge cases

def test_an_empty_span_is_left_alone_rather_than_emitting_an_empty_widget():
    assert md.to_tiddlywiki(r"a \(\) b") == r"a \(\) b"


def test_display_and_inline_in_one_body_keep_their_own_modes():
    out = md.to_tiddlywiki(r"\(a\) then \[b\] then \(c\)")
    assert out.count('displayMode="false"') == 2
    assert out.count('displayMode="true"') == 1


def test_math_spanning_a_newline_is_still_one_span():
    out = md.to_tiddlywiki("start \\(a +\nb\\) end")
    assert out.count("<$latex") == 1


def test_a_lone_delimiter_is_not_a_span():
    assert md.to_tiddlywiki(r"cost is \( 5 dollars") == r"cost is \( 5 dollars"


def test_spans_reports_offsets_that_index_the_source():
    text = r"we set \(x\) below"
    (start, end, body, display), = md.spans(text)
    assert text[start:end] == r"\(x\)"
    assert (body, display) == ("x", False)
