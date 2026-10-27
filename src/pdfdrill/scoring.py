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
    # 025: a trailing sentence mark is not mathematics. Dropping it here means
    # a separated value and an unseparated one still compare EQUAL, so a
    # half-migrated corpus never reads as a finding storm.
    from .mathqc import strip_trailing_punct_for_compare
    s = strip_trailing_punct_for_compare(s)
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


#: The font commands `normalize_latex` does NOT already unwrap (`_MATHRM` has
#: mathrm/text/mathbf/mathit/boldsymbol, `_OPNAME` has operatorname). A
#: multi-letter identifier's FONT is not its content: MathPix reads
#: `\textsc{TrivialTree}` as `\operatorname{TrivialTree}`, and the two are the
#: same function in the same formula.
_FONT_WRAP = re.compile(r"\\(?:operatorname|textsc|textit|mathit|textrm|textsf|"
                        r"mathsf|texttt|mathtt|mbox)\s*\{([^{}]*)\}")
#: `x^{\prime}` and `x'` are one apostrophe in two spellings.
_PRIME = re.compile(r"\^\{?\\prime\}?")
#: A run of scripts hanging off one base: `_i^2`, `^2_i`, `'_i`, `_i'`. Sub and
#: super (and a prime) COMMUTE, and the two orders are the same mathematics.
_SCRIPT_RUN = re.compile(r"((?:[_^](?:\{[^{}]*\}|\\?\w+)|'){2,})")
_SCRIPT_PART = re.compile(r"[_^](?:\{[^{}]*\}|\\?\w+)|'")


def author_match_key(s: str) -> str:
    r"""The key that decides "the author wrote THIS formula".

    `normalize_latex` is the comparison this repo SCORES with, and every
    agreement number it quotes came from it. This is a stricter question than
    scoring asks: not how close two readings are, but whether a model object
    and an author's own source are the same piece of mathematics — because what
    is attached is shown to a reader as the author's LaTeX, and a wrong one is
    worse than none.

    It is `normalize_latex` plus four stated equivalences, each one a class the
    corpus actually carries. What each class is worth, measured 2026-10-27 over
    the drill library's MathPix-route models (85,446 Formula objects in 55
    documents, cumulative, in this order):

        normalize_latex alone            29,184
        + \ldots == \dots                29,206   (+22)
        + a font wrapper is not content  29,207   (+1)
        + x^{\prime} == x'               30,453   (+1,246)
        + script order commutes          +36 of a 2,588-formula sample (1.4%)

    `\textsc`/`\textit` pay almost nothing corpus-wide and a great deal on a
    document with an algorithm block (14 of 1702.06385's 160 formulas), which
    is why the measure is quoted per class and not as one number.

    The whole key, over the whole population, is in `docs/HANDOVER.md`:
    38,681 of 69,667 Formula objects in 391 documents, median 61.1% per
    document.

    NOT a similarity threshold. The display-equation loop attaches at 0.55,
    which is right for an equation; an inline formula is three characters long,
    and at that length `\mid`/`\min` score 0.75 and `X_{2}`/`Y_2` score 0.67.
    """
    t = s or ""
    # BEFORE `normalize_latex`, not after: its own brace collapse turns
    # `\textit{type}(a)` into `\textittype(a)`, where no wrapper is left to
    # unwrap. The two passes are not commutative and the wrong order is silent.
    for _ in range(4):                       # a font wrapper inside another
        n = _FONT_WRAP.sub(r"\1", t)
        if n == t:
            break
        t = n
    t = _PRIME.sub("'", t)
    t = normalize_latex(t)
    if not t:
        return ""
    t = t.replace("\\ldots", "\\dots")
    return _SCRIPT_RUN.sub(
        lambda m: "".join(sorted(_SCRIPT_PART.findall(m.group(1)))), t)


def latex_similarity(a: str, b: str) -> float:
    r"""Similarity of two LaTeX strings, normalized first. Symmetric.

    522 — `autojunk=False` IS THE WHOLE POINT OF THIS LINE. difflib's
    autojunk heuristic marks any element occurring in more than 1% of the
    SECOND sequence as "popular" and refuses to match on it, but only once
    that sequence reaches 200 elements. Normalized LaTeX is a small alphabet,
    so every one of `\ _ = , - + 1 2 3 a b c` crosses 1% immediately and the
    ratio collapses.

    Two consequences, both live before this was fixed:

    - the function was NOT SYMMETRIC. On 0902.0431 one pair scored 0.857 in
      the order injectlatex calls it and 0.005 with the arguments swapped,
      for identical inputs — 0.857 is the true value and 0.005 is the
      artefact.
    - it was scored with autojunk ACTIVE for 91 of 1,112 injected candidates
      (8.2%), every one of them a long multi-line equation, which is exactly
      the population where a reading is hardest and the score matters most.

    A depressed score cannot misjoin — the argmax survived on all 45 affected
    candidates in 0902.0431 — but it can fall under `injectlatex`'s 0.55
    attach threshold, which silently drops a correct match.
    """
    na, nb = normalize_latex(a), normalize_latex(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio()


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
