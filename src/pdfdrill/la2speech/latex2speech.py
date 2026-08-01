"""
latex2speech -- LaTeX in, TTS-ready plain text out.

This is the "TeX2Speech minus the speech synth" pipeline. Nothing here talks to
an audio device; the output is a str you hand to whatever TTS you like.

ENTRY POINT / PROVENANCE
------------------------
The keywords Nemeth / ClearSpeak / SimpleSpeak all lead to the math-accessibility
world, and specifically to two rule engines:

  * Speech Rule Engine (SRE, npm `speech-rule-engine`, the engine inside MathJax)
      locales: en, de, fr, es, it, nb, nn, sv, ...  plus `nemeth` and `euro`
               as *braille* locales
      domains (speech rule sets): clearspeak, mathspeak, chromevox, emacspeak, default
      styles:  clearspeak -> ~30 named preferences (Fraction_Over, Roots_RootEnd, ...)
               mathspeak  -> default | brief | sbrief
    -> implemented here as SRESpeechBackend (tested, see TESTS below)

  * MathCAT (Rust; daisy/MathCAT, Python binding daisy/MathCATForPython)
      SpeechStyle: ClearSpeak | SimpleSpeak | LiteralSpeak
      BrailleCode: Nemeth | UEB | CMU | Vietnam | ...
    -> implemented here as MathCATSpeechBackend (NOT TESTED -- MathCAT is not on
       PyPI and needs a Rust build; see the class docstring)

"SimpleSpeak" exists only in MathCAT. SRE has no SimpleSpeak; MathSpeak `brief`
is the nearest terse analogue, and is what SIMPLESPEAK_FALLBACK maps to.

PIPELINE
--------
    LaTeX source
      -> segment()            split into text runs and math runs
      -> text runs            pylatexenc LatexNodes2Text  -> prose
      -> math runs            latex2mathml -> MathML -> backend -> spoken math
      -> interleave           -> single speakable string

INTERFACE CONTRACT
------------------
    SpeechBackend (protocol)
        speak(mathml: str, display: bool = False) -> str
            Pure function of its input. Raises SpeechError on engine failure.
            MUST NOT raise for merely unusual (but well-formed) MathML.
        close() -> None
            Idempotent. Safe to call on a never-started backend.

    latex_to_mathml(tex: str, display: bool = False) -> str
        Returns a `<math>` element as str. Raises MathMLError.
        NOTE: latex2mathml does not reject malformed LaTeX; garbage in,
        garbage out. Validate upstream if you care.

    segment(tex: str) -> list[Segment]
        Segment = (kind, text, display); kind in {"text", "math"}.
        Concatenating the raw slices reproduces the input body verbatim except
        for comments and (optionally) the preamble.

    LatexSpeaker(backend).speak(tex) -> str
    LatexSpeaker(backend).speak_math(tex, display=False) -> str

DEPENDENCIES
------------
    pip install latex2mathml pylatexenc
    npm install speech-rule-engine        (in the directory passed as node_dir)

TESTS -- see test_latex2speech.py. Run it. Do not trust this docstring.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Protocol, Sequence

from . import latexproject

__all__ = [
    "Segment",
    "SpeechError",
    "BackendUnavailable",
    "MathMLError",
    "SpeechBackend",
    "SRESpeechBackend",
    "MathCATSpeechBackend",
    "NullSpeechBackend",
    "LatexSpeaker",
    "segment",
    "latex_to_mathml",
    "clean_math",
    "split_text_math",
    "normalize_alphabet_runs",
    "repair_braces",
    "brace_imbalance",
    "find_unspoken_math",
    "repair_left_right",
    "strip_math_delimiters",
    "has_math_delimiters",
    "__version__",
    "_resolved_package_path",
]


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------

class SpeechError(RuntimeError):
    """Backend failed to turn MathML into speech."""


def _resolved_package_path(node_dir: str, pkg: str = "speech-rule-engine") -> str:
    """Absolute path node actually resolves `pkg` to, or "" if it cannot.

    Worth reporting explicitly: node's resolver walks *up* from the working
    directory through every ancestor's node_modules, so a package can be found
    in a parent (or a global prefix on NODE_PATH) while `find .` inside the
    project shows nothing at all.
    """
    try:
        r = subprocess.run(
            ["node", "-e", "process.stdout.write(require.resolve("
                           f"'{pkg}/package.json'))"],
            cwd=node_dir, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def _node_error_line(stderr: str) -> str:
    """The one useful line from a node traceback.

    Node prints four lines of loader boilerplate before the actual error, so
    the naive `splitlines()[0]` reports `node:internal/modules/cjs/loader:1386`
    and tells you nothing.
    """
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
    for l in lines:
        if "Cannot find module" in l or re.match(r"\w*Error:", l):
            return l[:200]
    return (lines[0] if lines else "(no output)")[:200]


class BackendUnavailable(SpeechError):
    """The speech engine could not be reached at all.

    Distinct from SpeechError because the remedies differ completely: a
    SpeechError means *this expression* did not convert, a BackendUnavailable
    means *nothing* will convert and every fragment in the document is about to
    become a placeholder. It is never swallowed into `[unspoken math]`.
    """


class MathMLError(RuntimeError):
    """LaTeX could not be turned into MathML."""


# --------------------------------------------------------------------------
# segmentation
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Segment:
    kind: str          # "text" | "math" | "verbatim"
    text: str          # raw slice; delimiters stripped for math and verbatim
    display: bool = False


#: environments whose bodies are math.
#: The second group are strictly *inner* environments (LaTeX requires them to sit
#: inside math mode). Real documents -- and anything OCR'd or pasted out of a
#: converter -- routinely use them at top level, and silently rendering them as
#: prose is worse than treating them as math, so they are listed here too.
MATH_ENVIRONMENTS = frozenset({
    "math", "displaymath", "equation", "eqnarray", "align", "alignat",
    "gather", "multline", "flalign", "split", "dmath", "dgroup",
    # inner / amsmath
    "aligned", "alignedat", "gathered", "cases", "dcases", "rcases",
    "array", "subarray", "matrix", "pmatrix", "bmatrix", "Bmatrix",
    "vmatrix", "Vmatrix", "smallmatrix",
})

#: environments whose bodies must be passed through untouched (never math)
VERBATIM_ENVIRONMENTS = frozenset({
    "verbatim", "Verbatim", "lstlisting", "minted", "alltt", "comment",
})

_DISPLAY_ENVS = MATH_ENVIRONMENTS - {"math"}

_ENV_BEGIN = re.compile(r"\\begin\{([A-Za-z@*]+)\}")
_VERB_INLINE = re.compile(r"\\verb\*?(.)")


#: macros that essentially never appear outside math mode. If one shows up in a
#: text run, segmentation missed a math block and the prose renderer is about to
#: turn it into pseudo-ASCII garbage instead of speech -- the silent failure mode
#: this guard exists to catch.
_MATH_ONLY = re.compile(
    r"\\(?:frac|dfrac|tfrac|sum|prod|int|oint|sqrt|lim|infty|partial|nabla"
    r"|alpha|beta|gamma|delta|lambda|sigma|theta|mu|nu|xi|pi|rho|tau|phi|chi|psi|omega"
    r"|leq|geq|neq|approx|equiv|sim|propto|subset|supset|in|notin|forall|exists"
    r"|cdot|times|pm|mp|left|right|begin\{(?:aligned|array|matrix|[pbBvV]matrix|cases)\}"
    r"|mathbb|mathcal|mathfrak|mathbf|hat|vec|bar|tilde|dot|ddot|eth)"
    r"(?![A-Za-z])")   # NOT \b -- `_` is a word char, so \b would reject \sum_{i}


def find_unspoken_math(segs: Iterable[Segment]) -> List[str]:
    """Text segments that still look like math. Non-empty means a missed block.

    Use it as a lint pass over any new corpus before trusting the output:

        bad = find_unspoken_math(segment(open("paper.tex").read()))
    """
    out = []
    for seg in segs:
        if seg.kind != "text":
            continue
        hits = sorted(set(_MATH_ONLY.findall(seg.text) or []))
        m = _MATH_ONLY.search(seg.text)
        if m:
            ctx = " ".join(seg.text[max(0, m.start() - 30):m.start() + 70].split())
            out.append(f"math-looking text run near {m.group(0)!r}: ...{ctx}...")
    return out


def _find_env_end(tex: str, env: str, start: int) -> int:
    """Index of the `\\end{env}` matching a `\\begin{env}` that ended at `start`.

    Depth-counting, so `\\begin{array}...\\begin{array}...\\end{array}...\\end{array}`
    does not terminate at the inner `\\end`. Returns -1 if unbalanced.
    """
    begin_tok = "\\begin{%s}" % env
    end_tok = "\\end{%s}" % env
    depth, i = 1, start
    while i < len(tex):
        nb = tex.find(begin_tok, i)
        ne = tex.find(end_tok, i)
        if ne < 0:
            return -1
        if 0 <= nb < ne:
            depth += 1
            i = nb + len(begin_tok)
            continue
        depth -= 1
        if depth == 0:
            return ne
        i = ne + len(end_tok)
    return -1


def _strip_comments(tex: str) -> str:
    """Remove TeX comments, honouring \\% and preserving line structure."""
    out = []
    for line in tex.split("\n"):
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "%":
                line = line[:i]
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def _body_only(tex: str) -> str:
    """If this looks like a full document, return only what is between
    \\begin{document} and \\end{document}."""
    b = tex.find(r"\begin{document}")
    if b < 0:
        return tex
    b += len(r"\begin{document}")
    e = tex.find(r"\end{document}", b)
    return tex[b:e] if e >= 0 else tex[b:]


def segment(tex: str, strip_preamble: bool = True) -> List[Segment]:
    """Split LaTeX into alternating text/math segments.

    Recognised math delimiters:
        $...$   $$...$$   \\(...\\)   \\[...\\]   \\begin{eq*}...\\end{eq*}
    Verbatim-ish environments are emitted as a single text segment and are
    never scanned for math delimiters.
    """
    if strip_preamble:
        tex = _body_only(tex)
    tex = _strip_comments(tex)

    segs: List[Segment] = []
    buf: List[str] = []
    i, n = 0, len(tex)

    def flush_text():
        if buf:
            s = "".join(buf)
            if s:
                segs.append(Segment("text", s))
            buf.clear()

    while i < n:
        c = tex[i]

        # escaped char / delimiter
        if c == "\\" and i + 1 < n:
            nxt = tex[i + 1]
            if nxt == "[":
                j = tex.find(r"\]", i + 2)
                if j >= 0:
                    flush_text()
                    segs.append(Segment("math", tex[i + 2:j], True))
                    i = j + 2
                    continue
            if nxt == "(":
                j = tex.find(r"\)", i + 2)
                if j >= 0:
                    flush_text()
                    segs.append(Segment("math", tex[i + 2:j], False))
                    i = j + 2
                    continue
            mv = _VERB_INLINE.match(tex, i)
            if mv:
                delim = mv.group(1)
                j = tex.find(delim, mv.end())
                if j >= 0:
                    flush_text()
                    segs.append(Segment("verbatim", tex[mv.end():j], False))
                    i = j + 1
                    continue
            m = _ENV_BEGIN.match(tex, i)
            if m:
                env = m.group(1)
                base = env.rstrip("*")
                end_tok = "\\end{%s}" % env
                j = _find_env_end(tex, env, m.end())
                if j >= 0:
                    if base in VERBATIM_ENVIRONMENTS:
                        flush_text()
                        segs.append(Segment("verbatim", tex[m.end():j], False))
                        i = j + len(end_tok)
                        continue
                    if base in MATH_ENVIRONMENTS:
                        flush_text()
                        segs.append(Segment(
                            "math",
                            r"\begin{%s}%s\end{%s}" % (env, tex[m.end():j], env),
                            base in _DISPLAY_ENVS,
                        ))
                        i = j + len(end_tok)
                        continue
            buf.append(tex[i:i + 2])
            i += 2
            continue

        if c == "$":
            if tex.startswith("$$", i):
                j = tex.find("$$", i + 2)
                if j >= 0:
                    flush_text()
                    segs.append(Segment("math", tex[i + 2:j], True))
                    i = j + 2
                    continue
            else:
                j = _find_unescaped_dollar(tex, i + 1)
                if j >= 0:
                    flush_text()
                    segs.append(Segment("math", tex[i + 1:j], False))
                    i = j + 1
                    continue

        buf.append(c)
        i += 1

    flush_text()
    return segs


def _find_unescaped_dollar(s: str, start: int) -> int:
    i, n = start, len(s)
    while i < n:
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "$":
            return i
        i += 1
    return -1


# --------------------------------------------------------------------------
# LaTeX -> MathML
# --------------------------------------------------------------------------

#: commands that carry no spoken content and confuse the MathML converter.
#: NOTE: \left. and \right. must NOT be listed here. They are null delimiters,
#: not noise -- deleting one half of a \left...\right pair strands the other and
#: the whole expression fails to convert. latex2mathml handles them natively.
_DROP_ARGLESS = re.compile(
    r"\\(?:nonumber|notag|displaystyle|textstyle|scriptstyle|limits|nolimits"
    r"|!)")
_DROP_WITH_ARG = re.compile(r"\\(?:label|tag|ref|eqref|nonumber)\s*\{[^{}]*\}")
_NUMBERED_ENV = re.compile(r"\\(begin|end)\{(align|gather|multline|flalign|eqnarray|equation)\}")


_LEFT_RIGHT = re.compile(r"\\(left|right)\b")


def repair_left_right(tex: str) -> tuple:
    """Append `\\right.` for each unmatched `\\left`. Returns (repaired, n_added).

    OCR and PDF-extraction routinely drop one half of a `\\left ... \\right`
    pair; latex2mathml then rejects the whole expression with
    ExtraLeftOrMissingRightError and the formula is lost entirely.
    Surplus `\\right` is reported but not repaired -- prepending a `\\left.`
    would guess at where the group starts, and guessing wrong changes meaning.
    """
    toks = _LEFT_RIGHT.findall(tex)
    depth = 0
    for t in toks:
        depth += 1 if t == "left" else -1
    if depth > 0:
        return tex + "\\right." * depth, depth
    return tex, 0


def brace_imbalance(tex: str) -> int:
    """Unclosed-brace count (negative means surplus closers). Honours \\{ and \\}."""
    depth, i, n = 0, 0, len(tex)
    while i < n:
        c = tex[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return depth


def repair_braces(tex: str) -> tuple:
    """Append/trim braces so the fragment balances. Returns (repaired, n_added).

    Truncated sources -- OCR output, copy-paste from a PDF, a `\\text{...` whose
    closer was lost -- otherwise abort the whole conversion. `n_added` is
    non-zero whenever a repair happened, so callers can report it.

    When the fragment is wrapped in `\\begin{env}...\\end{env}`, the closers are
    inserted *before* the `\\end`, not after it. Appending at the very end would
    leave the `\\end{env}` itself inside the unclosed group -- which is exactly
    what happens when a `\\text{` runs off the end of a truncated environment.
    """
    m = _ENV_WRAPPER.match(tex)
    if m:
        head, body, tail = m.group(1), m.group(3), m.group(4)
        d = brace_imbalance(body)
        if d > 0:
            return head + body + "}" * d + tail, d
        return tex, 0
    d = brace_imbalance(tex)
    if d > 0:
        return tex + "}" * d, d
    return tex, 0


_ENV_WRAPPER = re.compile(r"(\\begin\{([A-Za-z@*]+)\})(.*)(\\end\{\2\})", re.S)


#: `aligned`/`gathered` are laid out by latex2mathml without treating `&` as a
#: cell separator, so the ampersands get spoken literally. Their outer
#: equivalents are handled correctly, and are semantically the same for speech.
_INNER_ALIGN = re.compile(r"\\(begin|end)\{(aligned|gathered|alignedat)\}")
_INNER_ALIGN_MAP = {"aligned": "align*", "gathered": "gather*",
                    "alignedat": "alignat*"}

#: a row-initial `&` produces an empty first cell, spoken as "blank" on every
#: single line. It carries no information for a listener.
_LEADING_AMP = re.compile(r"(\\begin\{[A-Za-z@*]+\}(?:\{[^{}]*\})?|\\\\)\s*&")


#: \ensuremath{X} is a mode-switching wrapper with no spoken content, but
#: latex2mathml does not know it and emits <mi>\ensuremath</mi>, which the
#: speech engine reads out literally. Unwrap it, keeping the argument.
_ENSUREMATH = re.compile(r"\\ensuremath\s*\{")


def _unwrap_ensuremath(tex: str) -> str:
    out, i = [], 0
    while True:
        m = _ENSUREMATH.search(tex, i)
        if not m:
            out.append(tex[i:])
            return "".join(out)
        out.append(tex[i:m.start()])
        depth, j = 1, m.end()
        while j < len(tex) and depth:
            if tex[j] == "\\":
                j += 2
                continue
            if tex[j] == "{":
                depth += 1
            elif tex[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(tex[m.end():j])
        i = j + 1


__version__ = "0.5.2"

#: outer math shifts that must come off before a fragment reaches the MathML
#: converter. They arrive whenever a fragment is fed with `--raw`, or when a
#: formula-array line already carries its own `$$...$$` -- the converter has no
#: idea what a math shift is and reads it out as the word "Dollar".
_MATH_DELIMS = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$"))


def strip_math_delimiters(tex: str) -> tuple:
    """Remove outer `$$..$$`, `$..$`, `\\[..\\]`, `\\(..\\)`. Returns (body, display).

    `display` is True when the outermost delimiter was a display one, so the
    caller can keep the display/inline distinction the author intended.
    Nested shifts are peeled repeatedly; unmatched delimiters are left alone.
    """
    display = False
    changed = True
    while changed:
        changed = False
        s = tex.strip()
        for open_d, close_d in _MATH_DELIMS:
            if (len(s) > len(open_d) + len(close_d)
                    and s.startswith(open_d) and s.endswith(close_d)):
                inner = s[len(open_d):-len(close_d)]
                # `$a$ + $b$` must not be mistaken for one `$...$` group
                if open_d == "$" and "$" in inner:
                    continue
                if open_d == "$$" and "$$" in inner:
                    continue
                tex = inner
                display = display or open_d in ("$$", "\\[")
                changed = True
                break
    return tex, display


def has_math_delimiters(tex: str) -> bool:
    """True when the fragment already carries its own math shift."""
    return strip_math_delimiters(tex)[0].strip() != tex.strip()


#: Commands whose argument is prose. A `$` inside one of them RE-ENTERS math in
#: real LaTeX, but latex2mathml emits it literally, so `\text{at $\Lambda$ rest}`
#: was spoken as "at dollar backslash Lambda dollar rest". Real sources reach
#: this constantly: `\mbox{...$X$...}` is the idiomatic way to put a symbol in a
#: annotation, and pdfdrill now maps `\mbox` to `\text`.
_TEXT_ARG_CMD = re.compile(
    r"\\(text|textrm|textnormal|textit|textbf|mbox|hbox)\s*\{")


def _read_balanced(tex: str, open_idx: int) -> tuple:
    """(body, index_after_close) for the group whose `{` sits at open_idx."""
    if open_idx >= len(tex) or tex[open_idx] != "{":
        return None, open_idx
    depth, j = 1, open_idx + 1
    while j < len(tex):
        if tex[j] == "\\":
            j += 2
            continue
        if tex[j] == "{":
            depth += 1
        elif tex[j] == "}":
            depth -= 1
            if depth == 0:
                return tex[open_idx + 1:j], j + 1
        j += 1
    return None, open_idx


def _split_unescaped_dollar(body: str) -> Optional[List[str]]:
    """Alternating [text, math, text, ...] split on `$` at brace depth 0.

    Returns None when the dollars are unbalanced or nested-brace scoped, so a
    fragment we cannot read confidently is left exactly as it was.
    """
    parts, buf, depth, i = [], [], 0, 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            buf.append(body[i:i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "$" and depth == 0:
            if body.startswith("$$", i):     # display inside prose: not ours
                return None
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts if len(parts) % 2 == 1 else None


def split_text_math(tex: str) -> str:
    """`\\text{a $x$ b}` -> `\\text{a }x\\text{ b}`.

    The `$` is a mode switch, not a character: dropping it would put `\\Lambda`
    inside prose where it renders as literal backslash-L-a-m-b-d-a, and keeping
    it makes the converter speak the delimiter. Splitting the run is the only
    reading that preserves what the author wrote.
    """
    out, i = [], 0
    while True:
        m = _TEXT_ARG_CMD.search(tex, i)
        if not m:
            out.append(tex[i:])
            return "".join(out)
        body, after = _read_balanced(tex, m.end() - 1)
        if body is None:
            out.append(tex[i:m.end()])
            i = m.end()
            continue
        out.append(tex[i:m.start()])
        parts = _split_unescaped_dollar(body) if "$" in body else None
        if parts is None:
            out.append(tex[m.start():after])
        else:
            cmd = m.group(1)
            for k, seg in enumerate(parts):
                if k % 2 == 0:
                    if seg:
                        out.append(f"\\{cmd}{{{seg}}}")
                elif seg.strip():
                    out.append(seg)
        i = after


#: Alphabet commands whose variant is pure STYLING. latex2mathml emits one
#: `<mi>` per letter for every `\math*` command, so a multi-letter run is read
#: letter by letter -- and for `\mathrm` each upright letter is then matched
#: against SRE's SI unit tables (`m`->meter, `l`->liter, `t`->ton), which turns
#: `\mathrm{mult}` into "meters normal u liters tons". `\text{}` is the only
#: wrapper that yields a single `<mtext>`.
#:
#: `\mathbb`, `\mathcal`, `\mathfrak` and `\mathscr` are deliberately ABSENT:
#: there the variant carries the meaning, not the style. `\mathbb{R}` speaks as
#: "the real numbers" and `\mathfrak{g}` as "German g"; rewriting either to
#: `\text{}` would destroy exactly the information the author encoded.
_STYLE_ALPHABETS = ("mathrm", "mathbf", "mathit", "mathsf", "mathtt",
                    "mathnormal")

#: Two or more plain ASCII letters and nothing else -- a name, not a symbol.
#: A single letter is left alone: `\mathrm{m}` inside a quantity really is the
#: unit metre, and `\mathbf{v}` really is a vector.
_ALPHABET_RUN = re.compile(
    r"\\(" + "|".join(_STYLE_ALPHABETS) + r")\s*\{([A-Za-z]{2,})\}")


def normalize_alphabet_runs(tex: str) -> str:
    """`\\mathrm{mult}` -> `\\text{mult}`; single letters untouched."""
    return _ALPHABET_RUN.sub(lambda m: "\\text{" + m.group(2) + "}", tex)


def clean_math(tex: str, suppress_numbering: bool = True,
               normalize_inner_align: bool = True,
               drop_leading_amp: bool = True) -> str:
    """Remove non-spoken LaTeX cruft from a math fragment.

    `suppress_numbering` rewrites align -> align* etc., otherwise the converter
    injects equation numbers which the speech engine reads out as "open paren 1
    close paren".
    """
    tex, _ = strip_math_delimiters(tex)
    tex = _unwrap_ensuremath(tex)
    tex = split_text_math(tex)
    tex = normalize_alphabet_runs(tex)
    tex = _DROP_WITH_ARG.sub("", tex)
    tex = _DROP_ARGLESS.sub("", tex)
    if normalize_inner_align:
        tex = _INNER_ALIGN.sub(
            lambda m: "\\%s{%s}" % (m.group(1), _INNER_ALIGN_MAP[m.group(2)]), tex)
    if suppress_numbering:
        tex = _NUMBERED_ENV.sub(lambda m: "\\%s{%s*}" % (m.group(1), m.group(2)), tex)
    if drop_leading_amp:
        tex = _LEADING_AMP.sub(lambda m: m.group(1), tex)
    return tex.strip()


def latex_to_mathml(tex: str, display: bool = False,
                    suppress_numbering: bool = True,
                    repair: bool = True,
                    warnings: Optional[List[str]] = None) -> str:
    """Convert a LaTeX math fragment (no delimiters) to a MathML string.

    `repair=True` closes unbalanced braces rather than aborting; each repair is
    appended to `warnings` if a list is supplied.
    """
    import latex2mathml.converter as _conv  # local import: keeps import cost off cold paths

    src = clean_math(tex, suppress_numbering)
    if not src:
        raise MathMLError("empty math fragment")
    if repair:
        src, added = repair_braces(src)
        if added and warnings is not None:
            warnings.append(
                f"closed {added} unbalanced brace(s) in {tex[:60]!r}...")
        src, added_lr = repair_left_right(src)
        if added_lr and warnings is not None:
            warnings.append(
                f"closed {added_lr} unmatched \\left in {tex[:60]!r}...")
    try:
        mathml = _conv.convert(src, display="block" if display else "inline")
    except Exception as exc:  # latex2mathml raises assorted types
        raise MathMLError(f"{type(exc).__name__}: {exc} -- source: {src!r}") from exc
    if "<math" not in mathml:
        raise MathMLError(f"converter produced no <math> element for {src!r}")
    # \quad, \qquad, \hspace ... become <mspace/>, which SRE reads out as the
    # literal word "empty". Spacing is never spoken; drop it.
    mathml = _MSPACE.sub("", mathml)
    return mathml


_MSPACE = re.compile(r"<mspace\b[^>]*/>|<mspace\b[^>]*>\s*</mspace>")


# --------------------------------------------------------------------------
# speech backends
# --------------------------------------------------------------------------

class SpeechBackend(Protocol):
    def speak(self, mathml: str, display: bool = False) -> str: ...
    def close(self) -> None: ...


class NullSpeechBackend:
    """Diagnostic backend: returns a placeholder instead of speech.

    Useful for testing segmentation without a node install.
    """

    def speak(self, mathml: str, display: bool = False) -> str:
        return "[math]"

    def close(self) -> None:
        pass


class SRESpeechBackend:
    """Speech Rule Engine backend, driven as a long-lived node subprocess.

    One node process is started lazily and reused; startup is ~300 ms and
    rule-set loading a further ~100-400 ms, so per-call subprocess spawning is
    not viable for documents.

    Parameters
    ----------
    node_dir : directory containing node_modules/speech-rule-engine and
               sre_bridge.js
    domain   : "clearspeak" | "mathspeak" | "chromevox" | "emacspeak" | "default"
    style    : rule-set dependent. mathspeak: default|brief|sbrief.
               clearspeak: e.g. "Fraction_Over", "Roots_RootEnd", "default".
    locale   : "en", "de", "fr", ... ; or "nemeth"/"euro" together with
               modality="braille"
    modality : "speech" | "braille"
    """

    #: MathCAT's SimpleSpeak has no SRE equivalent; this is the nearest terse one.
    SIMPLESPEAK_FALLBACK = ("mathspeak", "brief")

    def __init__(self, node_dir: str, domain: str = "clearspeak",
                 style: str = "default", locale: str = "en",
                 modality: str = "speech", bridge: str = "sre_bridge.js",
                 timeout: float = 30.0):
        self.node_dir = os.path.abspath(node_dir)
        self.bridge = os.path.join(self.node_dir, bridge)
        self.domain, self.style = domain, style
        self.locale, self.modality = locale, modality
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._id = 0
        self._lock = threading.Lock()
        self._stderr_file = None
        self.resolved_from = ""

    # -- process management -------------------------------------------------

    def _ensure(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if not os.path.isfile(self.bridge):
            raise BackendUnavailable(
                f"sre_bridge.js not found at {self.bridge}. Run "
                "`--check` for a full diagnosis.")
        # xmldom chatters on stderr for malformed input, so it cannot go to our
        # own stderr -- but discarding it loses the one message that explains a
        # failed startup. Capture to a temp file and read it only on failure.
        import tempfile
        self._stderr_file = tempfile.NamedTemporaryFile(
            mode="w+", suffix=".sre-stderr", delete=False)
        self._proc = subprocess.Popen(
            ["node", self.bridge],
            cwd=self.node_dir,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            text=True, encoding="utf-8", bufsize=1,
        )
        self._id = 0
        return self._proc

    def bridge_stderr(self) -> str:
        """Whatever the node process wrote to stderr, for diagnostics."""
        if not self._stderr_file:
            return ""
        try:
            with open(self._stderr_file.name, encoding="utf-8",
                      errors="replace") as fh:
                return fh.read()
        except OSError:
            return ""

    def close(self) -> None:
        if self._stderr_file:
            try:
                self._stderr_file.close()
                os.unlink(self._stderr_file.name)
            except OSError:
                pass
            self._stderr_file = None
        self.resolved_from = ""
        p, self._proc = self._proc, None
        if p is None or p.poll() is not None:
            return
        try:
            p.stdin.write("QUIT\n")
            p.stdin.flush()
            p.wait(timeout=5)
        except Exception:
            p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def preflight(self) -> str:
        """Verify the engine is actually reachable. Returns a one-line report.

        Raises BackendUnavailable naming the specific missing piece. Without
        this, a misplaced `npm install` yields a document in which every single
        formula is `[unspoken math]` and the only clue is one line on stderr.
        """
        import shutil

        if shutil.which("node") is None:
            raise BackendUnavailable(
                "`node` is not on PATH. Speech Rule Engine runs under Node.js; "
                "install Node and retry.")
        if not os.path.isdir(self.node_dir):
            raise BackendUnavailable(
                f"--node-dir {self.node_dir} does not exist. It must be the "
                "directory holding sre_bridge.js and node_modules/"
                "speech-rule-engine.")
        if not os.path.isfile(self.bridge):
            raise BackendUnavailable(
                f"sre_bridge.js not found at {self.bridge}. Copy it there, or "
                "point --node-dir at the directory that has it.")
        probe = subprocess.run(
            ["node", "-e",
             "const v=require('speech-rule-engine/package.json').version;"
             "const s=require('speech-rule-engine');"
             "process.stdout.write(v+'|'+(typeof s.toSpeech))"],
            cwd=self.node_dir, capture_output=True, text=True)
        if probe.returncode != 0:
            detail = _node_error_line(probe.stderr)
            # package.json resolving proves nothing: a partial install (blocked
            # postinstall scripts, a pruned or interrupted npm run) leaves the
            # manifest in place while lib/ is missing, and the version still
            # reports correctly.
            manifest_only = subprocess.run(
                ["node", "-e", "process.stdout.write(require("
                               "'speech-rule-engine/package.json').version)"],
                cwd=self.node_dir, capture_output=True, text=True)
            if manifest_only.returncode == 0:
                where = _resolved_package_path(self.node_dir)
                raise BackendUnavailable(
                    f"speech-rule-engine {manifest_only.stdout.strip()} is "
                    "present but its main entry will not load -- the install is "
                    "incomplete or was interrupted.\n"
                    f"  resolved from: {where or '(unknown)'}\n"
                    "  NOTE: node's resolver walks UP from the working "
                    "directory, so this may be an ancestor directory or a "
                    "global prefix, not your project.\n"
                    f"  Fix: cd {self.node_dir} && npm install --prefix . "
                    "speech-rule-engine\n"
                    "       (--prefix . is required: npm also walks up, so a "
                    "package.json in a\n"
                    "        parent directory makes a plain `npm install` "
                    "target the parent instead)\n"
                    f"  node said: {detail}")
            raise BackendUnavailable(
                "speech-rule-engine is not resolvable from "
                f"{self.node_dir}. A global `npm install -g` is not enough -- "
                "node resolves from the working directory. Run:\n"
                f"    cd {self.node_dir} && npm install --prefix . "
                "speech-rule-engine\n"
                f"node said: {detail}")
        version, to_speech = (probe.stdout.strip().split("|") + ["?"])[:2]
        if to_speech != "function":
            raise BackendUnavailable(
                f"speech-rule-engine {version} loaded but exposes no toSpeech() "
                f"(got {to_speech!r}). This build is not usable; reinstall or "
                "pin a known-good version.")
        try:
            spoken = self.speak(
                '<math xmlns="http://www.w3.org/1998/Math/MathML">'
                "<mfrac><mi>a</mi><mi>b</mi></mfrac></math>")
        except SpeechError as exc:
            raise BackendUnavailable(
                f"speech-rule-engine {version} is installed but the bridge did "
                f"not answer: {exc}") from exc
        if not spoken.strip():
            raise BackendUnavailable(
                f"speech-rule-engine {version} returned empty speech for a "
                f"trivial fraction (domain={self.domain}, style={self.style}, "
                f"locale={self.locale}, modality={self.modality}). Check that "
                "this combination exists -- `sre --opt` lists the valid ones.")
        node_v = subprocess.run(["node", "-v"], capture_output=True,
                                text=True).stdout.strip()
        self.resolved_from = _resolved_package_path(self.node_dir)
        return (f"OK: node {node_v}, speech-rule-engine {version}\n"
                f"    resolved from: {self.resolved_from or '(unknown)'}\n"
                f"    node-dir     : {self.node_dir}\n"
                f"    rule set     : domain={self.domain} style={self.style} "
                f"locale={self.locale} modality={self.modality}\n"
                f"    round-trip   : a/b -> {spoken.strip()!r}")

    # -- the actual call ----------------------------------------------------

    def speak(self, mathml: str, display: bool = False) -> str:
        with self._lock:
            proc = self._ensure()
            self._id += 1
            req = {
                "id": self._id, "mathml": mathml, "locale": self.locale,
                "domain": self.domain, "style": self.style,
                "modality": self.modality,
            }
            try:
                proc.stdin.write(json.dumps(req) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
            except (BrokenPipeError, ValueError) as exc:
                self._proc = None
                raise BackendUnavailable(
                    f"the node bridge died: {exc}. Run `--check`.") from exc
            if not line:
                detail = _node_error_line(self.bridge_stderr())
                self._proc = None
                raise BackendUnavailable(
                    "the node bridge produced no response. node said: "
                    + detail)
            try:
                resp = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SpeechError(f"bad bridge response: {line!r}") from exc
            if not resp.get("ok"):
                raise SpeechError(resp.get("error", "unknown SRE error"))
            return resp.get("text", "")


class MathCATSpeechBackend:
    """MathCAT backend -- UNVERIFIED.

    Not exercised by the test suite: MathCAT ships no PyPI wheel, so this code
    path has never been executed. Treat every line below as a hypothesis.

    To make it real:
        git clone https://github.com/daisy/MathCATForPython
        # needs a Rust toolchain; build produces libmathcat_py
        # and a Rules/ directory that MathCAT must be pointed at

    MathCAT is the only engine that implements SimpleSpeak, and its Nemeth
    output is generally considered better than SRE's.
    """

    def __init__(self, rules_dir: str, style: str = "SimpleSpeak",
                 language: str = "en", braille_code: str = "Nemeth",
                 braille: bool = False):
        try:
            import libmathcat_py as libmathcat  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise SpeechError(
                "libmathcat_py not importable -- MathCAT must be built from "
                "source; see class docstring"
            ) from exc
        self._m = libmathcat
        self._m.SetRulesDir(rules_dir)
        self._m.SetPreference("SpeechStyle", style)
        self._m.SetPreference("Language", language)
        self._m.SetPreference("BrailleCode", braille_code)
        self._m.SetPreference("TTS", "None")
        self.braille = braille

    def speak(self, mathml: str, display: bool = False) -> str:  # pragma: no cover
        self._m.SetMathML(mathml)
        return (self._m.GetBraille("") if self.braille
                else self._m.GetSpokenText())

    def close(self) -> None:  # pragma: no cover
        pass


# --------------------------------------------------------------------------
# document-level driver
# --------------------------------------------------------------------------

class LatexSpeaker:
    """Turn LaTeX into one speakable string.

    Parameters
    ----------
    backend        : a SpeechBackend
    on_error       : "placeholder" | "raise" | "raw"
                     what to do when a math fragment cannot be converted
    display_prefix : spoken before a display equation ("" to disable)
    display_suffix : spoken after a display equation
    """

    #: pylatexenc emits typographic symbols that TTS engines mangle
    SYMBOL_SPEECH = {
        "\u00a7": "Section ",   # from \section
        "\u00b6": "Paragraph ",
        "\u2014": ", ",         # em dash
        "\u2013": " to ",       # en dash
        "\u00a0": " ",
    }

    def __init__(self, backend: SpeechBackend,
                 on_error: str = "placeholder",
                 display_prefix: str = "",
                 display_suffix: str = "",
                 suppress_numbering: bool = True,
                 verbatim_mode: str = "raw",
                 symbol_speech: Optional[dict] = None,
                 lint: bool = True,
                 formula_array: Optional[Sequence[str]] = None,
                 expand_macros: bool = True,
                 protect_identifiers: bool = True,
                 not_identifiers: Iterable[str] = ()):
        if on_error not in ("placeholder", "raise", "raw"):
            raise ValueError("on_error must be placeholder|raise|raw")
        if verbatim_mode not in ("raw", "skip", "announce"):
            raise ValueError("verbatim_mode must be raw|skip|announce")
        self.backend = backend
        self.on_error = on_error
        self.display_prefix = display_prefix
        self.display_suffix = display_suffix
        self.suppress_numbering = suppress_numbering
        self.verbatim_mode = verbatim_mode
        self.lint = lint
        self.formula_array = formula_array
        self.expand_macros = expand_macros
        self.protect_identifiers = protect_identifiers
        self.not_identifiers = frozenset(not_identifiers)
        self.symbol_speech = (self.SYMBOL_SPEECH if symbol_speech is None
                              else symbol_speech)
        self.errors: List[str] = []
        #: backend invocations so far; a caller comparing transclusion
        #: strategies reads the delta to see how often the same formula was
        #: re-spoken rather than reused.
        self.math_calls = 0
        self._text_conv = None

    # -- text side ----------------------------------------------------------

    def render_text(self, tex: str) -> str:
        """De-TeX a prose run: \\emph{x} -> x, ~ -> space, \\S -> section sign."""
        if self._text_conv is None:
            from pylatexenc.latex2text import LatexNodes2Text
            self._text_conv = LatexNodes2Text(
                math_mode="text", keep_comments=False, strict_latex_spaces=False)
        try:
            out = self._text_conv.latex_to_text(tex)
        except Exception:
            out = tex
        for k, v in self.symbol_speech.items():
            out = out.replace(k, v)
        return out

    # -- math side ----------------------------------------------------------

    def speak_math(self, tex: str, display: bool = False) -> str:
        """LaTeX math fragment -> spoken text.

        Delimiters are optional: an outer `$$..$$` / `\\[..\\]` / `$..$` is
        stripped, and a display delimiter promotes the fragment to display.
        """
        _, found_display = strip_math_delimiters(tex)
        display = display or found_display
        if self.protect_identifiers:
            # math only: wrapping prose in \text{} would be meaningless, and a
            # lowercase word before "(" is common in ordinary sentences.
            tex = latexproject.protect_identifiers(tex, self.not_identifiers)
        try:
            mathml = latex_to_mathml(tex, display, self.suppress_numbering,
                                     warnings=self.errors)
        except MathMLError as exc:
            return self._fail(tex, exc)
        try:
            self.math_calls += 1
            return self.backend.speak(mathml, display).strip()
        except BackendUnavailable:
            raise                      # environmental, not a bad expression
        except SpeechError as exc:
            return self._fail(tex, exc)

    def _fail(self, tex: str, exc: Exception) -> str:
        self.errors.append(f"{type(exc).__name__}: {exc}")
        if self.on_error == "raise":
            raise exc
        if self.on_error == "raw":
            return tex
        return "[unspoken math]"

    # -- document -----------------------------------------------------------

    def speak(self, tex: str, strip_preamble: bool = True,
              table: Optional["latexproject.MacroTable"] = None,
              array: Optional["latexproject.ArrayRef"] = None) -> str:
        """Whole-document (or snippet) conversion.

        Runs find_unspoken_math() over the segmentation and records any hit in
        self.errors, because a missed math block produces plausible-looking
        prose rather than an exception.
        """
        if self.expand_macros:
            # Macros are declared in the preamble, not in the individual math
            # runs, so the whole document is expanded once before segmentation.
            # This also promotes an expanded \Expr{n} sitting in prose into a
            # real `$..$` run, which the segmenter would otherwise never see.
            # A caller walking a docmodel harvests once across every unit and
            # passes the table in; definitions live in one tiddler and uses in
            # another, so re-harvesting per unit would miss them.
            tex = latexproject.expand(
                tex,
                table if table is not None else latexproject.harvest_macros(tex),
                array if array is not None else latexproject.resolve_array(
                    tex, external=self.formula_array),
                warnings=self.errors)
        segs = segment(tex, strip_preamble)
        if self.lint:
            self.errors.extend(find_unspoken_math(segs))
        return "".join(self._pieces(segs))

    def _pieces(self, segs: Sequence[Segment]) -> Iterator[str]:
        for seg in segs:
            if seg.kind == "text":
                yield self.render_text(seg.text)
            elif seg.kind == "verbatim":
                if self.verbatim_mode == "skip":
                    continue
                if self.verbatim_mode == "announce":
                    yield "\nBegin code.\n" + seg.text.strip() + "\nEnd code.\n"
                else:
                    yield seg.text
            else:
                spoken = self.speak_math(seg.text, seg.display)
                if seg.display:
                    yield "\n" + self.display_prefix + spoken + self.display_suffix + "\n"
                else:
                    yield spoken

    # -- convenience --------------------------------------------------------

    def close(self) -> None:
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def normalize_whitespace(s: str) -> str:
    """Collapse the ragged whitespace TeX leaves behind, keeping paragraphs."""
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

#: capabilities probed from the module itself, so a stale copy self-identifies
#: even when the version string was not bumped
_FEATURES = (
    ("projections", "PROJECTIONS"),
    ("docmodel", "tiddlerpipe"),
    ("preflight/check", "BackendUnavailable"),
    ("where", "_resolved_package_path"),
    ("delimiter-strip", "strip_math_delimiters"),
    ("left-right-repair", "repair_left_right"),
    ("brace-repair", "repair_braces"),
    ("unspoken-lint", "find_unspoken_math"),
)


def build_report() -> str:
    """Version, file, content hash and capability list.

    The hash is the authoritative answer to "which build am I running": it does
    not depend on my having remembered to bump __version__, and it survives
    copying the file around.
    """
    import hashlib
    path = os.path.abspath(__file__)
    try:
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()[:16]
    except OSError:
        digest = "(unreadable)"
    have = [name for name, sym in _FEATURES if sym in globals()]
    missing = [name for name, sym in _FEATURES if sym not in globals()]
    lines = [f"latex2speech {__version__}",
             f"    file    : {path}",
             f"    sha256  : {digest}",
             f"    features: {', '.join(have) or '(none)'}"]
    if missing:
        lines.append(f"    MISSING : {', '.join(missing)}  <- stale copy")
    return "\n".join(lines)


def _read_array(path: Optional[str]) -> Optional[List[str]]:
    """Read an external .dat formula array (one expression per line)."""
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read().rstrip("\n").split("\n")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="LaTeX -> speakable plain text (no TTS).")
    class _Version(argparse.Action):
        """argparse's built-in version action re-wraps the text, which
        destroys the layout of a multi-line build report."""
        def __init__(self, option_strings, dest, **kw):
            super().__init__(option_strings, dest, nargs=0, **kw)

        def __call__(self, parser, namespace, values, option_string=None):
            print(build_report())
            parser.exit()

    ap.add_argument("--version", action=_Version,
                    help="print version, content hash and capabilities")
    ap.add_argument("input", nargs="?", help="LaTeX file; omit to read stdin")
    ap.add_argument("-o", "--output", help="output file; default stdout")
    ap.add_argument("--node-dir", default=None,
                    help="dir with node_modules/speech-rule-engine + "
                         "sre_bridge.js (default: $SRE_DIR, else ./sre)")
    ap.add_argument("-d", "--domain", default="clearspeak",
                    help="clearspeak|mathspeak|chromevox|emacspeak|default")
    ap.add_argument("-s", "--style", default="default",
                    help="rule-set style, e.g. brief / sbrief / Fraction_Over")
    ap.add_argument("-c", "--locale", default="en")
    ap.add_argument("-b", "--modality", default="speech",
                    choices=("speech", "braille"))
    ap.add_argument("--simplespeak", action="store_true",
                    help="MathCAT SimpleSpeak has no SRE equivalent; use the "
                         "nearest terse rule set (mathspeak/brief)")
    ap.add_argument("--nemeth", action="store_true",
                    help="shorthand for --locale nemeth --modality braille")
    ap.add_argument("--raw", action="store_true",
                    help="treat input as a bare math fragment, not a document")
    ap.add_argument("--keep-preamble", action="store_true")
    ap.add_argument("--on-error", default="placeholder",
                    choices=("placeholder", "raise", "raw"))
    ap.add_argument("--verbatim", default="raw", choices=("raw", "skip", "announce"),
                    help="what to do with verbatim/lstlisting blocks")
    ap.add_argument("--projection", metavar="NAME",
                    help="run a named projection: latex | docmodel | speech | text "
                         "(see --list-projections)")
    ap.add_argument("--list-projections", action="store_true",
                    help="describe the available projections and exit")
    ap.add_argument("--tiddlers", metavar="IN.json",
                    help="read a LATW-style tiddler array; speech is merged "
                         "back onto each tiddler and written with -o")
    ap.add_argument("--transclusion-mode", default="cached",
                    choices=("inline", "cached", "hybrid"),
                    help="how {{..}} references resolve: inline re-speaks at "
                         "each use site, cached reuses the target's speech "
                         "field, hybrid reads latex=/speech= from the marker")
    ap.add_argument("--speech-field", default="speech", metavar="NAME",
                    help="tiddler field the spoken text is merged into")
    ap.add_argument("--protect-identifiers", action="store_true",
                    help="wrap multi-letter identifiers in \\text{} so the "
                         "engine reads AVERAGE as a word instead of spelling "
                         "it (on by default in the library, off here)")
    ap.add_argument("--not-identifier", action="append", default=[],
                    metavar="NAME",
                    help="never treat NAME as an identifier; repeatable "
                         "(e.g. --not-identifier AB for a geometry segment)")
    ap.add_argument("--no-expand", action="store_true",
                    help="skip macro/formula-array expansion; \\newcommand "
                         "bodies then reach the engine verbatim")
    ap.add_argument("--array-file", default=None,
                    help="external .dat formula array instead of filecontents")
    ap.add_argument("--where", action="store_true",
                    help="report where node resolves speech-rule-engine from, "
                         "plus npm's local and global roots, and exit")
    ap.add_argument("--check", action="store_true",
                    help="verify the speech engine is reachable and exit")
    ap.add_argument("--no-preflight", action="store_true",
                    help="skip the startup engine check")
    args = ap.parse_args(argv)

    # Provenance matters: an exported SRE_DIR silently overrides the ./sre
    # default, so passing --node-dir explicitly can change behaviour in a way
    # that looks like the default is broken.
    if args.node_dir is not None:
        node_dir_src = "--node-dir"
    elif os.environ.get("SRE_DIR"):
        args.node_dir = os.environ["SRE_DIR"]
        node_dir_src = "$SRE_DIR"
    else:
        args.node_dir = "./sre"
        node_dir_src = "default ./sre relative to cwd " + os.getcwd()

    domain, style = args.domain, args.style
    if args.simplespeak:
        domain, style = SRESpeechBackend.SIMPLESPEAK_FALLBACK
    locale, modality = args.locale, args.modality
    if args.nemeth:
        locale, modality, domain, style = "nemeth", "braille", "default", "default"

    if args.where:
        print(f"cwd              : {os.getcwd()}")
        print(f"--node-dir       : {args.node_dir}  (from {node_dir_src})")
        print(f"NODE_PATH        : {os.environ.get('NODE_PATH', '(unset)')}")
        base = args.node_dir if os.path.isdir(args.node_dir) else os.getcwd()
        resolved = _resolved_package_path(base)
        print(f"resolves SRE to  : {resolved or '(not resolvable)'}")

        # Resolving the manifest proves only that a directory exists. The
        # question that decides whether anything works is whether the package
        # main loads -- report it here rather than making the user find out
        # from a failed run.
        if resolved:
            probe = subprocess.run(
                ["node", "-e", "require('speech-rule-engine')"],
                cwd=base, capture_output=True, text=True)
            if probe.returncode == 0:
                print("main entry       : loads OK")
            else:
                print("main entry       : FAILS -- "
                      + _node_error_line(probe.stderr))
                print("                   this install is incomplete; the "
                      "manifest is there but the code is not")
            pkg_dir = os.path.dirname(resolved)
            try:
                print("package contents : "
                      + ", ".join(sorted(os.listdir(pkg_dir))[:12]))
            except OSError:
                pass
        # npm walks up as well: an ancestor package.json redirects a plain
        # `npm install` away from the directory you ran it in.
        probe_dir = os.path.abspath(base)
        hijack = None
        d = probe_dir
        while True:
            if d != probe_dir and os.path.isfile(os.path.join(d, "package.json")):
                hijack = d
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        if hijack:
            print(f"npm root would be: {hijack}  <- a package.json there makes "
                  "a plain\n                   `npm install` land in that "
                  "directory, not in --node-dir.\n                   Use: npm "
                  "install --prefix . speech-rule-engine")
        for label, cmd in (("npm root (local) ", ["npm", "root"]),
                           ("npm root -g      ", ["npm", "root", "-g"]),
                           ("npm prefix -g    ", ["npm", "config", "get", "prefix"])):
            try:
                r = subprocess.run(cmd, cwd=base, capture_output=True, text=True)
                print(f"{label}: {r.stdout.strip() or '(none)'}")
            except OSError:
                print(f"{label}: (npm not found)")
        print("\nnode resolves by walking UP from the working directory, so a "
              "package\nfound here may live in an ancestor directory or a "
              "global prefix.\n`find . -name '*.js'` only looks DOWN and will "
              "not show it.")
        return 0

    if args.check:
        be = SRESpeechBackend(args.node_dir, domain=domain, style=style,
                              locale=locale, modality=modality)
        try:
            print(be.preflight())
            print(f"    node-dir from: {node_dir_src}")
            return 0
        except BackendUnavailable as exc:
            print("latex2speech: " + str(exc), file=sys.stderr)
            print(f"latex2speech: node-dir came from {node_dir_src}",
                  file=sys.stderr)
            return 2
        finally:
            be.close()

    if args.list_projections:
        from . import projections
        print("projections:")
        print(projections.describe())
        return 0

    if args.projection == "text":
        from . import projections
        from . import tiddlerpipe
        out = projections.project_text(
            tiddlerpipe.load_tiddlers(args.input), field=args.speech_field)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
        else:
            sys.stdout.write(out + "\n")
        return 0

    if args.projection in ("latex", "docmodel"):
        import json as _json
        from . import projections
        src = (open(args.input, encoding="utf-8").read() if args.input
               else sys.stdin.read())
        warns: List[str] = []
        if args.projection == "latex":
            out = projections.project_latex(
                src, protect=args.protect_identifiers,
                exclude=args.not_identifier, warnings=warns)
        else:
            out = _json.dumps(projections.project_docmodel(src, warnings=warns),
                              ensure_ascii=False, indent=1)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
        else:
            sys.stdout.write(out + "\n")
        for w in warns:
            print("latex2speech: " + w, file=sys.stderr)
        return 0

    if args.tiddlers or args.projection == "speech":
        from . import tiddlerpipe
        if not args.output:
            print("latex2speech: --tiddlers needs -o for the updated docmodel",
                  file=sys.stderr)
            return 2
        model = tiddlerpipe.load_tiddlers(args.tiddlers or args.input)
        backend = SRESpeechBackend(args.node_dir, domain=domain, style=style,
                                   locale=locale, modality=modality)
        with LatexSpeaker(backend, on_error=args.on_error,
                          verbatim_mode=args.verbatim,
                          expand_macros=not args.no_expand,
                          protect_identifiers=args.protect_identifiers,
                          not_identifiers=args.not_identifier) as sp:
            stats = tiddlerpipe.speak_tiddlers(
                model, sp, field=args.speech_field,
                mode=args.transclusion_mode)
        tiddlerpipe.save_tiddlers(args.output, model)
        print(f"latex2speech: {stats['spoken']} tiddler(s) spoken, "
              f"{stats['calls']} engine call(s), {stats['skipped']} skipped, "
              f"{stats['warnings']} warning(s) -> {args.output}",
              file=sys.stderr)
        return 1 if stats["warnings"] else 0

    src = (open(args.input, encoding="utf-8").read() if args.input
           else sys.stdin.read())

    backend = SRESpeechBackend(args.node_dir, domain=domain, style=style,
                               locale=locale, modality=modality)
    if not args.no_preflight:
        try:
            backend.preflight()
        except BackendUnavailable as exc:
            backend.close()
            print("latex2speech: " + str(exc), file=sys.stderr)
            print(f"latex2speech: node-dir came from {node_dir_src}",
                  file=sys.stderr)
            print("latex2speech: aborting -- every formula would have become "
                  "'[unspoken math]'. Run --check to retest.", file=sys.stderr)
            return 2
    with LatexSpeaker(backend, on_error=args.on_error,
                      verbatim_mode=args.verbatim,
                      formula_array=_read_array(args.array_file),
                      expand_macros=not args.no_expand,
                      protect_identifiers=args.protect_identifiers,
                      not_identifiers=args.not_identifier) as sp:
        out = (sp.speak_math(src) if args.raw
               else normalize_whitespace(sp.speak(src, not args.keep_preamble)))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    else:
        sys.stdout.write(out + "\n")

    for e in sp.errors:
        print("latex2speech: " + e, file=sys.stderr)
    unspoken = out.count("[unspoken math]")
    if unspoken:
        print(f"latex2speech: {unspoken} math fragment(s) could not be spoken. "
              "Rerun with --on-error raise for the full traceback, or "
              "--audit to check a formula array.", file=sys.stderr)
    return 1 if unspoken else 0


if __name__ == "__main__":
    # `latex2speech --version | head -1` otherwise dies with a BrokenPipeError
    # traceback instead of exiting quietly like every other CLI tool.
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError, OSError):
        pass
    raise SystemExit(_main())
