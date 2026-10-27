r"""`\textsc{X}` -> `\text{X}`, and the small caps are lost.

Owner's word, 2026-10-27, relayed by the drillgroup coordinator after the
`author-latex-every-route` gate: of the three follow-ups put to them,
"`\textsc{X}` as `\text{X}`" only — "Add it as one rule in latex_only.RULES,
stating that small caps are lost. Test first: the four algorithm-block formulas
render."

WHY IT WAS NOT THERE. `latex_only`'s own docstring argued the other way:
`\textsc` is "formatting a renderer genuinely cannot do (KaTeX has no small
caps). Translating them would be a guess about what the author meant, not a
no-op." That is still true, and it is what the owner weighed: a formula set in
upright text, with the small caps gone, beats a formula that does not render at
all. The rule is therefore the module's first that CHANGES what is drawn, and
it says so where it is defined.

WHERE THE FOUR COME FROM. 1702.06385's Algorithm 1 writes its procedure names
as `\textsc{...}` inside inline maths. They were invisible until
`author-latex-every-route` attached the author's reading to inline formulas —
those forms are not in the page's own text layer at all — and they are 4 of the
5 KaTeX refusals the gate then measured, on both routes and in two independent
renders (mine in node, the coordinator's in Chrome 139):

    \textsc{Crack}(D, \mathcal{M})
    \mathit{res}(a_i) \leftarrow \textsc{RobustMinDiff}(a_i)
    T_i \leftarrow \textsc{TrivialTree}(a_i)
    T'_i \leftarrow \textsc{RefineLeaf}(T_i, l, j)

The fifth refusal is the `\midM` fusion, which the owner did NOT choose.

Corpus-wide the measure counted `\textsc` as the first error on 24 display
equations in 8 documents, which is the population the rule carries.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from pdfdrill import latex_only as L

#: 1702.06385 Algorithm 1, verbatim from the model built by the gate run.
THE_FOUR = (
    r"\textsc{Crack}(D, \mathcal{M})",
    r"\mathit{res}(a_i) \leftarrow \textsc{RobustMinDiff}(a_i)",
    r"T_i \leftarrow \textsc{TrivialTree}(a_i)",
    r"T'_i \leftarrow \textsc{RefineLeaf}(T_i, l, j)",
)

RESOLVED = (
    r"\text{Crack}(D, \mathcal{M})",
    r"\mathit{res}(a_i) \leftarrow \text{RobustMinDiff}(a_i)",
    r"T_i \leftarrow \text{TrivialTree}(a_i)",
    r"T'_i \leftarrow \text{RefineLeaf}(T_i, l, j)",
)


def test_the_rule_is_one_rule_in_the_table():
    """Not a special case somewhere in `resolve`: a `Rule` with its own
    example and its own measured population, like the other six."""
    names = [r.name for r in L.RULES]
    assert "textsc" in names
    rule = next(r for r in L.RULES if r.name == "textsc")
    assert rule.kind == L.RENAME
    assert rule.to == "text"
    assert rule.equations == 24 and rule.documents == 8


def test_the_four_algorithm_block_formulas_resolve():
    for before, after in zip(THE_FOUR, RESOLVED):
        assert L.resolve(before) == after, before


def test_nothing_else_in_them_changed():
    r"""`\mathit`, `\leftarrow`, the primes and the subscripts are the author's
    and must survive untouched — the rule renames one command, it does not
    normalise the formula."""
    out = L.resolve(THE_FOUR[1])
    assert r"\mathit{res}" in out and r"\leftarrow" in out
    assert L.resolve(THE_FOUR[3]).startswith("T'_i")


def test_the_argument_is_kept_exactly():
    r"""`\text` takes the same braced argument, so the rename is the whole
    transform: nothing parses or rewrites the group."""
    assert L.resolve(r"\textsc{Merge-Sort_2}") == r"\text{Merge-Sort_2}"
    assert L.resolve(r"\textsc{\textsc{X}}") == r"\text{\text{X}}"


def test_the_unbraced_form_is_renamed_too():
    r"""TeX's `\textsc` takes one token, and so does `\text`, so the shape is
    preserved whichever form the author wrote."""
    assert L.resolve(r"a \textsc X b") == r"a \text X b"


def test_a_longer_name_is_not_touched():
    r"""The gate is a control sequence: `\textscale` is somebody's macro."""
    assert L.resolve(r"\textscale{2}{x}") == r"\textscale{2}{x}"
    assert L.resolve(r"\textsf{x}") == r"\textsf{x}"


def test_small_caps_are_lost_and_the_rule_says_so():
    """The one rule in this module that changes what is drawn. If that is not
    written down where it is defined, the next reader will take it for a
    no-op like the other six."""
    doc = L.__doc__ or ""
    assert "small caps" in doc.lower()
    import inspect
    src = inspect.getsource(L)
    i = src.index('Rule("textsc"')
    before = src[max(0, i - 900):i]
    assert "small caps" in before.lower() or "SMALL CAPS" in before, (
        "the rule's own comment must state what is lost")


def test_resolve_is_still_idempotent():
    once = L.resolve(THE_FOUR[0])
    assert L.resolve(once) == once


def test_names_left_reports_it_before_and_not_after():
    assert "textsc" in L.names_left(THE_FOUR[0])
    assert "textsc" not in L.names_left(L.resolve(THE_FOUR[0]))


def test_the_other_six_rules_are_unchanged():
    assert L.resolve(r"|\ensuremath{\mathbb{D}}(a)| = 1") == r"|\mathbb{D}(a)| = 1"
    assert L.resolve(r"a \vspace{1em} + b") == "a  + b"
    assert L.resolve(r"\noindent x = y") == "x = y"


def test_emph_is_still_refused_a_translation():
    r"""The owner chose `\textsc` and not `\emph` (8 equations, 7 documents).
    Italic text inside maths is not the same guess, and it was not made."""
    assert "emph" not in [r.name for r in L.RULES]
    assert L.resolve(r"\emph{x} = y") == r"\emph{x} = y"


_KATEX = os.environ.get("PDFDRILL_KATEX")
_HINT = ("set $PDFDRILL_KATEX to a katex 0.16.9 install "
         "(`npm install katex@0.16.9` -> ./node_modules/katex)")


@pytest.mark.skipif(not _KATEX or not Path(_KATEX or "").exists(), reason=_HINT)
def test_the_four_render_in_the_version_the_inspector_loads():
    """THE GATE THE OWNER ASKED FOR. The four refusals, in the renderer that
    refused them, with `throwOnError: true` — `false` puts KaTeX's own error
    into the output as red text and a caller's catch never fires, which is why
    the counts were zero before T-0080."""
    js = (r"const k=require(process.argv[1]);"
          r"for(const t of JSON.parse(process.argv[2])){"
          r"try{k.renderToString(t,{throwOnError:true,displayMode:false});}"
          r"catch(e){console.log('FAIL '+t+' :: '+e.message);}}")
    ok = subprocess.run(["node", "-e", js, "--", _KATEX,
                         json.dumps([L.resolve(t) for t in THE_FOUR])],
                        capture_output=True, text=True, timeout=120)
    assert ok.returncode == 0, ok.stderr[-400:]
    assert not ok.stdout.strip(), ok.stdout
    raw = subprocess.run(["node", "-e", js, "--", _KATEX,
                          json.dumps(list(THE_FOUR))],
                         capture_output=True, text=True, timeout=120)
    assert raw.stdout.count("FAIL") == 4, (
        "this KaTeX does not refuse the four, so the measurement was against "
        "a different version: " + raw.stdout)
