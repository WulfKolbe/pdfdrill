r"""The author's macros were expanded for equations and paragraphs, never for
theorem statements — and never for prose at all.

Reported by a CLI driving pdfdrill on arxiv.math_9807032 and measured there:
`\RAgroups` 66 times, `\NeumannN` 18, `\Det` 15, `\forget` 7, all in the
output, all defined in the author's own preamble (`\RAgroups` → `\mathcal G`,
`\forget` → an empty body: `\newcommand{\forget}[1]{}`).

Expansion itself was solved long ago — `expand_macros` in 2b01201f
(2026-05-30), `expand_math` in 043e92da (2026-10-27). `build_source_model`
called it in exactly two places, the Equation branch and the inline span of a
Paragraph. The Theorem, Proof and Abstract branches stored what the author
typed, and 4b599430 (2026-06-26) created those objects and printed them as
tiddlers in the same commit — a month after the expansion existed. So this is
not a regression and not the projector work of 893a4dfb/ce5a20e3, which made
four-month-old unexpanded text visible in four more projections.

Two further gaps the same measurement found, both fixed here:

  * `expand_macros` was never applied to PROSE. Its only callers were
    `expand_math` (a math fragment) and a Diagram's `code`, so a TEXT-mode
    macro was expanded nowhere, on any route. `\forget{Thomas Schick …}` is
    the case: the author defined it to discard its argument, so expansion is
    not a guess about what they meant — it is their own instruction.
  * a display environment inside a statement reached the Markdown as
    `\begin{equation}`, which no Markdown renderer types. 22 inside Theorem
    statements and 24 inside Proof statements on that paper, which is exactly
    the 46 in its `.md`. The LaTeX projection must NOT be "fixed" the same
    way: there the environment is already right.

NOT fixed here, deliberately: `[section]` theorem numbering (the model counts
1,2,3… where the paper prints 2.9). It is a documented caveat
(`latex_source.py`'s `extract_theorems`), two existing tests pin the sequential
numbers, and correcting it rewrites every theorem number in every projection —
so it needs the printed numbers of several real papers as its fixture, not a
synthetic one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                    # noqa: E402
from docops.base import OperatorConfig                           # noqa: E402
from docops.projectors.latex import LaTeXProjector               # noqa: E402
from docops.projectors.markdown import MarkdownProjector         # noqa: E402
from pdfdrill import latex_source as ls                          # noqa: E402

PREAMBLE = (
    "\\documentclass{article}\n"
    "\\newcommand{\\RAgroups}{\\mathcal G}\n"
    "\\newcommand{\\Det}{\\operatorname{det}}\n"
    "\\newcommand{\\NeumannN}{\\mathcal N}\n"
    "\\newcommand{\\forget}[1]{}\n"
    "\\newtheorem{theorem}{Theorem}\n"
    "\\newtheorem{lemma}[theorem]{Lemma}\n"
)


def _model(body: str, tmp_path, bibkey: str = "T"):
    tex = tmp_path / "main.tex"
    tex.write_text(f"{PREAMBLE}\\begin{{document}}\n\\section{{Body}}\n"
                   f"{body}\n\\end{{document}}\n", encoding="utf-8")
    return ls.build_source_model(str(tex), bibkey=bibkey)


def _one(doc, kind: str):
    return next(o for o in doc.objects.values() if o.type == kind)


def _section(doc, needle: str) -> str:
    """The caption of the Section whose heading contains `needle`.

    `_model` writes its own `\\section{Body}` wrapper, so the FIRST Section is
    never the one under test.
    """
    return next(str(o.props.get("caption") or "")
                for o in doc.objects.values()
                if o.type == "Section" and needle in str(o.props.get("caption") or ""))


def _md(doc, **params):
    params.setdefault("front_matter", False)
    return MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector", params=params)).project(doc)


def _tex(doc):
    return LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector")).project(doc)


# ── the author's macros, in every prose site ─────────────────────────────────

def test_a_theorem_statement_has_its_math_macros_expanded(tmp_path):
    doc = _model(r"\begin{theorem} The group $\RAgroups$ is amenable."
                 r" \end{theorem}", tmp_path)
    st = _one(doc, "Theorem").props["statement"]
    assert r"\mathcal G" in st
    assert "RAgroups" not in st


def test_a_proof_statement_has_its_math_macros_expanded(tmp_path):
    doc = _model(r"\begin{theorem} X. \end{theorem}"
                 "\n\n"
                 r"\begin{proof} Because $\Det$ vanishes. \end{proof}", tmp_path)
    st = _one(doc, "Proof").props["statement"]
    assert r"\operatorname{det}" in st
    assert "Det" not in st.replace(r"\operatorname{det}", "")


def test_an_abstract_has_its_math_macros_expanded(tmp_path):
    doc = _model(r"\begin{abstract} We study $\NeumannN$ here. \end{abstract}",
                 tmp_path)
    st = _one(doc, "Abstract").props["text"]
    assert r"\mathcal N" in st and "NeumannN" not in st


def test_the_delimiters_the_author_used_are_kept(tmp_path):
    r"""Expanding a span must not re-delimit it: `$x$` stays `$x$`, because the
    Markdown projector decides the dialect and a statement is prose."""
    doc = _model(r"\begin{theorem} Both $\RAgroups$ and \(\Det\) here."
                 r" \end{theorem}", tmp_path)
    st = _one(doc, "Theorem").props["statement"]
    assert r"$\mathcal G$" in st
    assert r"\(\operatorname{det}\)" in st


def test_a_text_macro_the_author_defined_away_disappears_from_prose(tmp_path):
    r"""`\newcommand{\forget}[1]{}` — the author's own instruction to discard
    the argument. Nothing expanded prose, so it reached every reader."""
    doc = _model(r"\forget{Thomas Schick, Göttingen} Real prose follows.",
                 tmp_path)
    text = " ".join(o.props.get("text", "") for o in doc.objects.values()
                    if o.type == "Paragraph")
    assert "Real prose follows." in text
    assert "forget" not in text and "Göttingen" not in text


def test_a_text_macro_disappears_from_a_statement_too(tmp_path):
    doc = _model(r"\begin{theorem}\forget{a note} The claim holds."
                 r" \end{theorem}", tmp_path)
    st = _one(doc, "Theorem").props["statement"]
    assert "The claim holds." in st
    assert "forget" not in st and "a note" not in st


def test_expanding_prose_does_not_eat_an_ordinary_backslash_command(tmp_path):
    """A command with no macro definition is left exactly as it stands — this
    pass expands what the author defined, it does not strip LaTeX."""
    doc = _model(r"Prose with \emph{stress} and \undefinedcmd{x} in it.",
                 tmp_path)
    text = " ".join(o.props.get("text", "") for o in doc.objects.values()
                    if o.type == "Paragraph")
    assert "stress" in text
    assert r"\undefinedcmd" in text


# ── a bracket title is prose as well ────────────────────────────────────────

def test_a_bracket_title_is_cleaned_like_the_prose_it_is(tmp_path):
    r"""`\begin{lemma}[\textbf{Scaling}]` — the optional argument is prose and
    was the one string stored raw, which is why a command in a title reached
    the reader as a command."""
    doc = _model(r"\begin{lemma}[\textbf{Scaling}] If $a$ then $b$."
                 r" \end{lemma}", tmp_path)
    assert _one(doc, "Theorem").props["title"] == "Scaling"


def test_a_macro_in_a_bracket_title_is_expanded(tmp_path):
    doc = _model(r"\begin{lemma}[The $\RAgroups$ case] Body. \end{lemma}",
                 tmp_path)
    title = _one(doc, "Theorem").props["title"]
    assert r"\mathcal G" in title and "RAgroups" not in title


# ── a display environment inside a statement ────────────────────────────────

def test_markdown_types_a_display_environment_from_a_statement(tmp_path):
    doc = _model(r"\begin{theorem} We have \begin{equation} x = y"
                 r" \end{equation} as claimed. \end{theorem}", tmp_path)
    out = _md(doc)
    assert "$$x = y$$" in out.replace("\n", "") or "$$ x = y $$" in out
    assert "begin{equation}" not in out


def test_markdown_wraps_an_aligned_family_environment(tmp_path):
    r"""`align` inside `$$…$$` is not valid for a Markdown math renderer;
    `\begin{aligned}` is the form KaTeX and MathJax both accept."""
    doc = _model(r"\begin{theorem} Thus \begin{align} a &= b \\ c &= d"
                 r" \end{align} holds. \end{theorem}", tmp_path)
    out = _md(doc)
    assert r"\begin{aligned}" in out and r"\end{aligned}" in out
    assert "begin{align}" not in out.replace(r"\begin{aligned}", "")


def test_the_latex_projection_keeps_the_environment_as_the_author_wrote_it():
    """The same statement must NOT be re-delimited for LaTeX: there
    `\\begin{equation}` is already the right thing, and `$$` is the wrong one."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    doc.meta["source_counts"] = {"theorems": 1}
    doc.add(DocObject(type="Theorem", props={
        "kind": "theorem", "env": "theorem", "printed_title": "Theorem",
        "number": 1, "flow_index": 1,
        "statement": r"We have \begin{equation} x = y \end{equation} so."}))
    tex = _tex(doc)
    assert r"\begin{equation}" in tex
    assert "$$" not in tex


# ── the citations that were deleted with their markers ──────────────────────

def test_markdown_keeps_a_citation_instead_of_deleting_it(tmp_path):
    r"""`{{<bibkey>_REF_<key>||CIT}}` was stripped with every other unresolved
    marker, so "as shown in [12]" read "as shown in". 26 of them on
    arxiv.math_9807032; the LaTeX route resolves all 26 and Markdown resolved
    none."""
    doc = _model(r"As shown in \cite{Lueck1994} this holds.", tmp_path)
    out = _md(doc)
    assert "Lueck1994" in out
    assert "||CIT}}" not in out
    assert "As shown in" in out


def test_a_citation_inside_a_statement_survives_too(tmp_path):
    doc = _model(r"\begin{theorem} By \cite{Lueck1994} the claim holds."
                 r" \end{theorem}", tmp_path)
    out = _md(doc)
    assert "Lueck1994" in out and "||CIT}}" not in out


# ── a heading is prose as well, and the last site still carrying a macro ────

def test_a_section_heading_has_its_macros_expanded(tmp_path):
    r"""The residual the real paper showed after the four prose sites were
    fixed: `## Properties of the class $\RAgroups$`."""
    doc = _model(r"\section{Properties of the class $\RAgroups$}" "\n\n"
                 r"Prose.", tmp_path)
    cap = _section(doc, "Properties")
    assert r"\mathcal G" in cap and "RAgroups" not in cap


def test_a_ref_in_a_heading_keeps_its_label(tmp_path):
    r"""Macro expansion only — NOT `_clean_prose`, which rewrites `\ref{x}` to
    `(x)`. The TiddlyWiki projector turns that label into a `<$link>` to the
    theorem the heading names, and it needs the label to do it."""
    doc = _model(r"\section{Proof of Theorem~\ref{thm:main}}" "\n\n" r"Prose.",
                 tmp_path)
    cap = _section(doc, "Proof of")
    assert r"\ref{thm:main}" in cap
