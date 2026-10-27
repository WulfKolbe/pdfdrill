r"""latex_only — the commands a formula carries for LaTeX's sake and nothing else.

T-0080 item 1 (drillgroup, owner 2026-10-27: "resolve \ensuremath/\xspace and
whatever else the measure finds, as stated rules").

An author writes `\newcommand{\dom}{\ensuremath{\mathbb{D}}}` and
`latex_source.expand_macros` substitutes the body verbatim, which is correct:
that IS the macro. But `\ensuremath` exists to say "be in maths mode even if
you are not", and a formula is already in maths mode — so inside one the
command carries no meaning at all, and the browser renderer has never heard of
it. The expansion is right and unrenderable at the same time, which is why
this is a separate pass and not a bug in the expander.

WHAT THE MEASURE FOUND (2026-10-27, read-only over the drill library: 530
e-print sources readable, 441 of them with at least one display equation,
23,608 display equations expanded through `expand_macros`, each then given to
KaTeX 0.16.9 — the version `docinspect._KATEX_JS` loads — with
`throwOnError: true`):

    7,438 of 23,608 expanded equations (31.5%) were refused.

Of those refusals, SIX command names were the FIRST error on 1,163
equations, and are all one class — present for the document, meaningless in
the formula:

    equations  docs  command
          732    30  \ensuremath      asserts maths mode; we are already in it
          352    18  \vspace          vertical space, in a formula a renderer lays out
           53     8  \xspace          the xspace package's spacing nudge
           17     3  \centering
            7     1  \label           already on the object as `label`
            2     2  \noindent

Applying the rules below: 7,438 -> 6,373 refused, so 1,065 equations went
from refused to rendering with **0 newly broken**, and none of the six is left
as a first error anywhere. 1,065 and not 1,163 because 98 of those equations
have a second, different error underneath — 20 of them `\ifmmode`, which is
the same idea written by hand. The two gate papers (1702.06385,
2210.01629v3) go from 13 refused to 0.

WHAT IS DELIBERATELY NOT HERE, because it is a different defect in each case:

  * `\ref` (35 equations, 18 documents) and `\eqref` (20, 7) PRINT SOMETHING —
    a number this pass does not know. Dropping them would silently remove
    content, which is worse than a formula that visibly does not render. They
    belong to the marking in item 2.
  * `\emph` (8 equations, 7 documents) is formatting a renderer genuinely
    cannot do. Translating it would be a guess about what the author meant,
    not a no-op. Also item 2.

    `\textsc` (24, 8) was in this list for the same reason and is now a rule,
    by the owner's decision of 2026-10-27: `\textsc{X}` -> `\text{X}`, and
    THE SMALL CAPS ARE LOST. It is the only rule here that changes what is
    drawn. What bought it: the four `\textsc` procedure names in 1702.06385's
    Algorithm 1, which are 4 of the 5 KaTeX refusals the
    `author-latex-every-route` gate measured once inline formulas carried the
    author's reading at all. A procedure name set upright beats a formula that
    does not render.
  * `tikzcd` (1,072 equations, 17 documents) and `tikzpicture` (545, 8) are the
    single largest group of refusals left, and no rewriting reaches them: they
    are pictures that were captured as equations.
  * 374 of the 456 distinct undefined names occur in ONE document each (2,084
    equations) — the author's own macros that `extract_macros` did not pick up,
    usually defined in a bundled `.sty` or with `\def`. That is a gap in macro
    COLLECTION, not a wrapper to unwrap, and `docops.katex_notice` already
    records the corpus-wide form of it (11,088 of 11,624 undefined occurrences).

THIS PASS IS FOR MATHS ONLY. A Diagram's or Table's `latex_code` goes to a real
`xelatex` run (`pdfdrill svg`), where `\vspace` means exactly what it says, so
the two graphics call sites deliberately do not use it. `latex_source.
expand_math` is the maths-side entry point, and
`tests/test_a_formula_carries_no_latex_only_command.py` holds the call sites to
that split.

`latex_original` is NEVER touched by anything here: the author's form is the
provenance, and the whole point of the pair is that one of them is verbatim.
"""
from __future__ import annotations

import re
from typing import NamedTuple

#: the command is an identity — drop the command, keep its argument
IDENTITY = "identity"
#: the command and its one braced argument both go
DROP_WITH_ARGUMENT = "drop-with-argument"
#: the command alone goes; it takes no argument
DROP = "drop"
#: the command is RENAMED, keeping whatever argument it had. The only kind
#: that changes what is DRAWN rather than removing something unrenderable —
#: see `\textsc` below, and the owner's decision recorded in this module's
#: docstring.
RENAME = "rename"


class Rule(NamedTuple):
    """One stated rule, with the example it is stated BY.

    `before`/`after` are not decoration: the test applies every rule to its own
    example, so a rule that is written down and does not work fails, and a rule
    that works and is not written down cannot be added.
    """
    name: str                 #: without the backslash
    kind: str                 #: IDENTITY | DROP_WITH_ARGUMENT | DROP | RENAME
    before: str
    after: str
    equations: int            #: equations it refused, corpus-wide
    documents: int            #: documents those came from
    to: str = ""              #: RENAME only: the command it becomes


#: THE RULES. Order is irrelevant — `resolve` applies all of them until none
#: fires — but the counts are the order they matter in.
RULES = (
    Rule("ensuremath", IDENTITY,
         r"|\ensuremath{\mathbb{D}}(a)| = 1", r"|\mathbb{D}(a)| = 1", 732, 30),
    Rule("vspace", DROP_WITH_ARGUMENT,
         r"a \vspace{1em} + b", r"a  + b", 352, 18),
    Rule("xspace", DROP,
         r"L(\ensuremath{D}\xspace, M)", r"L(D, M)", 53, 8),
    Rule("centering", DROP,
         r"\centering x = y", r"x = y", 17, 3),
    Rule("label", DROP_WITH_ARGUMENT,
         r"x = y \label{eq:one}", r"x = y ", 7, 1),
    Rule("noindent", DROP,
         r"\noindent x = y", r"x = y", 2, 2),
    # SMALL CAPS ARE LOST. This rule does not remove something meaningless —
    # it draws the author's text in a different face, which is why the measure
    # listed `\textsc` among the things it deliberately did NOT translate.
    # The owner weighed that on 2026-10-27 and chose it anyway: a procedure
    # name set in upright text beats a formula that does not render at all.
    # The four that bought the decision are 1702.06385's Algorithm 1, inline
    # (`\textsc{Crack}(D, \mathcal{M})` and three more) — 4 of the 5 KaTeX
    # refusals on the `author-latex-every-route` gate, in two independent
    # renders. `\emph` (8 equations, 7 documents) was NOT chosen with it.
    Rule("textsc", RENAME,
         r"\textsc{Crack}(D, \mathcal{M})", r"\text{Crack}(D, \mathcal{M})",
         24, 8, to="text"),
)

_IDENTITY = tuple(r.name for r in RULES if r.kind == IDENTITY)
_WITH_ARG = tuple(r.name for r in RULES if r.kind == DROP_WITH_ARGUMENT)
_BARE = tuple(r.name for r in RULES if r.kind == DROP)
_RENAME = tuple((r.name, r.to) for r in RULES if r.kind == RENAME)


def _braced(s: str, i: int) -> "tuple[str, int]":
    r"""`(contents, index just past the closing brace)` for the group at
    `s[i] == '{'`, counting nested braces and stepping over `\{`.

    A regex cannot do this and the failure is silent: `\vspace{\dimexpr 1em}`
    matched by `\{[^}]*\}` eats the first `}` and leaves a stray one behind,
    which makes the formula WORSE than the command it removed.
    """
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":                      # an escaped brace is not a brace
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)               # unbalanced source: take the rest


def _resolve_identity(s: str, name: str) -> str:
    r"""`\<name>{X}` -> `X`, and `\<name>` with no brace -> dropped.

    The second form is TeX's: `\ensuremath` takes ONE token, so
    `\ensuremath\boldsymbol{x}` has `\boldsymbol` as its argument and the
    `{x}` after it belongs to `\boldsymbol`. In maths mode both forms mean the
    same thing, so removing the command alone is correct for both. Measured:
    nine equations in one document use it (2602.14075v1).
    """
    pat = re.compile(r"\\" + name + r"(?![A-Za-z])[ \t]*")
    out, i = [], 0
    while True:
        m = pat.search(s, i)
        if not m:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:m.start()])
        if m.end() < len(s) and s[m.end()] == "{":
            inner, end = _braced(s, m.end())
            out.append(_resolve_identity(inner, name))      # nested wrappers
            i = end
        else:
            i = m.end()                    # the command alone goes; its token stays


def _drop_with_argument(s: str, name: str) -> str:
    r"""`\<name>[opt]{X}` -> nothing, star form included (`\vspace*{2em}`)."""
    pat = re.compile(r"\\" + name + r"(?![A-Za-z])\*?[ \t]*(\[[^\]]*\][ \t]*)?")
    out, i = [], 0
    while True:
        m = pat.search(s, i)
        if not m:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:m.start()])
        if m.end() < len(s) and s[m.end()] == "{":
            _inner, end = _braced(s, m.end())
            i = end
        else:
            i = m.end()                    # no argument there: drop the command
    

def _rename(s: str, name: str, to: str) -> str:
    r"""`\<name>` -> `\<to>`, and nothing else.

    The argument is not parsed: `\textsc` and `\text` take the same one, braced
    or a single token, so renaming the control sequence preserves whatever the
    author wrote. A brace-reading version would have to decide what to do with
    `\textsc X`, and there is nothing to decide.
    """
    return re.sub(r"\\" + name + r"(?![A-Za-z])", "\\\\" + to, s)


def _drop(s: str, name: str) -> str:
    r"""`\<name>` -> nothing. `(?![A-Za-z])` is load-bearing: without it
    `\xspace` would also eat the start of a longer name."""
    return re.sub(r"\\" + name + r"(?![A-Za-z])[ \t]?", "", s)


def resolve(latex: str) -> str:
    """Apply every rule in `RULES` to a MATHS fragment and return the result.

    Idempotent, and never applied to `latex_original` or to a Diagram's or
    Table's `latex_code` — see this module's docstring.
    """
    if not latex:
        return latex
    out = latex
    for name in _IDENTITY:
        out = _resolve_identity(out, name)
    for name in _WITH_ARG:
        out = _drop_with_argument(out, name)
    for name in _BARE:
        out = _drop(out, name)
    for name, to in _RENAME:
        out = _rename(out, name, to)
    return out


def names_left(latex: str) -> list:
    """Which rule names a fragment still contains, in `RULES` order — for a
    caller that wants to say so rather than guess."""
    return [r.name for r in RULES
            if re.search(r"\\" + r.name + r"(?![A-Za-z])", latex or "")]
