r"""
LaTeXPipeline — the inspectable model→LaTeX generator.

Where `LaTeXProjector` (latex.py) is a single opaque text-dump, this is a PIPELINE
of pure, inspectable STAGES — each returns plain data you can dump to a file and
test independently (the textscan-style inspectability). `pdfdrill latex
--dump-stages` writes them next to the assembled `.tex`:

    00-transclusions.json   {marker-id → LaTeX}      (array lookup)
    01-citations.json       [citekey, …]             (\cite map)
    02-bibliography.bib      thebibliography / .bib   (\bibitem)
    03-glossary.tex          \newacronym/\printindex  (next increment)

The stages fix the "Markdown with a LaTeX header" problem: a MathPix/scan doc's
paragraph text carries `{{<bibkey>_FO0001||FO}}` transclusion markers + Markdown
headings; the body resolver turns each marker into the formula's `$…$` (by array
lookup) and each heading into `\section`, so the body is real LaTeX.

Status: stages 0 (transclusion), 1 (citation), 2 (bibliography) are wired.
Stage 3 (glossary/acronym/index) reuses `semantic.stex` and lands next.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from docmodel.core import Document
from .tiddlywiki import title_for

# a transclusion marker: {{<title>||<TPL>}} where TPL ∈ FO/FREF/FN/PIC/DIA/CIT…
_MARKER = re.compile(r"\{\{([^|{}]+?)\|\|([A-Z]+)\}\}")
# a Markdown / leaked heading at line start
_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_TEX_SECTION = re.compile(r"^\\(sub)*section\*?\{")


# ── stage 0: transclusion as a readarray ARRAY (filecontents + readarray) ────
#
# The formula LaTeX goes ONCE into a `.dat` array (one entry per line); each
# `{{<bibkey>_FO0001||FO}}` marker becomes `\Expr{<index>}`. This is real
# transclusion (define once, reference by index), not inline expansion — the
# user's filecontents+readarray idiom. Deduped by content so identical math
# shares one slot.

# MathPix / OCR emit Unicode math operators INSIDE the LaTeX. In math mode these
# are NOT rendered by xelatex/pdflatex without unicode-math — the classic one is
# U+2212 (a "minus" that isn't ASCII `-`). Map them to LaTeX macros / ASCII.
_MATH_UNICODE = {
    "−": "-", "–": "-", "—": "-", "×": "\\times ",
    "÷": "\\div ", "±": "\\pm ", "∓": "\\mp ",
    "≤": "\\leq ", "≥": "\\geq ", "≠": "\\neq ",
    "≈": "\\approx ", "≡": "\\equiv ", "∞": "\\infty ",
    "∑": "\\sum ", "∏": "\\prod ", "∫": "\\int ",
    "√": "\\sqrt ", "∂": "\\partial ", "∇": "\\nabla ",
    "∈": "\\in ", "∉": "\\notin ", "⊂": "\\subset ",
    "⊆": "\\subseteq ", "∪": "\\cup ", "∩": "\\cap ",
    "→": "\\to ", "⇒": "\\Rightarrow ", "⇔": "\\Leftrightarrow ",
    "∀": "\\forall ", "∃": "\\exists ", "·": "\\cdot ",
    "…": "\\dots ", "°": "^{\\circ}",
    "α": "\\alpha ", "β": "\\beta ", "γ": "\\gamma ",
    "δ": "\\delta ", "ε": "\\epsilon ", "λ": "\\lambda ",
    "μ": "\\mu ", "π": "\\pi ", "σ": "\\sigma ",
    "φ": "\\phi ", "ω": "\\omega ", "Δ": "\\Delta ",
    "Σ": "\\Sigma ", "Ω": "\\Omega ",
}
_MATH_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _MATH_UNICODE))


# text-mode structure that leaks INTO a math body from an enclosing environment
# (MathPix/extraction captures `\end{itemize}` after the equation) — illegal in
# math mode. Also `\item`, list/float begins+ends.
_LEAKED_MATH_ENV = re.compile(
    r"\\(?:begin|end)\s*\{(?:itemize|enumerate|description|list|quote|quotation"
    r"|center|flushleft|flushright|verbatim|abstract|figure|table|proof|minipage"
    r"|thebibliography)\*?\}"
    r"|\\item\b(?:\s*\[[^\]]*\])?")


def _strip_math_delimiters(latex: str) -> str:
    """Remove a WRAPPING math delimiter (`\\[…\\]`, `\\(…\\)`, `$$…$$`, `$…$`) —
    an Equation body carrying its own `\\[…\\]` would nest display math inside
    `\\begin{equation}` ('Bad math environment delimiter'). Only strips when the
    WHOLE (trimmed) string is one wrapped span, so `$a$ and $b$` is left alone."""
    s = latex.strip()
    if s.startswith("$$") and s.endswith("$$") and len(s) >= 4:
        return s[2:-2].strip()
    for op, cl in (("\\[", "\\]"), ("\\(", "\\)")):
        if s.startswith(op) and s.endswith(cl) and len(s) >= len(op) + len(cl):
            return s[len(op):-len(cl)].strip()
    if len(s) >= 2 and s.startswith("$") and s.endswith("$") and s.count("$") == 2:
        return s[1:-1].strip()
    return s


#: The plain-TeX matrix forms amsmath REFUSES outright, and the names it wants
#: instead. T-0156.
#:
#: amsmath answers `\pmatrix{a\cr b}` with "Package amsmath Error: Old form
#: `\pmatrix' should be \begin{pmatrix}" and stops. arxiv.0912.2444 writes
#: three of each:
#:
#:     \pmatrix{\lfloor cN \rfloor\cr\lfloor cN_2\rfloor}
#:     \cases{ H(\mathbb{G}_0)+\beta, &\quad if … \cr H_{m+1}+\beta, &\quad …}
#:
#: 6 errors for the forms themselves and 9 more for the `\cr` inside them —
#: measured, ALL NINE `\cr` in that document sit inside these six groups, so
#: the two are one construct and not two classes.
#:
#: `\matrix`, `\eqalign` and `\atop` are NOT here: zero occurrences in the
#: corpus, and a name added without one is a guess. `\over` IS there, 207
#: times on the same document, and is deliberately left alone — amsmath
#: accepts it, it raises no error, and rewriting it to `\frac` would mean
#: parsing its two sides, which is a different job with its own failure mode.
_PLAIN_TEX_MATRIX = {"pmatrix": "pmatrix", "cases": "cases"}


def _cases_second_column_is_text(body: str) -> str:
    r"""Restore the text mode plain TeX's `\cases` gives its second column.

    T-0156 — THE TWO FORMS DIFFER IN MORE THAN SPELLING. Plain TeX sets the
    column after `&` in TEXT mode; amsmath's `cases` sets it in MATH mode. So
    an author who writes

        \cases{ H(\G_0)+\beta, &\quad if $i\stackrel{0}{\not\sim} k$; \cr …}

    is correct — the `$…$` opens maths inside a text column — and the same
    row inside `\begin{cases}` toggles maths OFF and leaves `k$;` in text
    mode. xelatex answers "Missing $ inserted", three times for that one row.

    MEASURED on the eight e-prints: 24 of the 146 errors are `Missing $
    inserted`, and arxiv.0912.2444 — which writes three `\cases` groups —
    carries all of them.

    Wrapping the column in `\text{…}` keeps the author's own `$…$` valid
    INSIDE it, so the row is restored rather than rewritten: nothing is
    dropped and no mathematics is reinterpreted. A column with no `$` is
    left alone, since it is then already what amsmath expects.
    """
    out = []
    for row in body.split(r"\\"):
        amp = row.find("&")
        if amp < 0 or "$" not in row[amp:]:
            out.append(row)
            continue
        head, tail = row[:amp + 1], row[amp + 1:]
        lead = tail[:len(tail) - len(tail.lstrip())]
        inner = tail.strip()
        # `\quad` and friends belong OUTSIDE the text box: inside it they
        # would be set as literal words.
        m = re.match(r"((?:\\(?:quad|qquad|,|;|:|!|\s)\s*)*)(.*)$", inner, re.S)
        spacing, rest = (m.group(1), m.group(2)) if m else ("", inner)
        if not rest.strip():
            out.append(row)
            continue
        out.append(head + lead + spacing + r"\text{" + rest.strip() + "}")
    return r"\\".join(out)


def _plain_tex_matrices(latex: str) -> str:
    r"""`\pmatrix{a\cr b}` -> `\begin{pmatrix}a\\b\end{pmatrix}`.

    The row separator goes with the form: plain TeX breaks a row with `\cr`
    and the amsmath environment with `\\`, so a conversion that kept `\cr`
    would trade one error for another. Only the `\cr` INSIDE the group is
    rewritten -- the rule is local, even though the measurement says every one
    of them is inside.

    A trailing separator is dropped: `\cases{a\cr b\cr}` would otherwise end in
    an empty row, which amsmath reports as a misplaced `\noalign`.
    """
    for name, env in _PLAIN_TEX_MATRIX.items():
        pat = re.compile(r"\\" + name + r"\s*\{")
        while True:
            m = pat.search(latex)
            if not m:
                break
            open_at = m.end() - 1
            depth, close = 0, None
            for i in range(open_at, len(latex)):
                if latex[i] == "{" and (i == 0 or latex[i - 1] != "\\"):
                    depth += 1
                elif latex[i] == "}" and latex[i - 1] != "\\":
                    depth -= 1
                    if depth == 0:
                        close = i
                        break
            if close is None:
                break                     # unbalanced: leave it for the crop
            body = latex[open_at + 1:close]
            body = re.sub(r"\\cr(?![A-Za-z])", r"\\\\", body)
            body = re.sub(r"(?:\\\\\s*)+$", "", body)
            if name == "cases":
                body = _cases_second_column_is_text(body)
            latex = (latex[:m.start()] + "\\begin{" + env + "}" + body
                     + "\\end{" + env + "}" + latex[close + 1:])
    return latex


def sanitize_math(latex: str) -> str:
    """Make a formula body compile in math mode: replace Unicode math operators
    (U+2212 minus, ×, ≤, Greek, …) with their LaTeX macros, DROP text-mode
    structure that leaked in (`\\end{itemize}`, `\\item`), and STRIP a wrapping
    math delimiter (`\\[…\\]`). A formula that then STARTS with `[` (a Lie bracket
    `[X,Y]=…`) is prefixed with `{}` so amsmath doesn't read the bracket as a
    misplaced optional argument ('Bracket group … at formula start!')."""
    latex = _MATH_UNICODE_RE.sub(lambda m: _MATH_UNICODE[m.group(0)], latex)
    latex = _LEAKED_MATH_ENV.sub(" ", latex)      # drop leaked list/float envs
    latex = _plain_tex_matrices(latex)            # \pmatrix{…} -> the environment
    latex = _strip_math_delimiters(latex)         # unwrap \[…\] / $…$ / …
    latex = _drop_dangling_backslash(latex)
    latex = _fix_text_mode_specials(latex)
    if latex.lstrip().startswith("["):
        latex = "{}" + latex
    return latex


#: `\text{...}` with a brace-free body — the shape the measured artifact has.
_TEXT_GROUP_RE = re.compile(r"\\text\s*\{([^{}]*)\}")


def _fix_text_mode_specials(latex: str) -> str:
    r"""`^` and `_` inside `\text{...}` are text-mode errors; make them valid.

    MEASURED on BH2's German projection, 2026-11-12. TWO occurrences of
    `\text {^ }` — at source lines 132 and 144 of a 15,008-line file — held
    xelatex to 4 PAGES with 189 errors. Patching those two characters gave 468
    pages with 21. The same shape as `_drop_dangling_backslash` above: one
    character, and it takes the rest of the document with it, because TeX's
    recovery from a mode error derails everything after it.

    `{ }^{\text {^ }}` is what MathPix read — it saw the circumflex printed
    over a C as a caret character. That reading is the producer's record and is
    NOT edited: `props['latex']` keeps it verbatim, and the projection, which
    has to emit something that compiles, substitutes the text-mode spelling of
    the same glyph.

    A brace-free body only. `\text{\textbf{x} ^}` needs a brace matcher this
    does not have, so it is left alone and reports as a compile error — which
    is visible, where a wrong guess would be silent.
    """
    def fix(m: "re.Match[str]") -> str:
        body = m.group(1)
        if "^" not in body and "_" not in body:
            return m.group(0)
        body = re.sub(r"(?<!\\)\^", r"\\textasciicircum{}", body)
        body = re.sub(r"(?<!\\)_", r"\\textunderscore{}", body)
        return "\\text{" + body + "}"
    return _TEXT_GROUP_RE.sub(fix, latex)


def _drop_dangling_backslash(latex: str) -> str:
    r"""Remove a trailing backslash that would escape the CLOSING delimiter.

    822 — the worst kind of defect: one character, and it takes the rest of the
    document with it. A Formula whose body is `52-\` is wrapped by the projector
    as `${body}$` and comes out `$52-\$` — the closing `$` is escaped, the span
    never closes, and every error after it is a consequence. Measured on
    2605.23109: this single formula accounted for 120 of the file's 215
    xelatex errors, and bisecting the document was the only way to find it,
    because TeX reports the failure wherever the runaway finally collides with
    something — 800 lines later, inside a longtable that compiles perfectly on
    its own.

    `balance_math` cannot catch it: it counts `(?<!\\)\$`, and the delimiter
    here is added AFTER it runs, by the caller wrapping the body.

    An odd number of trailing backslashes is always wrong at the end of a
    formula — `\\` is a line break and legal, a lone `\` is a truncation — so
    this is a defect a reader can prove without understanding the mathematics,
    and it has exactly one correction.
    """
    body = latex.rstrip()
    n = len(body) - len(body.rstrip("\\"))
    if n % 2:
        body = body[:-1]
    return body


# DISPLAY-only math environments — invalid inside inline math (`\ensuremath`,
# which is what `\Expr` uses). A Formula carrying one is really a display equation
# mis-classified; strip the env + alignment so `\Expr{i}` compiles (cramped but
# valid) instead of erroring "Not allowed in LR mode".
_DISPLAY_ENV = re.compile(
    r"\\(?:begin|end)\{(?:aligned|split|gathered|gather\*?|align\*?|cases|"
    r"array|equation\*?|multline\*?|eqnarray\*?)\}(?:\{[^}]*\})?")


def _inline_safe(latex: str) -> str:
    """Make a formula safe for INLINE math: strip display-only environments and
    the alignment markers (`\\\\` line breaks, `&`) that error in LR mode."""
    if "\\begin{" not in latex and "\\\\" not in latex and "&" not in latex:
        return latex                                 # plain inline — untouched
    latex = _DISPLAY_ENV.sub(" ", latex)
    latex = latex.replace("\\\\", " \\; ").replace("&", " ")
    return re.sub(r"\s+", " ", latex).strip()


def _flatten(latex: str) -> str:
    """readarray splits entries on `\\par`, so each formula must be a SINGLE line —
    collapse internal whitespace/newlines to one space, normalise Unicode math
    operators (`sanitize_math`), and make display-math inline-safe (`_inline_safe`)
    so `\\Expr{i}` (inline `\\ensuremath`) never hits 'Not allowed in LR mode'."""
    return _inline_safe(sanitize_math(re.sub(r"\s+", " ", latex.strip())))


def _flatten_display(latex: str) -> str:
    """A DISPLAY equation → ONE physical line for the readarray array, PRESERVING
    its display structure (`\\\\` line breaks, `aligned`/`cases`) — unlike
    `_flatten`, which inline-flattens. Only real whitespace/newlines are collapsed
    to single spaces (so the entry stays one array line); `\\\\` stays two chars,
    not a newline, so it survives. Used for `\\EqExpr{i}` inside `\\begin{equation}`
    (which already provides display math, so no `\\ensuremath`)."""
    s = sanitize_math(re.sub(r"\s+", " ", latex.strip()))
    return re.sub(r"(?:\\\\\s*)+$", "", s).strip()          # drop a trailing \\


def formula_array(doc: Document) -> tuple[list[str], dict[str, int]]:
    """Return `(ordered distinct formula LaTeX, {object-title: 1-based index})`.

    Ordered by object title so the array is stable across builds; deduped by
    (flattened) content so an expression used many times shares ONE array slot.
    The index map is what the body resolver rewrites each `{{id||FO}}` into."""
    bibkey = str(doc.meta.get("bibkey") or "DOC")
    order: list[str] = []
    by_content: dict[str, int] = {}          # flattened latex → 1-based index
    title_index: dict[str, int] = {}
    # FLOW order (not obj.id) so the `<bibkey>_FO<NNNN>` numbering matches the
    # source builder's, which numbers by first appearance in the text.
    objs = [o for o in doc.objects.values() if o.type in ("Formula", "Equation")]
    objs.sort(key=lambda o: (o.props.get("flow_index", 0), o.id))
    fo_no = eq_no = 0
    for obj in objs:
        # a display Equation is stored display-preserving (\\ / aligned kept) so
        # it transcludes via `\EqExpr{i}`; an inline Formula is inline-flattened.
        if obj.type == "Equation":
            latex = _flatten_display(obj.props.get("latex") or "")
        else:
            latex = _flatten(obj.props.get("latex") or "")
        if not latex:
            continue
        idx = by_content.get(latex)
        if idx is None:
            order.append(latex)
            idx = len(order)                 # 1-based array position
            by_content[latex] = idx
        title_index[obj.id] = idx            # markers keyed by the object id
        # AND by the transclusion TITLE the source builder / tiddler projector
        # uses (`<bibkey>_FO<NNNN>` / `_EQ<NNNN>`, per-type, by first appearance).
        if obj.type == "Formula":
            fo_no += 1
            title_index[_safe_title(title_for(bibkey, "Formula", fo_no))] = idx
        else:
            eq_no += 1
            title_index[_safe_title(title_for(bibkey, "Equation", eq_no))] = idx
    return order, title_index


def _safe_title(t: str) -> str:
    """Match the source builder's title sanitisation (`[^A-Za-z0-9_\\-.]`→`_`)."""
    return re.sub(r"[^A-Za-z0-9_\-.]", "_", t)


def formula_preamble(order: list[str], dat_name: str) -> str:
    """The preamble block: write the formula array to `<dat_name>` via the
    `filecontents*` ENVIRONMENT, load it with `readarray`, and define BOTH
    transclusion macros — `\\Expr{<i>}` (INLINE, `\\ensuremath`, for a `$…$`
    formula in prose) and `\\EqExpr{<i>}` (DISPLAY, bare, for use inside
    `\\begin{equation}…\\end{equation}`, which already provides math mode). So an
    inline formula AND a display equation both transclude from the SAME array.

    The `filecontents` PACKAGE is obsolete — the environment is in the LaTeX
    kernel (2019+), and loading the package prints an "obsolete" warning — so we
    do not `\\usepackage{filecontents}`. `[overwrite]` regenerates the `.dat`
    every run (the kernel default refuses to overwrite an existing file → a
    stale array survives an edit)."""
    if not order:
        return ""
    body = "\n".join(order)
    return (
        f"\\begin{{filecontents*}}[overwrite]{{{dat_name}}}\n{body}\n"
        "\\end{filecontents*}\n"
        "\\usepackage{readarray}\n"
        "\\readarraysepchar{\\par}\n"
        f"\\readdef{{{dat_name}}}{{\\MathData}}\n"
        "\\readarray{\\MathData}{\\MathExpr}[-,\\nrows]\n"
        "\\newcommand{\\Expr}[1]{\\ensuremath{\\MathExpr[#1]}}\n"
        "\\newcommand{\\EqExpr}[1]{\\MathExpr[#1]}"
    )


# ── THE BRANCH TABLE (640-a) ────────────────────────────────────────────────
#
# `clean` → `heading_cleanup.materialize_transclusions` writes the TiddlyWiki
# PROJECTION of every paragraph back into `props["text"]`, so after a full
# drill a paragraph's prose is not raw LaTeX any more: it is
# `see {{D_FN0003||FN}} and {{D_REF_a||CIT}}`. Until 640 this projector knew
# only the array templates and the CIT tail, and EVERY other template fell
# through to a literal `(?D_FN0003)` printed into the document — 63 of them on
# penev_A, together with the 21 `\footnotemark[n]` 638 had won. A projection
# that prints a placeholder is the transclusion failure docs/TRANSCLUSION.md
# describes, and it is invisible: it compiles and it reads like prose.
#
# So: ONE table, keyed by `tiddlywiki.TEMPLATES`, and
# `tests/test_latex_templates.py` fails when a template is added there without
# a row here. Three actions:
#
#   ARRAY    the readarray lookup (`\Expr{i}`) — the math templates.
#   HANDLER  the projector supplies an object-aware renderer (it has the
#            Document; this module does not).
#   DROP     renders nothing, deliberately, matching the empty TiddlyWiki
#            template. Counted as `dropped:<TPL>`, never silent.
#
# A template with no handler at the call site is a REFUSAL, and a refusal is
# COUNTED (`template_unhandled:<TPL>`) and renders nothing. It is never a
# literal placeholder again.
ARRAY = "array"
HANDLER = "handler"
DROP = "drop"

TEMPLATE_ACTIONS: dict[str, str] = {
    "FO":      ARRAY,      # inline formula   → \Expr{i}
    "FREF":    ARRAY,      # equation ref     → \Expr{i} (the number's own entry)
    "EQ":      ARRAY,      # display equation (649: renamed from EQBLOCK)
    "CIT":     HANDLER,    # → \cite{key}          (642's resolver / title tail)
    "FN":      HANDLER,    # → \footnotemark[n] + \footnotetext[n]{…}  (638)
    "SN":      HANDLER,    # → \marginpar{\footnotesize …}
    "PIC":     HANDLER,    # → whatever the projector renders for the object
    "DIA":     HANDLER,
    "TAB":     HANDLER,
    "LI":      HANDLER,
    "PARA":    HANDLER,
    "ABS":     HANDLER,
    "PROOF":   HANDLER,
    "TOC":     HANDLER,
    "LTX":     DROP,       # a leaked LaTeX command renders nothing in the wiki
}

#: `<sup>N</sup>` is not a template — it is what
#: `TiddlyWikiProjector._substitute_footnotes` emits for a marker whose refnum
#: names NO Footnote object (44 of them on penev_A, the 638-measured extraction
#: gap). Left alone it printed the literal HTML tag into the .tex. A mark with
#: no body is exactly `\footnotemark[n]`.
_SUP_MARKER = re.compile(r"<sup>\s*(\d{1,3})\s*</sup>")


def marker_titles(text: str, tpl: str) -> list[str]:
    """Every `{{<title>||<tpl>}}` title in `text`, in order. Used to decide,
    BEFORE rendering, which objects a materialised block will print itself."""
    return [m.group(1) for m in _MARKER.finditer(text or "") if m.group(2) == tpl]


def _bump(counts, key: str) -> None:
    if counts is not None:
        counts[key] = counts.get(key, 0) + 1


def resolve_sup_markers(text: str, counts: dict | None = None,
                        handler=None) -> str:
    """`<sup>3</sup>` → `\\footnotemark[3]`. See `_SUP_MARKER`.

    641 fix round 1 — `handler(n) -> str | None` lets the PROJECTOR decide,
    because a `<sup>n</sup>` is the materialised spelling of the same marker the
    bare `\\({ }^{n}\\)` walk resolves, and the rule behind both is one function
    (`footnotes.decide`). This module has no Document, which is why the decision
    is injected here exactly as `resolve_transclusions` injects its handlers.
    Returning None keeps the default, and the default is `\\footnotemark[n]`:
    640's ruling that a mark with no body IS a mark. A literal `<sup>` tag is
    never emitted — that is 640-a, and it printed 44 times into penev_A."""
    def sub(m: re.Match) -> str:
        _bump(counts, "resolved:SUP")
        if handler is not None:
            out = handler(m.group(1))
            if out is not None:
                return out
        return f"\\footnotemark[{m.group(1)}]"
    return _SUP_MARKER.sub(sub, text)


def resolve_transclusions(text: str, title_index: dict[str, int],
                          handlers: dict | None = None,
                          counts: dict | None = None) -> str:
    """Rewrite every `{{<title>||TPL}}` marker through the branch table above.

    `handlers` maps a template name to `f(title) -> str | None`; returning None
    means "this handler cannot render that title", and the marker then falls
    through to the table. `counts` (mutated in place) records what happened by
    template name, so a refusal is a NUMBER somebody reads rather than a
    character somebody finds in the PDF.
    """
    handlers = handlers or {}

    def sub(m: re.Match) -> str:
        title, tpl = m.group(1), m.group(2)
        h = handlers.get(tpl)
        if h is not None:
            out = h(title)
            if out is not None:
                _bump(counts, f"resolved:{tpl}")
                return out
        action = TEMPLATE_ACTIONS.get(tpl)
        if action == DROP:
            _bump(counts, f"dropped:{tpl}")
            return ""
        if action == ARRAY:
            idx = title_index.get(title)
            if idx is not None:
                _bump(counts, f"resolved:{tpl}")
                return f"\\Expr{{{idx}}}"
            _bump(counts, f"unresolved_title:{tpl}")
            return ""
        if tpl == "CIT":
            # No handler (a bare pipeline call): the citekey is the title tail.
            # `{{<bibkey>_REF_<citekey>||CIT}}` → `\cite{<citekey>}`, which is
            # the key the `\bibitem` carries.
            _bump(counts, "resolved:CIT")
            for sep in ("_REF_", "_CIT_", "_BIB_"):
                if sep in title:
                    return f"\\cite{{{title.split(sep, 1)[-1]}}}"
            return f"\\cite{{{title}}}"
        _bump(counts, f"template_unhandled:{tpl}")
        return ""
    return _MARKER.sub(sub, text)


# Ligatures the PDF text layer emits as single codepoints — decompose so the
# font doesn't have to carry them (and word search / spell works).
_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
              "ﬅ": "ft", "ﬆ": "st"}
_LIG_RE = re.compile("|".join(_LIGATURES))
# Source LaTeX commands that leak into prose but must NOT survive projection: a
# bibliography is emitted as a `thebibliography` block, so a `\bibliography{db}` /
# `\bibliographystyle{s}` would try to load a missing .bib.
_LEAKED_CMD = re.compile(r"\\bibliography(?:style)?\s*\{[^}]*\}")

# Document-STRUCTURE / frontmatter commands that leak from a LaTeX source into
# body prose (the source builder can ingest a `\maketitle` line as a Paragraph).
# The projection OWNS this scaffolding (`\maketitle` only when a title exists,
# its own `\begin{document}`, its own bibliography), so a stray copy in the body
# is at best noise and at worst fatal (`\maketitle` with no `\title` → error).
# `\title{…}`/`\author{…}` are captured by the projector first (see
# `leaked_title`), then stripped here.
_STRUCT_CMD = re.compile(
    r"\\(?:maketitle|tableofcontents|begin\s*\{document\}|end\s*\{document\}"
    r"|appendix|newpage|clearpage|cleardoublepage|pagebreak|nopagebreak"
    r"|pagestyle\s*\{[^}]*\}|thispagestyle\s*\{[^}]*\})"
)
# frontmatter commands whose ARGUMENT can carry NESTED braces
# (`\title{{\large\NoCaseChange{…}}}`) — a plain `\{[^}]*\}` strips only to the
# FIRST `}` and leaves a `}}` orphan in the prose. Removed brace-balanced instead.
_BALANCED_STRIP_CMDS = ("title", "author", "date", "institute", "institution",
                        "affiliation", "affil", "thanks")
# a leaked `\title{…}` — captured so a title-less model still gets one.
_TITLE_CMD = re.compile(r"\\title\s*\{([^}]*)\}")


def _strip_balanced_command(text: str, cmd: str) -> str:
    """Remove every `\\<cmd>{ … }` from `text`, honouring NESTED braces (so
    `\\title{{\\large X{y}}}` is removed whole, not up to the first `}`)."""
    out, i, n, tok = [], 0, len(text), "\\" + cmd
    while i < n:
        j = text.find(tok, i)
        if j == -1:
            out.append(text[i:]); break
        # not a longer command sharing the prefix (\titleformat vs \title)
        k = j + len(tok)
        if k < n and text[k].isalpha():
            out.append(text[i:k]); i = k; continue
        out.append(text[i:j])
        while k < n and text[k] in " \t":
            k += 1
        if k < n and text[k] == "{":              # brace-balanced arg → drop it
            depth = 0
            while k < n:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        k += 1; break
                k += 1
            i = k                                 # arg consumed
        else:
            i = k                                 # no arg — drop the bare command
    return "".join(out)


def leaked_title(text: str) -> str | None:
    """A `\\title{…}` the source builder left in body prose (title-less model)."""
    m = _TITLE_CMD.search(text or "")
    return m.group(1).strip() if m and m.group(1).strip() else None


# every natbib / biblatex cite variant → plain `\cite` (the projection's
# bibliography is a numeric `thebibliography`, and the default preamble does NOT
# load natbib, so `\citep`/`\citet`/`\parencite`/… would be UNDEFINED). Optional
# `[pre]`/`[post]` args are dropped; the `{keys}` are kept.
_CITE_CMD = re.compile(
    r"\\(?:[Cc]ite(?:t|p|al[tp]|author|year(?:par)?|num)?|parencite|textcite"
    r"|autocite|smartcite|footcite|supercite)\*?\s*(?:\[[^\]]*\]){0,2}\s*(\{[^}]*\})")


def normalize_cite_commands(text: str) -> str:
    """Rewrite `\\citep[..]{k}` / `\\citet{k}` / `\\parencite{k}` / … → `\\cite{k}`."""
    return _CITE_CMD.sub(lambda m: "\\cite" + m.group(1), text)


# inline math spans to PROTECT from prose-special escaping (subscripts, `&`
# alignment inside `$…$` must survive).
_MATH_SPAN = re.compile(r"(\$\$.*?\$\$|\\\[.*?\\\]|\$[^$]*\$|\\\(.*?\\\))", re.DOTALL)


#: What each text-mode special becomes. `^` and `~` do NOT take a bare
#: backslash: `\\^` is the circumflex ACCENT and wants an argument, so `x\\^2`
#: sets a circumflex over the 2 or fails outright.
_PROSE_ESCAPES = {"#": "\\#", "%": "\\%", "&": "\\&", "_": "\\_",
                  "^": "\\textasciicircum{}", "~": "\\textasciitilde{}"}
_PROSE_SPECIALS = re.compile(r"(?<!\\)([#%&_^~])")

#: T-0156 — A C STRING ESCAPE IS NOT A CONTROL SEQUENCE.
#:
#: `\n` has no meaning in LaTeX at all, so a `\n` in prose is the two
#: characters the PAGE DRAWS. 2507.21892v1 is a paper about model reasoning
#: and its figures print verbatim transcripts — `<think>\nTo answer the
#: question, I need to identify the director …` — which the reading carries
#: faithfully and the projector emitted unescaped. All 43 of that document's
#: errors were this, every one "Undefined control sequence": `\n` x34,
#: `\nTo` x4, `\nThe` x3, `\nFrom` x2, the glued forms being `\n` followed by
#: the next word.
#:
#: THE NEGATIVE LOOKAHEAD IS THE WHOLE RULE. Every real LaTeX command
#: beginning with `n` continues in lowercase, so measured over the eight
#: T-0156 e-prints the commands actually used — `\nabla`, `\ne`, `\neg`,
#: `\neq`, `\newtheorem`, `\nobreak`, `\node`, `\not`, `\notin`, `\npar`,
#: `\nu` — are untouched, including the two `\nabla` in this very document.
#: 86 occurrences matched across the eight projections and all 86 are in
#: 2507.21892v1; the other seven have none.
#:
#: `\t` AND `\r` ARE DELIBERATELY NOT HERE. Both are real LaTeX accents —
#: `\t{oo}` is the tie, `\r{a}` the ring — so the argument that makes `\n`
#: unambiguous does not reach them, and guessing would cost a character the
#: author wrote.
#:
#: NOT A GENERAL BACKSLASH ESCAPE, and that is on purpose. Prose here carries
#: the model's own inline LaTeX (`\cite{…}`, `\(…\)`, `\emph{…}`), which is
#: why `{ } $ \` are exempt above and why 24.5% of table cells hold `\(…\)`
#: (see `_cell_tex`). Escaping every backslash would turn every citation into
#: literal text. An UNDEFINED AUTHOR MACRO is also left alone on purpose: the
#: answer to `\gameval` is to emit the author's preamble that defines it
#: (T-0156 class B), and escaping it here would hide the error that class B's
#: gate measures rather than fix it.
_STRING_ESCAPE_N = re.compile(r"\\n(?![a-z])")


#: T-0156 — A NAME IS NOT PROSE.
#:
#: `escape_prose_specials` escapes `_` wherever it stands, and 822 gives the
#: measured reason: prose holds CODE IDENTIFIERS (`read_inc`,
#: `all_less_than`), and a bare `_` there is "Missing $ inserted" whatever we
#: do. But a reference or a citation standing in prose has its ARGUMENT
#: escaped with it, and an escaped name is a DIFFERENT name:
#:
#:     \label{main_algo}     emitted unescaped, from the object's prop
#:     \cref{main\_algo}     escaped, because it stood in prose
#:
#: Measured on arxiv.2402.03975: 89 distinct citation keys against 89
#: `\bibitem`s. 23 of the keys carry an escaped underscore and NOT ONE of them
#: matches a bibitem; all 23 match once unescaped. Of the 66 keys without one,
#: 65 match. So the escaping is the only systematic citation failure on that
#: document, and it breaks 26% of its bibliography — the owner's third
#: requirement is that every in-text citation resolves to its entry.
#:
#: Plus two references: `\cref{main\_algo}` and `\cref{conditioned\_discount}`
#: against `\label{main_algo}` and `\label{conditioned_discount}`.
#:
#: THE EXPOSURE IS WIDER THAN THE EIGHT. Across 2,731 library source documents,
#: 95,184 of 723,939 reference and label arguments (13%) hold an underscore in
#: the name, in 1,250 documents (46%); and 7% of citation keys do. Only 25
#: arguments bite today because so few references survive into prose at all
#: (33 of 590) — which is why this is fixed BEFORE class F promotes 115 more,
#: not after.
#:
#: Same family as the citation placed inside a maths span: a prose rule
#: reaching into a command's argument.
_NAME_ARG = re.compile(
    r"\\(?:label|ref|eqref|autoref|cref|Cref|labelcref|pageref|vref|nameref"
    r"|cite|citep|citet|citeauthor|citeyear|citealp|citealt|nocite|bibitem)"
    r"\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}")


#: T-0156 — A REFERENCE IS A COMMAND WHEN ITS TARGET EXISTS, AND TEXT OTHERWISE.
#:
#: `_PROSE_CLEAN` flattens `\ref{tab:x}` to `(tab:x)`, keeping the target as
#: text. Promoting those back is the owner's fifth requirement, but only where
#: the label is emitted: a `\ref` against a label nothing defines is
#: "Reference undefined", which his first requirement counts as a failure.
#:
#: ONE RULE, BOTH DIRECTIONS. The same test promotes and demotes, so the 18
#: cleveref commands that today point at list-item labels we do not emit
#: become text instead of dangling — and when list items arrive, their labels
#: enter the emitted set and the same rule promotes them with no change here.
#:
#: WHY THE DECISION NEEDS THE MODEL AND NOT JUST THE BODY. Measured over the
#: eight audit documents, 166 parenthesised tokens equal an emitted label and
#: 60 of them — 36% — were never a reference: `(1)` six times and `(3)`
#: nineteen times on 1503.00301 alone, against labels named "1" and "3". All
#: four documents carrying them are READING-built, with no source and so no
#: reference ever flattened. So the body is asked only "is this label
#: emitted"; the model is asked "was this span a reference", through the
#: `xrefs` prop `latex_source._flattened_xrefs` writes. On arxiv.0912.2444:
#: 109 records, 93 whose label the body emits, 0 body occurrences not backed
#: by a record, 0 numeric labels.
#:
#: Both reference systems resolve this way — LaTeXML fills one label table and
#: then writes, tex4ht lets TeX write the .aux and reads it back — because the
#: label set does not exist until the document is complete. `latex.py` emits
#: `\label{}` at seven sites and keeps no central set, which is the same fact
#: from our side.
_EMITTED_LABEL = re.compile(r"\\label\s*\{([^}]*)\}")

#: The commands a dangling reference can arrive as. `\ref` and `\eqref` the
#: projection writes itself; `\cref`/`\labelcref` reach the body from an
#: author's prose and have no definition here (see `_AUTHOR_PACKAGES`).
_EMITTED_REF = re.compile(
    r"\\(ref|eqref|autoref|cref|Cref|labelcref)\s*\{([^{}]*)\}")


#: T-0156 — THE AUTHOR'S FIGURES ARE WHERE THE AUTHOR'S SOURCE IS.
#:
#: `_DEFAULT_PREAMBLE` emits `\graphicspath{{./}{../}}`: `./` is the `latex/`
#: directory the compile runs in, `../` is the document folder, where OUR OWN
#: `report-crops/` live. That is why 2507.21892v1 compiles clean with 18
#: `\includegraphics` — its images are ours. An author's path
#: (`figures/DVS_image.png`) reaches neither, because the source is unpacked
#: at `<doc>/texsrc/`.
#:
#: AND A MISSING IMAGE IS FATAL UNDER XELATEX. xetex pipes its DVI to
#: xdvipdfmx, which aborts:
#:
#:     xdvipdfmx:fatal: Image inclusion failed. Could not find file: figures/…
#:     No output PDF file written.
#:
#: so xetex dies of the broken pipe (rc -13) with its log truncated mid-word.
#: 2102.08145 produced NO document at all for this reason, and its 34 errors
#: and 0.0% word coverage were consequences. The last line of that truncated
#: log named `\unitfrac`, which had nothing to do with it.
#:
#: MEASURED on the real .tex, one entry added:
#:
#:     plain     rc=-13   34 errors   NO pages    4 unable-to-load
#:     withsrc   rc=1     30 errors   27 pages    0 unable-to-load
#:
#: RELATIVE WHEN THE LAYOUT HOLDS. `cmd_latex` writes the .tex to
#: `<blob_dir>/latex/` and the source is unpacked under `<blob_dir>/`, so
#: `../<name>/` is correct and keeps the file portable. The condition is
#: CHECKED rather than assumed — the sibling `latex/` directory must exist —
#: and a source somewhere else gets its absolute path, because a wrong
#: relative path fails the same fatal way the missing figure did.
_GRAPHICSPATH_CMD = re.compile(r"\\graphicspath\s*\{")


def source_graphics_entry(meta, doc_dir=None) -> str:
    r"""The `{…/}` entry for the author's own figure directory, or "".

    `doc_dir` is the folder the .tex is written beside (pdfdrill passes it
    from the projector's `crops_dir` param, whose parent IS that folder).
    Without it nothing is emitted: the entry is a RELATIVE path, and a
    relative path is only correct when the source sits beside the output.
    """
    src = (meta or {}).get("latex_source_dir")
    if not src or not doc_dir:
        return ""
    try:
        d = Path(str(src))
        if not d.is_dir():
            return ""
        # THE TEST IS THE ONE THING WE KNOW EXACTLY, and it must hold AT
        # PROJECTION TIME. The first version asked whether a sibling `latex/`
        # directory existed — pdfdrill's own output directory, which
        # `cmd_latex` creates on the line AFTER `projector.project(doc)` and
        # which the audit runner removes first. So on a clean run that check
        # ALWAYS failed and the entry was never emitted; it passed only when
        # an earlier run had left `latex/` behind. It cost a wrong report: a
        # measurement I declared void for concurrency was correct, and the
        # single-document runs I "confirmed" against were the stale ones.
        #
        # `doc_dir` removes the guessing. The projector is told the folder it
        # writes beside, so the condition is an equality rather than a probe:
        # the source directory is a CHILD of that folder, hence `../<name>/`.
        if d.parent == Path(str(doc_dir)):
            return "{../%s/}" % d.name
        # NO ABSOLUTE FALLBACK, and the reason is not portability alone.
        #
        # A source directory outside the document folder is a path on THIS
        # machine, and for a library document it is a path THROUGH THE LIBRARY:
        # `1503.00301`'s source dir is `pdfdrill-library/<folder>/<sub>`, so an
        # absolute entry would write a library folder name into the projected
        # .tex — an output file. The owner's rule keeps those names out of
        # source, logs and messages, and a projection is the deliverable.
        #
        # Nothing is lost by refusing: the figures are not beside the document
        # in that case either, so the fix there is to COPY them in, which is a
        # different step with a different gate. Measured over the eight, the
        # only document whose figures were unreachable (2102.08145) has its
        # source under the document folder and gets the relative entry; the one
        # document with an outside source (1503.00301) references no author
        # figure at all, so it stays byte-identical.
        return ""
    except OSError:
        return ""


def add_source_graphicspath(preamble: str, meta, doc_dir=None) -> str:
    r"""Put the author's source directory on the graphics search path."""
    entry = source_graphics_entry(meta, doc_dir)
    if not entry or entry in preamble:
        return preamble
    m = _GRAPHICSPATH_CMD.search(preamble)
    if not m:
        return preamble.rstrip("\n") + "\n\\graphicspath{{./}{../}%s}\n" % entry
    close = _matching_brace(preamble, m.end() - 1)
    if close < 0:
        return preamble
    return preamble[:close] + entry + preamble[close:]


def _matching_brace(s: str, open_at: int) -> int:
    """Index of the `}` closing the `{` at `open_at`, or -1."""
    depth = 0
    for i in range(open_at, len(s)):
        if i and s[i - 1] == "\\":
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


#: T-0156 — A PRINTED NUMBER, OR NOTHING.
#:
#: `refnum` does not always hold a number. Over 8,854 equation refnums in the
#: library, 54 carry a LaTeX special or a backslash, and the values show what
#: they really are — a whole mis-parsed expression written into a number
#: field:
#:
#:     left7^{*}right
#:     psi=left[begin{array}{c}nu  e  u^{r} … end{array}right]
#:     mathrm{A}-mathrm{C}
#:     3 cdot 4        by Eq. 13        *        {
#:
#: As `\tag{…}` each of those prints a mis-parsed expression in the equation's
#: margin: output that compiles, renders, and is visibly wrong — and
#: `common.equation_label` strips the backslashes, so it reads as text rather
#: than as broken LaTeX. The audit's eight e-prints cannot show this: all 78
#: of their refnums are plain digits. The evidence is the library census, not
#: a board row.
#:
#: THE RULE IS MEASURED, NOT GUESSED. A first version accepted 99.0% but threw
#: away REAL compound numbers — `3.26-27 /24-25` and `3.9 /7` are printed
#: numbers with a space in them. So: every whitespace-separated token must
#: contain a digit and consist only of number-ish characters. A token with no
#: digit is not part of a number, which is what rejects `by Eq. 13` and
#: `3 cdot 4` while keeping `4a`, `3.8b`, `A.1` and `3.9 /7`.
#:
#: The upstream cause is NOT fixed here. Something writes mathematics into a
#: number field; that is a reading defect with its own cause and its own gate.
#: This keeps it out of the output and names it.
#: The characters a printed number is made of, and the longest run of letters
#: one can contain: `A.1` and `3.8b` yes, `cdot` and `mathrm` no. Spelled as
#: three properties rather than one regex, because the first regex I wrote
#: rejected `A.1`, `/7` and `3.26-27 /24-25` — all of them real.
_NUMBERISH = re.compile(r"^[A-Za-z0-9.\-/,]+$")
_LETTER_RUN = re.compile(r"[A-Za-z]{3,}")


def looks_like_a_printed_number(value: str) -> bool:
    r"""True when `value` could be the number a page prints beside a display.

    Every whitespace-separated token must hold a digit and be made only of
    number-ish characters. A token with NO DIGIT is not part of a number,
    which is what rejects `by Eq. 13` and `3 cdot 4`.
    """
    v = (value or "").strip()
    if not v or len(v) > 20:
        return False
    tokens = v.replace("(", " ").replace(")", " ").split()
    if not tokens:
        return False
    return all(_NUMBERISH.match(t) and any(c.isdigit() for c in t)
               and not _LETTER_RUN.search(t) for t in tokens)


def _body_spellings(source: str) -> "list[str]":
    """The spellings a flattened reference can carry in the rendered body.

    As recorded, and as `escape_prose_specials` writes it once it is prose.
    """
    escaped = escape_prose_specials(source)
    return [source] if escaped == source else [source, escaped]


def _xref_records(doc) -> "list[dict]":
    """Every `xrefs` record in the document, duplicates kept.

    `Document.objects` is a dict KEYED BY ID, so this iterates `.values()`.
    Iterating the mapping itself yields the id strings, which carry no
    `props`, and the function then returns nothing and changes nothing — a
    silent no-op that only the reference census could see.
    """
    objects = getattr(doc, "objects", None) or {}
    out: list[dict] = []
    for obj in (objects.values() if hasattr(objects, "values") else objects):
        props = getattr(obj, "props", None) or {}
        for rec in props.get("xrefs") or []:
            if isinstance(rec, dict) and rec.get("source") and rec.get("label"):
                out.append(rec)
    return out


def resolve_xrefs(doc, body: str) -> "tuple[str, dict]":
    r"""Promote a flattened reference whose label the body emits; demote an
    emitted reference whose label it does not.

    Returns the body and a count table for the command's own report.
    """
    labels = set(_EMITTED_LABEL.findall(body))
    counts = {"promoted": 0, "left_as_text": 0, "demoted": 0, "not_found": 0}

    # PROMOTE. At most as many substitutions as there are records, so a
    # parenthesised token the model never recorded is never touched.
    per_source: dict[str, int] = {}
    for rec in _xref_records(doc):
        if rec["label"] not in labels:
            counts["left_as_text"] += 1
            continue
        per_source[rec["source"]] = per_source.get(rec["source"], 0) + 1
    for source, allowed in per_source.items():
        label = source[1:-1]
        command = "\\ref{%s}" % label
        done = 0
        # A FLATTENED REFERENCE IS PROSE BY THE TIME IT REACHES THE BODY, so
        # `escape_prose_specials` has escaped its specials — `(a_b)` is written
        # `(a\_b)`. Looking only for the recorded spelling missed 40 of 46
        # distinct sources on arxiv.2402.03975 (105 records), every one of them
        # a label with an underscore, and every one present in escaped form.
        # The first version reported those as `not_found`, which read like lost
        # prose and was a matcher that did not know its own pipeline.
        for spelling in _body_spellings(source):
            at = body.find(spelling)
            while at >= 0 and done < allowed:
                body = body[:at] + command + body[at + len(spelling):]
                done += 1
                at = body.find(spelling, at + len(command))
            if done >= allowed:
                break
        counts["promoted"] += done
        counts["not_found"] += allowed - done

    # DEMOTE, the same test the other way round.
    def _demote(m: "re.Match") -> str:
        if m.group(2) in labels:
            return m.group(0)
        counts["demoted"] += 1
        return "(%s)" % m.group(2)

    body = _EMITTED_REF.sub(_demote, body)
    return body, counts


#: T-0156 — THE REVIEW'S COMMENTS, the half `latexdiff` cannot produce.
#:
#: The owner's sixth requirement asks for an AI peer review as tracked changes
#: AND comments. The changes come from `latexdiff` over two projections — it
#: adds no errors, measured on arxiv.0912.2444's 125-equation projection: 36
#: before, 36 after, with 35 `\DIFadd` and 46 `\DIFdel` visible in the PDF.
#: A comment is not a difference, so it is carried separately, as a note
#: attached to the OBJECT it is about.
#:
#: `\todo`, NOT `\marginpar`. The projector already emits `\marginpar` for a
#: Sidenote — the DOCUMENT'S OWN margin note, which 638 exists to preserve —
#: and a reviewer's comment set the same way would read as the author's. The
#: `todonotes` package is the standard for the other thing and says so
#: visually.
#:
#: LOADED ONLY WHEN THE BODY EMITS ONE, the same body-first order
#: `graphics_preamble` and `author_package_preamble` use and for the same
#: reason: only the body knows what it emitted.
_TODO_CMD = re.compile(r"\\todo\s*(?:\[[^\]]*\])?\s*\{")


def review_notes(obj) -> "list[str]":
    """The review comments attached to this object, in order."""
    props = getattr(obj, "props", None) or {}
    raw = props.get("review_notes")
    if isinstance(raw, str):
        raw = [raw]
    return [str(n).strip() for n in (raw or []) if str(n).strip()]


def todo_markup(obj) -> str:
    r"""`\todo{…}` for each comment on this object, or "".

    The note is prose, so it is escaped like prose; a comment holding a `%`
    would otherwise comment out the rest of the line it lands on.
    """
    out = []
    for note in review_notes(obj):
        out.append("\\todo{%s}" % escape_prose_specials(note))
    return "".join(out)


def todo_preamble(body: str) -> str:
    r"""`\usepackage{todonotes}` when the body carries a note, else ""."""
    return ("\\usepackage[textsize=footnotesize]{todonotes}"
            if _TODO_CMD.search(body or "") else "")


def escape_prose_specials(text: str) -> str:
    r"""Escape the text-mode specials in the NON-math parts of prose.

    Each is illegal in text mode and never needed literally here: a bare `%`
    comments out the rest of the line, `C#` and `R&D` error. IDEMPOTENT
    (`(?<!\)`), and math spans (`$…$`, `\(…\)`, `\[…\]`) are left untouched so
    subscripts and alignment survive. `{ } $ \` are still NOT escaped — they are
    the structure the model's inline LaTeX is made of.

    822 — `_` WAS ON THAT EXEMPT LIST AND SHOULD NOT HAVE BEEN. The reasoning
    was that it "carries the model's inline LaTeX", but a subscript outside a
    math span is already an error: `_` in text mode is `Missing $ inserted`
    whatever we do, and leaving it bare loses the character too. What prose
    actually holds is CODE IDENTIFIERS — `read_inc`, `all_less_than` in
    2605.23109 — and a reader compiling that file by hand met 46 of these
    errors. Escaping turns an error into the underscore the author wrote.

    Safe in that order because `balance_math` runs FIRST: an unclosed `\(` is
    closed before this sees it, so a span meant as math is protected as math
    rather than escaped as text.
    """
    # A NAME IS NOT PROSE: the arguments of the reference and citation
    # commands are split out and put back untouched, the same way the maths
    # spans are. See `_NAME_ARG`.
    parts = _MATH_SPAN.split(text)
    for i in range(0, len(parts), 2):             # even indices = non-math text
        chunks = _NAME_ARG.split(parts[i])
        names = _NAME_ARG.findall(parts[i])
        if names:
            parts[i] = "".join(
                _escape_prose_run(c) + (names[j] if j < len(names) else "")
                for j, c in enumerate(chunks))
            continue
        # The string escape goes FIRST so the `\textbackslash{}` it inserts is
        # the one the reader sees; `_PROSE_SPECIALS` touches neither backslash
        # nor braces, so the order is free and this one reads better.
        parts[i] = _escape_prose_run(parts[i])
    return "".join(parts)


def _escape_prose_run(run: str) -> str:
    """One stretch of real prose: the string escape, then the specials."""
    run = _STRING_ESCAPE_N.sub(r"\\textbackslash{}n", run)
    return _PROSE_SPECIALS.sub(lambda m: _PROSE_ESCAPES[m.group(1)], run)


def clean_prose(text: str) -> str:
    """Normalise prose before it is emitted: expand ligatures, strip leaked
    source-LaTeX bibliography / structure commands (the projection owns those),
    and normalise natbib/biblatex cite commands to `\\cite`."""
    text = _LIG_RE.sub(lambda m: _LIGATURES[m.group(0)], text)
    text = _LEAKED_CMD.sub("", text)
    for _cmd in _BALANCED_STRIP_CMDS:         # \title{{…}}/\author{…} (nested braces)
        text = _strip_balanced_command(text, _cmd)
    text = _STRUCT_CMD.sub("", text)          # leaked \maketitle/\begin{document}/…
    text = normalize_cite_commands(text)      # \citep/\citet/… → \cite
    return text


#: inline math spans in prose: `\(…\)` and `$…$`
_MATH_SPAN_RE = re.compile(r"\\\((.*?)\\\)|(?<!\\)\$(.+?)(?<!\\)\$", re.S)


def fix_text_mode_in_math_spans(text: str) -> str:
    r"""Apply the text-mode repair INSIDE the inline math spans of prose.

    MEASURED on BH2, and it is why repairing `props['latex']` alone was not
    enough. After `sanitize_math` learned the fix, the real projection still
    stopped at line 133 on

        \(C\) durch das Zeichen \({ }^{\text {^ }}\) in der Form \(\hat{C}\)

    Exactly ONE model object carries this artifact in `props['latex']`, which
    `sanitize_math` covers. The one that broke the document carries it in a
    PARAGRAPH'S PROSE, inside an inline span — a different emission path.

    Only inside the spans. A `^` in running prose belongs to
    `escape_prose_specials`, and two passes escaping one character would
    double it.
    """
    if "\\text" not in text:
        return text

    def fix(m: "re.Match[str]") -> str:
        body = m.group(1) if m.group(1) is not None else m.group(2)
        fixed = _fix_text_mode_specials(body)
        if fixed == body:
            return m.group(0)
        return ("\\(" + fixed + "\\)") if m.group(1) is not None \
            else ("$" + fixed + "$")
    return _MATH_SPAN_RE.sub(fix, text)


def balance_math(text: str) -> str:
    """Contain a runaway: extraction sometimes drops a closing `\\)` or `$`, and an
    unclosed inline-math span then swallows everything up to the next `\\section`
    ('Not allowed in LR mode'). Balance the delimiters PER BLOCK — append the
    missing `\\)` / `$` — so a malformed span stays inside its own paragraph."""
    opens = len(re.findall(r"\\\(", text))
    closes = len(re.findall(r"\\\)", text))
    if opens > closes:
        text = text + "\\)" * (opens - closes)
    elif closes > opens:
        text = "\\(" * (closes - opens) + text
    # `$` inline math: an odd count is unbalanced (ignore `\$` escaped dollars)
    dollars = len(re.findall(r"(?<!\\)\$", text))
    if dollars % 2:
        text = text + "$"
    return text


def resolve_headings(line: str) -> str:
    """A Markdown `## X` (or a leaked heading) → `\\section{X}` at the right depth.
    Non-heading text passes through; an existing `\\section{…}` is left alone."""
    if _TEX_SECTION.match(line.strip()):
        return line
    m = _MD_HEADING.match(line)
    if not m:
        return line
    depth = len(m.group(1))
    cmd = {1: "section", 2: "section", 3: "subsection",
           4: "subsubsection", 5: "paragraph", 6: "subparagraph"}[depth]
    return f"\\{cmd}{{{m.group(2).strip()}}}"


# ── stage 1: citations (\cite map) ───────────────────────────────────────────

def reference_section_ids(doc: Document) -> set[str]:
    """Ids of every References/Bibliography Section AND the objects under it (its
    printed `[1] …` list). The projector skips these — the `thebibliography` block
    built from Reference objects replaces them, so the list is not duplicated and
    its reference LABELS `[1]` are never mangled into `\\cite`."""
    ref_secs = {
        o.id for o in doc.objects.values()
        if o.type == "Section"
        and re.search(r"\b(references|bibliography|literatur|literaturverzeichnis)\b",
                      str(o.props.get("caption", "")), re.I)
    }
    ids = set(ref_secs)
    for o in doc.objects.values():
        if o.props.get("parent_section") in ref_secs:
            ids.add(o.id)
    return ids


def reference_map(doc: Document) -> dict[int, str]:
    """`{reference number: citekey}` — rewrites a numeric in-text `[N]` to the
    matching `\\cite{<citekey>}` (and the same citekey the bibliography `\\bibitem`
    uses, so they resolve)."""
    m: dict[int, str] = {}
    for o in doc.objects.values():
        if o.type != "Reference":
            continue
        num, key = o.props.get("number"), o.props.get("citekey")
        if num is not None and key:
            try:
                m[int(num)] = str(key)
            except (TypeError, ValueError):
                pass
    return m


_CITE_BRACKET = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")


def _expand_bracket_numbers(inner: str) -> "list[int] | None":
    """`"11"` → [11]; `"11, 12"` → [11,12]; `"11-13"` → [11,12,13]. None if it
    isn't a clean numeric citation group."""
    nums: list[int] = []
    for part in re.split(r"\s*,\s*", inner.strip()):
        rng = re.fullmatch(r"(\d+)\s*[\-–]\s*(\d+)", part)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if b < a or b - a > 50:
                return None
            nums.extend(range(a, b + 1))
        elif part.isdigit():
            nums.append(int(part))
        else:
            return None
    return nums


def resolve_citations(text: str, ref_map: dict[int, str]) -> str:
    """Rewrite a numeric in-text `[N]` / `[N, M]` / `[N-M]` to
    `\\cite{key,...}` using the reference map. A bracket whose numbers are NOT all
    references (an array index, an interval `[0,1]`) is left RAW — never a broken
    `\\cite`."""
    if not ref_map:
        return text

    def sub(m: re.Match) -> str:
        nums = _expand_bracket_numbers(m.group(1))
        if not nums or any(n not in ref_map for n in nums):
            return m.group(0)                    # not a citation — leave raw
        return "\\cite{" + ",".join(ref_map[n] for n in nums) + "}"
    return _CITE_BRACKET.sub(sub, text)


def citation_keys(doc: Document) -> list[str]:
    """The in-text citation keys, in flow order — resolved to the REFERENCE
    citekey when the Citation is numeric (so the dump matches the `\\cite` output),
    else the Citation's own key."""
    ref_map = reference_map(doc)
    cites = [o for o in doc.objects.values() if o.type == "Citation"]
    cites.sort(key=lambda o: o.props.get("flow_index", 0))
    out: list[str] = []
    for o in cites:
        key = str(o.props.get("citekey") or "").strip()
        num = o.props.get("number")
        if num is not None:
            try:
                key = ref_map.get(int(num), key)
            except (TypeError, ValueError):
                pass
        if key:
            out.append(key)
    return out


# ── stage 2: bibliography (\bibitem / thebibliography) ───────────────────────

def _bib_escape(s: str) -> str:
    """Escape the specials in a bibliography/glossary entry (author/title). IDEMPOTENT:
    only an UNescaped special is escaped (`(?<!\\)`), so an entry that already
    carries `\\&`/`\\_` from the source `.bbl` is not double-escaped into `\\\\&`.
    Leaves `$ { } \\` for accents / math the BibTeX carries."""
    s = re.sub(r"(?<!\\)&", r"\\&", s)
    s = re.sub(r"(?<!\\)%", r"\\%", s)
    s = re.sub(r"(?<!\\)#", r"\\#", s)
    s = re.sub(r"(?<!\\)_", r"\\_", s)
    s = re.sub(r"(?<!\\)~", r"\\textasciitilde{}", s)
    return s


def _balance_braces(s: str) -> str:
    """Make `s` brace-balanced: drop a stray `}`, append `}` for each unmatched
    `{`. Escaped braces (`\\{` / `\\}`) are literals, not grouping."""
    depth, out, i, n = 0, [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n and s[i + 1] in "{}":
            out.append(s[i:i + 2]); i += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                i += 1; continue                  # drop a stray closer
            depth -= 1
        out.append(c); i += 1
    return "".join(out) + "}" * depth


# a TRUNCATED accent (`Van Merri{\` ← `{\"e}`, `Manning {\{`, `Rockt{\`): a `{\`
# whose control word is missing (followed by a space/brace/punctuation/EOF).
_BROKEN_ACCENT = re.compile(r"\{\\(?=[\s{}(),.;:]|$)")


def _sanitize_bib_body(s: str) -> str:
    """Make a heuristic/OCR bibliography body COMPILE-SAFE, from the RAW body.
    Such a body can carry a truncated accent that leaves an unbalanced brace
    (`Van Merri{\\ (2014)`), OCR forced line breaks (`\\\\`), an unescaped `&` —
    all fatal in `thebibliography` — or a dropped `\\)`/`$` closing an inline-math
    span (640-f: `Steerable Wavelet Frames and Pyramids in \\(L^` (Unser16), the
    one remaining compile error on Steerable — 'Missing { inserted' on the
    NEXT `\\bibitem`, because the runaway span swallowed it). Order matters:
    collapse the `\\\\` breaks and drop the broken accent FIRST, THEN escape
    specials (so a collapsed `\\\\&` becomes ` &` → `\\&`, never a bare `&`),
    THEN balance math (every OTHER paragraph is routed through
    `balance_math` in `_prose`; a `\\bibitem` body is prose too and was the
    one block that skipped it), then balance braces."""
    s = s.replace("\\\\", " ")                    # OCR forced line breaks first
    s = _BROKEN_ACCENT.sub("", s)                 # truncated `{\` accent → drop
    s = _bib_escape(s)                            # escape unescaped &/%/#/_/~
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    s = balance_math(s)                           # 640-f: a runaway `\(`/`$`
    return _balance_braces(s)


#: T-0156 — THE LINK THE READER CAN FOLLOW, from the record we already hold.
#:
#: The owner's third requirement asks for the reference's download link, and
#: the model has it: of 256 References across the eight audit e-prints, 89
#: carry a full `bibtex` record and 41 of those hold a DOI, 2 a url, 2 an
#: eprint. None of it reached the page — 256 printed entries carried no link
#: of any kind and both compiled PDFs held ZERO external URI annotations.
#:
#: `\url`, NOT `\href{…}{doi:…}`, and the difference was measured rather than
#: reasoned. Adding `\href{https://doi.org/X}{doi:X}` to 40 entries of
#: arxiv.2402.03975 took its errors 43 -> 55: a DOI like
#: `10.1007/978-3-642-22006-7_13` puts an underscore in the DISPLAYED text and
#: every one is "Missing $ inserted". `\url` handles the specials by catcode,
#: and the same 40 entries give 40 links with the error count UNCHANGED.
#:
#: The .bib is NOT the mechanism and is not replaced: `_bibitem`'s own reason
#: stands — a `.bib` needs a two-pass bibtex compile, so the self-contained
#: `thebibliography` is the default. This adds the link to the printed entry.
_BIB_DOI = re.compile(r"(?i)\bdoi\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]")
_BIB_URL = re.compile(r"(?i)\burl\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]")
_BIB_EPRINT = re.compile(r"(?i)\beprint\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]")


def reference_link(ref) -> str:
    r"""`\url{…}` for a Reference that carries one, else "".

    DOI first (it is the citable identifier), then an explicit url, then an
    arXiv eprint. A STUB carries nothing and gets nothing: its entry stays the
    visible `[unresolved: key]` that `_bibitem` prints, because a stub with a
    link would read as a resolved entry.
    """
    props = getattr(ref, "props", None) or {}
    if props.get("stub"):
        return ""
    record = str(props.get("bibtex") or "")
    if not record:
        return ""
    m = _BIB_DOI.search(record)
    if m:
        doi = m.group(1).strip().rstrip(".,;")
        if doi:
            return "\\url{https://doi.org/%s}" % doi
    m = _BIB_URL.search(record)
    if m:
        url = m.group(1).strip().rstrip(".,;")
        if url.startswith(("http://", "https://")):
            return "\\url{%s}" % url
    m = _BIB_EPRINT.search(record)
    if m:
        eprint = m.group(1).strip().rstrip(".,;")
        if eprint:
            return "\\url{https://arxiv.org/abs/%s}" % eprint
    return ""


def _bibitem(ref) -> str:
    """A `\\bibitem` for one Reference. ALWAYS emitted (even for a ref carrying full
    `bibtex`): a `.bib` needs a 2-pass bibtex compile, so the self-contained
    `thebibliography` is the default. Formatted from the structured
    author/year/title (from bibsource / the heuristic parse), else raw_text.

    639 -- a `stub` Reference (010: created for every cited key at first
    Citation, before `bibsource`/`bibliography` fills it) carries none of
    that content. It still needs a `\\bibitem` -- every `\\cite{key}` in the
    body must resolve or the document fails to compile -- so it prints with
    a VISIBLE placeholder body instead of silently falling back to the bare
    citekey, which would read as a real (if terse) entry rather than an
    unresolved one."""
    p = ref.props
    key = str(p.get("citekey") or "ref").strip()
    if p.get("stub"):
        return f"\\bibitem{{{key}}} \\textit{{[unresolved: {_sanitize_bib_body(key)}]}}"
    author = str(p.get("author") or "").strip()
    year = str(p.get("year") or "").strip()
    title = str(p.get("title") or p.get("titlefield") or "").strip()
    body = " ".join(x for x in (author, f"({year})" if year else "", title) if x) \
        or str(p.get("raw_text") or "").strip() or key
    link = reference_link(ref)
    return (f"\\bibitem{{{key}}} {_sanitize_bib_body(body)}"
            + (" " + link if link else ""))


def bibliography_block(doc: Document) -> str:
    """A `thebibliography` environment from the model's Reference objects (empty
    string when there are none). References carrying full `bibtex` are emitted to
    a `.bib` by `bib_database` instead; here we render the printed entries."""
    refs = [o for o in doc.objects.values() if o.type == "Reference"]
    refs.sort(key=lambda o: str(o.props.get("citekey") or ""))
    items = [b for b in (_bibitem(r) for r in refs) if b]
    if not items:
        return ""
    # `\bibitem` here carries NO optional [label], so labels are auto-NUMBERED
    # ([1]…[N]); the width arg must be the widest NUMBER, not a long citekey.
    widest = "9" * len(str(len(items)))
    return ("\\begin{thebibliography}{%s}\n" % widest
            + "\n".join(items) + "\n\\end{thebibliography}")


def bib_database(doc: Document) -> str:
    """The `.bib` file: every Reference that carries a full `bibtex` record."""
    out = []
    for o in doc.objects.values():
        if o.type == "Reference" and o.props.get("bibtex"):
            out.append(str(o.props["bibtex"]).strip())
    return "\n\n".join(out)


# ── graphics preamble (tikz / pgfplots / listings setup) ─────────────────────

def _balanced_block(text: str, cmd: str) -> list[str]:
    """Every `\\cmd` in `text` with ALL its consecutive `{ … }` / `[ … ]` argument
    groups (brace-balanced, may span lines / nest). Captures multi-arg commands
    whole: `\\definecolor{name}{HTML}{4A7C9B}` (3 groups), `\\usetikzlibrary{…}`
    (1), `\\pgfplotsset{…}`."""
    out, i, tok, n = [], 0, "\\" + cmd, len(text)
    while True:
        j = text.find(tok, i)
        if j == -1:
            return out
        k = j + len(tok)
        if k < n and text[k].isalpha():           # \pgfplotssetfoo ≠ \pgfplotsset
            i = k; continue
        # consume every consecutive {…}/[…] group (skipping intra-whitespace)
        while True:
            m = k
            while m < n and text[m] in " \t\n":
                m += 1
            if m >= n or text[m] not in "{[":
                break
            close = "}" if text[m] == "{" else "]"
            openc = text[m]
            depth = 0
            while m < n:
                if text[m] == openc:
                    depth += 1
                elif text[m] == close:
                    depth -= 1
                    if depth == 0:
                        m += 1; break
                m += 1
            k = m
        if k > j + len(tok):                      # at least one arg group captured
            out.append(text[j:k])
        i = k if k > j else j + len(tok)


#: T-0156 — A PACKAGE THE AUTHOR LOADED AND THE BODY STILL USES.
#:
#: Keyed by package, valued by the commands that justify loading it. Both
#: conditions are required: the author's own preamble loads the package, AND
#: the projected body emits one of its commands. The first says what the
#: command means — a bare `\interval` could be anyone's macro — and the second
#: keeps the preamble to what this document needs.
#:
#: MEASURED on arxiv.2402.03975's own projected .tex, two xelatex passes each,
#: a PDF produced in every case:
#:
#:     baseline                     131
#:     + \usepackage{interval}      112      -19, no new error class
#:     + \usepackage{cleveref}      125       -6, and a NEW class appears
#:     + both                       106
#:
#: `cleveref` IS DELIBERATELY NOT HERE, and that is the finding this table
#: exists to record. It defines `\labelcref`, which takes 46 of the document's
#: 64 undefined control sequences down to 27 — and then RUNS, resolving labels
#: the projection does not emit, so `Missing \endcsname` rises 43 -> 49 and
#: `Extra \endcsname` appears 6 times where there were none. A package can be
#: installed, load cleanly, and still make things worse by executing against
#: content we do not have. It waits for the `\label`/`\ref` work (the owner's
#: fifth requirement), not for a preamble line.
#:
#: This is a NAMED TABLE, not a rule over every `\usepackage` the author wrote:
#: emitting the author's whole package list was measured and refuted (it cost
#: arxiv.2402.03975 its PDF through `amsaddr`, which assumes an AMS document
#: class). One entry, one measurement.
_AUTHOR_PACKAGES = {"interval": (r"\interval",)}


def author_package_preamble(doc, body: str) -> str:
    r"""`\usepackage` lines for the packages in `_AUTHOR_PACKAGES` that this
    document's author loaded and whose commands the projected body emits.

    Read from the captured `standalone` preamble, which keeps the author's
    `\usepackage` lines; the body is the one this projector has just written,
    so "uses" is what was actually emitted and not what the source contained.
    """
    pre = getattr(doc, "meta", {}).get("latex_preamble")
    sa = pre.get("standalone", "") if isinstance(pre, dict) else ""
    if not sa or not body:
        return ""
    out: list[str] = []
    for pkg, commands in sorted(_AUTHOR_PACKAGES.items()):
        if not re.search(r"\\usepackage[^{]*\{[^}]*\b" + re.escape(pkg)
                         + r"\b[^}]*\}", sa):
            continue
        if not any(re.search(re.escape(c) + r"(?![A-Za-z])", body)
                   for c in commands):
            continue
        from .latex import _DEFAULT_PREAMBLE as _DP
        if re.search(r"\\usepackage[^{]*\{[^}]*\b" + re.escape(pkg) + r"\b",
                     _DP):
            continue                       # already ours
        out.append("\\usepackage{%s}" % pkg)
    return "\n".join(out)


def graphics_preamble(doc, body: str) -> str:
    """Setup lines the PROJECTED body needs but the default article preamble
    lacks — pulled from the source model's captured `standalone` preamble
    (`doc.meta['latex_preamble']['standalone']`, curated by the source builder to
    keep exactly tikz/pgfplots/definecolor/…). A projected paper whose Diagram/
    Table `latex_code` holds a `tikzpicture` / `\\addplot` / `lstlisting` would
    otherwise error 'Environment tikzpicture undefined' / '\\addplot undefined'.

    Only the setup the body ACTUALLY uses is injected (packages gated on the body;
    `\\definecolor`/`\\usetikzlibrary`/`\\pgfplotsset`/`\\tikzset`/`\\lstset` always
    carried when a tikz/pgfplots/listings need is present, since a diagram may
    reference a named colour/library/style)."""
    pre = getattr(doc, "meta", {}).get("latex_preamble")
    sa = pre.get("standalone", "") if isinstance(pre, dict) else ""
    if not sa:
        return ""
    needs_tikz = "\\begin{tikzpicture}" in body or "\\tikz" in body
    needs_pgf = "\\addplot" in body or "\\begin{axis}" in body \
        or "\\begin{semilogxaxis}" in body or "\\begin{loglogaxis}" in body
    needs_lst = "\\begin{lstlisting}" in body or "\\lstinline" in body
    if not (needs_tikz or needs_pgf or needs_lst):
        return ""

    lines: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip()
        if s and s not in seen:
            seen.add(s); lines.append(s)

    # package loads (gated by need; pgfplots pulls tikz in)
    if needs_tikz or needs_pgf:
        add("\\usepackage{tikz}")
    if needs_pgf:
        add("\\usepackage{pgfplots}")
    if needs_lst:
        add("\\usepackage{listings}")
    # setup blocks from the source preamble (only when a graphics need exists)
    if needs_tikz or needs_pgf:
        for cmd in ("usetikzlibrary", "pgfplotsset", "tikzset", "definecolor",
                    "tikzstyle"):
            for blk in _balanced_block(sa, cmd):
                add(" ".join(blk.split()))         # collapse multi-line to one
    if needs_lst:
        for cmd in ("lstset", "lstdefinestyle", "definecolor"):
            for blk in _balanced_block(sa, cmd):
                add(" ".join(blk.split()))
    return "\n".join(lines)


# ── driver: run + dump the stages ────────────────────────────────────────────

def run_stages(doc: Document, bibkey: str = "DOC") -> dict:
    """Every stage's inspectable data, keyed by dump-filename stem. Stage 0 is the
    readarray formula array — the `.dat` (one formula per line) AND the
    `{title: index}` map — plus the citation list and the bibliography."""
    from . import footnotes as _fn                     # local: avoid a cycle
    from . import citations as _cit                    # local: avoid a cycle
    order, title_index = formula_array(doc)
    return {
        "00-formulas.dat": "\n".join(order),          # the readarray data file
        "00-formula-index": title_index,               # title → 1-based index
        "01-citations": citation_keys(doc),
        "02-bibliography": bibliography_block(doc),
        "02-bib-database": bib_database(doc),
        # 638 — which running-text marker took which Footnote body, with the
        # page each side was on and whether the pairing needed the order
        # tie-break. The one place the disambiguation is inspectable.
        "03-footnotes": _fn.resolve(doc).table(),
        # 642 — which citation GROUP became which `\cite`, with the exact source
        # substring it replaced. The one place the group substitution is
        # inspectable, and the counts that say what did NOT become a `\cite`.
        "04-citations": _cit.resolve(doc).table(),
    }


def dump_stages(stages: dict, out_dir: Path) -> list[Path]:
    """Write each stage to an inspectable file (`.json` for data maps, `.dat`/
    `.bib`/`.tex` for text). Returns the written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, data in stages.items():
        if isinstance(data, (dict, list)):
            p = out_dir / f"{name}.json"
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            p = out_dir / (name if "." in name else f"{name}.bib" if "bib" in name
                           else f"{name}.tex")
            p.write_text(str(data), encoding="utf-8")
        written.append(p)
    return written


# ── stage 3: acronyms / glossary (from the named-concept layer) ──────────────

def glossary_block(records) -> str:
    """An `Acronyms` section as a `description` list (single-pass — no
    `makeglossaries`). `records` is `[(name, expansion), …]` from the concept
    layer; empty → empty string."""
    items = [(str(n).strip(), str(e).strip()) for n, e in records
             if str(n).strip() and str(e).strip()]
    if not items:
        return ""
    lines = ["\\section*{Acronyms}", "\\begin{description}"]
    for name, exp in items:
        lines.append(f"  \\item[{_bib_escape(name)}] {_bib_escape(exp)}")
    lines.append("\\end{description}")
    return "\n".join(lines)
