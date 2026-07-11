"""
Three-source prose merge — LaTeX is the CONTENT truth, MathPix the LAYOUT truth.

The problem: the LaTeX-source build (`build_source_model`) splits prose only at
source blank lines, so a long author paragraph stays one 3000-char block where
MathPix — splitting by visual layout — would give 3-4 paragraphs each with its
own `region`. The MathPix path has the fine boundaries + geometry but OCR'd
(lossy) text; the LaTeX path has gold text but coarse boundaries.

`merge_latex_prose` takes a MathPix model as the SKELETON (its Paragraph objects
define the boundaries + `region`s) and re-partitions the gold LaTeX prose across
those boundaries by word-alignment (`difflib.SequenceMatcher`). Each paragraph's
`text` is REPLACED by its aligned LaTeX span (**LaTeX always wins**), the MathPix
`region` is kept, and the original OCR text is preserved under `text_source` for
audit. A MathPix paragraph with no LaTeX counterpart (a caption OCR'd as prose)
is left untouched — LaTeX wins only where it actually has text.

Pure + idempotent. pdfminer coordinate refinement of inline-formula regions is a
separate leg (the CTM chain) that slots onto the same objects later.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_WORD = re.compile(r"\S+")


def _words(text: str):
    """[(normalized_word, start_char, end_char)] over `text`."""
    out = []
    for m in _WORD.finditer(text or ""):
        norm = re.sub(r"[^0-9a-z]+", "", m.group(0).lower())
        out.append((norm, m.start(), m.end()))
    return out


_TEXT_WRAP = re.compile(
    r"\\(?:emph|textbf|textit|texttt|textsc|textrm|textsf|text|mbox|"
    r"underline|mathrm)\s*\{")
_DROP_CMD = re.compile(
    r"\\(?:cite[a-z]*|ref|eqref|cref|autoref|label|footnote|footnotemark|"
    r"index|nocite)\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}")
_BARE_CMD = re.compile(r"\\(?:noindent|clearpage|newpage|par|centering|"
                       r"smallskip|medskip|bigskip|hfill|vfill)\b")


def _unwrap_text_commands(text: str) -> str:
    """Replace `\\emph{x}`/`\\textbf{x}`/... with their argument `x` (balanced)."""
    out, i = [], 0
    while i < len(text):
        m = _TEXT_WRAP.match(text, i)
        if not m:
            out.append(text[i]); i += 1; continue
        open_pos = m.end() - 1
        close = _balanced_brace(text, open_pos)
        if close < 0:
            out.append(text[i]); i += 1; continue
        out.append(_unwrap_text_commands(text[open_pos + 1:close - 1]))
        i = close
    return "".join(out)


def _balanced_brace(text: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def latex_prose_from_body(body: str) -> str:
    """Extract clean GOLD prose from a LaTeX `body`: blank display math / floats /
    sectioning (reusing `latex_source._STRUCT_RE`), drop cite/ref/label/footnote,
    unwrap text-formatting wrappers, and keep inline `$..$`/`\\(..\\)` math as
    `\\(..\\)` (the MathPix convention — the tiddler projector FOX-izes residual
    inline math). Returns one whitespace-collapsed prose string."""
    from . import latex_source as ls
    text = ls.strip_comments(body or "")
    text = ls._STRUCT_RE.sub(" ", text)
    text = _DROP_CMD.sub(" ", text)
    text = _unwrap_text_commands(text)
    text = _BARE_CMD.sub(" ", text)
    # inline math: $x$ -> \(x\)  (\(..\) already in that form)
    text = re.sub(r"(?<!\$)\$([^$]+)\$(?!\$)", r"\\(\1\\)", text)
    # residual environments we didn't blank: drop their \begin/\end shells
    text = re.sub(r"\\(?:begin|end)\s*\{[^{}]*\}", " ", text)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def _flow(o):
    try:
        return float(o.props.get("flow_index") or 0)
    except (TypeError, ValueError):
        return 0.0


def merge_latex_prose(doc, latex_prose: str) -> int:
    """Re-partition `latex_prose` across the MathPix Paragraph boundaries.

    Returns the number of paragraphs whose text was replaced by a gold span.
    """
    paras = sorted(doc.objects_of_type("Paragraph"), key=_flow)
    if not paras or not (latex_prose or "").strip():
        return 0

    # MathPix word stream + per-paragraph [start, end) word ranges
    mp_words: list[tuple[str, int, int]] = []
    bounds: list[tuple[int, int]] = []
    for p in paras:
        start = len(mp_words)
        w = _words(p.props.get("text") or "")
        mp_words.extend(w)
        bounds.append((start, len(mp_words)))

    lx_words = _words(latex_prose)
    if not mp_words or not lx_words:
        return 0

    # word-level alignment: mp word index -> lx word index (matched words only)
    sm = SequenceMatcher(None, [w[0] for w in mp_words], [w[0] for w in lx_words],
                         autojunk=False)
    mp2lx: dict[int, int] = {}
    for i, j, n in sm.get_matching_blocks():
        for k in range(n):
            mp2lx[i + k] = j + k

    # each paragraph's lx START = the first mapped lx index within its word range;
    # keep boundaries monotonic so slices never overlap or reorder.
    lx_start: list[int | None] = []
    for a, b in bounds:
        s = None
        for i in range(a, b):
            if i in mp2lx:
                s = mp2lx[i]
                break
        lx_start.append(s)

    # forward-fill so each paragraph gets a monotone non-decreasing start
    filled: list[int | None] = list(lx_start)
    running = 0
    for k, s in enumerate(filled):
        if s is None:
            filled[k] = None            # decide per-paragraph below
        else:
            running = max(running, s)
            filled[k] = running

    changed = 0
    for idx, p in enumerate(paras):
        s = filled[idx]
        if s is None:                   # no matched word → LaTeX has no span here
            continue
        # end = next paragraph's start that is defined and > s, else end of prose
        e = len(lx_words)
        for nxt in filled[idx + 1:]:
            if nxt is not None and nxt > s:
                e = nxt
                break
        if e <= s:
            continue
        span = latex_prose[lx_words[s][1]:lx_words[e - 1][2]].strip()
        if not span:
            continue
        old = p.props.get("text") or ""
        if span == old.strip():
            continue
        p.props.setdefault("text_source", old)
        p.props["text"] = span
        p.props["merged_from"] = "latex"
        changed += 1
    return changed
