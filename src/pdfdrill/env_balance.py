"""126 — record that MathPix emitted an environment fragment, without blanking
the equation.

MathPix glues a stray environment CLOSER onto display math that ends a list:

    \\[ (A \\vee B)^{\\prime}=-B \\vee A . \\] \\end{itemize}

Two separate facts live in that one value, and each is worth keeping:

  * The MATHEMATICS is intact. `renderable()` drops the trailing \\end{X} and the
    equation typesets correctly — that repair took 0902.0431 from 31 unrendered
    equations to 7, at confidences up to 1.000.
  * The EXTRACTION is defective. MathPix returned a fragment of the surrounding
    prose structure inside a maths value, and no amount of correct rendering
    makes that not have happened.

Rejecting the value (the other reading of this task) records the second fact by
destroying the first. This module records the second fact directly: a flag on
the object naming the count mismatch and the environment, leaving the render
alone.

The flag is diagnostic only. Nothing gates on it, because a value that renders
correctly after repair is not a rendering problem — it is an input-quality
signal about the OCR, and belongs where input quality is read.
"""
from __future__ import annotations

import re

_BEGIN = re.compile(r"\\begin\{(\w+\*?)\}")
_END = re.compile(r"\\end\{(\w+\*?)\}")
#: a closer at the very end of the value is the shape renderable() repairs
_TRAILING_END = re.compile(r"\\end\{(\w+\*?)\}\s*$")


def env_defect(latex: str) -> dict | None:
    """Environment-balance defect in `latex`, or None when it is balanced.

        {"unmatched_end":   {"itemize": 1},
         "unmatched_begin": {},
         "trailing":        "itemize" | None}

    Counts, not set membership: a value opening `array` once and closing it
    twice is unbalanced even though both names appear on both sides, and a
    set-difference check would call it clean.
    """
    if not latex:
        return None
    b, e = {}, {}
    for m in _BEGIN.finditer(latex):
        b[m.group(1)] = b.get(m.group(1), 0) + 1
    for m in _END.finditer(latex):
        e[m.group(1)] = e.get(m.group(1), 0) + 1
    if b == e:
        return None
    un_end = {k: e[k] - b.get(k, 0) for k in e if e[k] > b.get(k, 0)}
    un_beg = {k: b[k] - e.get(k, 0) for k in b if b[k] > e.get(k, 0)}
    if not un_end and not un_beg:
        return None
    t = _TRAILING_END.search(latex)
    return {"unmatched_end": un_end, "unmatched_begin": un_beg,
            "trailing": t.group(1) if t and t.group(1) in un_end else None}


def flag_document(doc) -> int:
    """Set `env_mismatch` on every Equation/Formula whose environments do not
    balance. Returns how many objects were flagged.

    Idempotent: re-running overwrites the same prop with the same value, and a
    value that has since been corrected loses the flag rather than keeping a
    stale one.
    """
    n = 0
    for o in doc.objects.values():
        if o.type not in ("Equation", "Formula"):
            continue
        d = env_defect(o.props.get("latex") or "")
        if d:
            o.props["env_mismatch"] = d
            n += 1
        elif "env_mismatch" in o.props:
            del o.props["env_mismatch"]
    return n


def summarise(doc) -> dict[str, int]:
    """{environment: count} over the flagged objects — what a report shows."""
    out: dict[str, int] = {}
    for o in doc.objects.values():
        d = (o.props or {}).get("env_mismatch")
        if not d:
            continue
        for env in list(d.get("unmatched_end", {})) + list(d.get("unmatched_begin", {})):
            out[env] = out.get(env, 0) + 1
    return out
