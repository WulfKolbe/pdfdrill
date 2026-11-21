r"""The author's front matter is not a drilled paragraph.

T-0156 class C. The front matter reached the body as PROSE. On
arxiv.0912.2444 it arrived as three Paragraph objects —

    '\begin{frontmatter}'
    '\begin{aug}\n\author[A]{\fnms{Mohsen} \snm{Bayati}\thanksref{t1}…'
    '\end{frontmatter}'

— and `meta["authors"]` kept the markup too, so the projection emitted
`\author{\fnms{Mohsen} \snm{Bayati}\thanksref{t1}\ead[label=e1]{…}}`.

DROPPED TO TEXT, NOT KEPT AS STRUCTURE, and the owner's requirement list is
what decides it. The six gates are an error-free compile, addressable
paragraphs, references as BibTeX with hyperlinked `\cite`, equation numbers
with `\tag`, internal cross-references, and an AI review as tracked changes.
Not one of them reads the document's own `\address`, `\kwd`, `\thanksref`,
`\ead`, `\corref` or `\runtitle`. The TiddlyWiki projector says the same in
code: its only `authors` field is written for a REFERENCE object
(`tiddlywiki.py`, `ref.props["author"]`) — the bibliography's authors, which
requirement 3 does need — and it has no document-level author or keyword field
at all. `meta["title"]` and `meta["authors"]` already exist and the LaTeX
projector already emits `\title`/`\author` from them, so the names keep the
home they have and nothing new is invented. DESIGN D-9/D-11: every output is a
projection, so a field no projection reads is not a field.

MEASURED, the audit's two commands on fresh copies, both halves from a clean
directory:

    arxiv.0912.2444   142 -> 103     the other seven unchanged, total 325 -> 286

39 errors went, of which 23 were front matter itself (`\kwd` 6, `\fnms` 3,
`\snm` 3, `\thanksref` 3, `\ead` 3, `\printead` 3, `\runtitle` 1, `\corref` 1)
and 16 were cascades.

AND `\dvtx` IS NOT FRONT MATTER, which is a correction to the measurement that
set this gate. I had grouped error tokens against a list of imsart names I
wrote myself, and counted `\dvtx` x16 among them. The class states otherwise —
`arximspdf.cls:1110`, `\def\dvtx{\nobreak\,\colon\relax}` — a spaced colon,
and on that page it stands inside body mathematics:
`$H_i\dvtx [q^-]\rightarrow\mathbb{R}$`. It is the shape of `\interval` and
`\labelcref`: a command the author's CLASS provides and we do not. Neither
class B nor variant C can reach it, because `_collect_macro_defs` reads the
document's preamble and that definition lives in the `.cls`. Those 16 remain
and are a separate decision.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

LS = pytest.importorskip("pdfdrill.latex_source")

AUG = "\n".join([
    r"\begin{aug}",
    r"\author[A]{\fnms{Mohsen} \snm{Bayati}\thanksref{t1}"
    r"\ead[label=e1]{bayati@stanford.edu}},",
    r"\author[B]{\fnms{David} \snm{Gamarnik}\corref{}\thanksref{t2}}",
    r"\runauthor{M. Bayati, D. Gamarnik and P. Tetali}",
    r"\affiliation{Stanford Univeristy, MIT and Georgia Tech}",
    r"\address[A]{M. Bayati\\ Stanford University\\ \printead{e1}}",
    r"\end{aug}",
])


# ── the author string that reaches \author{…} ───────────────────────────────

def test_an_author_name_keeps_only_the_name():
    r"""`\fnms`/`\snm` are UNWRAPPED — the name is the one thing in that front
    matter a requirement reads — and the rest is dropped."""
    got = LS._clean_frontmatter(
        r"\fnms{Mohsen} \snm{Bayati}\thanksref{t1}"
        r"\ead[label=e1]{bayati@stanford.edu}")
    assert got == "Mohsen Bayati"


@pytest.mark.parametrize("raw,want", [
    (r"\fnms{David} \snm{Gamarnik}\corref{}\thanksref{t2}", "David Gamarnik"),
    (r"Jane Q. Doe\thanks{supported by X}", "Jane Q. Doe"),
    (r"\fnms{A.}\snm{B.}\printead{e1}", "A.B."),
])
def test_the_author_furniture_does_not_survive(raw, want):
    assert LS._clean_frontmatter(raw) == want


def test_thanksref_is_reached_although_thanks_is_guarded():
    r"""`\thanks` was already stripped, and its `(?![a-zA-Z])` guard means it
    never reached `\thanksref` — which is why the markup survived."""
    assert LS._clean_frontmatter(r"X\thanksref{t1}") == "X"
    assert LS._clean_frontmatter(r"X\thanks{note}") == "X"


# ── the chunks that must not become paragraphs ──────────────────────────────

@pytest.mark.parametrize("chunk", [
    r"\begin{frontmatter}",
    r"\end{frontmatter}",
    AUG,
    r"\maketitle",
    "\n".join([r"\begin{keyword}[class=AMS]", r"\kwd[Primary ]{05C80}",
               r"\kwd{60C05}", r"\kwd[; secondary ]{82-08}",
               r"\end{keyword}"]),
])
def test_a_chunk_of_pure_front_matter_is_not_a_paragraph(chunk):
    assert LS._front_matter_only(chunk) is True


def test_the_environments_optional_argument_is_part_of_it():
    r"""imsart writes `\begin{keyword}[class=AMS]`. Matching only
    `\begin{keyword}` left `[class=AMS]` behind — three letters that made the
    whole keyword block look like prose, so its `\kwd` stayed undefined. That
    was the difference between 291 and 286 on the gate."""
    assert LS._front_matter_only(r"\begin{keyword}[class=AMS] \kwd{x}") is True
    assert LS._front_matter_only(r"\begin{keyword} \kwd{x}") is True


@pytest.mark.parametrize("chunk", [
    "A paragraph of ordinary prose with no markup at all.",
    r"\title{Combinatorial approach} and then real prose follows here",
    r"\includegraphics{figure.png}",
    r"A node potential is a function $H_i\dvtx [q^-]\rightarrow\mathbb{R}$, and",
    r"\begin{abstract} We prove a theorem about graphs. \end{abstract}",
])
def test_a_chunk_with_content_is_kept(chunk):
    r"""THE TEST IS SUBTRACTIVE so it cannot delete prose: each front-matter
    construct goes with its brace-balanced arguments, and the chunk is front
    matter only if NO letter or digit survives.

    `\includegraphics` is not front matter. `\begin{abstract}` is deliberately
    not in `_FM_ENV`: an abstract is a paragraph by the owner's second
    requirement, and it is captured as its own object because it is content.
    And a line of body maths using `\dvtx` is mathematics, not front matter —
    see this module's docstring.
    """
    assert LS._front_matter_only(chunk) is False


def test_the_chunk_walker_skips_them():
    r"""End to end through `_prose_chunks`: the three objects arxiv.0912.2444
    produced are gone and the paragraph between them survives."""
    body = "\n\n".join([r"\begin{frontmatter}", AUG,
                        "This is the first real paragraph of the paper.",
                        r"\end{frontmatter}",
                        "And this is the second one."])
    chunks = [c for _pos, c in LS._prose_chunks(body)]
    assert len(chunks) == 2
    assert "first real paragraph" in chunks[0]
    assert "second one" in chunks[1]
