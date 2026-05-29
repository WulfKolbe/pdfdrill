"""Node: Math expression detection from CharMeta font classification.

Detects inline and display math spans using:
1. Font class from CharMeta (math, text, bold, italic)
2. Unicode math symbols
3. Bridge propagation through operators/parens/digits
4. Display classification by line centering

Reference-aware: uses exclusion set from reference_detector.
Bracket-aware: parenthesized text phrases are excluded.
"""

from __future__ import annotations

from ..context import (
    CharMeta,
    DocumentContext,
    Span,
    MATH_INLINE,
    MATH_DISPLAY,
)
from ..engine import Node
from .reference_detector import get_reference_exclusion_set


MATH_CODEPOINTS: set[int] = set()
MATH_CODEPOINTS.update(range(0x0391, 0x03C9 + 1))  # Greek
MATH_CODEPOINTS.update(range(0x2200, 0x22FF + 1))  # Math operators
MATH_CODEPOINTS.update(range(0x2190, 0x21FF + 1))  # Arrows
MATH_CODEPOINTS.update(range(0x27C0, 0x27EF + 1))
MATH_CODEPOINTS.update(range(0x2980, 0x29FF + 1))
MATH_CODEPOINTS.update(range(0x2A00, 0x2AFF + 1))
MATH_CODEPOINTS.update(range(0x2070, 0x209F + 1))

BRIDGE_CHARS = set("=<>+-*/^_()[]{}|:;, 0123456789")
BREAK_CHARS = set(".\n\f")
VARIABLE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _is_math_unicode(text: str) -> bool:
    return any(ord(ch) in MATH_CODEPOINTS for ch in (text or ""))


def _score_from_meta(ch: str, cm: CharMeta) -> float:
    """Score a character using its CharMeta font classification."""
    if cm.font_class == "math":
        if _is_math_unicode(ch):
            return 1.0
        if ch in VARIABLE_CHARS:
            return 0.9
        return 0.8
    if _is_math_unicode(ch):
        return 0.85
    return 0.0


# ---------------------------------------------------------------------------
# Parenthesized text detection
# ---------------------------------------------------------------------------

def _boost_small_text(
    scores: list[float],
    text: str,
    char_meta: list[CharMeta],
) -> None:
    """Boost math scores for text-font chars at sub/superscript size.

    Text-font chars like 'log' at size 8.0 when body text is 10.9
    are part of math layout (e.g., n^{1+C/log log n}).
    If they're near math-font chars, boost their score.
    """
    from collections import Counter
    text_sizes = [cm.size for cm in char_meta if cm.size > 0 and cm.font_class == "text"]
    if not text_sizes:
        return
    size_counts = Counter(round(s, 0) for s in text_sizes)
    body_size = size_counts.most_common(1)[0][0]

    for i in range(len(scores)):
        if scores[i] > 0.3:
            continue
        cm = char_meta[i]
        if cm.size <= 0 or cm.size >= body_size * 0.85:
            continue
        ch = text[i]
        if ch.isspace() or ch in "\n\f":
            continue
        # This char is at small size -- check if there's math nearby
        has_math_nearby = any(
            scores[j] >= 0.5
            for j in range(max(0, i - 8), min(len(scores), i + 8))
        )
        if has_math_nearby:
            scores[i] = 0.6


def _find_text_parens(text: str, scores: list[float]) -> set[int]:
    """Find parenthesized phrases that are text, not math.

    A paren group like "(this avoids..." where the content after '(' is
    lowercase text should be excluded from math detection.
    """
    excluded: set[int] = set()
    i = 0
    while i < len(text):
        if text[i] == '(':
            # Look ahead: if next 3+ chars are lowercase text with low math score,
            # this is a text parenthetical, not math
            j = i + 1
            text_chars = 0
            while j < len(text) and j < i + 50 and text[j] != ')' and text[j] != '\n':
                if text[j].isalpha() and text[j].islower() and scores[j] < 0.3:
                    text_chars += 1
                j += 1
            if text_chars >= 3 and j < len(text) and text[j] == ')':
                for k in range(i, j + 1):
                    excluded.add(k)
        i += 1
    return excluded


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def _propagate_bridges(
    scores: list[float],
    text: str,
    excluded: set[int],
) -> list[float]:
    """Propagate math scores through bridge characters."""
    result = scores[:]
    for i in excluded:
        if i < len(result):
            result[i] = 0.0

    for _ in range(5):
        changed = False
        for i in range(len(result)):
            if result[i] >= 0.4 or i in excluded or i >= len(text):
                continue
            ch = text[i]
            if ch in BREAK_CHARS or ch not in BRIDGE_CHARS:
                continue
            left = any(result[j] >= 0.5 for j in range(max(0, i - 3), i))
            right = any(result[j] >= 0.5 for j in range(i + 1, min(len(result), i + 4)))
            if left and right:
                result[i] = 0.5
                changed = True
        if not changed:
            break
    return result


def _group_spans(scores: list[float], threshold: float = 0.4) -> list[tuple[int, int]]:
    spans = []
    in_span = False
    start = 0
    for i, s in enumerate(scores):
        if s >= threshold and not in_span:
            in_span = True
            start = i
        elif s < threshold and in_span:
            in_span = False
            spans.append((start, i))
    if in_span:
        spans.append((start, len(scores)))
    return spans


def _merge_nearby(spans: list[tuple[int, int]], text: str, max_gap: int = 2) -> list[tuple[int, int]]:
    if not spans:
        return []
    merged = [spans[0]]
    for start, end in spans[1:]:
        gap = start - merged[-1][1]
        if gap <= max_gap:
            gap_text = text[merged[-1][1]:start] if merged[-1][1] < start else ""
            if "\n" not in gap_text and "\f" not in gap_text:
                merged[-1] = (merged[-1][0], end)
                continue
        merged.append((start, end))
    return merged


MATH_OPERATOR_NAMES = frozenset({
    "log", "sin", "cos", "tan", "exp", "lim", "sup", "inf", "max", "min",
    "det", "dim", "ker", "mod", "gcd", "lcm", "deg", "arg", "hom",
    "ord", "rank", "disc", "Gal", "Aut", "End", "Hom", "sgn", "vol",
})


def _split_at_text_words(
    spans: list[tuple[int, int]],
    raw_scores: list[float],
    text: str,
    char_meta: list[CharMeta] | None = None,
) -> list[tuple[int, int]]:
    """Split spans at runs of 3+ consecutive low-score alphabetic characters.

    Exceptions (don't split at):
    - Small-size text (subscripts/superscripts in math)
    - Known math operator names (log, sin, cos, max, etc.)
    """
    result = []

    # Compute body text size for comparison
    body_size = 10.0
    if char_meta:
        all_sizes = [cm.size for cm in char_meta if cm.size > 0 and cm.font_class == "text"]
        if all_sizes:
            all_sizes.sort()
            body_size = all_sizes[len(all_sizes) // 2]

    for start, end in spans:
        text_run_start = -1
        text_run = 0
        split_points = []
        for i in range(start, end):
            if raw_scores[i] < 0.3 and i < len(text) and text[i].isalpha():
                if text_run == 0:
                    text_run_start = i
                text_run += 1
            else:
                if text_run >= 3:
                    word = text[text_run_start:text_run_start + text_run]
                    if not _is_math_text_run(word, text_run_start, char_meta, body_size):
                        split_points.append((text_run_start, text_run_start + text_run))
                text_run = 0
        if text_run >= 3:
            word = text[text_run_start:text_run_start + text_run]
            if not _is_math_text_run(word, text_run_start, char_meta, body_size):
                split_points.append((text_run_start, text_run_start + text_run))

        if not split_points:
            result.append((start, end))
            continue
        prev = start
        for sp_start, sp_end in split_points:
            if sp_start > prev:
                result.append((prev, sp_start))
            prev = sp_end
        if prev < end:
            result.append((prev, end))
    return result


def _is_math_text_run(word: str, pos: int, char_meta: list[CharMeta] | None, body_size: float) -> bool:
    """Return True if this text run should stay inside a math zone."""
    if word in MATH_OPERATOR_NAMES:
        return True
    if char_meta and pos < len(char_meta):
        run_size = char_meta[pos].size
        if run_size > 0 and run_size < body_size * 0.85:
            return True
    return False


def _filter_spans(
    spans: list[tuple[int, int]],
    raw_scores: list[float],
    text: str,
) -> list[tuple[int, int]]:
    """Filter out low-quality and text-heavy spans."""
    result = []
    for start, end in spans:
        high = sum(1 for i in range(start, end) if raw_scores[i] >= 0.7)
        if high < 1:
            continue
        span_text = text[start:end] if end <= len(text) else ""
        if len(span_text) > 10:
            alpha = sum(1 for c in span_text if c.isalpha() and c.isascii())
            if alpha / len(span_text) > 0.65:
                continue
        result.append((start, end))
    return result


def _balance_brackets(
    spans: list[tuple[int, int]],
    text: str,
) -> list[tuple[int, int]]:
    """Extend spans to include matching closing brackets.

    If a span contains unbalanced opening brackets and the character
    immediately after the span is the matching closer, absorb it.
    Also absorb leading openers if the char before the span opens.
    """
    pairs = {'(': ')', '{': '}', '[': ']'}
    result = []
    for start, end in spans:
        span_text = text[start:end]
        # Extend right: absorb closing brackets
        new_end = end
        for _ in range(5):
            s = text[start:new_end]
            for op, cl in pairs.items():
                while s.count(op) > s.count(cl) and new_end < len(text) and text[new_end] == cl:
                    new_end += 1
                    s = text[start:new_end]
            if new_end == end:
                break
            end = new_end

        # Trim trailing spaces
        while new_end > start and text[new_end - 1] == ' ':
            new_end -= 1

        result.append((start, new_end))
    return result


def _extend_boundaries(
    spans: list[tuple[int, int]],
    text: str,
    char_meta: list[CharMeta],
    raw_scores: list[float],
) -> list[tuple[int, int]]:
    """Extend math spans to absorb adjacent digits, operators, and superscripts.

    Fixes cases like:
    - Absorbs trailing digits after operators (delta > 0)
    - Absorbs superscript digits by size comparison
    - Trims trailing spaces
    """
    extend_chars = set("0123456789=<>+-.,;:!?")
    result = []

    for start, end in spans:
        new_start = start
        new_end = end

        # What is the last meaningful char in the span?
        last_meaningful = ""
        for k in range(new_end - 1, max(new_start - 1, new_end - 4), -1):
            if k >= 0 and k < len(text) and not text[k].isspace():
                last_meaningful = text[k]
                break

        # Extend right: absorb digits/operators that logically continue the expression
        while new_end < len(text):
            ch = text[new_end]
            if ch == " ":
                # If the span ends with an operator (>, <, =, +, -, /)
                # then space + digit/letter is a continuation
                if last_meaningful in ">=<+-/" and new_end + 1 < len(text):
                    next_ch = text[new_end + 1]
                    if next_ch in "0123456789" or (new_end + 1 < len(char_meta) and
                                                    char_meta[new_end + 1].font_class == "math"):
                        new_end += 1  # absorb space
                        continue
                # Superscript digit after space
                if new_end + 1 < len(text) and text[new_end + 1] in "0123456789":
                    cm_next = char_meta[new_end + 1] if new_end + 1 < len(char_meta) else None
                    if cm_next and cm_next.size > 0 and new_start < len(char_meta):
                        body_size = max(cm.size for cm in char_meta[new_start:new_end] if cm.size > 0) if new_end > new_start else 10
                        if cm_next.size < body_size * 0.85:
                            new_end += 2
                            while new_end < len(text) and text[new_end] in "0123456789,/+-":
                                new_end += 1
                            continue
                break
            elif ch in "0123456789":
                if last_meaningful in ">=<+-/^_({[,":
                    new_end += 1
                    last_meaningful = ch
                    continue
                cm = char_meta[new_end] if new_end < len(char_meta) else None
                if cm and cm.size > 0 and new_end - 1 >= new_start:
                    prev_cm = char_meta[new_end - 1]
                    if prev_cm.size > 0 and cm.size < prev_cm.size * 0.85:
                        new_end += 1
                        last_meaningful = ch
                        continue
                break
            else:
                break

        # Trim trailing spaces
        while new_end > new_start and text[new_end - 1] == " ":
            new_end -= 1

        result.append((new_start, new_end))

    return result


def _classify_display(
    spans: list[tuple[int, int]],
    text: str,
    char_meta: list[CharMeta],
    propagated: list[float],
) -> list[tuple[int, int, str, float]]:
    """Classify spans as inline or display math using char positions."""
    # Build line groups from char_meta
    line_groups: dict[int, list[int]] = {}
    for i, cm in enumerate(char_meta):
        if cm.line_idx >= 0:
            line_groups.setdefault(cm.line_idx, []).append(i)

    results = []
    for start, end in spans:
        avg_conf = sum(propagated[i] for i in range(start, end)) / max(end - start, 1)

        is_display = False
        if start < len(char_meta):
            line_idx = char_meta[start].line_idx
            line_positions = line_groups.get(line_idx, [])
            if line_positions:
                line_len = len(line_positions)
                math_in_line = sum(1 for p in line_positions if propagated[p] >= 0.4)
                if line_len > 0 and math_in_line >= 3:
                    math_frac = math_in_line / line_len
                    if math_frac > 0.6 and line_len < 60:
                        # Check centering from x-coordinates
                        xs = [char_meta[p].x0 for p in line_positions if char_meta[p].x0 > 0]
                        xes = [char_meta[p].x1 for p in line_positions if char_meta[p].x1 > 0]
                        if xs and xes:
                            page_idx = char_meta[start].page
                            # Approximate page width (common values: 612, 595)
                            pw = 612.0
                            line_center = (min(xs) + max(xes)) / 2
                            if abs(line_center - pw / 2) < pw * 0.15:
                                is_display = True

        mtype = "display" if is_display else "inline"
        results.append((start, end, mtype, avg_conf))
    return results


def _merge_adjacent_display(
    classified: list[tuple[int, int, str, float]],
    text: str,
    max_gap: int = 5,
) -> list[tuple[int, int, str, float]]:
    """Merge consecutive display math spans on adjacent lines."""
    if not classified:
        return []
    result = []
    i = 0
    while i < len(classified):
        start, end, mtype, conf = classified[i]
        if mtype == "display":
            while i + 1 < len(classified):
                ns, ne, nt, nc = classified[i + 1]
                if nt != "display":
                    break
                gap = text[end:ns] if ns > end else ""
                if len(gap) <= max_gap and all(c in " \n\t" for c in gap):
                    end = ne
                    conf = (conf + nc) / 2
                    i += 1
                else:
                    break
        result.append((start, end, mtype, conf))
        i += 1
    return result


# ---------------------------------------------------------------------------
# Pipeline Node
# ---------------------------------------------------------------------------

def _trim_span(start: int, end: int, text: str, char_meta: list[CharMeta]) -> tuple[int, int]:
    """Trim whitespace and text-font punctuation from span boundaries."""
    # Left: strip whitespace
    while start < end and text[start] in " \t":
        start += 1
    # Right: strip whitespace
    while end > start and text[end - 1] in " \t":
        end -= 1
    # Right: strip trailing comma/semicolon if in text font (not part of math)
    while end > start and text[end - 1] in ",;":
        if end - 1 < len(char_meta) and char_meta[end - 1].font_class != "math":
            end -= 1
        else:
            break
    # Right: strip trailing whitespace again
    while end > start and text[end - 1] in " \t":
        end -= 1
    return start, end


class MathDetectorNode(Node):
    name = "math_detector"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        char_meta = ctx.char_meta

        if not char_meta or len(char_meta) != len(text):
            return ctx

        # Build scores directly from char_meta
        raw_scores = [_score_from_meta(text[i], char_meta[i]) for i in range(len(text))]

        # Boost scores for text-font chars at subscript/superscript size
        # (these are part of math layout even though their font is "text")
        _boost_small_text(raw_scores, text, char_meta)

        # Get reference exclusion set
        excluded = get_reference_exclusion_set(ctx)

        # Find parenthesized text phrases to exclude
        text_parens = _find_text_parens(text, raw_scores)
        excluded = excluded | text_parens

        # Propagate through bridges
        propagated = _propagate_bridges(raw_scores, text, excluded)

        # Group, split, filter, balance brackets
        spans = _group_spans(propagated)
        spans = _merge_nearby(spans, text, max_gap=2)
        spans = _split_at_text_words(spans, raw_scores, text, char_meta)
        spans = _filter_spans(spans, raw_scores, text)
        spans = _balance_brackets(spans, text)
        spans = _extend_boundaries(spans, text, char_meta, raw_scores)
        # Final trim: strip whitespace and trailing text-font punctuation
        spans = [_trim_span(s, e, text, char_meta) for s, e in spans]
        spans = [(s, e) for s, e in spans if s < e]

        # Classify inline vs display
        classified = _classify_display(spans, text, char_meta, propagated)
        classified = _merge_adjacent_display(classified, text)

        # Create L4 math spans
        for start, end, mtype, conf in classified:
            if start >= end or start >= len(text):
                continue
            kind = MATH_DISPLAY if mtype == "display" else MATH_INLINE
            ctx.L4.append(Span(
                start=start,
                end=min(end, len(text)),
                kind=kind,
                props={"confidence": round(conf, 3)},
            ))

        return ctx


def get_math_zones(ctx: DocumentContext) -> list[dict]:
    """Extract math zone information from L4 spans."""
    zones = []
    for s in ctx.L4:
        if s.kind in (MATH_INLINE, MATH_DISPLAY):
            zones.append({
                "start": s.start,
                "end": s.end,
                "type": s.kind.replace("math_", ""),
                "confidence": (s.props or {}).get("confidence"),
                "text": ctx.graphemes[s.start:s.end],
            })
    return zones
