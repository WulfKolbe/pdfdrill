r"""A journal class's front matter, provided and never imposed.

T-0156, requirement 1, fifth step.

A paper written for a journal calls its class's own commands, and we
typeset in `article`. arxiv.0912.2444 (imsart) writes `\thankstext` three
times, `\revised` and `\received` once each, and opens four proofs with
`\begin{pf}` — 13 of the eight e-prints' errors. The environments cost
more than they look: an undefined `\begin{pf}` reports "Environment pf
undefined" AND leaves its `\end{pf}` to mismatch whatever is open, which
the census counted as two separate classes.

TYPESETTING IN THE AUTHOR'S CLASS INSTEAD WAS MEASURED AND LOST, and the
measurement is in `latex_source.document_addon_preamble`: the author's
preamble replacing ours went 241 -> 384, and under `acmart`
`width=\linewidth` divides by zero and 20 crops fail. That is a property of
changing the class at all.

WHY THIS IS BUILT ON ITS COST AND NOT ON ITS FREQUENCY. Over 150
source-built library documents, 36 use a class other than article/amsart
and only 2 of those use any command this floor provides. That rate is close
to the macro-GENERATOR shape refused just before it (1 in 121). The cases
differ in COST, not frequency: the generator needed a new mechanism for
carrying author invocations, with real risk about what else they do, while
this is `\providecommand` — which CANNOT override — and two
`\@ifundefined` guards. "No document worse" is structural here rather than
statistical.

NOTHING OF THE AUTHOR'S IS DROPPED, AND THE FIRST VERSION DROPPED IT. That
version let the commands swallow their arguments, losing a funding note and
two dates — author content, invisible to the content row, and a loss under
rule 4. I had reasoned that `\footnote` before `\maketitle` and `\thanks`
outside `\title` both misbehave, which is true of those two, and concluded
the content could not be kept. `\footnotetext` does exactly the right
thing: the note lands on the title page, where the journal puts it, and the
dates accumulate into `\date`.

"The approaches I thought of fail" is not "it cannot be done", and writing
a loss down honestly is not the same as establishing it was necessary.

A DATE IS NOT PLAIN TEXT. imsart writes
`\received{\smonth{10} \syear{2011}}`, so providing `\received` alone left
`\smonth` and `\syear` undefined inside its argument — 6 new errors. The
isolated file I verified the floor with used `\received{January 2010}`,
invented rather than taken from the document, so it could not see that.
The test below uses the document's own form.

MEASURED: arxiv.0912.2444 18 -> 1, the total 73 -> 56, every content column
identical — and the author's funding notes and both dates present in the
PDF (`MBA Class of 1969`, `CMMI-1031332`, `Received 10 2011; revised 10
2012`).
"""
import re

from docops.projectors.latex import _DEFAULT_PREAMBLE as PRE


def test_the_front_matter_commands_are_provided():
    for cmd in (r"\thankstext", r"\received", r"\revised", r"\corref"):
        assert "\\providecommand{%s}" % cmd.replace("\\", "\\\\") in PRE.replace(
            "\\\\", "\\\\") or ("providecommand{%s}" % cmd) in PRE


def test_they_are_provided_not_defined():
    r"""`\providecommand` never overrides: a class that defines them wins."""
    for cmd in ("thankstext", "received", "revised", "corref"):
        assert re.search(r"\\providecommand\{\\" + cmd + r"\}", PRE)
        assert not re.search(r"\\newcommand\{\\" + cmd + r"\}", PRE)
        assert not re.search(r"\\renewcommand\{\\" + cmd + r"\}", PRE)


def test_the_proof_environments_are_guarded():
    r"""`\newenvironment` errors if the name exists, so it is behind
    `\@ifundefined` — the same floor-not-policy rule as the commands."""
    for env in ("pf", r"pf\*"):
        assert re.search(r"\\@ifundefined\{" + env + r"\}\{\\newenvironment", PRE)


def test_the_guards_are_inside_makeatletter():
    r"""`\@ifundefined` contains `@` and is only legal between
    `\makeatletter` and `\makeatother`."""
    i = PRE.index(r"\@ifundefined")
    before, after = PRE[:i], PRE[i:]
    assert before.rfind(r"\makeatletter") > before.rfind(r"\makeatother")
    assert after.index(r"\makeatother") > 0


def test_pf_maps_to_proof():
    """The environment is the author's name for a proof, not a new thing."""
    assert r"\newenvironment{pf}{\begin{proof}}{\end{proof}}" in PRE


def test_the_floor_takes_the_arguments_the_commands_carry():
    r"""`\thankstext{t1}{text}` takes two; swallowing one would leave the
    other in the body as stray text."""
    assert re.search(r"\\providecommand\{\\thankstext\}\[2\]", PRE)
    assert re.search(r"\\providecommand\{\\received\}\[1\]", PRE)


def test_the_funding_note_is_kept_not_swallowed():
    r"""`\footnotetext` puts it on the title page, where the journal does."""
    assert r"\providecommand{\thankstext}[2]{\footnotetext{#2}}" in PRE


def test_the_dates_reach_the_date_line():
    assert r"\providecommand{\received}[1]{\pd@adddate{Received #1}}" in PRE
    assert r"\providecommand{\revised}[1]{\pd@adddate{revised #1}}" in PRE
    assert r"\date{\pd@dates}" in PRE


def test_the_date_components_are_provided_too():
    r"""The document's own form is `\received{\smonth{10} \syear{2011}}`:
    providing `\received` alone leaves two more class commands undefined
    INSIDE it, which an invented plain-text date cannot show."""
    for c in ("smonth", "syear", "sday"):
        assert re.search(r"\\providecommand\{\\" + c + r"\}\[1\]", PRE)
