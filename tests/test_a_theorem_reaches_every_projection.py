"""Defect 3, second half: the markdown projector was not the only one.

893a4dfb gave `Theorem`, `Proof` and `Algorithm` a branch in the Markdown
projector. A CLI driving pdfdrill then measured the same document through the
other projections and found the bodies missing there too — 66 theorem
statements and 23 proofs, 3,307 + 2,770 words, in every one of them.

The root cause is one shared gate, not three oversights:
`common.CONTENT_TYPES` — which `flow_ordered_content` filters by, and which
SEVEN projectors take their flow from (comparison_html, beamer, distill_reader,
latex, plaintext, llm_compact twice) — never contained `Theorem`, `Proof` or
`Algorithm`. A projector cannot render an object its flow never yields, so a
branch alone would have done nothing.

The default set is deliberately NOT widened here: four of those seven have no
branch for these types and are not touched by this task, and a flow object
nobody renders is at best nothing and at worst noise. `flow_ordered_content`
takes the extra types as an argument instead, so each projector states which
types it renders.

`llm_text` is the exception that proves the shape: it iterates every object and
never consulted the gate, so there it really was a missing branch — plus two
missing rows in `_TITLED_TYPES`, without which `title[o.id]` raises KeyError.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                    # noqa: E402
from docops.base import OperatorConfig                           # noqa: E402
from docops.projectors.common import flow_ordered_content        # noqa: E402
from docops.projectors.latex import LaTeXProjector               # noqa: E402
from docops.projectors.llm_text import build_llm_text            # noqa: E402
from docops.projectors.plaintext import PlainTextProjector       # noqa: E402

BK = "Schick2001"

THEOREM = {"kind": "theorem", "env": "theorem", "printed_title": "Theorem",
           "title": "Hirzebruch", "number": 3, "label": "thm:main",
           "starred": False,
           "statement": r"Let $M$ be closed. Then $\alpha(M) = 0$."}
PROOF = {"name": "Proof", "of_label": "thm:main",
         "statement": r"Apply the index theorem to $D$."}


def _doc(*objs, meta=None):
    d = Document()
    d.meta["bibkey"] = BK
    d.meta["source_counts"] = {"theorems": 1}
    d.meta.update(meta or {})
    for i, o in enumerate(objs):
        o.props.setdefault("flow_index", i + 1)
        d.add(o)
    return d


def _with_steps(doc, alg, *steps):
    for text, depth in steps:
        st = DocObject(type="AlgorithmStep", props={"text": text, "depth": depth},
                       parent=alg.id)
        doc.add(st)
        alg.children.append(st.id)
    return doc


def _txt(doc):
    return PlainTextProjector(OperatorConfig(
        op="projector", classname="PlainTextProjector")).project(doc)


def _tex(doc):
    return LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector")).project(doc)


# ── the shared gate ──────────────────────────────────────────────────────────

def test_the_default_flow_still_excludes_a_theorem():
    """The four projectors this task does not touch must see exactly what they
    saw before: a type with no branch in them stays out of their flow."""
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)),
               DocObject(type="Paragraph", props={"text": "Prose."}))
    types = [o.type for o in flow_ordered_content(doc)]
    assert types == ["Paragraph"]


def test_a_projector_can_ask_for_the_types_it_renders():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)),
               DocObject(type="Paragraph", props={"text": "Prose."}),
               DocObject(type="Proof", props=dict(PROOF)))
    got = [o.type for o in
           flow_ordered_content(doc, types=("Theorem", "Proof", "Algorithm"))]
    assert got == ["Theorem", "Paragraph", "Proof"]


def test_asking_for_a_type_twice_does_not_duplicate_it():
    doc = _doc(DocObject(type="Paragraph", props={"text": "Prose."}))
    got = flow_ordered_content(doc, types=("Paragraph",))
    assert [o.type for o in got] == ["Paragraph"]


# ── llmtext ──────────────────────────────────────────────────────────────────

def test_llmtext_carries_the_theorem_statement():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)))
    out = build_llm_text(list(doc.objects.values()), doc.meta)
    assert r"Let $M$ be closed. Then $\alpha(M) = 0$." in out
    assert f"{BK}_THM0001" in out


def test_llmtext_carries_the_proof_statement():
    doc = _doc(DocObject(type="Proof", props=dict(PROOF)))
    out = build_llm_text(list(doc.objects.values()), doc.meta)
    assert r"Apply the index theorem to $D$." in out
    assert f"{BK}_PROOF0001" in out


def test_llmtext_heads_a_theorem_with_its_printed_title_and_number():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)))
    out = build_llm_text(list(doc.objects.values()), doc.meta)
    assert "Theorem 3 (Hirzebruch)" in out


def test_llmtext_skips_a_theorem_with_no_statement():
    doc = _doc(DocObject(type="Theorem", props={"kind": "theorem",
                                                "statement": "  "}),
               DocObject(type="Paragraph", props={"text": "Prose."}))
    out = build_llm_text(list(doc.objects.values()), doc.meta)
    assert "THM" not in out
    assert "Prose." in out


def test_llmtext_keeps_the_units_it_already_emitted():
    doc = _doc(DocObject(type="Section", props={"caption": "Introduction"}),
               DocObject(type="Paragraph", props={"text": "Prose."}),
               DocObject(type="Formula", props={"latex": r"\pi_1(M)"}))
    out = build_llm_text(list(doc.objects.values()), doc.meta)
    assert "# Introduction" in out and "Prose." in out and r"\pi_1(M)" in out


# ── plaintext ────────────────────────────────────────────────────────────────

def test_plaintext_carries_the_theorem_and_the_proof():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)),
               DocObject(type="Proof", props=dict(PROOF)))
    out = _txt(doc)
    assert "[THEOREM 3 (Hirzebruch)]" in out
    assert r"Let $M$ be closed. Then $\alpha(M) = 0$." in out
    assert "[PROOF]" in out
    assert r"Apply the index theorem to $D$." in out


def test_plaintext_renders_an_algorithm_with_its_steps():
    alg = DocObject(type="Algorithm", props={"number": 1, "title": "Label it"})
    doc = _with_steps(_doc(alg),
                      alg, ("initialise the forest", 0),
                      ("for each pixel do", 0), ("union the roots", 1))
    out = _txt(doc)
    assert "[ALGORITHM 1 Label it]" in out
    assert out.index("initialise the forest") < out.index("union the roots")
    assert re.search(r"\n\s+\S*\s*union the roots", out)


def test_plaintext_renders_an_algorithm_step_once():
    alg = DocObject(type="Algorithm", props={"number": 2, "title": "Scan"})
    doc = _with_steps(_doc(alg, DocObject(type="Paragraph",
                                          props={"text": "Closing prose."})),
                      alg, ("scan the rows", 0))
    out = _txt(doc)
    assert out.count("scan the rows") == 1
    assert out.index("scan the rows") < out.index("Closing prose.")


def test_plaintext_drops_a_theorem_with_no_statement():
    doc = _doc(DocObject(type="Theorem", props={"kind": "theorem",
                                                "statement": ""}))
    assert "THEOREM" not in _txt(doc)


# ── latex ────────────────────────────────────────────────────────────────────

def test_latex_wraps_a_theorem_in_the_authors_own_environment():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)))
    tex = _tex(doc)
    assert "\\begin{theorem}" in tex and "\\end{theorem}" in tex
    assert r"Then $\alpha(M) = 0$." in tex


def test_latex_keeps_a_non_english_environment_name():
    """`env` is the author's own `\\newtheorem` name, and a projection that
    renamed it to `theorem` would no longer match the author's source."""
    props = dict(THEOREM, env="satz", printed_title="Satz", title="")
    doc = _doc(DocObject(type="Theorem", props=props))
    tex = _tex(doc)
    assert "\\begin{satz}" in tex and "\\end{satz}" in tex


def test_latex_carries_the_bracket_title_as_the_optional_argument():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)))
    assert "\\begin{theorem}[Hirzebruch]" in _tex(doc)


def test_latex_keeps_the_label_so_a_ref_still_resolves():
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)))
    assert "\\label{thm:main}" in _tex(doc)


def test_latex_wraps_a_proof_in_a_proof_environment():
    doc = _doc(DocObject(type="Proof", props=dict(PROOF)))
    tex = _tex(doc)
    assert "\\begin{proof}" in tex and "\\end{proof}" in tex
    assert r"Apply the index theorem to $D$." in tex


def test_latex_declares_every_environment_it_uses():
    r"""The same standard the preamble already holds `listings` to: a block that
    reaches the .tex without its declaration does not render badly, it FAILS TO
    COMPILE. `--compile` is a real flag, so this is not cosmetic."""
    props = dict(THEOREM, env="satz", printed_title="Satz")
    doc = _doc(DocObject(type="Theorem", props=props),
               DocObject(type="Proof", props=dict(PROOF)))
    tex = _tex(doc)
    assert "\\usepackage{amsthm}" in tex
    assert "\\newtheorem{satz}{Satz}" in tex
    assert tex.index("\\newtheorem{satz}") < tex.index("\\begin{document}")


def test_latex_takes_the_declaration_from_the_authors_own_preamble_scan():
    """`latex_source` records every `\\newtheorem` the author wrote
    (`meta['environments']['newtheorem']`), with its printed title and whether
    it is starred. That is better than anything this projector could guess."""
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM, env="lemma",
                                                    printed_title="")),
               meta={"environments": {"newtheorem": [
                   {"name": "lemma", "title": "Lemme", "star": False}]}})
    assert "\\newtheorem{lemma}{Lemme}" in _tex(doc)


def test_latex_does_not_declare_an_environment_the_preamble_already_has():
    """An author preamble carries its own `\\newtheorem`, and a second
    declaration is a compile error ("Command \\theorem already defined")."""
    doc = _doc(DocObject(type="Theorem", props=dict(THEOREM)),
               meta={"latex_preamble":
                     "\\documentclass{article}\n\\usepackage{amsthm}\n"
                     "\\newtheorem{theorem}{Theorem}\n"})
    tex = _tex(doc)
    assert tex.count("\\newtheorem{theorem}") == 1
    assert tex.count("\\usepackage{amsthm}") == 1


def test_latex_renders_an_algorithm_as_a_numbered_list():
    alg = DocObject(type="Algorithm", props={"number": 1, "title": "Label it"})
    doc = _with_steps(_doc(alg), alg,
                      ("initialise the forest", 0), ("union the roots", 1))
    tex = _tex(doc)
    assert "initialise the forest" in tex and "union the roots" in tex
    assert "\\begin{enumerate}" in tex


def test_latex_drops_a_theorem_with_no_statement():
    doc = _doc(DocObject(type="Theorem", props={"kind": "theorem",
                                                "statement": "   "}))
    assert "\\begin{theorem}" not in _tex(doc)


def test_latex_still_projects_a_document_with_no_theorem_at_all():
    """No Theorem and no Proof: no amsthm, no declarations, nothing added."""
    doc = _doc(DocObject(type="Paragraph", props={"text": "Prose only."}))
    tex = _tex(doc)
    assert "\\newtheorem" not in tex
    assert "Prose only." in tex
