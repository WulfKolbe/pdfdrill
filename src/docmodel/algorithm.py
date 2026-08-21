"""086 — `algorithm` / `algorithmic` / `algpseudocode` become `Algorithm` objects.

Not a CodeListing. out/078 measured 97 documents opening an algorithm
environment against 41 opening lstlisting: pseudocode is the larger population
and it is a different object. A listing is source someone can run; an algorithm
float is a typeset description of a procedure, with numbered lines, keywords
set in a maths font, and cross-references into the surrounding prose. Storing
one as the other would assert something false about both.

Two shapes, and they nest:

    \\begin{algorithm}            a FLOAT: carries \\caption and \\label, and
      \\caption{..}\\label{..}     usually wraps the body below
      \\begin{algorithmic}[1]     the BODY: \\State, \\For, \\If, ...
      \\end{algorithmic}
    \\end{algorithm}

A float that wraps a body yields ONE object, not two — otherwise every
algorithm in the corpus counts twice. A bare `algorithmic` with no float
around it is its own object, and carries no caption because there is nowhere
to put one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from docmodel.codelisting import _balanced, clean_caption

_FLOAT = re.compile(r"\\begin\s*\{(algorithm)\*?\}")
_BODY = re.compile(r"\\begin\s*\{(algorithmic|algpseudocode)\*?\}")
_CAPTION = re.compile(r"\\caption\s*\*?\s*\{")
_LABEL = re.compile(r"\\label\s*\{")
#: the statement macros algorithmic/algpseudocode define — counting them is how
#: a body's size is reported, since a pseudocode line is a macro call and not a
#: text line
_STEP = re.compile(r"\\(State|Statex|For|EndFor|While|EndWhile|If|ElsIf|Else|"
                   r"EndIf|Repeat|Until|Function|EndFunction|Procedure|"
                   r"EndProcedure|Loop|EndLoop|Require|Ensure|Return|Comment)\b")


def _end_of(text: str, env: str, start: int) -> int:
    """Index of the matching \\end{env}, honouring nesting of the same env."""
    b = re.compile(r"\\begin\s*\{" + env + r"\*?\}")
    e = re.compile(r"\\end\s*\{" + env + r"\*?\}")
    depth, i = 1, start
    while i < len(text):
        mb, me = b.search(text, i), e.search(text, i)
        if me is None:
            return -1
        if mb and mb.start() < me.start():
            depth += 1
            i = mb.end()
            continue
        depth -= 1
        if depth == 0:
            return me.start()
        i = me.end()
    return -1


def _first_group(text: str, pat: re.Pattern) -> str:
    m = pat.search(text)
    if not m:
        return ""
    inner, _ = _balanced(text, m.end() - 1, "{", "}")
    return inner


@dataclass
class Algorithm:
    body: str                        # VERBATIM
    caption: str = ""
    caption_raw: str = ""
    label: str = ""
    kind: str = "algorithm"          # algorithm | algorithmic | algpseudocode
    floated: bool = False            # was there an algorithm float around it
    source_file: str = ""
    source_line: int = 0
    steps: int = 0                   # \State/\For/\If… count
    options: dict = field(default_factory=dict)

    def props(self, bibkey: str = "") -> dict:
        p = {"caption": self.caption, "caption_raw": self.caption_raw,
             "label": self.label, "body": self.body, "env": self.kind,
             "floated": self.floated, "source_file": self.source_file,
             "source_line": self.source_line, "steps": self.steps,
             "lines": self.body.count("\n") + 1 if self.body else 0}
        if bibkey:
            p["bibkey"] = bibkey
        return p


def parse_algorithms(text: str, source_file: str = "") -> Iterator[Algorithm]:
    """Every algorithm/algorithmic/algpseudocode in `text`.

    A float that contains a body yields one object. Bodies already inside a
    float are not emitted again.
    """
    claimed: list[tuple[int, int]] = []
    out: list[Algorithm] = []
    for m in _FLOAT.finditer(text):
        end = _end_of(text, "algorithm", m.end())
        if end < 0:
            continue
        body = text[m.end():end]
        claimed.append((m.end(), end))
        cap = _first_group(body, _CAPTION)
        out.append(Algorithm(
            body=body.strip("\n"), caption=clean_caption(cap), caption_raw=cap,
            label=_first_group(body, _LABEL), kind="algorithm", floated=True,
            source_file=source_file, source_line=text.count("\n", 0, m.start()) + 1,
            steps=len(_STEP.findall(body))))
    for m in _BODY.finditer(text):
        if any(a <= m.start() < b for a, b in claimed):
            continue                       # already inside a float we emitted
        env = m.group(1)
        end = _end_of(text, env, m.end())
        if end < 0:
            continue
        body = text[m.end():end]
        cap = _first_group(body, _CAPTION)
        out.append(Algorithm(
            body=body.strip("\n"), caption=clean_caption(cap), caption_raw=cap,
            label=_first_group(body, _LABEL), kind=env, floated=False,
            source_file=source_file, source_line=text.count("\n", 0, m.start()) + 1,
            steps=len(_STEP.findall(body))))
    out.sort(key=lambda a: a.source_line)
    return iter(out)


def to_docobjects(algs, bibkey: str = ""):
    from docmodel.core import DocObject
    return [DocObject(type="Algorithm", props=a.props(bibkey)) for a in algs]
