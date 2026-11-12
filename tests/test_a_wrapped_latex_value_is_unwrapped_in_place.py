r"""`props['latex']` is math-mode CONTENT, and a model built before f7d69aee
may hold a wrapped one. Repair it in place, never by rebuilding.

OWNER, 2026-11-12, on the inspector's KaTeX panel for BH2: "your translation or
bilingual version is defect". The translation was not the cause — `latex` has no
language twin and `translate` never touches it — but one of the three refused
forms was a real stored defect, on page 134 of that book:

    latex       \[ \left(s_{(k)}\right)_{1}^{4} \hat{=}… \] \end{itemize}
    latex_raw   \n\[\n\left(s_{(k)}\right)_{1}^{4} \hat{=}…\n\]\n\end{itemize}

Every consumer wraps this field itself, so a `\[` inside it is math inside math
and the trailing `\end{itemize}` is a closer with no opener: KaTeX answers
"Undefined control sequence: \[" and xelatex "Bad math environment delimiter".

WHY A REPAIR AND NOT A REBUILD. `_normalize_latex` has stripped both since
f7d69aee (2026-08-25); this model predates it. The rebuild route is refused for
that document because it is translated, and that refusal is correct — so the
only honest fix is one that works from what is already on disk. `clean` is the
verb that already does in-place model repairs.

MEASURED over the 40 most recent library models with an ingested author LaTeX:
16,260 `latex` props, 15 with a display wrapper and 10 with an unmatched
`\end{...}`, in 7 of the 40 documents.
"""
from docmodel.core import Document, DocObject

from pdfdrill.heading_cleanup import renormalize_math_latex

BAD = (r"\[ \left(s_{(k)}\right)_{1}^{4} \hat{=}\left({ }^{2} "
       r"\bar{\kappa}_{(\mu)}\right)_{1}^{3} . \] \end{itemize}")
GOOD = (r"\left(s_{(k)}\right)_{1}^{4} \hat{=}\left({ }^{2} "
        r"\bar{\kappa}_{(\mu)}\right)_{1}^{3} .")


def _doc(objs):
    d = Document()
    for o in objs:
        d.add(o)
    return d


def test_the_owners_equation_is_unwrapped():
    o = DocObject(type="Equation", props={"latex": BAD, "latex_raw": BAD})
    d = _doc([o])
    assert renormalize_math_latex(d) == 1
    assert o.props["latex"] == GOOD


def test_the_verbatim_record_is_never_edited():
    """`latex_raw`/`latex_original`/`latex_author` are the producer's own words
    (docs/layers/PROPS.md). A repair that edits the evidence is not a repair."""
    o = DocObject(type="Equation", props={
        "latex": BAD, "latex_raw": BAD, "latex_original": BAD,
        "latex_author": BAD})
    renormalize_math_latex(_doc([o]))
    assert o.props["latex_raw"] == BAD
    assert o.props["latex_original"] == BAD
    assert o.props["latex_author"] == BAD


def test_a_clean_model_is_left_alone():
    o = DocObject(type="Formula", props={"latex": r"\alpha + \beta^{2}"})
    assert renormalize_math_latex(_doc([o])) == 0
    assert o.props["latex"] == r"\alpha + \beta^{2}"


def test_whitespace_alone_is_not_a_change():
    """`_normalize_latex` also collapses runs of spaces. Counting that as a
    repair would rewrite thousands of clean values and report a fix that fixed
    nothing."""
    o = DocObject(type="Formula", props={"latex": r"\alpha  +   \beta"})
    assert renormalize_math_latex(_doc([o])) == 0
    assert o.props["latex"] == r"\alpha  +   \beta"


def test_it_is_idempotent():
    o = DocObject(type="Equation", props={"latex": BAD})
    d = _doc([o])
    assert renormalize_math_latex(d) == 1
    assert renormalize_math_latex(d) == 0


def test_the_stored_value_is_normalized_not_rederived_from_the_raw():
    """THE HAZARD THIS AVOIDS. On an arXiv document the author's gold LaTeX is
    promoted into `latex` while `latex_raw` keeps MathPix's reading of the same
    equation. Re-deriving from `latex_raw` would quietly replace the author's
    mathematics with the OCR's — a worse model with a better-formed field."""
    author = r"\oint_{\partial\Sigma}\mathbf{E}\cdot d\boldsymbol{\ell}"
    o = DocObject(type="Equation", props={
        "latex": author, "latex_raw": r"\[ \oint E d l \] \end{itemize}"})
    assert renormalize_math_latex(_doc([o])) == 0
    assert o.props["latex"] == author


def test_a_value_that_would_empty_is_left_for_a_human():
    """An empty `latex` is a worse defect than a wrapped one: it reads as "this
    object has no mathematics" rather than "this needs unwrapping"."""
    o = DocObject(type="Formula", props={"latex": r"\[ \]"})
    assert renormalize_math_latex(_doc([o])) == 0
    assert o.props["latex"] == r"\[ \]"


def test_a_balanced_environment_keeps_both_halves():
    """`_strip_trailing_structure` removes an UNMATCHED closer only. A value
    that opens and closes its own environment is correct as it stands."""
    s = r"\begin{itemize}\item a\end{itemize}"
    o = DocObject(type="Formula", props={"latex": s})
    renormalize_math_latex(_doc([o]))
    assert o.props["latex"] == s


def test_an_object_without_latex_is_untouched():
    o = DocObject(type="Paragraph", props={"text": "prose"})
    assert renormalize_math_latex(_doc([o])) == 0
