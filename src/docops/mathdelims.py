r"""MathPix's math delimiters, translated into each projection's own form.

THE PROBLEM
-----------
MathPix writes inline math as ``\(...\)`` and display math as ``\[...\]``,
in both its `text` and `text_display` fields, essentially without exception
(measured over 306 documents: 1,012,698 ``\(...\)``, 28,857 ``\[...\]``,
74 ``$...$``). Those are MathPix's delimiters, not ours.

Math that becomes a DocObject never carries them --- `FormulaProcessor`
strips them and the TiddlyWiki projector re-emits the body through the
`<$latex .../>` widget, from which `okf` derives ``$...$`` / ``$$...$$`` for
Markdown and the LaTeX pipeline derives an environment. The widget is the
pivot every other projection converts from.

Math that stays in a body text bypasses that pivot entirely, and reaches
every downstream projection as MathPix's raw delimiters. Measured across
the 20 published documents (85,938 tiddlers, `text` and `caption` fields):

    24,419  in prose bodies      sidenote 11,792, listitem 8,770,
                                 table 1,771, footnote 1,118,
                                 Figure/Fig caption 684, reference 156
     1,263  in LaTeX-source bodies (the body carries a `\begin{...}`)

TiddlyWiki's KaTeX plugin renders the widget and ``$$...$$``; it does not
render ``\(...\)``, so all 24,419 show as literal backslash-parenthesis.

THE RULE
--------
One conversion, at the pivot: a prose body's ``\(...\)`` becomes the same
`<$latex .../>` widget an inline Formula would have produced. Everything
downstream then works unchanged, because everything downstream already
knows that widget.

A body carrying a `\begin{...}` environment is LaTeX SOURCE, not prose --- a
Table's `raw_text` tabular, a listing --- and is left exactly as it is.
Rewriting math inside a tabular would break the tabular, and those bodies
are destined for the SVG route anyway (docs/layers/RECLASSIFY.md).

WHY THIS IS NOT THE TRANSCLUSION RULE
--------------------------------------
This module renders math IN PLACE. It creates no object, no title and no
transclusion, so it does not reintroduce what docmodel/line_types.py
refuses: a heading with math keeps its math legible without claiming there
is an inline formula there. The two rules are independent and both hold.
"""
from __future__ import annotations

import re

#: MathPix's two delimiters. Display first: neither can nest in the other,
#: but scanning `\[` first keeps the alternation unambiguous to a reader.
MATHPIX = re.compile(r"\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)")

#: A body containing one of these is LaTeX source, not prose.
_ENVIRONMENT = re.compile(r"\\begin\{")


def is_latex_source(text: str) -> bool:
    """True when the body is LaTeX source and must be left verbatim."""
    return bool(_ENVIRONMENT.search(text or ""))


def spans(text: str):
    """Yield ``(start, end, body, display)`` for each MathPix math span."""
    for m in MATHPIX.finditer(text or ""):
        display = m.group(1) is not None
        body = (m.group(1) if display else m.group(2)) or ""
        yield m.start(), m.end(), body.strip(), display


def widget_safe(body: str) -> bool:
    r"""True when `body` can go in a `<$latex text="...">` attribute.

    A TiddlyWiki attribute has NO escape character, so a body containing a
    double quote cannot be double-quoted. TiddlyWiki does accept single and
    triple-double quoting, but the reader on the other end does not:
    `okf._attr_value` parses only the double-quoted form (and `okf._ATTR_RE`
    tokenises on whitespace, so a single-quoted value with spaces does not
    survive tokenisation at all). Switching quote style here would produce a
    widget that renders in the wiki and comes out of the Markdown route with
    its quotes still attached.

    So the body is left in MathPix's own delimiters instead, and
    `unconvertible()` reports it. Measured over the 1,363-document library:
    74 of 1,428,984 math bodies contain a double quote --- 0.005%, all of
    them a `\text{"..."}` inside the maths.
    """
    return '"' not in (body or "")


def unconvertible(text: str) -> list:
    """The math bodies `to_tiddlywiki` will leave in MathPix's delimiters."""
    return [b for _s, _e, b, _d in spans(text) if b and not widget_safe(b)]


def to_tiddlywiki(text: str) -> str:
    """MathPix delimiters -> the `<$latex .../>` widget, in place.

    A LaTeX-source body is returned unchanged; so is a body with no math.
    """
    if not text or is_latex_source(text):
        return text

    def repl(m: "re.Match") -> str:
        display = m.group(1) is not None
        body = ((m.group(1) if display else m.group(2)) or "").strip()
        if not body or not widget_safe(body):
            return m.group(0)
        return "<$latex text=\"%s\" displayMode=\"%s\"/>" % (
            body, "true" if display else "false")

    return MATHPIX.sub(repl, text)


def to_markdown(text: str) -> str:
    """MathPix delimiters -> ``$...$`` / ``$$ ... $$``, in place.

    The same forms `okf._self_widgets_to_markdown` produces from the widget,
    so a body converted here and a body converted via the widget agree.
    """
    if not text or is_latex_source(text):
        return text

    def repl(m: "re.Match") -> str:
        display = m.group(1) is not None
        body = ((m.group(1) if display else m.group(2)) or "").strip()
        if not body:
            return m.group(0)
        return "$$ %s $$" % body if display else "$%s$" % body

    return MATHPIX.sub(repl, text)


def to_plain(text: str) -> str:
    """MathPix delimiters removed, the LaTeX body kept.

    For a reader with no math renderer at all (plaintext, an LLM prompt);
    the peer of `transclusion_render`'s `detranscluded` policy, for math
    that never became a transclusion.
    """
    if not text or is_latex_source(text):
        return text
    return MATHPIX.sub(
        lambda m: ((m.group(1) if m.group(1) is not None else m.group(2))
                   or "").strip(), text)


#: Named policies, so a projector declares which standard it wants by NAME
#: instead of calling a function whose target is implicit at the call site.
POLICIES = {"tiddlywiki": to_tiddlywiki,
            "markdown": to_markdown,
            "plain": to_plain}


def render(text: str, policy: str = "tiddlywiki") -> str:
    """Apply a named policy. An unknown name raises rather than defaulting."""
    try:
        fn = POLICIES[policy]
    except KeyError:
        raise ValueError("unknown math-delimiter policy %r; have %s"
                         % (policy, ", ".join(sorted(POLICIES)))) from None
    return fn(text)
