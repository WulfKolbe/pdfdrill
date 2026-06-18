"""
Formula QC — detect FLATTENED formulas.

When a keyless model is built by visually transcribing a rendered page (the
tesseract chain, or an LLM that hand-rolls a pseudo-`lines.json` instead of
emitting LaTeX), a 2-D equation gets *linearised*: subscripts/superscripts drop
onto neighbouring lines and the equation number is mashed into the body, e.g.

    M = m a (F + j ) (B65)      ->  should be  M = m_a (F + j_0) \\tag{B65}
    n + 0                            (the "n", "0" are detached subscripts)

The result is 65 "formula" tiddlers that are not valid LaTeX and won't render in
KaTeX or transclude meaningfully. `is_flattened` is a conservative heuristic that
flags such strings so `pdfdrill mathcheck` can report them and steer the user
back to `pdfdrill remath` (the LaTeX-demanding reconstruction). Pure / stdlib.
"""
from __future__ import annotations

import re
from typing import Iterable

# An equation number "(B65)" / "(12)" embedded in the body of the LaTeX. A clean
# equation carries its number as \tag{...} (or as a separate equation_number
# line), never inline — so an inline one is a flattening tell.
_EMBEDDED_EQNUM = re.compile(r"\(\s*[A-Za-z]{0,2}\d{1,4}\s*\)")

# A standalone single letter (a detached sub/superscript), not part of a word or
# a LaTeX command.
_SINGLE_LETTER = re.compile(r"(?<![\w\\])[A-Za-z](?![\w])")

# The math-fidelity types whose `latex` we audit.
FORMULA_TYPES = {"Equation", "Formula", "MathExpression", "DisplayEquation"}


def is_flattened(latex: str) -> bool:
    """True if `latex` looks like a linearised transcription rather than LaTeX.

    Conservative — real LaTeX is NEVER flagged. The decisive tell of a flattened
    transcription is that it carries no LaTeX markup at all: a string with any of
    ``\\ { } _ ^`` is structured math (even ``\\mathbf{x}^{(1)}`` or ``p(\\mid)``),
    so we trust it. Only a markup-free string is examined for the failure cues.
    """
    s = (latex or "").strip()
    if not s:
        return False
    # Any LaTeX control markup => structured math, not a flattened transcription.
    if any(ch in s for ch in ("\\", "{", "}", "_", "^")):
        return False
    # Markup-free from here. A "formula" spanning several visual lines, or an
    # equation number mashed inline (no \tag is possible without a backslash), or
    # many detached single letters in a long run — all signal a collapsed layout.
    if "\n" in s:
        return True
    if _EMBEDDED_EQNUM.search(s):
        return True
    if len(_SINGLE_LETTER.findall(s)) >= 4 and len(s.split()) >= 6:
        return True
    return False


def is_math_bearing(pdf, sc) -> "tuple[bool, str]":
    """Best-effort, cheap, offline test that a document carries mathematics —
    so a keyless (tesseract) build that produced 0 equations is a FAILURE, not a
    result. Returns (True, reason) when ANY signal fires, reusing existing layers
    with no new heavy deps:

      - math fonts in the font layer (CMEX/CMMI/CMSY/MSAM/MSBM/Symbol/…);
      - an `equation.*` named destination (pdfinfo -dests);
      - display math ($$ / \\[) recorded by a prior `md` layer (cached only);
      - right-margin equation-number tokens from a prior `geometry` pass (cached).

    The first two run their (cheap, offline) tool directly; the last two are read
    from the sidecar only (never triggered here — they may need MathPix). On a
    pure scan with no font layer the first two can't fire; run `geometry`/`md`
    first for that case.
    """
    # 1) math fonts (pdffonts — fast, offline). Cached layer preferred.
    try:
        from .font_image_layers import fetch_fonts, summarize_fonts
        fonts = getattr(sc, "fonts_layer", None) or fetch_fonts(pdf)
        if fonts:
            s = summarize_fonts(fonts)
            if s.get("n_math", 0) > 0:
                names = ", ".join(sorted({
                    (f.get("base") or f.get("name") or "").split("+")[-1]
                    for f in fonts if f.get("is_math")})[:3]) or "math"
                return True, f"math fonts: {names}"
    except Exception:
        pass
    # 2) equation.* named destinations (pdfinfo -dests — cheap, offline).
    try:
        dests = getattr(sc, "dests", None)
        if dests is None:
            from .pdfinfo_layers import fetch_dests
            dests = fetch_dests(pdf)
        if any((d.get("kind") == "equation") for d in (dests or [])):
            return True, "equation.* named destinations"
    except Exception:
        pass
    # 3) display math detected by a prior md layer (sidecar cache only).
    try:
        md_math = sc.get_evidence("md_display_math")
        if md_math:
            return True, "display math in md layer"
    except Exception:
        pass
    # 4) right-margin equation-number tokens from a prior geometry pass (cache).
    try:
        if sc.get_evidence("geometry_equation_numbers"):
            return True, "right-margin equation numbers (geometry)"
    except Exception:
        pass
    return False, ""


def _latex_of(node) -> str:
    """Best LaTeX string for a doc node/graph node (props['latex'] or 'latex_code')."""
    props = getattr(node, "props", None) or {}
    for key in ("latex", "latex_code"):
        v = props.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def audit_formulas(nodes: Iterable, *, max_samples: int = 12) -> dict:
    """Audit formula nodes → {total, flattened, samples:[{id,type,latex}], ratio}."""
    total = 0
    flagged = []
    for n in nodes:
        if getattr(n, "type", None) not in FORMULA_TYPES:
            continue
        latex = _latex_of(n)
        if not latex.strip():
            continue
        total += 1
        if is_flattened(latex):
            flagged.append(n)
    samples = [
        {"id": getattr(n, "id", "?"), "type": getattr(n, "type", "?"),
         "latex": _latex_of(n)}
        for n in flagged[:max_samples]
    ]
    return {
        "total": total,
        "flattened": len(flagged),
        "ratio": (len(flagged) / total) if total else 0.0,
        "samples": samples,
    }
