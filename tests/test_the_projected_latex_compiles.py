r"""Two defects that stop `pdfdrill latex` output from compiling, both measured.

OWNER, 2026-11-12: "one goal of pdfdrill is to generate rendered LaTeX that
looks better than the original."

MEASURED on BH2's German projection (400 printed pages, 5,214 math objects),
with xelatex:

    as projected, --no-transclude      4 pages, 189 errors
    + 2 chars of MathPix artifact      468 pages, 21 errors,  4.2 s
    + stmaryrd + extarrows + Varangle  468 pages,  4 errors,  2.0 s

So TIME WAS NEVER THE BLOCKER — 468 pages in two seconds. 189 errors was a
cascade from a handful of constructs, and TeX stopped at its 100-error limit
after 4 pages. Of the 21 that remained once the cascade was cut, 16 were two
missing packages:

    \llbracket, \rrbracket   14   stmaryrd
    \xlongequal               2   extarrows

The projector EMITS those symbols — they come through from the reading — and
its own preamble did not define them. A symbol the projection can write and the
preamble cannot resolve is not a rendering problem, it is a compile failure,
which is the reason `listings` is already declared unconditionally here.

AND THE AUTHOR WAS SPELT OUT ONE LETTER PER LINE. `meta["authors"]` on BH2 is
the STRING "Burkhard Heim", and the projector did `for a in authors` — so it
iterated characters and emitted
`\author{B \and u \and r \and k \and h \and a \and r \and d \and \and H \and
e \and i \and m}`: thirteen authors, each one letter, on the title page of
every projection of every document whose model holds a plain string there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject            # noqa: E402
from docops.base import OperatorConfig                   # noqa: E402
from docops.projectors.latex import LaTeXProjector        # noqa: E402


def _proj():
    return LaTeXProjector(OperatorConfig(op="projector", classname="LaTeXProjector"))


def _doc(**meta):
    d = Document()
    d.meta["bibkey"] = "demo"
    d.meta["title"] = "A Demo"
    d.meta.update(meta)
    d.add(DocObject(type="Paragraph", id="p1",
                    props={"text": "Body prose.", "flow_index": 1, "page": 1}))
    return d


# ── the packages ───────────────────────────────────────────────────────────

SYMBOL_PACKAGE = [
    ("\\llbracket", "stmaryrd", 14),
    ("\\rrbracket", "stmaryrd", 14),
    ("\\xlongequal", "extarrows", 2),
]


def test_the_preamble_declares_a_package_for_every_symbol_it_can_emit():
    """Each of these was an `Undefined control sequence` on BH2, with the count
    measured there. A projection that cannot compile is not a projection."""
    tex = _proj().project(_doc())
    for symbol, package, seen in SYMBOL_PACKAGE:
        assert package in tex, (
            f"{symbol} reaches the .tex ({seen} times on BH2) and nothing in "
            f"the preamble defines it — add {package}")


def test_the_preamble_still_declares_what_it_declared_before():
    """stmaryrd redefines a few amssymb glyphs, so the order and the existing
    set matter; this pins that nothing was dropped to make room."""
    tex = _proj().project(_doc())
    for pkg in ("amsmath", "amssymb", "amsfonts", "mathtools", "bm",
                "graphicx", "booktabs", "multirow", "longtable", "xcolor",
                "url", "hyperref", "listings"):
        assert pkg in tex, f"{pkg} is no longer declared"


# ── the author ─────────────────────────────────────────────────────────────

def test_an_author_string_is_one_author_not_one_per_letter():
    """BH2's model holds the string "Burkhard Heim". `for a in authors` over a
    string iterates CHARACTERS."""
    tex = _proj().project(_doc(authors="Burkhard Heim"))
    assert "\\author{Burkhard Heim}" in tex, \
        [l for l in tex.splitlines() if l.startswith("\\author")]
    assert "\\and" not in tex, "one name was split into several authors"


def test_a_list_of_authors_still_joins_with_and():
    tex = _proj().project(_doc(authors=["Ada Lovelace", "Alan Turing"]))
    assert "\\author{Ada Lovelace \\and Alan Turing}" in tex


def test_an_author_string_is_still_escaped():
    """The string path must not skip `_escape_text` — a `&` in a name is a
    LaTeX error, and that is what the escaping is for."""
    tex = _proj().project(_doc(authors="Smith & Sons"))
    assert "\\&" in tex and "Smith" in tex


def test_no_authors_emits_no_author_line():
    tex = _proj().project(_doc())
    assert "\\author{" not in tex


def test_an_empty_author_string_emits_no_author_line():
    """`authors: ""` is "we do not know", not an author whose name is blank."""
    tex = _proj().project(_doc(authors="   "))
    assert "\\author{" not in tex


# ── the one character that cost 464 pages ──────────────────────────────────
r"""MEASURED on BH2's German projection: TWO occurrences of `\text {^ }`, at
source lines 132 and 144, held the compile to 4 pages with 189 errors. Patching
those two characters gave 468 pages with 21 errors. `^` and `_` are math-mode
operators; inside `\text{...}` the mode is TEXT and they are errors, and TeX's
recovery from them derails everything after.

THE MODEL IS NOT EDITED. `{ }^{\text {^ }}` is what MathPix read — it saw the
printed circumflex over a C as a caret character — and that reading is the
producer's record. The repair belongs in the PROJECTION, which has to emit
valid LaTeX, exactly as `_drop_dangling_backslash` beside it already does.
"""
from docops.projectors import latex_pipeline as _pipe     # noqa: E402


def test_a_bare_caret_inside_text_is_made_valid():
    out = _pipe.sanitize_math(r"C \text{ wird zu }{ }^{\text {^ }} C")
    assert "\\textasciicircum" in out, out
    assert not __import__("re").search(r"\\text\s*\{[^{}]*\^", out), out


def test_a_bare_underscore_inside_text_is_made_valid():
    out = _pipe.sanitize_math(r"x = \text{a _ b}")
    assert "\\textunderscore" in out, out


def test_a_caret_in_math_mode_is_untouched():
    """`x^{2}` is the normal case and must not be touched — this is a text-mode
    repair, not a global substitution."""
    out = _pipe.sanitize_math(r"x^{2} + y_{1}")
    assert out == r"x^{2} + y_{1}"


def test_an_already_valid_text_group_is_untouched():
    out = _pipe.sanitize_math(r"\text{already fine}")
    assert out == r"\text{already fine}"


def test_a_text_group_with_nested_braces_is_left_alone():
    r"""A STATED LIMIT, not an oversight. The measured artifact is
    `\text {^ }` — a brace-free body — and rewriting inside nested groups
    needs a brace matcher this does not have. Leaving it reports as a compile
    error, which is visible; guessing wrong would be silent."""
    src = r"\text{\textbf{x} ^}"
    assert _pipe.sanitize_math(src) == src


def test_projecting_does_not_change_the_object():
    """The repair is applied on the way out; `props['latex']` keeps MathPix's
    verbatim reading."""
    bad = r"{ }^{\text {^ }}"
    d = _doc()
    d.add(DocObject(type="Formula", id="f1",
                    props={"latex": bad, "display": True,
                           "flow_index": 2, "page": 1}))
    _proj().project(d)
    assert d.objects["f1"].props["latex"] == bad, "the projection edited the model"


# ── the same artifact, on the OTHER path ───────────────────────────────────
r"""MEASURED, and it is why the first fix was not enough. After `sanitize_math`
learned the repair, the real `pdfdrill latex --lang original` output still
stopped on

    l.133 ...\(C\) durch das Zeichen \({ }^{\text {^ }}\) in der Form \(\hat{C}\)

Of the model objects carrying this artifact, exactly ONE has it in
`props['latex']`, which `sanitize_math` covers. The one that actually broke the
document has it in a PARAGRAPH'S PROSE, inside an inline `\(…\)` span — a
different emission path, which `sanitize_math` never sees.

Math is math wherever the model keeps it, so the repair belongs on both paths.
"""


def test_an_inline_math_span_in_prose_gets_the_same_repair():
    out = _pipe.fix_text_mode_in_math_spans(
        r"C durch das Zeichen \({ }^{\text {^ }}\) in der Form")
    assert "\\textasciicircum" in out, out


def test_a_dollar_span_gets_it_too():
    out = _pipe.fix_text_mode_in_math_spans(r"the value $\text{a ^ b}$ holds")
    assert "\\textasciicircum" in out, out


def test_prose_outside_math_is_not_touched():
    r"""`^` in running prose is `escape_prose_specials`' business, not this
    function's. Two passes escaping the same character would double it."""
    src = r"a caret ^ in prose, and \text{^} outside any span"
    out = _pipe.fix_text_mode_in_math_spans(src)
    assert out.count("caret ^ in prose") == 1, out


def test_text_with_no_specials_is_returned_unchanged():
    src = r"plain prose with \(x^{2}\) inline"
    assert _pipe.fix_text_mode_in_math_spans(src) == src


def test_the_projector_applies_it_to_paragraph_prose():
    """End to end on the shape that broke BH2."""
    d = _doc()
    d.add(DocObject(type="Paragraph", id="p2", props={
        "flow_index": 2, "page": 1,
        "text": r"das Zeichen \({ }^{\text {^ }}\) in der Form \(\hat{C}\)"}))
    tex = _proj().project(d)
    assert "\\textasciicircum" in tex, \
        [l for l in tex.splitlines() if "Zeichen" in l]
    assert d.objects["p2"].props["text"].count("\\textasciicircum") == 0, \
        "the projection edited the model's prose"
