"""Defect 3 — the author's LaTeX reached the model and not the Markdown.

Measured on the fifteen-document set and reported by a CLI driving pdfdrill:
`md` for an arXiv e-print gave Schick2001 2,021 words across 28 pages (~72 a
page, against 400-600 for a paper of that density). Two mechanisms, both in
the projector and neither in the reading:

1. `latex_source.build_source_model` cuts every inline math span OUT of the
   paragraph and files it as its own `Formula`, leaving `{{<bibkey>_FO0001||FO}}`
   in the prose. `_flow` then skips `Formula` ("rendered inside the prose that
   hosts it") and `_strip_transclusions` drops the marker "keeping nothing
   behind" — on the documented assumption that the caller resolved it first.
   `_md_from_latex_source` never did. The LaTeX stayed in the model, referenced
   by nothing in the output.

2. `Theorem`, `Proof`, `Algorithm` and `AlgorithmStep` are object types the
   LaTeX-source reader creates and `_block` had no branch for, so it returned
   the empty string for each. A statement-and-proof paper loses its substance
   that way, which is why Schick2001 is hit far harder than an experimental
   paper.

And the author's `$ … $` is mathematics, not a literal dollar: in LaTeX source
a literal one is written `\\$`. `_mathpix_math` escapes a bare dollar because on
the MathPix route that is right (`escape_dollar: True` is in the conversion
options pdfdrill sends), and it turned `$\\alpha(M)$` into `\\$\\alpha(M)\\$`.
Which route the prose came from decides, so the two cases are both tested here.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                # noqa: E402
from docops.base import OperatorConfig                       # noqa: E402
from docops.projectors.markdown import MarkdownProjector     # noqa: E402
from docops.projectors.tiddlywiki import title_for           # noqa: E402

TRANSCLUSION = re.compile(r"\{\{[^{}]*\|\|[A-Z]{2,4}\}\}")
BK = "Schick2001"

#: The marker `build_source_model` writes, sanitised exactly as it sanitises it.
def _fo(n: int) -> str:
    return "{{" + re.sub(r"[^A-Za-z0-9_\-\.]", "_",
                         title_for(BK, "Formula", n)) + "||FO}}"


def _doc(*objs, latex_source: bool = True):
    """A document whose objects are in the order given.

    `latex_source` sets the meta `_is_latex_source_model` reads, because that is
    what decides whether a bare `$` is the author's mathematics or a dollar sign.
    """
    d = Document()
    d.meta["bibkey"] = BK
    if latex_source:
        d.meta["source_path"] = "LaTeX source (arXiv e-print)"
    for i, o in enumerate(objs):
        o.props.setdefault("flow_index", i + 1)
        d.add(o)
    return d


def _md(doc, **params):
    params.setdefault("front_matter", False)
    return MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector", params=params)).project(doc)


def _formula(latex: str, display: bool = False) -> DocObject:
    return DocObject(type="Formula", props={"latex": latex, "display": display})


# ── 1. inline mathematics is rendered where it stands ────────────────────────

def test_an_inline_formula_is_rendered_where_it_stands():
    """The projector's own rule, from its header: "a formula is rendered where
    it stands". It was being deleted instead."""
    doc = _doc(_formula(r"\pi_1(M)"),
               DocObject(type="Paragraph",
                         props={"text": f"The group {_fo(1)} acts freely."}))
    out = _md(doc)
    assert r"The group $\pi_1(M)$ acts freely." in out


def test_a_formula_used_twice_is_rendered_at_both_occurrences():
    """`build_source_model` de-duplicates by content: the symbol `f` used 20×
    is ONE Formula transcluded 20 times. Resolving only the first occurrence
    would lose 19 of them."""
    doc = _doc(_formula("f"),
               DocObject(type="Paragraph",
                         props={"text": f"Both {_fo(1)} and {_fo(1)} again."}))
    assert "Both $f$ and $f$ again." in _md(doc)


def test_the_formulas_of_a_second_paragraph_are_numbered_from_the_first():
    """The marker numbers run across the whole document, so the reverse map has
    to be built in flow order over every Formula — not per paragraph."""
    doc = _doc(_formula("x"), _formula("y"),
               DocObject(type="Paragraph", props={"text": f"first {_fo(1)}"}),
               DocObject(type="Paragraph", props={"text": f"second {_fo(2)}"}))
    out = _md(doc)
    assert "first $x$" in out and "second $y$" in out


def test_a_display_formula_gets_the_display_delimiters():
    doc = _doc(_formula(r"\sum_i a_i", display=True),
               DocObject(type="Paragraph", props={"text": f"Observe {_fo(1)}."}))
    assert r"Observe $$\sum_i a_i$$." in _md(doc)


def test_an_unresolvable_marker_still_leaves_no_literal_transclusion():
    """A marker naming no Formula is the state this code found: there is nothing
    to render, and a literal `{{X_FO0001||FO}}` in prose is the "invalid
    transclusion" a reader reported. Dropping it stays right."""
    doc = _doc(DocObject(type="Paragraph",
                         props={"text": f"The group {_fo(7)} acts."}))
    out = _md(doc)
    assert not TRANSCLUSION.search(out)
    assert "The group" in out


def test_a_formula_with_no_latex_is_dropped_rather_than_rendered_empty():
    """Same standard as `_equation`: an object with no LaTeX yields nothing,
    never an empty `$$` that every renderer shows as a stray fence."""
    doc = _doc(DocObject(type="Formula", props={"latex": "", "display": False}),
               DocObject(type="Paragraph", props={"text": f"A {_fo(1)} B"}))
    out = _md(doc)
    assert "$" not in out
    assert not TRANSCLUSION.search(out)


# ── 2. the author's dollar is mathematics; MathPix's is a dollar ─────────────

def test_the_authors_dollar_math_survives_as_math():
    r"""`$\alpha(M)$` in a LaTeX-source statement became `\$\alpha(M)\$`."""
    doc = _doc(DocObject(type="Abstract",
                         props={"text": r"We show $\alpha(M)$ vanishes."}))
    out = _md(doc)
    assert r"We show $\alpha(M)$ vanishes." in out
    assert r"\$" not in out


def test_an_escaped_dollar_in_latex_source_stays_a_dollar_sign():
    r"""A literal dollar in LaTeX source is written `\$`, and must not be read
    as an opening math delimiter."""
    doc = _doc(DocObject(type="Abstract",
                         props={"text": r"It costs \$5 and $n$ hours."}))
    out = _md(doc)
    assert r"costs \$5" in out
    assert "$n$ hours" in out


def test_a_mathpix_reading_still_escapes_its_bare_dollar():
    """The MathPix route asks for `escape_dollar: True` and writes its
    mathematics as `\\( … \\)`, so a bare `$` there is a dollar sign. 58 of 400
    intact downloads carry 302 escaped ones; this is the behaviour that guards
    them."""
    doc = _doc(DocObject(type="Paragraph",
                         props={"text": r"It costs $5 for \(n\) hours."}),
               latex_source=False)
    out = _md(doc)
    assert r"costs \$5" in out
    assert "$n$ hours" in out


def test_a_display_fence_of_the_mathpix_dialect_is_untouched():
    doc = _doc(DocObject(type="Paragraph", props={"text": r"Thus \[x = y\] holds."}),
               latex_source=False)
    assert "$$x = y$$" in _md(doc)


# ── 3. the blocks `_block` had no branch for ─────────────────────────────────

def test_a_theorem_carries_its_printed_title_number_and_statement():
    """The shape the TiddlyWiki projector already uses for the same object
    (`**Theorem 3 (Hirzebruch).** …`), so the two projections agree."""
    doc = _doc(DocObject(type="Theorem", props={
        "kind": "theorem", "printed_title": "Theorem", "title": "Hirzebruch",
        "number": 3, "label": "thm:main", "starred": False,
        "statement": r"Let $M$ be closed. Then $\alpha(M) = 0$."}))
    out = _md(doc)
    assert r"**Theorem 3 (Hirzebruch).** Let $M$ be closed. Then $\alpha(M) = 0$." in out


def test_a_starred_theorem_is_rendered_without_a_number():
    doc = _doc(DocObject(type="Theorem", props={
        "kind": "lemma", "printed_title": "Lemma", "number": None,
        "starred": True, "statement": "The sequence converges."}))
    out = _md(doc)
    assert "**Lemma.** The sequence converges." in out
    assert "None" not in out


def test_a_theorem_with_no_printed_title_falls_back_to_its_kind():
    doc = _doc(DocObject(type="Theorem", props={
        "kind": "proposition", "number": 2, "statement": "It is open."}))
    assert "**Proposition 2.** It is open." in _md(doc)


def test_a_theorem_with_no_statement_is_dropped_rather_than_a_bare_label():
    """A heading with nothing under it is furniture, not content."""
    doc = _doc(DocObject(type="Theorem", props={
        "kind": "theorem", "printed_title": "Theorem", "number": 1,
        "statement": "   "}))
    assert "Theorem" not in _md(doc)


def test_a_proof_is_rendered_with_its_statement_and_a_closing_box():
    """The box ends the proof, as it does in the TiddlyWiki projection — which
    matters when the next block is prose and nothing else marks the end."""
    doc = _doc(DocObject(type="Proof", props={
        "name": "Proof", "statement": r"Apply the index theorem to $D$."}))
    out = _md(doc)
    assert r"**Proof.** Apply the index theorem to $D$. $\square$" in out


def test_a_proof_that_ends_in_its_own_box_does_not_get_a_second():
    doc = _doc(DocObject(type="Proof", props={
        "name": "Proof", "statement": r"Immediate. $\blacksquare$"}))
    out = _md(doc)
    assert r"**Proof.** Immediate. $\blacksquare$" in out
    assert r"\square" not in out


def test_a_named_proof_keeps_the_theorem_it_proves():
    r"""`\begin{proof}[Proof of Theorem 2]` names its target, and in Markdown
    there is no field to put it in — so it belongs in the text."""
    doc = _doc(DocObject(type="Proof", props={
        "name": "Proof of Theorem 2", "statement": "Immediate."}))
    assert "**Proof of Theorem 2.** Immediate." in _md(doc)


def test_an_algorithm_renders_its_steps_in_order():
    alg = DocObject(type="Algorithm", props={"number": 1,
                                             "title": "Label the components"})
    doc = _doc(alg)
    for text, depth in (("initialise the forest", 0),
                        ("for each pixel do", 0),
                        ("union the roots", 1)):
        st = DocObject(type="AlgorithmStep", props={"text": text, "depth": depth},
                       parent=alg.id)
        doc.add(st)
        alg.children.append(st.id)
    out = _md(doc)
    assert "**Algorithm 1** Label the components" in out
    assert out.index("initialise the forest") < out.index("for each pixel do")
    assert out.index("for each pixel do") < out.index("union the roots")
    # The nested step is indented under the step it belongs to.
    assert re.search(r"\n {2,}\S*\s*union the roots", out)


def test_an_algorithm_step_is_rendered_once_and_only_by_its_algorithm():
    """`TableCell` is skipped in `_flow` because its Table renders it. An
    `AlgorithmStep` carries no `flow_index` at all, so left in the flow it
    would sort to the end of the document and print there, after the
    bibliography."""
    alg = DocObject(type="Algorithm", props={"number": 2, "title": "Scan"})
    doc = _doc(alg, DocObject(type="Paragraph", props={"text": "Closing prose."}))
    st = DocObject(type="AlgorithmStep", props={"text": "scan the rows", "depth": 0},
                   parent=alg.id)
    doc.add(st)
    alg.children.append(st.id)
    out = _md(doc)
    assert out.count("scan the rows") == 1
    assert out.index("scan the rows") < out.index("Closing prose.")


def test_an_algorithm_with_no_steps_still_states_itself():
    """`cmd_algorithms` and the LaTeX reader both build an Algorithm before its
    steps; an empty one is a real object the reader should see named."""
    doc = _doc(DocObject(type="Algorithm", props={"number": 3, "title": "Union-find"}))
    assert "**Algorithm 3** Union-find" in _md(doc)


def test_the_mathematics_of_a_theorem_statement_is_rendered_too():
    """A theorem statement goes through `_clean` like any prose, so a marker in
    one resolves as well."""
    doc = _doc(_formula(r"\mathbb{Z}"),
               DocObject(type="Theorem", props={
                   "kind": "theorem", "printed_title": "Theorem", "number": 1,
                   "statement": f"The group is {_fo(1)}."}))
    assert r"**Theorem 1.** The group is $\mathbb{Z}$." in _md(doc)


# ── 4. the whole document, which is how the defect was reported ─────────────

def test_a_statement_and_proof_paper_keeps_its_substance():
    """The reported shape: 28 pages of theorems and proofs down to 2,021 words.
    Everything in this fixture used to render as the heading alone."""
    alg = DocObject(type="Algorithm", props={"number": 1, "title": "Index"})
    doc = _doc(
        DocObject(type="Section", props={"caption": "Introduction", "level": 1}),
        _formula(r"\pi_1(M)"),
        DocObject(type="Paragraph", props={"text": f"The group {_fo(1)} acts."}),
        DocObject(type="Theorem", props={
            "kind": "theorem", "printed_title": "Theorem", "number": 1,
            "statement": r"Then $\alpha(M) = 0$."}),
        DocObject(type="Proof", props={"name": "Proof",
                                       "statement": "By the index theorem."}),
        alg,
    )
    st = DocObject(type="AlgorithmStep", props={"text": "compute the index",
                                                "depth": 0}, parent=alg.id)
    doc.add(st)
    alg.children.append(st.id)
    out = _md(doc)
    for fragment in (r"$\pi_1(M)$", r"**Theorem 1.** Then $\alpha(M) = 0$.",
                     "**Proof.** By the index theorem.",
                     "**Algorithm 1** Index", "compute the index"):
        assert fragment in out, fragment
    assert not TRANSCLUSION.search(out)
