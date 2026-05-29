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
