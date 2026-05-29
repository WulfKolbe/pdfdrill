"""Node: Tokenization with hyphen resolution.

Splits the grapheme string into word tokens using Unicode-aware regex,
then detects and resolves line-end hyphens.
"""

from __future__ import annotations

import re

from ..context import (
    DocumentContext,
    Span,
    TOKEN,
    HYPHEN,
)
from ..engine import Node


# Unicode word pattern: sequences of word characters (letters, digits, combining marks)
# plus internal hyphens/apostrophes that don't end the word
_WORD_RE = re.compile(r"[\w][\w''ʼ-]*[\w]|[\w]", re.UNICODE)

# Line-end hyphen: hyphen at end of line followed by continuation
_HYPHEN_RE = re.compile(r"(\w+)-\n(\w+)", re.UNICODE)


class TokenizerNode(Node):
    name = "tokenizer"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes

        # Phase 1: detect line-end hyphens
        hyphen_resolutions = _detect_hyphens(text)
        hyphen_positions = {h_pos for h_pos, res, merged, comps in hyphen_resolutions if res == "soft_removed"}

        # Phase 2: build a "cleaned" view for tokenization
        # but keep original indices by building an index map
        clean_parts: list[str] = []
        old_to_new: list[int] = []  # old index -> new index
        new_to_old: list[int] = []  # new index -> old index
        new_idx = 0

        i = 0
        while i < len(text):
            if i in hyphen_positions:
                # Skip the hyphen and the following newline
                old_to_new.append(-1)  # hyphen skipped
                i += 1
                if i < len(text) and text[i] == "\n":
                    old_to_new.append(-1)  # newline skipped
                    i += 1
                continue
            clean_parts.append(text[i])
            old_to_new.append(new_idx)
            new_to_old.append(i)
            new_idx += 1
            i += 1

        clean_text = "".join(clean_parts)

        # Phase 3: tokenize on the cleaned text
        for m in _WORD_RE.finditer(clean_text):
            # Map back to original indices
            clean_start = m.start()
            clean_end = m.end()

            if clean_start >= len(new_to_old) or clean_end - 1 >= len(new_to_old):
                continue

            orig_start = new_to_old[clean_start]
            orig_end = new_to_old[clean_end - 1] + 1

            ctx.L3.append(Span(
                start=orig_start,
                end=orig_end,
                kind=TOKEN,
            ))

        # Phase 4: add hyphen resolution spans
        for h_pos, resolution, merged_form, components in hyphen_resolutions:
            props: dict = {"resolution": resolution}
            if merged_form:
                props["merged_form"] = merged_form
            if components:
                props["components"] = components
            ctx.L3.append(Span(
                start=h_pos,
                end=h_pos + 1,
                kind=HYPHEN,
                props=props,
            ))

        return ctx


def _detect_hyphens(text: str) -> list[tuple[int, str, str | None, list[str] | None]]:
    """Find line-end hyphens and decide whether they are soft (to remove) or hard (to keep).

    Returns list of (hyphen_pos, resolution, merged_form, components).
    """
    resolutions: list[tuple[int, str, str | None, list[str] | None]] = []

    for m in _HYPHEN_RE.finditer(text):
        prefix = m.group(1)
        suffix = m.group(2)
        hyphen_pos = m.start() + len(prefix)

        # Heuristic: if the suffix starts with a lowercase letter,
        # it's likely a soft hyphen (word continuation)
        if suffix and suffix[0].islower():
            merged = prefix + suffix
            resolutions.append((
                hyphen_pos,
                "soft_removed",
                merged,
                [prefix + "-", suffix],
            ))
        else:
            # Uppercase after hyphen-newline: likely a hard/compound hyphen
            resolutions.append((
                hyphen_pos,
                "hard_retained",
                None,
                [prefix + "-", suffix],
            ))

    return resolutions
