"""LaTeX -> Symbol Layout Tree, and the LgEval `.lg` label-graph format.

An SLT (Zanibbi, Blostein & Cordy, TPAMI 2002) is what a recogniser has to
recover: symbols as nodes, spatial relations as edges. The author's LaTeX
STATES that tree — `A_{i,j}^{h,l}` says which symbols are scripts of which base
— which is why arXiv source is ground truth for structure, not merely for text.

`.lg` is what LgEval scores and what CROHME and InftyMCCDB-2 distribute:
    N, <id>, <label>, <weight>
    E, <parent>, <child>, <relation>, <weight>

RULE 5 IS LOAD-BEARING HERE. An unsupported construct is never given a
plausible relation. It becomes an `Unresolved` node, which compares unequal to
every other `Unresolved` — a sentinel string would make every unidentified
symbol the same symbol, and a gold set that quietly agrees with itself is worse
than a smaller honest one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Optional

RIGHT, SUP, SUB, ABOVE, BELOW, INSIDE = "Right", "Sup", "Sub", "Above", "Below", "Inside"

# Spacing: real LaTeX, no ink. Never symbols.
_SPACING = {"~",                       # 057: a non-breaking space puts no ink
                                       # on the page; scoring.py:21 has always
                                       # treated it as spacing and the SLT did
                                       # not, so `\mathrm{~d}` scored 2 edits
                                       # against `\mathrm{d}` while the two
                                       # comparators disagreed (out/055.txt)
            r"\,", r"\;", r"\:", r"\!", r"\quad", r"\qquad", r"\ ", r"\thinspace",
            r"\medspace", r"\thickspace", r"\hspace", r"\vspace", r"\displaystyle",
            r"\textstyle", r"\scriptstyle", r"\left", r"\right", r"\limits",
            r"\nolimits", r"\mathrm", r"\mathit", r"\bf", r"\rm"}


class Unresolved:
    """An explicitly unidentified construct. Two are never equal — identity, not
    value: `"UNKNOWN" == "UNKNOWN"` is true, and that is the bug being avoided."""

    __slots__ = ("what",)

    def __init__(self, what: str):
        self.what = what

    def __repr__(self) -> str:
        return f"Unresolved({self.what!r})"

    def __eq__(self, other: Any) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)


@dataclass
class Node:
    id: str
    label: Any                       # str, or Unresolved


@dataclass
class Edge:
    parent: str
    child: str
    relation: str


@dataclass
class SLT:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# --------------------------------------------------------------------------- lexer
_TOKEN = re.compile(r"""
    (?P<cmd>\\(?:[A-Za-z]+|.))      |   # \alpha, \frac, \, , \!
    (?P<open>\{) | (?P<close>\})    |
    (?P<sup>\^) | (?P<sub>_)        |
    (?P<space>\s+)                  |
    (?P<char>[^\s{}^_\\])
""", re.X)


# Modifiers that carry no ink AND must not interrupt a base from its scripts.
# `\sum\limits_{i}` is a base with a subscript; treating `\limits` as a term
# left the `_` with no base and raised on 18 of 3000 real gold equations.
# Dropped at LEX time so they are never terms at all.
#
# The horizontal spacers belong to the same class for the same reason:
# `c\;\!\!^\dagger` (a creation operator with the dagger tucked in) ended the
# base's run at the first `\;` and left the `^` with nothing to attach to.
# That construct alone accounted for 4 of the 59 scorable gold equations.
# `\hspace`/`\vspace` are deliberately NOT here — they take an argument, and
# dropping the command would leave `{1cm}` behind as symbols either way.
_TRANSPARENT = {r"\limits", r"\nolimits", r"\displaystyle", r"\textstyle",
                r"\scriptstyle", r"\scriptscriptstyle", r"\left", r"\right",
                r"\bigl", r"\bigr", r"\Bigl", r"\Bigr", r"\biggl", r"\biggr",
                r"\,", r"\;", r"\:", r"\!", r"\ ", r"\quad", r"\qquad",
                r"\thinspace", r"\medspace", r"\thickspace", r"\negthinspace",
                # Typeface selectors: they put no ink on the page either, and
                # as TERMS they returned nothing, so `x^\mathrm{i}` raised
                # "script argument is empty" — 55 of 21,334 corpus equations.
                r"\mathrm", r"\mathit", r"\mathsf", r"\mathtt", r"\bf", r"\rm",
                r"\it", r"\operatorname"}


def _lex(src: str) -> list[tuple[str, str]]:
    out, i = [], 0
    while i < len(src):
        m = _TOKEN.match(src, i)
        if not m:
            raise ValueError(f"cannot lex at offset {i}: {src[i:i+12]!r}")
        i = m.end()
        kind = m.lastgroup
        if kind == "space":
            continue
        if kind == "cmd" and m.group() in _TRANSPARENT:
            continue
        if m.group() == "~":               # 057: spacing, whatever kind it lexes as
            continue
        out.append((kind, m.group()))
    return out


# --------------------------------------------------------------------------- parser
_ARG2 = {r"\frac", r"\dfrac", r"\tfrac", r"\binom"}
_ARG1_INSIDE = {r"\sqrt", r"\overline", r"\underline", r"\hat", r"\bar", r"\vec",
                r"\tilde", r"\widehat", r"\widetilde"}


class _Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.toks, self.i = toks, 0
        self.slt = SLT()
        self._ids = count()

    # -- plumbing
    def _peek(self) -> Optional[tuple[str, str]]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self) -> tuple[str, str]:
        if self.i >= len(self.toks):
            raise ValueError("expression ends mid-construct")
        t = self.toks[self.i]
        self.i += 1
        return t

    def _node(self, label: Any) -> str:
        nid = f"n{next(self._ids)}"
        self.slt.nodes.append(Node(nid, label))
        return nid

    def _edge(self, parent: str, child: str, rel: str) -> None:
        self.slt.edges.append(Edge(parent, child, rel))

    # -- grammar
    def parse(self) -> SLT:
        first, last = self._sequence(stop_on_close=False)
        if self.i != len(self.toks):
            raise ValueError("unbalanced expression: trailing '}'")
        return self.slt

    def _sequence(self, stop_on_close: bool) -> tuple[Optional[str], Optional[str]]:
        """A run of terms joined left-to-right by RIGHT. Returns (first, last)."""
        first = last = None
        while True:
            t = self._peek()
            if t is None:
                if stop_on_close:
                    raise ValueError("unbalanced expression: missing '}'")
                break
            if t[0] == "close":
                if not stop_on_close:
                    raise ValueError("unbalanced expression: unexpected '}'")
                break
            head, tail = self._term()
            if head is None:                       # a term with no ink (spacing)
                continue
            if first is None:
                first = head
            else:
                self._edge(last, head, RIGHT)
            last = tail
        return first, last

    def _group(self) -> tuple[Optional[str], Optional[str]]:
        """`{...}` or a single ATOM — the argument of a script or a command.

        Unbraced, the argument is one atom and takes no script of its own:
        `x^a_b` is x with both scripts, not x sup (a sub b). Letting it parse a
        full term let it swallow the following `_` and silently built the tree
        one level too deep. Braces still nest: `x^{a_b}` really is nested.
        """
        t = self._peek()
        if t is None:
            raise ValueError("expression ends where an argument was required")
        if t[0] == "open":
            self._next()
            head, tail = self._sequence(stop_on_close=True)
            self._next()                            # consume '}'
            return head, tail
        return self._term(scripts=False)

    def _term(self, scripts: bool = True) -> tuple[Optional[str], Optional[str]]:
        kind, text = self._next()

        if kind == "open":
            self.i -= 1
            head, tail = self._group()
            base_head, base_tail = head, tail
        elif kind == "cmd":
            if text in _SPACING:
                return None, None
            if text in _ARG2:
                nid = self._node(text)
                for rel in (ABOVE, BELOW):
                    h, _t = self._group()
                    if h is None:
                        raise ValueError(f"{text} argument is empty")
                    self._edge(nid, h, rel)
                base_head = base_tail = nid
            elif text in _ARG1_INSIDE:
                nid = self._node(text)
                h, _t = self._group()
                if h is None:
                    raise ValueError(f"{text} argument is empty")
                self._edge(nid, h, INSIDE)
                base_head = base_tail = nid
            elif text == r"\begin":
                # An environment is structure this parser does not model. Say so.
                name = ""
                if self._peek() and self._peek()[0] == "open":
                    self._next()
                    while self._peek() and self._peek()[0] != "close":
                        name += self._next()[1]
                    self._next()
                depth = 1
                while self.i < len(self.toks) and depth:
                    k, x = self._next()
                    if k == "cmd" and x == r"\begin":
                        depth += 1
                    elif k == "cmd" and x == r"\end":
                        depth -= 1
                        if self._peek() and self._peek()[0] == "open":
                            self._next()
                            while self._peek() and self._peek()[0] != "close":
                                self._next()
                            self._next()
                base_head = base_tail = self._node(Unresolved(name or "environment"))
            else:
                base_head = base_tail = self._node(text)
        elif kind in ("sup", "sub"):
            raise ValueError(f"{text!r} with no base")
        elif kind == "close":
            raise ValueError("unbalanced expression: unexpected '}'")
        else:
            base_head = base_tail = self._node(text)

        # scripts attach to the BASE, and both attach to the same base
        while scripts:
            t = self._peek()
            if t is None or t[0] not in ("sup", "sub"):
                break
            self._next()
            rel = SUP if t[0] == "sup" else SUB
            h, _t = self._group()
            if h is None:
                raise ValueError("script argument is empty")
            # the RIGHTMOST symbol of the base: `{ab}^c` puts c after b, so
            # the edge starts at b. For a single-symbol base head == tail, which
            # is why every earlier test passed either way.
            self._edge(base_tail, h, rel)
        return base_head, base_tail


def parse_latex_slt(latex: str) -> SLT:
    """Parse LaTeX maths into an SLT. Raises ValueError on an unbalanced source."""
    return _Parser(_lex(latex or "")).parse()


# --------------------------------------------------------------------------- .lg
# `,` is both a legitimate symbol and the .lg field separator. LgEval's own
# corpora write the comma symbol as `COMMA`; we escape on the way out and
# restore on the way in so a round trip is lossless either way.
_LG_ESCAPE = {",": "COMMA"}
_LG_UNESCAPE = {v: k for k, v in _LG_ESCAPE.items()}


def _lab_out(label: Any) -> str:
    if isinstance(label, Unresolved):
        return f"UNRESOLVED_{label.what}"
    return _LG_ESCAPE.get(label, label)


def _lab_in(text: str) -> Any:
    if text.startswith("UNRESOLVED_"):
        return Unresolved(text[len("UNRESOLVED_"):])
    return _LG_UNESCAPE.get(text, text)


def slt_to_lg(slt: SLT, *, weight: float = 1.0) -> str:
    out = ["# label graph emitted by pdfdrill mathgold"]
    for n in slt.nodes:
        out.append(f"N, {n.id}, {_lab_out(n.label)}, {weight}")
    for e in slt.edges:
        out.append(f"E, {e.parent}, {e.child}, {e.relation}, {weight}")
    return "\n".join(out) + "\n"


def lg_to_slt(text: str) -> SLT:
    slt = SLT()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if parts[0] == "N" and len(parts) >= 3:
            slt.nodes.append(Node(parts[1], _lab_in(parts[2])))
        elif parts[0] == "E" and len(parts) >= 4:
            slt.edges.append(Edge(parts[1], parts[2], parts[3]))
    return slt
