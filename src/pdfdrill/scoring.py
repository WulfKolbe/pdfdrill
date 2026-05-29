"""
Phase-2 scoring: turn the multi-provenance comparison into numbers.

For each equation we have up to three readings of the same crop — MathPix
(from lines.json), Snip (/v3/text, with a confidence), and an LLM — plus the
CDN image. Scoring quantifies how well they agree, so a human (and later the
self-learning loop) can rank equations by review priority instead of eyeballing
all of them.

LaTeX is normalized before comparison (a light, language-aware canonicalization
in the comby/loadable-grammar spirit — strip delimiters, spacing macros,
\left/\right, \operatorname wrappers) so cosmetic differences don't count as
disagreement. `latex_similarity` is a 0..1 ratio on the normalized forms.
"""
from __future__ import annotations

import difflib
import re

_DELIMS = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$"))
_SPACING = ("\\,", "\\;", "\\!", "\\:", "\\ ", "~")
_OPNAME = re.compile(r"\\operatorname\s*\{([^}]*)\}")
_MATHRM = re.compile(r"\\(?:mathrm|text|mathbf|mathit|boldsymbol)\s*\{([^}]*)\}")


def normalize_latex(s: str) -> str:
    """Canonicalize a LaTeX string for comparison (not for display)."""
    if not s:
        return ""
    s = s.strip()
    for left, right in _DELIMS:
        if s.startswith(left) and s.endswith(right) and len(s) >= len(left) + len(right):
            s = s[len(left):-len(right)]
            break
    s = _OPNAME.sub(r"\1", s)
    s = _MATHRM.sub(r"\1", s)
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\begin{aligned}", "").replace("\\end{aligned}", "")
    s = s.replace("&", "").replace("\\\\", "")
    for sp in _SPACING:
        s = s.replace(sp, "")
    s = re.sub(r"\s+", "", s)
    # Collapse single-token braces so x^{2}==x^2, _{i}==_i, {\beta}==\beta.
    for _ in range(3):                       # a few passes for nested cases
        new = re.sub(r"\{(\\?\w+)\}", r"\1", s)
        if new == s:
            break
        s = new
    return s


def latex_similarity(a: str, b: str) -> float:
    na, nb = normalize_latex(a), normalize_latex(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def score_equation(mathpix_latex: str, candidates: dict[str, dict],
                   low_agreement: float = 0.75,
                   low_confidence: float = 0.6) -> dict:
    """Score one equation.

    candidates: {provenance: {"latex": str, "score": float|None}}.
    Returns {agreement:{prov:sim}, mean_agreement, snip_confidence,
             min_signal, flags:[...]}.
    """
    agreement = {prov: round(latex_similarity(mathpix_latex, c.get("latex", "")), 3)
                 for prov, c in candidates.items() if c.get("latex")}
    snip_conf = None
    snip = candidates.get("snip")
    if snip and snip.get("score") is not None:
        snip_conf = round(float(snip["score"]), 3)

    mean_agreement = round(sum(agreement.values()) / len(agreement), 3) if agreement else None

    # Corroborated = at least two independent readings agree strongly with the
    # MathPix LaTeX. Independent consensus outweighs a single tool's low
    # confidence, so a corroborated equation is trusted despite low snip conf.
    high = [v for v in agreement.values() if v >= 0.9]
    corroborated = len(high) >= 2

    flags: list[str] = []
    if mean_agreement is not None and mean_agreement < low_agreement:
        flags.append("low_agreement")
    if snip_conf is not None and snip_conf < low_confidence and not corroborated:
        flags.append("low_confidence")
    if not candidates:
        flags.append("no_competing_reading")

    # A single 0..1 review signal: lower = more worth a human look.
    signals = [v for v in (mean_agreement, snip_conf) if v is not None]
    min_signal = round(min(signals), 3) if signals else None

    return {
        "agreement": agreement,
        "mean_agreement": mean_agreement,
        "snip_confidence": snip_conf,
        "corroborated": corroborated,
        "min_signal": min_signal,
        "flags": flags,
    }
