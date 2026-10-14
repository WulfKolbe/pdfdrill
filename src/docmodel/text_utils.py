"""
Shared text primitives for OCR cleanup.

The soft-hyphen decision (does a line-final `word-` join with the next line?)
is needed by more than one operator. Centralizing the regex and the heuristic
here keeps the "good" decision in one place; callers supply their own
surrounding mechanics (which lines to look at, how to splice them).
"""
from __future__ import annotations

import re

# A line whose visible text ends with `word-` (Latin or German umlaut letters).
# group(1) is the word before the hyphen.
HYPHEN_TAIL = re.compile(r"([A-Za-zäöüÄÖÜß]+)-\s*$")

# First whitespace-delimited token of the following line.
NEXT_WORD = re.compile(r"^([A-Za-zäöüÄÖÜß0-9][^\s]*)")

# Prefixes that conventionally retain the hyphen even at end-of-line.
PRESERVE_PREFIXES = {
    # English
    "well", "self", "non", "pre", "anti", "co", "sub", "super",
    "inter", "cross", "re", "un", "over", "under", "multi", "semi",
    "ex", "post", "pro", "neo",
    # German
    "nicht", "halb", "fast", "all", "aussen", "ausser", "innen", "ober",
}


def is_soft_break(tail_word: str, next_token: str) -> bool:
    """
    Decide whether `tail_word-` at end-of-line is a soft hyphen (should join)
    rather than a real compound hyphen (should stay).

    Returns False (keep the hyphen) when the next token is empty, itself
    contains a hyphen (continuing a compound like "to-one"), starts uppercase
    (its own word), or `tail_word` is a conventional hyphen-retaining prefix.
    """
    if not next_token:
        return False
    if "-" in next_token:
        return False
    if next_token[0].isupper():
        return False
    if tail_word.lower() in PRESERVE_PREFIXES:
        return False
    return True


#: 256 — MathPix states the join. A line's own `subtype` says how it attaches
#: to the line BEFORE it; this maps that subtype to what to do at the break.
#: `newline` is a source line break inside running prose, so it joins with a
#: space exactly as `space` does. A subtype that is absent or unknown is not in
#: here, and the caller's own heuristic owns the break (59% of corpus text
#: lines). Three readers now share this dict: the paragraph composer, the
#: DehyphenationProcessor's derived stream, and the Dehyphenate mutator.
STATED_JOIN = {
    "continues_line_no_hyphen": "drop_hyphen",
    "continues_line_no_space": "no_space",
    "continues_line_space": "space",
    "continues_line_newline": "space",
}


def join_stated(prev: str, text: str, action: str) -> tuple[str, str, bool]:
    """
    Splice `text` onto `prev` as `action` (a STATED_JOIN value) states.

    Returns `(prev, chunk, hyphen_dropped)`: the possibly-rewritten preceding
    text, the piece to append to it, and whether a soft hyphen was removed.
    `prev + chunk` is the joined result.

    `drop_hyphen` is only a hyphen instruction when there IS one to drop. On a
    line MathPix already stripped (139,660 corpus lines) it just means "no
    extra character", so never amputate a real last letter.

    `as_is` appends the text untouched, for a caller whose line already
    carries its own joiner.

    ONLY A STATED JOIN IS NORMALIZED HERE. `text_display` carries MathPix's
    own layout, and a leading "\n\n" is it saying the line begins a block:
    all 34 numbered rules of texbook Appendix G start one that way. Stripping
    that from every line cost 8 of them their line in the projection, so a
    line that states no join is joined verbatim by the caller and never
    reaches this function.
    """
    if action == "as_is":
        return prev, text, False
    head = prev.rstrip()
    tail = text.lstrip()
    dropped = False
    if action == "drop_hyphen":
        m = HYPHEN_TAIL.search(head)
        if m is not None:
            head = head[: m.start()] + m.group(1)
            dropped = True
        return head, tail, dropped
    if action == "no_space":
        return head, tail, False
    return head, (" " + tail if tail else ""), False


def join_stated_lines(parts, default=None) -> str:
    """
    Join `(text, subtype)` continuation lines into one string.

    `subtype` decides via STATED_JOIN. Where it is absent `default` decides —
    a STATED_JOIN action, or a callable `(joined_so_far, next_text) -> action`
    for a caller with its own heuristic — and `None`, from either, means join
    with one space and touch nothing else, which is what all four callers did
    before. Empty texts are skipped, as they all did too.

    That default is not laziness: a line stating no join keeps whatever
    `text_display` gave it, including the leading "\n\n" MathPix uses to say
    the line begins a block. Normalizing those away is a layout decision this
    function has no business making, and it silently merged 8 of texbook
    Appendix G's 34 numbered rules into the rule above them.

    This exists because four composers each concatenated the lines of one
    object — paragraph, list item, abstract, sidenote — and each one joined
    with a space, so MathPix's stated join was ignored four times over in the
    very field it is stated in.
    """
    out = ""
    started = False
    for text, subtype in parts:
        if not text:
            continue
        if not started:
            out = text
            started = True
            continue
        action = STATED_JOIN.get(subtype or "")
        if action is None and default is not None:
            action = default(out, text) if callable(default) else default
        if action is None:
            out = out + " " + text
            continue
        head, chunk, _ = join_stated(out, text, action)
        out = head + chunk
    return out
