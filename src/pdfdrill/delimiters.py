r"""308 — `\left(` closed by `\right.`

`\right.` is an INVISIBLE right delimiter. It is legal, it compiles, and it
prints nothing: `\left( x \right.` sets an opening parenthesis with no closing
one. The construct exists for genuine one-sided fences — a `cases`-style brace,
a bracket carried across a line break — so its presence is not by itself a
defect.

It becomes one when the scan shows a delimiter that the LaTeX does not print.
Then the reader sees `(x` where the page shows `(x)`, nothing errors, and no
width or balance check fires: to a bracket counter, `\left` and `\right` are
matched. That is the whole difficulty — the defect is invisible to every rule
that counts rather than looks.

This module only COUNTS the construct and reports which opener it closes.
Whether the page shows a delimiter is a question about the scan, not about the
LaTeX, and is not decided here.
"""

from __future__ import annotations

import re

_LR = re.compile(r"\\(left|right)\s*")

#: The delimiter tokens TeX accepts after \left / \right. `.` is the invisible
#: one. Longest first, so `\langle` is not read as `\l` + `angle`.
_DELIMS = [
    r"\langle", r"\rangle", r"\lfloor", r"\rfloor", r"\lceil", r"\rceil",
    r"\lbrace", r"\rbrace", r"\lbrack", r"\rbrack", r"\lgroup", r"\rgroup",
    r"\lmoustache", r"\rmoustache", r"\arrowvert", r"\Arrowvert",
    r"\bracevert", r"\updownarrow", r"\Updownarrow", r"\uparrow",
    r"\downarrow", r"\Uparrow", r"\Downarrow", r"\backslash",
    r"\vert", r"\Vert", r"\|", r"\{", r"\}", r"\/",
    "(", ")", "[", "]", "/", "|", ".", "<", ">",
]
_DELIMS.sort(key=len, reverse=True)


def _read_delim(text: str, i: int):
    """(delimiter, next index) at position i, or (None, i)."""
    for d in _DELIMS:
        if text.startswith(d, i):
            return d, i + len(d)
    return None, i


def pairs(latex: str) -> list:
    r"""Depth-matched `\left`/`\right` pairs.

    A stack, not a regex: `\left( \left[ x \right] \right.` has its invisible
    right closing the PARENTHESIS, and pairing by proximity would blame the
    bracket. Unbalanced input yields the pairs that did match plus the
    leftovers, rather than nothing.
    """
    out, stack = [], []
    for m in _LR.finditer(latex or ""):
        d, _end = _read_delim(latex, m.end())
        if d is None:
            continue
        if m.group(1) == "left":
            stack.append((d, m.start()))
        elif stack:
            od, opos = stack.pop()
            out.append({"left": od, "right": d,
                        "left_pos": opos, "right_pos": m.start()})
    return out


def invisible_rights(latex: str) -> list:
    r"""Every pair whose right delimiter is `.` — the invisible one."""
    return [p for p in pairs(latex) if p["right"] == "."]


def count(latex: str) -> dict:
    r"""`\right.` occurrences, and the openers they close."""
    inv = invisible_rights(latex)
    by_opener = {}
    for p in inv:
        by_opener[p["left"]] = by_opener.get(p["left"], 0) + 1
    # A `\right.` that never matched an opener is still a `\right.`; counting
    # only the paired ones would under-report exactly the malformed values
    # this is looking for.
    raw = len(re.findall(r"\\right\s*\.", latex or ""))
    return {"right_dot_raw": raw, "right_dot_paired": len(inv),
            "by_opener": by_opener,
            "opened_by_paren": by_opener.get("(", 0)}
