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

      - math fonts in the font layer (CMEX/CMMI/CMSY/MSAM/MSBM/MTExtra/…; the
        ubiquitous Adobe "Symbol" font is NOT counted — too many false positives);
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


# --------------------------------------------------------------------------- #
#  P7 — text tails inside math regions (2026-08-18).
#  MathPix often keeps the sentence fragment AROUND a display equation inside
#  the math region: "\mathrm{n a c h\;A d d i t i o n}\; <math> \mathrm{w a s
#  ~i m~V e r-}". The prose is not math; `tailsplit` moves it to a sibling
#  <id>.tail object. Pure detector here; census + split in commands.
# --------------------------------------------------------------------------- #
_TEXT_GROUP = re.compile(r"\s*(?:\\[;,:!]|~|\\quad|\\qquad)*\s*"
                         r"\\(?:mathrm|text|textrm|mbox)\s*(?=\{)")
_NOT_PROSE = {"const", "konst", "d", "e", "i", "mod", "min", "max", "det",
              "tr", "sp", "im", "re", "grad", "div", "rot"}


def _collapse_letters(txt: str) -> str:
    r"""MathPix spaces every letter ('n a c h' -> 'nach'); \; and ~ are word
    gaps. Collapse to readable words."""
    txt = re.sub(r"\\[;,:!]|~", "  ", txt)
    parts = []
    for chunk in re.split(r"\s{2,}", txt.strip()):
        toks = chunk.split()
        if toks and all(len(t) == 1 for t in toks):
            parts.append("".join(toks))
        else:
            parts.append(re.sub(r"(?<=\b\w) (?=\w\b)", "", chunk))
    return " ".join(p for p in parts if p)


def _is_prose(txt: str) -> bool:
    words = re.findall(r"[A-Za-zäöüÄÖÜß-]{2,}", _collapse_letters(txt))
    words = [w for w in words if w.lower().strip("-") not in _NOT_PROSE]
    if not words:
        return False
    return len(words) >= 2 or len(words[0]) >= 4


def _take_text_groups(s: str):
    """Consume leading \\mathrm/\\text{...} groups; -> (joined content, rest)."""
    content, i = [], 0
    while True:
        m = _TEXT_GROUP.match(s, i)
        if not m:
            break
        j = m.end()
        depth, k = 0, j
        while k < len(s):
            if s[k] == "{":
                depth += 1
            elif s[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth != 0:
            break
        content.append(s[j + 1:k])
        i = k + 1
    return " ".join(content), s[i:].lstrip()


def text_tail(latex: str):
    """(lead, trail) prose fragments of a math latex, or (None, None).

    lead/trail are the RAW latex substrings (so the caller can strip them
    exactly); prose-ness is judged on the collapsed text."""
    s = (latex or "").strip()
    lead = trail = None
    # 095: a leading \text{} run may be commentary ("nach Addition, S=...")
    # or the SUBJECT of the line ("\text{Pack}_{<\omega}-complete"). The
    # difference is what is LEFT: an expression, or a dangling modifier.
    # A remainder that opens with _ or ^ has lost the thing it modifies, so
    # the run was the subject and must stay (out/093: 0911.3722_EQ0019 lost
    # two thirds of its words this way). A blanket "trailing runs only"
    # rule was tried first and regressed the case the feature was built for.
    content, rest = _take_text_groups(s)
    if content and _is_prose(content) and not _DANGLES.match(rest):
        lead = s[:len(s) - len(rest)].rstrip()

    m = re.search(r"((?:\\(?:mathrm|text|textrm|mbox)\s*\{[^{}]*\}"
                  r"|[\s.,;:]|\\[;,:!]|~|\\quad|\\qquad)+)$", s)
    if m and len(m.group(1).strip()) > 3:
        groups = re.findall(r"\\(?:mathrm|text|textrm|mbox)\s*\{([^{}]*)\}",
                            m.group(1))
        if groups and _is_prose(" ".join(groups)):
            # 095: strip only where MATHEMATICS PRECEDES the prose, and the
            # test is where the line BEGINS. A line that opens with a
            # \text{} run is a sentence: its trailing run is part of the
            # sentence, not a comment on an expression.
            #   x^{2}=y \text{ where n is even }   -> splits, maths first
            #   \text{Pack}_{<\omega}\text{-complete} -> does not (out/093)
            # Judged on the OPENING token rather than on what survives after
            # the \text{} groups are removed: a subscript alone leaves
            # fragments like "2" or "<" that read as mathematics and are not.
            # the opening test applies to what is left once a leading run
            # has been taken: "nach Addition, S=... was im Ver-" opens with
            # prose but its TAIL still follows mathematics.
            if not _OPENS_PROSE.match(rest if lead else s):
                trail = m.group(1).strip()
    return lead, trail


# --------------------------------------------------------------------------- #
#  020/021/022 — a backslash severed from its command name (2026-08-20).
#  '\<whitespace>mathrm{e}' is a backslash that lost its command name: LaTeX
#  reads the gap as a control space and typesets the literal letters
#  "mathrme". A run of EVEN length (\\, \\\\) is a real row break and is
#  never touched. ONE detector, shared by the normaliser and the validator.
# --------------------------------------------------------------------------- #
#: 095 — a remainder opening with a subscript or superscript has lost
#: what it modified: the run that preceded it was the subject.
_DANGLES = re.compile(r"\s*[_^]")


#: 095 — the line OPENS with a prose run, so it is a sentence, not an
#: expression carrying a comment.
_OPENS_PROSE = re.compile(r"\s*\\(?:mathrm|text|textrm|mbox)\s*\{")


_SEVERED_RUN = re.compile(r"(\\+)(\s+)([A-Za-z])")


def severed_backslashes(value: str, newline_only: bool = False) -> int:
    """How many LONE backslashes in `value` are severed from their command."""
    n = 0
    for m in _SEVERED_RUN.finditer(value or ""):
        if len(m.group(1)) % 2 == 0:          # \\ : a legitimate row break
            continue
        if newline_only and not ("\n" in m.group(2) or "\r" in m.group(2)):
            continue
        n += 1
    return n


def join_severed_backslashes(value: str) -> "tuple[str, int]":
    """(normalised, n_joined) — join each lone backslash to the command name
    it was severed from. ONLY the severing whitespace is removed; every other
    space, newline and control space in the value is left exactly as it was."""
    n = 0

    def _fix(m):
        nonlocal n
        if len(m.group(1)) % 2 == 0:
            return m.group(0)                 # row break: untouched
        n += 1
        return m.group(1) + m.group(3)        # drop the severing gap only

    return _SEVERED_RUN.sub(_fix, value or ""), n


# --------------------------------------------------------------------------- #
#  025 — trailing sentence punctuation is NOT mathematics (2026-08-20).
#  The TiddlyWiki arrangement is the model: the character lives in the text
#  field and the <$latex> widget holds only mathematics. `trailing_punct` is
#  that separation made portable — the mark leaves `latex`, the projections
#  re-emit it OUTSIDE the math, and the comparison sees neither side's copy.
# --------------------------------------------------------------------------- #
_TRAIL_PUNCT = re.compile(r"([,;.:])\s*$")
_ONESIDED = re.compile(r"\\(?:right|left)\s*\.\s*$")


def _brace_depth_at(v: str, idx: int) -> int:
    d = i = 0
    while i < idx:
        c = v[i]
        if c == "\\" and i + 1 < len(v):
            i += 2
            continue
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
        i += 1
    return d


def split_trailing_punct(latex: str) -> "tuple[str, str]":
    """(mathematics, mark) — lift a TOP-LEVEL trailing sentence mark out of a
    math value. ('x = y,' -> ('x = y', ','))

    Deliberately stricter than the 024 census, which allowed closing braces
    after the mark and so reached INSIDE groups: all 50 of those hits were
    `\\text{... .}` prose tails or notation like `^{*,}`, and neither is
    trailing punctuation. Here the mark must be literally last at brace depth
    0, and `\\right.` / `\\left.` are left alone — that dot is an invisible
    delimiter, not a full stop.
    """
    v = (latex or "").rstrip()
    if not v or _ONESIDED.search(v):
        return latex or "", ""
    m = _TRAIL_PUNCT.search(v)
    if not m or _brace_depth_at(v, m.start(1)) != 0:
        return latex or "", ""
    return v[:m.start(1)].rstrip(), m.group(1)


def strip_trailing_punct_for_compare(latex: str) -> str:
    """The comparison's view: mathematics with any trailing mark removed, so
    a value that has been separated and one that has not still compare equal.
    The compare sees NEITHER side's copy — not the LaTeX side's, not the ink
    side's — so a half-migrated corpus never reads as a finding storm."""
    return split_trailing_punct(latex)[0]
