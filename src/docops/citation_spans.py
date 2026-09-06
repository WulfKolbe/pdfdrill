"""Where a citation GROUP sits in a line — the one derivation, read by both
projectors.

A citation group (`[a, b]`, `(Smith 1999; Jones 2001)`) is SEVERAL Citation
objects over ONE stretch of prose. 645 worked that out inside `tiddlywiki.py`:
which spans belong to one group, whether the group is wrapped in a bracket pair
of its own, and how to replace it WITHOUT deleting the characters no key covers.
642 needs exactly the same three answers for the LaTeX projector, so the logic
moved here rather than being derived a second time — two derivations of one
rule is how the two projections start disagreeing about the same document.

What is deliberately NOT here is the REPLACEMENT text. TiddlyWiki emits one
`{{<REF title>||CIT}}` per distinct key with the separators between them kept
(the `CIT` template supplies the brackets); LaTeX emits one `\\cite{a,b}` for the
whole group (`\\cite` supplies the brackets AND the separators). The groups are
the same; what is written over them is each projector's own business.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

#: What may separate two spans of ONE citation group: whitespace and the `,`/`;`
#: a multi-key citation is punctuated with. Anything else (a surname no detector
#: recognised, a phrase) ENDS the group, so it is emitted as the prose it is.
SEP_ONLY = re.compile(r"[\s,;]*")

#: The bracket pairs a citation group may be wrapped in. A projector whose
#: replacement supplies its own brackets must swallow the pair or the reader
#: gets `[[a], [b]]`.
BRACKETS = {"[": "]", "(": ")"}

#: One recognised citation span in a line: `(offset, length, payload)`. The
#: payload is whatever the caller needs back — a REF tiddler title, a citekey.
Span = tuple[int, int, Any]


@dataclass(frozen=True)
class Group:
    """One citation group on one line.

    `start`/`length` are the extent to REPLACE — the members' extent, plus the
    flanking bracket pair when the group is wrapped by one (`flanked`).
    `inner_start`/`inner_end` are the members' own extent, which is what a
    lossless replacement is built over.
    """
    start: int
    length: int
    inner_start: int
    inner_end: int
    members: tuple[Span, ...]
    flanked: bool

    @property
    def end(self) -> int:
        return self.start + self.length

    @property
    def payloads(self) -> list[Any]:
        """The DISTINCT payloads in source order (a key repeated inside one
        group is cited once)."""
        out: list[Any] = []
        seen: set = set()
        for _off, _ln, payload in self.members:
            if payload not in seen:
                seen.add(payload)
                out.append(payload)
        return out


def line_text(doc, line_anchor) -> str:
    """The `mathpix_lines` text a span's offset/length is measured against."""
    stream = doc.streams.get("mathpix_lines")
    payload = (stream.payload.get(line_anchor) or {}) if stream else {}
    return payload.get("text_display") or payload.get("text") or ""


def groups(text: str, spans: Iterable[Span], *,
           on_out_of_bounds: Optional[Callable[[], None]] = None) -> list[Group]:
    """Merge one line's citation spans into groups.

    Two spans belong to one group when they are identical, when they overlap, or
    when only `SEP_ONLY` separates them — the three shapes a multi-key citation
    takes. A span the line is too short for is DROPPED and reported through
    `on_out_of_bounds`, never clamped and never merged into a neighbour: a
    clamped span replaces the wrong characters and says nothing about it.
    """
    usable: list[Span] = []
    for off, length, payload in spans:
        if off < 0 or length < 0 or off + length > len(text):
            if on_out_of_bounds is not None:
                on_out_of_bounds()
            continue
        usable.append((off, length, payload))

    merged: list[list] = []
    for off, length, payload in sorted(usable, key=lambda s: (s[0], s[1])):
        end = off + length
        if merged:
            g = merged[-1]
            gap = text[g[1]:off] if off >= g[1] else ""
            if off <= g[1] or SEP_ONLY.fullmatch(gap):
                g[1] = max(g[1], end)
                g[2].append((off, length, payload))
                continue
        merged.append([off, end, [(off, length, payload)]])

    out: list[Group] = []
    for inner_start, inner_end, members in merged:
        flanked = (0 < inner_start and inner_end < len(text)
                   and BRACKETS.get(text[inner_start - 1]) == text[inner_end])
        start = inner_start - 1 if flanked else inner_start
        end = inner_end + 1 if flanked else inner_end
        out.append(Group(start=start, length=end - start,
                         inner_start=inner_start, inner_end=inner_end,
                         members=tuple(members), flanked=flanked))
    return out


def interleave(text: str, group: Group, render: Callable[[Any], str], *,
               on_text_kept: Optional[Callable[[int], None]] = None) -> str:
    """A LOSSLESS replacement for `group`: one `render(payload)` per DISTINCT
    payload in source order, with every character BETWEEN the recognised spans
    emitted VERBATIM.

    The only text a group loses this way is the citation spans themselves and
    (the caller's choice) the flanking bracket pair. `(Linsker 1988; Oja 1989;
    Sanger 1989; Földiák 1990; Plumbey 1991)` keeps `Földiák 1990` — no detector
    recognises that surname (645-b), and a substitution that swallowed the whole
    parenthetical would delete a reference the document actually makes. The kept
    characters are reported through `on_text_kept`.
    """
    out: list[str] = []
    cursor = group.inner_start
    seen: set = set()
    for off, length, payload in group.members:
        if off > cursor:
            out.append(text[cursor:off])
            if on_text_kept is not None:
                on_text_kept(off - cursor)
        if payload not in seen:
            seen.add(payload)
            out.append(render(payload))
        cursor = max(cursor, off + length)
    if cursor < group.inner_end:
        out.append(text[cursor:group.inner_end])
        if on_text_kept is not None:
            on_text_kept(group.inner_end - cursor)
    return "".join(out)
