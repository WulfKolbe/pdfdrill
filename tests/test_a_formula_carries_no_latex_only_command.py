r"""A formula carried commands that exist for the document and not for it.

T-0080 item 1 (drillgroup, owner 2026-10-27: "resolve \ensuremath/\xspace and
whatever else the measure finds, as stated rules"). The owner's goal for the
day: drilling an arXiv paper should give an inspect page with pdf2mmd2's
geometry AND the author's LaTeX — which means the author's LaTeX has to be
renderable, and 31.5% of it was not.

THE MEASURE (2026-10-27, read-only over the drill library through the same four
functions `cmd_injectlatex` uses: 530 e-print sources readable, 441 of them
with at least one display equation, 23,608 display equations expanded, each
given to KaTeX 0.16.9 with `throwOnError: true` — the version
`docinspect._KATEX_JS` loads from cdnjs):

    7,438 of 23,608 (31.5%) refused.
    Six command names were the first error on 1,163 of those, one class.
    After the rules: 6,373 refused — 1,065 equations went from refused to
    rendering, 0 newly broken, and none of the six survives as a first error.
    The two gate papers 1702.06385 and 2210.01629v3: 13 refused -> 0.

`throwOnError: true` is the measurement's own choice and matters: the inspector
passes `false`, which makes KaTeX put its error INTO the output as red text
instead of raising. With `false` this count is zero and every one of those
1,056 formulas looks like it rendered.

WHY THE EXPANDER IS NOT THE PLACE TO FIX IT. An author writes
`\newcommand{\dom}{\ensuremath{\mathbb{D}}}`; `expand_macros` substitutes the
body verbatim, which is correct — that IS the macro. `\ensuremath` means "be
in maths mode even if you are not", and a formula already is, so the expansion
is simultaneously right and unrenderable. Hence a separate, stated pass.

AND WHY IT IS MATHS-ONLY. A Diagram's or Table's `latex_code` goes to a real
`xelatex` run (`pdfdrill svg`), where `\vspace` means what it says. The two
graphics call sites must NOT resolve, and
`test_every_expansion_site_declares_which_side_it_is_on` is what keeps the
split from drifting.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from pdfdrill import latex_only as L
from pdfdrill import latex_source as ls

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


# ---------------------------------------------------------------------------
# The rules, each applied to the example it is stated by.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule", L.RULES, ids=[r.name for r in L.RULES])
def test_every_rule_resolves_its_own_example(rule):
    """A rule that is written down and does not work fails here, and a rule
    that works and is not written down cannot be added — the table carries its
    own example, so there is nowhere to put one without the other."""
    assert L.resolve(rule.before) == rule.after, (
        f"\\{rule.name}: {rule.before!r} -> {L.resolve(rule.before)!r}, "
        f"expected {rule.after!r}")


def test_the_rules_carry_the_population_each_came_from():
    """A count without its population is not a measurement. These are
    equations and documents out of 23,608 / 441."""
    for r in L.RULES:
        assert r.equations > 0 and r.documents > 0, r
        assert r.documents <= r.equations, r
    assert sum(r.equations for r in L.RULES) == 1163, (
        "the stated total no longer matches the rules; re-run the measure "
        "rather than editing the number")
    # 1,163 is the equations whose FIRST error was one of the six. 1,065 of
    # them render after the rules; the other 98 have a second error
    # underneath. The two numbers are different measurements of the same run
    # and neither is the other's correction.


def test_the_six_names_are_the_measured_six():
    assert [r.name for r in L.RULES] == [
        "ensuremath", "vspace", "xspace", "centering", "label", "noindent"]


# ---------------------------------------------------------------------------
# The shapes a regex gets wrong.
# ---------------------------------------------------------------------------

def test_the_unbraced_form_of_ensuremath_is_resolved_too():
    r"""TeX's `\ensuremath` takes ONE TOKEN, so `\ensuremath\boldsymbol{x}` has
    `\boldsymbol` as its argument and the `{x}` belongs to `\boldsymbol`. In
    maths mode both forms mean the same, so the command alone goes. Measured:
    nine equations in 2602.14075v1 use it, and a brace-only rule left every
    one of them refused."""
    assert L.resolve(r"\ensuremath\boldsymbol{A} *_\varepsilon") == \
        r"\boldsymbol{A} *_\varepsilon"


def test_a_nested_wrapper_is_fully_unwrapped():
    assert L.resolve(r"\ensuremath{\ensuremath{\frac{a}{b}}}") == r"\frac{a}{b}"


def test_a_braced_argument_is_brace_matched_and_not_regexed():
    r"""THE CASE BUILT TO FAIL. `\{[^}]*\}` stops at the FIRST `}`, so
    `\vspace{\dimexpr 1em+2pt}` loses the command and leaves a stray `}`
    behind — a formula made worse than the one the rule was removing."""
    assert L.resolve(r"a \vspace{\dimexpr 1em+2pt} b") == "a  b"
    assert "}" not in L.resolve(r"a \vspace{\dimexpr 1em+2pt} b")
    assert L.resolve(r"\ensuremath{\frac{a}{b}} + 1") == r"\frac{a}{b} + 1"


def test_an_escaped_brace_inside_the_argument_is_not_a_brace():
    assert L.resolve(r"a \vspace{x\}y} b") == "a  b"


def test_the_star_form_takes_its_argument_with_it():
    assert L.resolve(r"a \vspace*{2\baselineskip} b") == "a  b"


def test_an_optional_argument_goes_too():
    assert L.resolve(r"a \vspace[x]{1em} b") == "a  b"


def test_a_longer_command_that_merely_starts_the_same_is_untouched():
    r"""`(?![A-Za-z])` in every pattern. Without it `\xspace` eats the front of
    `\xspacer` and `\label` the front of `\labelled`, which turns a rule that
    removes nothing visible into one that corrupts a name."""
    src = r"\labelled{x} \xspacer \ensuremathy \vspaceX \noindentation"
    assert L.resolve(src) == src


def test_an_unbalanced_argument_does_not_hang_or_raise():
    """Real sources are truncated by `\\input` boundaries and bad captures."""
    assert L.resolve(r"a \vspace{1em") == "a "
    assert L.resolve(r"\ensuremath{x") == "x"


def test_resolving_twice_changes_nothing():
    for r in L.RULES:
        once = L.resolve(r.before)
        assert L.resolve(once) == once, r.name


def test_an_empty_or_absent_fragment_comes_back_unchanged():
    assert L.resolve("") == ""
    assert L.resolve(None) is None


# ---------------------------------------------------------------------------
# What is deliberately NOT a rule, and why.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [r"\ref{eq:1}", r"\eqref{eq:1}",
                                 r"\emph{x}", r"\textsc{x}"])
def test_a_command_that_prints_something_is_left_alone(cmd):
    r"""These REFUSE in KaTeX too — `\ref` in 35 equations across 18
    documents, `\eqref` in 20 across 7, `\textsc` in 24 across 8 — and are
    still not this pass's business. `\ref` prints a number this pass does not
    know, and dropping it would silently remove content; `\textsc` is
    formatting KaTeX genuinely cannot do, so translating it would be a guess
    about what the author meant. A formula that visibly does not render is
    better than one that renders something else, which is why they belong to
    the marking and not here."""
    assert L.resolve("x = " + cmd) == "x = " + cmd


def test_names_left_reports_the_rules_and_only_the_rules():
    assert L.names_left(r"a \ref{x} \vspace{1em} \ensuremath{y}") == \
        ["ensuremath", "vspace"]
    assert L.names_left("x = y") == []


# ---------------------------------------------------------------------------
# The split: maths resolves, a picture's body does not.
# ---------------------------------------------------------------------------

#: `expand_macros` call sites that must NOT resolve, because what they expand
#: goes to a real `xelatex` run where `\vspace` means what it says. Relative
#: path -> the stripped source lines, verbatim.
#:
#: THIS IS THE WHOLE SPLIT, and it is stated here because nothing else can
#: state it: both sides call the same expander on the same kind of string, and
#: the difference is only what the result is FOR. A new maths site that calls
#: `expand_macros` directly fails here rather than quietly shipping a formula
#: no renderer can read.
GRAPHICS_ONLY = {
    "pdfdrill/latex_source.py": {'code = expand_macros(it["code"], macros)'},
    "pdfdrill/commands.py": {'expanded = ls.expand_macros(g["code"], macros)'},
}


def _expander_calls():
    """{relpath: {stripped line}} for every call to the raw expander under
    `src/`, excluding its own definition and `expand_math`'s one use of it."""
    out = {}
    for p in sorted(SRC.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if "expand_macros(" not in s or s.startswith("def expand_macros"):
                continue
            if s.startswith("#") or s.startswith("*"):
                continue
            if "latex_only.resolve(expand_macros(" in s:   # expand_math itself
                continue
            out.setdefault(str(p.relative_to(SRC)), set()).add(s)
    return out


def test_every_expansion_site_declares_which_side_it_is_on():
    found = _expander_calls()
    extra = {rel: sorted(ls_ - GRAPHICS_ONLY.get(rel, set()))
             for rel, ls_ in found.items() if ls_ - GRAPHICS_ONLY.get(rel, set())}
    assert not extra, (
        "these call the raw expander and are not declared graphics-only, so "
        "either they build a FORMULA and must call `expand_math` (which "
        "resolves the LaTeX-only commands), or they build a picture body and "
        "belong in GRAPHICS_ONLY: " + repr(extra))
    missing = {rel: sorted(want - found.get(rel, set()))
               for rel, want in GRAPHICS_ONLY.items()
               if want - found.get(rel, set())}
    assert not missing, (
        "GRAPHICS_ONLY names a call site that is no longer there, so drop it: "
        + repr(missing))


def test_expand_math_is_the_expander_plus_the_rules():
    macros = ls.extract_macros(r"\newcommand{\dom}{\ensuremath{\mathbb{D}}}")
    raw = ls.expand_macros(r"|\dom(a)|", macros)
    assert raw == r"|\ensuremath{\mathbb{D}}(a)|", raw      # the expander is unchanged
    assert ls.expand_math(r"|\dom(a)|", macros) == r"|\mathbb{D}(a)|"


_PAPER = r"""
\documentclass{article}
\usepackage{xspace}
\newcommand{\dom}{\ensuremath{\mathbb{D}}\xspace}
\newcommand{\data}{\ensuremath{D}}
\begin{document}
Let \(|\dom(a)| = 1\) hold.
\begin{equation}\label{eq:mdl}
L(\data, M) = L(M) + L(\data \mid M) \vspace{1em}
\end{equation}
\begin{figure}
\begin{tikzpicture}
\node (a) {$\dom$}; \vspace{2em}
\end{tikzpicture}
\end{figure}
\end{document}
"""


@pytest.fixture(scope="module")
def built():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "paper.tex"
        p.write_text(_PAPER, encoding="utf-8")
        yield ls.build_source_model(str(p), bibkey="T0080")


def _one(doc, type_):
    got = [o for o in doc.objects.values() if o.type == type_]
    assert got, f"no {type_} object was built"
    return got[0]


def test_a_display_equation_reaches_the_model_renderable(built):
    eq = _one(built, "Equation")
    assert L.names_left(eq.props["latex"]) == [], eq.props["latex"]
    assert r"\mathbb{D}" not in eq.props["latex"]       # this one uses \data
    assert "L(D, M)" in eq.props["latex"], eq.props["latex"]


def test_inline_maths_reaches_the_model_renderable(built):
    fo = _one(built, "Formula")
    assert L.names_left(fo.props["latex"]) == [], fo.props["latex"]
    assert r"\mathbb{D}" in fo.props["latex"], fo.props["latex"]


def test_the_authors_own_form_is_never_touched(built):
    r"""The pair's whole point is that one of them is verbatim. `latex_original`
    keeps the macro the author typed — not the expansion, and not the
    resolution."""
    for type_ in ("Equation", "Formula"):
        o = _one(built, type_)
        assert o.props["latex_original"] == o.props["latex_original"].strip()
        assert r"\d" in o.props["latex_original"], o.props["latex_original"]
        assert o.props["latex_original"] != o.props["latex"]


def test_a_picture_body_keeps_its_latex_only_commands(built):
    r"""THE CASE BUILT TO FAIL IN THE OTHER DIRECTION. A `tikzpicture` is
    compiled by `pdfdrill svg` with xelatex, where `\vspace{2em}` is two
    ems of vertical space. Resolving it there would silently change the
    picture, and nothing downstream would say so."""
    dia = [o for o in built.objects.values()
           if o.type in ("Diagram", "Table") and o.props.get("latex_code")]
    assert dia, "the tikzpicture was not ingested as a graphic object"
    code = dia[0].props["latex_code"]
    assert r"\vspace{2em}" in code, code
    assert r"\ensuremath" in code, (
        "the graphic's body was resolved; it goes to a real LaTeX run")


# ---------------------------------------------------------------------------
# The gate itself, when the tool to run it is present.
# ---------------------------------------------------------------------------

_KATEX = os.environ.get("PDFDRILL_KATEX")
_KATEX_HINT = ("set $PDFDRILL_KATEX to a katex 0.16.9 install "
               "(`npm install katex@0.16.9` -> ./node_modules/katex) — the "
               "version docinspect loads from cdnjs")


@pytest.mark.skipif(not _KATEX or not Path(_KATEX).exists(), reason=_KATEX_HINT)
def test_the_resolved_form_renders_in_the_version_the_inspector_loads():
    """The measurement's own command, on the rules' own examples. `node` and
    KaTeX are not in any pdfdrill install, so this skips by default and names
    what to set — it is how the 1,056 and the 0-newly-broken were counted."""
    # argv[1], NOT argv[2]: `node -e` puts no script filename in argv, so the
    # first user argument is argv[1]. Measured — `node -e ... -- A B` gives
    # ["/usr/bin/node", "A", "B"], and argv[2] made this read the JSON as the
    # module path and fail with MODULE_NOT_FOUND.
    js = (r"const k=require(process.argv[1]);"
          r"for(const t of JSON.parse(process.argv[2])){"
          r"try{k.renderToString(t,{throwOnError:true,displayMode:true});}"
          r"catch(e){console.log('FAIL '+t+' :: '+e.message);}}")
    import json
    texts = [L.resolve(r.before) for r in L.RULES]
    r = subprocess.run(["node", "-e", js, "--", _KATEX, json.dumps(texts)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-400:]
    assert not r.stdout.strip(), r.stdout
    # and the UNRESOLVED forms must really have failed, or the pass is a no-op
    raw = subprocess.run(
        ["node", "-e", js, "--", _KATEX,
         json.dumps([r_.before for r_ in L.RULES if r_.name != "noindent"])],
        capture_output=True, text=True, timeout=120)
    assert "FAIL" in raw.stdout, (
        "KaTeX rendered the unresolved forms, so this version does not refuse "
        "them and the measurement was against a different one: " + raw.stdout)


def test_the_module_states_what_it_does_not_resolve():
    """The four classes the measure found and left: they are the reason the
    remaining 6,382 is not a regression but a different piece of work."""
    doc = L.__doc__ or ""
    for token in (r"\ref", "tikzcd", "tikzpicture", "textsc", "6,373", "7,438"):
        assert token in doc, f"latex_only's docstring no longer states {token}"
