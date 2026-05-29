"""Metrics for evaluating pipeline quality at each layer."""

from __future__ import annotations

from .context import (
    CITATION, EMPHASIS_BOLD, EMPHASIS_ITALIC, EQUATION_NUMBER,
    FLAG, MATH_DISPLAY, MATH_INLINE, PARAGRAPH, SENTENCE,
    STRUCTURAL_REF, STYLE_RUN, TOKEN, DocumentContext,
)
from .engine import Metric


class CharCoverage(Metric):
    name = "char_coverage"

    def compute(self, ctx: DocumentContext) -> float:
        text = ctx.graphemes
        if not text:
            return 0.0
        total = sum(1 for c in text if not c.isspace())
        if total == 0:
            return 0.0
        covered = set()
        for s in ctx.L1:
            if s.kind == STYLE_RUN:
                for i in range(s.start, s.end):
                    if i < len(text) and not text[i].isspace():
                        covered.add(i)
        return len(covered) / total


class TemplateCoverage(Metric):
    name = "template_coverage"

    def compute(self, ctx: DocumentContext) -> float:
        runs = [s for s in ctx.L1 if s.kind == STYLE_RUN]
        if not runs:
            return 0.0
        total = sum(s.end - s.start for s in runs)
        templated = sum(s.end - s.start for s in runs if s.template)
        return templated / total if total else 0.0


class TokenDensity(Metric):
    name = "token_density"

    def compute(self, ctx: DocumentContext) -> float:
        text_len = len(ctx.graphemes)
        tokens = sum(1 for s in ctx.L3 if s.kind == TOKEN)
        return tokens / text_len * 1000 if text_len else 0.0


class ParagraphCount(Metric):
    name = "paragraphs"

    def compute(self, ctx: DocumentContext) -> float:
        return float(sum(1 for s in ctx.L2 if s.kind in (PARAGRAPH, "heading")))


class MathZoneCount(Metric):
    name = "math_zones"

    def compute(self, ctx: DocumentContext) -> float:
        return float(sum(1 for s in ctx.L4 if s.kind in (MATH_INLINE, MATH_DISPLAY)))


class ReferenceCount(Metric):
    name = "references"

    def compute(self, ctx: DocumentContext) -> float:
        ref_kinds = {CITATION, EQUATION_NUMBER, EQUATION_REF, STRUCTURAL_REF}
        return float(sum(1 for s in ctx.L3 if s.kind in ref_kinds))


class FlagCount(Metric):
    name = "flags"

    def compute(self, ctx: DocumentContext) -> float:
        return float(sum(1 for s in ctx.L4 if s.kind == FLAG))


ALL_METRICS: list[Metric] = [
    CharCoverage(),
    TemplateCoverage(),
    TokenDensity(),
    ParagraphCount(),
    MathZoneCount(),
    ReferenceCount(),
    FlagCount(),
]
