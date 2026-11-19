r"""Counting the paragraph faults a reader can see, for the ratchet.

Three numbers, all COUNTS. A rate is not usable here: paragraph work moves
the denominator, and a measure whose denominator grows when the thing it
measures grows cannot fail. 5a3b3977 was reported as an improvement on a
rate that fell from 18.2 % to 15.7 % while the absolute number of bad splits
rose by 808 (coordinator, 2026-11-19).

  mid_sentence   a paragraph that begins in the middle of a sentence: it
                 starts lower-case and the paragraph before it did not end in
                 sentence punctuation. This is the fault the owner sees when
                 he reads a page.
  word_lists     the known FALSE POSITIVE of that test, counted apart rather
                 than silently included or silently dropped.
  fragments      a paragraph of fewer than 3 characters. No false positives of
                 the above kind; a bare `x` or `ρ` is never a paragraph.
"""
from __future__ import annotations

import re

#: Sentence punctuation, including the closing marks a sentence may end on.
_END = tuple(".!?:;”“\"')]»")

#: WHAT A WORD LIST IS, FIXED BEFORE THE NEXT DOCUMENT IS LOOKED AT.
#:
#: 2312.11532 p7 prints topic lists -- `spacecraft, orbit, module, capsule,
#: endeavour` -- one per row. They begin lower-case and follow a paragraph
#: that does not end in a full stop, so the mid-sentence test catches all
#: eight of them, and they are not faults: a list is its own unit and begins
#: lower-case because it is a list.
#:
#: Three or more comma-separated items, each of at most two words, and no
#: sentence punctuation anywhere in the line. A keyword row, an author list
#: and a topic row all satisfy it; a sentence that happens to contain two
#: commas does not, because it ends in a full stop and its items are longer.
_ITEMS = 3
_WORDS_PER_ITEM = 2


def is_word_list(text: str) -> bool:
    t = (text or "").strip()
    if not t or any(ch in t for ch in ".!?;"):
        return False
    items = [p.strip() for p in t.split(",")]
    if len(items) < _ITEMS or not all(items):
        return False
    return all(len(p.split()) <= _WORDS_PER_ITEM for p in items)


def counts(paragraphs) -> dict:
    """`paragraphs`: the texts, in reading order, of one document's
    Paragraph objects. Returns the three counts."""
    out = {"paragraphs": 0, "mid_sentence": 0, "word_lists": 0, "fragments": 0}
    prev = None
    for text in paragraphs:
        t = (text or "").strip()
        out["paragraphs"] += 1
        if len(t) < 3:
            out["fragments"] += 1
        if (t[:1].islower() and prev is not None
                and not prev.rstrip().endswith(_END)):
            if is_word_list(t):
                out["word_lists"] += 1
            else:
                out["mid_sentence"] += 1
        prev = t
    return out
