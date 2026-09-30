"""project_mmd — project the docmodel to Mathpix-compatible Markdown / LaTeX.

Three things this adds over `docmodel.to_markdown`:

1. CROP LINKS in Mathpix's exact CDN syntax, so a region we cannot turn into
   LaTeX is still *visible* in any Markdown editor instead of being an HTML
   comment nobody renders:

       ![](https://cdn.mathpix.com/cropped/<id>g-<page>.jpg?height=H&width=W&top_left_y=Y&top_left_x=X)

   Verified against a real Mathpix `tex.zip`: its bundled crops are named
   `<uuid>-<page:03d>_<height>_<width>_<top_left_y>_<top_left_x>.jpg`, and page
   25's diagram file `025_885_748_204_592` matches that page's lines.json
   region h=885 w=748 y=204 x=592. Query-param order is the same.

   LaTeX uses the same URL inside \\includegraphics, as Mathpix does.

2. PAGE SEPARATORS, because Markdown and pdftotext both emit them when asked.

3. FONT / HEADING documentation. Headings are not tagged in a PDF; they are
   inferred from type size and weight relative to the page's body text, and the
   evidence is emitted so the inference can be audited rather than trusted.

COORDINATES. The docmodel works in PDF points with y increasing UPWARD. Mathpix
regions are page-image pixels with y increasing DOWNWARD from the top-left. The
conversion is done once, here, in `crop_url`.
"""
from __future__ import annotations

import os
import collections
import re
from dataclasses import dataclass

import docmodel_six as docmodel
import listings
import structure
import texmap
from docmodel_six import GlyphNode, LineNode, PageNode

# Shared with `docmodel.to_lines_json`, deliberately: a crop URL and the
# lines.json written by the same run must be in ONE coordinate space, or a
# server handed both rescales every rectangle off the page.
DEFAULT_PX_PER_PT = docmodel.PX_PER_PT


def crop_url(rect, page: PageNode, doc_id: str, base: str,
             px_per_pt: float = DEFAULT_PX_PER_PT) -> str:
    """A Mathpix-syntax crop URL for a rect given in PDF points (y up)."""
    x0, y0, x1, y1 = rect
    page_top = page.rect[3]
    left = int(round(x0 * px_per_pt))
    top = int(round((page_top - y1) * px_per_pt))
    width = max(1, int(round((x1 - x0) * px_per_pt)))
    height = max(1, int(round((y1 - y0) * px_per_pt)))
    return (f"{base.rstrip('/')}/cropped/{doc_id}g-{page.page}.jpg"
            f"?height={height}&width={width}"
            f"&top_left_y={top}&top_left_x={left}")


# ------------------------------------------------------------------ headings
@dataclass
class FontProfile:
    """The type sizes a document actually uses, measured not assumed."""
    body_size: float
    body_font: str
    sizes: collections.Counter
    fonts: collections.Counter

    # Above this ratio, size alone settles it: nothing that much larger than
    # body text is ordinary prose.
    CLEARLY_LARGER = 1.35

    def rank(self, size: float) -> int:
        """0 = body or smaller; 1,2,3 = progressively larger heading levels."""
        if size <= self.body_size * 1.08:
            return 0
        if size <= self.body_size * 1.25:
            return 1
        if size <= self.body_size * 1.6:
            return 2
        return 3

    def clearly_larger(self, size: float) -> bool:
        return size > self.body_size * self.CLEARLY_LARGER


def profile(pages: list[PageNode]) -> FontProfile:
    sizes: collections.Counter = collections.Counter()
    fonts: collections.Counter = collections.Counter()
    for p in pages:
        for ln in p.lines:
            for g in ln.glyphs:
                if g.is_math:
                    continue
                sizes[round(g.size, 1)] += 1
                fonts[g.fontname.split("+")[-1]] += 1
    if not sizes:
        return FontProfile(0.0, "", sizes, fonts)
    # Body text is the size MOST glyphs are set in, not the smallest: footnotes
    # and captions are smaller, and a document may have more of them than one
    # might guess.
    body_size = sizes.most_common(1)[0][0]
    body_font = fonts.most_common(1)[0][0] if fonts else ""
    return FontProfile(body_size, body_font, sizes, fonts)


# TeX font names do not contain the word "bold". Computer Modern's bold is
# CMBX ("bold extended"), so matching only on "bold" loses every heading in
# every Computer Modern document -- measured: 4 headings found where MathPix
# found 17, because `CMBX12` did not look bold.
#: The font-family tests live in `texmap` with `is_italic` and
#: `is_monospace`; this name stays because `structure` imports it.
_is_bold = texmap.is_bold


def _line_is_bold(lines) -> bool:
    """Is this heading candidate set in a bold TEXT face?

    Judged on the text glyphs only. A heading containing mathematics carries
    the maths font too -- `Exceptional Lie group $G_2$` is CMBX12 plus CMMI12
    -- and requiring every font on the line to be bold rejects exactly the
    headings that have maths in them.
    """
    fonts = {g.fontname.split("+")[-1]
             for l in lines for g in l.glyphs if not g.is_math}
    return bool(fonts) and all(_is_bold(f) for f in fonts)


def line_size(ln: LineNode) -> float:
    vis = [g for g in ln.glyphs if not g.is_math]
    return max((g.size for g in vis), default=0.0)


def heading_level(ln: LineNode, fp: FontProfile) -> int:
    """Markdown heading level for a line, or 0 for body text.

    A heading is larger than body text, or bold and short. Length matters
    because a bold run inside a paragraph is emphasis, not a heading.
    """
    # A heading may contain mathematics -- `The Groups Pin(n) and Spin(n)` is a
    # section title. Requiring type == "text" silently demoted every such
    # heading to body text.
    if not ln.glyphs or ln.rotated:
        return 0
    size = line_size(ln)
    if size <= 0:
        return 0
    rank = fp.rank(size)
    text = docmodel._run_text(ln.glyphs).strip()
    bold = _line_is_bold([ln])

    # A heading is a PHRASE. One or two characters in a bold face is a chart
    # label, a page number or an axis tick -- measured: a bold `m` and `n`
    # from inside a bar chart became `### m` and `### n`, and five single
    # digits elsewhere did the same.
    if len(text.strip()) < 3 or not any(c.isalpha() for c in text):
        return 0

    if rank == 0:
        # 814 — AT BODY SIZE, BOLDNESS IS THE ONLY EVIDENCE, and a sentence
        # ending is evidence against. This branch reads a bold line no larger
        # than the prose around it as a heading; a bold SENTENCE inside a
        # callout box satisfies it exactly. Measured on 2609.26891 p2, where
        # three lines of a bold aside became headings — `it's called — by the
        # LLM in a Python REPL.`, `able in the REPL.` A heading is a label and
        # does not end in a full stop. Only this weakest branch is guarded: a
        # line that is CLEARLY LARGER than the body is a heading whatever its
        # punctuation.
        if bold and 0 < len(text) <= 80 and not text.rstrip().endswith("."):
            return 3
        return 0
    if len(text) > 120:
        return 0          # a large-type paragraph is not a heading

    # Between body size and CLEARLY_LARGER, size is not enough on its own.
    # A LaTeX title page sets the author block a step above body size in plain
    # roman -- `Jean Gallier`, `University of Pennsylvania`, the postal address
    # -- and calling those headings turns an address into six section titles.
    # A real section heading at that ratio is bold (measured: every heading in
    # a Springer maths book, 12pt bold against 10pt body). Above the ratio,
    # boldness stops mattering: a 20.7pt roman article title is still a title.
    if not bold and not fp.clearly_larger(size):
        return 0
    return {1: 3, 2: 2, 3: 1}[rank]


#: A run-in heading is separated from the prose that follows it by LaTeX's
#: `\paragraph` space — 1 em. Measured on 2510.04618 p7-p9: the separator is
#: 9.96-10.21pt at a 10.0pt body size (1.00 em), while the ordinary inter-glyph
#: gap on the same pages has median 2.75pt and p90 3.71pt (0.37 em). 0.6 em sits
#: in the empty band between the two populations, so the test needs no absolute
#: constant — it scales with the line's own font.
_RUNIN_GAP_EM = 0.6

#: Longest a run-in heading may be. `Analysis: Medical and Text-to-SQL
#: Benchmark` is 41 characters; a bold clause longer than this inside prose is
#: emphasis, which is what the existing `heading_level` cap of 80 is for too.
_RUNIN_MAX_CHARS = 60

#: Markdown level for a run-in heading. It is LaTeX's `\paragraph` — the
#: unnumbered, bold, run-in sectioning command — which `docmodel`'s header
#: module already maps to level 4.
_RUNIN_LEVEL = 4


def runin_heading(ln: LineNode, fp: "FontProfile") -> int:
    r"""Index into `ln.glyphs` where a RUN-IN HEADING ends, or 0 for none.

    814 — a heading that shares its baseline with the prose it introduces.
    `\paragraph{Analysis: Finance Benchmark}` sets the title bold, at BODY
    SIZE, and lets the text continue on the same line after a 1 em space:

        **Analysis: Finance Benchmark** As shown in Table 2, ACE delivers …

    `heading_level` cannot see it. It asks whether the LINE is bold, and this
    line is bold only at the front, so the heading was read as the first three
    words of a paragraph — in every projection, and in the docmodel, where it
    became prose. Reported by a reader of 1-s2.0-S2590118425000565-main, whose
    own headings are worse: section, subsection and run-in are all at 8.0pt
    there, separated only by weight (Bold / Italic / Bold), so SIZE RANKING
    yields one level for the whole document and the tree is flat.

    The evidence is a bold prefix at body size, a gap of at least
    `_RUNIN_GAP_EM`, and non-bold text after it. The gap is what separates a
    heading from a sentence that merely opens in bold, and it is the feature a
    reader names first: "the text ends with a larger white space".
    """
    gl = ln.glyphs
    if not gl or ln.rotated or len(gl) < 8:
        return 0
    vis = [g for g in gl if not g.is_math]
    if not vis:
        return 0
    # Body size only. A LARGER bold prefix is an ordinary heading and belongs to
    # `heading_level`, which ranks it; claiming it here would flatten it to 4.
    size = max((g.size for g in vis), default=0.0)
    if size <= 0 or fp.rank(size) != 0:
        return 0

    n = 0
    while n < len(gl) and (gl[n].is_math or _is_bold(gl[n].fontname.split("+")[-1])):
        n += 1
    # `n` may have run on through leading maths; require real bold text in it.
    if not any(not g.is_math and _is_bold(g.fontname.split("+")[-1])
               for g in gl[:n]):
        return 0
    if n == 0 or n >= len(gl):
        return 0                       # all bold: an ordinary heading, not run-in

    wg = docmodel._word_gap(gl)          # measured on the whole line, not a slice
    head = docmodel._run_text(gl[:n], wg).strip()
    rest = docmodel._run_text(gl[n:], wg).strip()
    if not (3 <= len(head) <= _RUNIN_MAX_CHARS) or not any(c.isalpha() for c in head):
        return 0
    if len(rest) < 10:
        return 0                       # a bold label with a word after it
    # A heading is not a sentence. It may end in a colon (`Analysis:`); a full
    # stop means the bold run was a sentence set in bold.
    if head.endswith("."):
        return 0
    # The remainder must be ordinary text, or this is two bold things in a row.
    if _is_bold(gl[n].fontname.split("+")[-1]):
        return 0
    if (gl[n].rect[0] - gl[n - 1].rect[2]) < _RUNIN_GAP_EM * size:
        return 0
    return n


# --------------------------------------------------------------- projections
def _merge_heading_runs(pages: list[PageNode], fp: "FontProfile"):
    """Group consecutive heading lines of the same level into one heading.

    A heading that wraps is two LineNodes and one heading: `10.2.1
    "Prolongation" of Anti-de Sitter to Black Hole` / `Solutions` must not
    become two `###`. Lines are joined only when they share a level AND sit
    within 1.5 line-heights of each other, so two unrelated headings separated
    by body text stay apart.

    HEURISTIC, and known to merge a chapter number with its title
    (`Chapter 10` + `Three-Dimensional Gravity`). That reads correctly here but
    has not been checked on other documents.
    """
    out = []
    for p in pages:
        groups: list[tuple[int, list]] = []
        for ln in p.lines:
            lvl = heading_level(ln, fp)
            if groups and groups[-1][0] == lvl and lvl:
                prev = groups[-1][1][-1]
                gap = prev.rect[1] - ln.rect[3]
                if 0 <= gap <= 1.5 * max(line_size(ln), 1.0):
                    groups[-1][1].append(ln)
                    continue
            groups.append((lvl, [ln]))
        out.append((p, groups))
    return out


def _escape_text(t: str) -> str:
    """Escape characters that would be read as Markdown or maths syntax.

    A literal `$` in prose opens a maths span and silently swallows text up to
    the next one. Measured in this corpus: a stray `$` produced an unbalanced
    `$$` that made a renderer treat 681 characters of prose as an equation.
    """
    return t.replace("\\", "\\textbackslash{}").replace("$", r"\$")


# Commands that REQUIRE a following argument. Emitting one without its brace
# makes a renderer fail outright -- KaTeX answers "Missing argument for
# \widetilde" and shows an error box where the mathematics should be. A crop
# is a worse reader experience than correct LaTeX but a far better one than a
# broken renderer, so anything that fails this check is deferred instead.
_NEEDS_ARG = re.compile(
    r"\\(widetilde|widehat|overline|underline|bar|hat|vec|tilde|check|dot|"
    r"ddot|mathbb|mathbf|mathrm|mathcal|mathfrak|mathscr|sqrt|frac|text)"
    r"\s*(?!\{)")


def is_emittable(tex: str | None) -> bool:
    """Is this LaTeX structurally safe to put in the document?"""
    if not tex or not tex.strip():
        return False
    # Depth, not counts: `a}b{` balances by count and is still malformed.
    # Escaped braces are literal characters, not grouping: `\{ x \in S \}`
    # is a set, and counting its braces as grouping rejected every set in the
    # document.
    depth = 0
    i = 0
    while i < len(tex):
        ch = tex[i]
        if ch == "\\" and i + 1 < len(tex):
            i += 2                      # skip the escaped character
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    if depth != 0:
        return False
    if _NEEDS_ARG.search(tex + " "):
        return False
    return True


# Content that carries no mathematics: delimiters, spacing, punctuation and
# grouping, with nothing between them.
_NO_CONTENT = re.compile(
    r"^(?:\\(?:left|right|bigg?[lrm]?|Bigg?[lrm]?|mid|quad|qquad|,|;|:|!|\s)"
    r"|[\s(){}\[\].,;:|]|\\[{}|])*$")


_LEFT_RIGHT = re.compile(r"\\(left|right)(?![A-Za-z])")


def balance_delims(tex: str) -> str:
    r"""Close any `\left` that has no `\right`, and vice versa.

    An unmatched `\left` is a FATAL LaTeX error, not a cosmetic one: the
    whole document stops. wzlxjtu-011 emitted

        \begin{aligned}
        \left[ \tanh\!\Bigl( \\
        \sigma_{0} = \cosh \\
        \frac{1}{4} \log [
        \end{aligned}

    -- the row opens a bracket whose partner is on another row of the page.
    (`\Bigl(` beside it is fine: the `\big` family only sizes a delimiter and
    needs no partner. `\left` is the one that pairs.)

    Since 732 a fused run is emitted as `aligned`, and `\left`/`\right` may
    not span a `\\`, so every ROW has to balance by itself -- which is what
    this is applied to.

    `\left.` and `\right.` are LaTeX's own null delimiters: they pair without
    drawing anything. Repairing this way keeps the row and says nothing that
    is not on the page, where dropping it would cost the whole display and
    guessing the missing bracket would invent one.
    """
    opened = unmatched_right = 0
    for m in _LEFT_RIGHT.finditer(tex):
        if m.group(1) == "left":
            opened += 1
        elif opened:
            opened -= 1
        else:
            unmatched_right += 1
    if unmatched_right:
        tex = "\\left. " * unmatched_right + tex
    if opened:
        tex = tex + " \\right." * opened
    return tex


def has_content(tex: str | None) -> bool:
    r"""Does this LaTeX say anything, or is it only punctuation?

    Measured on the four-column comparison: of 836 display equations pdf2mmd
    emitted across 102 documents, 202 carried three tokens or fewer and 55
    were EMPTY. The rest of that tail was `igl(`, `igr)`, `iggl[` --
    a delimiter alone, on its own line, wrapped in `$$`.

    Those are not deferrals waiting to be counted. They are wrong answers
    shipped at full confidence, and the crop metric could never see them
    because a crop is a REFUSAL and these are emissions.
    """
    if not tex or not tex.strip():
        return False
    return not _NO_CONTENT.match(tex.strip())


_EQ_TAG = re.compile(r"^\(\s*[0-9]+(?:\.[0-9]+)*\s*[a-zA-Z]?\s*\)$")


def equation_number(line, right: float) -> list:
    r"""The glyphs of a right-margin equation NUMBER, or [].

    An author's `(1)` at the right margin is a LABEL, not part of the
    expression. Absorbed into the maths it produced `L^{-1}dL \in g(1)`,
    `dL = Q + P(2)` and `= K_{0\ell i}(8)` -- readings that are wrong in a
    way no renderer can catch, because they compile.

    Three conditions together, measured on a real line: the run is a
    parenthesised number, it ENDS at the right margin (525..540 against a
    margin of 540.0), and a wide gap separates it from the mathematics
    (202pt on that line -- the trailing space of a display equation, not an
    inter-symbol gap).
    """
    gs = sorted((g for g in line.glyphs if g.text.strip()),
                key=lambda g: g.rect[0])
    if len(gs) < 3:
        return []
    # A LINE THAT IS NOTHING BUT THE NUMBER. The scan below walks back from
    # the end and stops at index 1, so it can only find a tag that has
    # mathematics before it ON THE SAME LINE. A display set on its own line
    # puts its number on a line of its own -- wzlxjtu-031 sets `(1)` at
    # x=286 with nothing else -- and that was never recognised, so it
    # reached the document as the stray text `(1)` after the equation.
    whole = "".join(g.text for g in gs).strip()
    if _EQ_TAG.match(whole) and gs[-1].rect[2] >= right - 2.0 * max(
            (g.size for g in gs), default=10.0):
        return list(gs)
    size = max(g.size for g in gs)
    for i in range(len(gs) - 1, 0, -1):
        run = gs[i:]
        if not _EQ_TAG.match("".join(g.text for g in run).strip()):
            continue
        if run[-1].rect[2] < right - 2.0 * size:
            return []                        # not at the margin
        gap = run[0].rect[0] - gs[i - 1].rect[2]
        # 739 — a number set FLUSH to the margin needs less of a gap.
        #
        # The three-em gap is the trailing space of a display equation, and a
        # wide display does not have it: wzlxjtu-068's fourth equation ends
        # `\Bigr)` at 541.5 and sets `(4)` from 551.4 to 563.0, the margin
        # exactly -- a 10.0pt gap against a 29.9pt test, so the tag was read
        # as mathematics and printed as `\Bigr)(4)`.
        #
        # What the gap rule protects against is a genuine `f(4)` at the end of
        # an expression, and there the `(` follows its function name with no
        # gap at all. So a run that ENDS ON the margin is accepted on a much
        # smaller separation; one that merely ends near it still needs three.
        # What the gap protects against is `f(1)`, a function APPLICATION, and
        # there the thing before the bracket is a NAME. `y(1)` must stay
        # mathematics however wide the gap; `\Bigr)(4)` cannot be an
        # application, because the expression has already closed.
        #
        # Gap alone cannot separate the two: wzlxjtu-068's real tag sits 10.0pt
        # (1.0 em) from the `\Bigr)` before it, while the synthetic `y(1)`
        # this file tests with sits 13pt from its `y`. The glyph before the
        # gap is what differs, and it is the thing to test.
        prev = gs[i - 1]
        applies = (prev.text or "").strip().isalpha()
        flush = run[-1].rect[2] >= right - 0.5 * size
        if gap < (0.6 * size if (flush and not applies) else 3.0 * size):
            return []                        # not separated from the maths
        return run
    return []


_OPS_CHARS = re.compile(r"[-+=<>/(){}\[\],.;:|*!'\d\s]")


def _fusable(text: str) -> bool:
    r"""Is this text piece part of the FORMULA either side of it?

    Operators, digits and punctuation are -- the display path already folds
    those. So is a LONE LETTER: a variable set in the roman font, which is how
    `= (x` came to sit between two maths spans in wzlxjtu-071 while being part
    of `\Delta_x = (x - T_{0n})^	op ...`.
    
    A WORD is not, however short. The test is that no run of letters is longer
    than one: `x` fuses, `as` does not, and prose can never be swallowed.
    """
    if not text.strip():
        return False
    rest = _OPS_CHARS.sub(" ", text)
    return all(len(w) == 1 and w.isalpha() for w in rest.split())


def _join_inline(parts: list) -> str:
    r"""Join a line's pieces, FUSING maths separated only by operators.

    One formula reaches this as several spans, because the roman font supplies
    its `=`, its parentheses, its digits and sometimes a variable. Emitted
    piece by piece, `\Delta_x = (x - T_{0n})^\top C_{0n}^{-1}(x - T_{0n})`
    came out of wzlxjtu-071 as

        $\Delta_{x}$ = (x $- \mathrm{T}_{0\mathrm{n}} )^{\top} ... $

    -- `$...$`, prose, `$...$` -- which a renderer sets in two styles and a
    reader cannot select as one expression.

    The display path already folds an operator-only run into the mathematics
    around it; this is the same rule for inline. The separator may be SEVERAL
    pieces (`=` and `(x` arrive apart), so the run between two maths spans is
    taken whole and fused only if every piece of it is fusable.
    """
    parts = [x for x in parts if x]
    out: list[str] = []
    i = 0

    def ismath(s):
        return s.startswith("$") and s.endswith("$") and len(s) > 2

    while i < len(parts):
        cur = parts[i]
        if not ismath(cur):
            out.append(cur)
            i += 1
            continue
        body = cur[1:-1].strip()
        j = i + 1
        while j < len(parts):
            k = j
            while k < len(parts) and not ismath(parts[k]):
                k += 1
            if k >= len(parts):
                break
            gap = parts[j:k]
            if gap and not all(_fusable(g) for g in gap):
                break
            body = " ".join([body] + [g.strip() for g in gap]
                            + [parts[k][1:-1].strip()])
            j = k + 1
        out.append("$%s$" % body)
        i = j
    return " ".join(out)


def _inline(tex: str | None) -> str:
    """An inline maths span, or nothing at all.

    Empty content must never be wrapped: `$` + `` + `$` is `$$`, which pairs
    with a display delimiter elsewhere and corrupts everything between.
    """
    # NOT gated on has_content, though `$\bigl($` is the same noise as
    # `$$\bigl($$`. Tried and reverted: a refused inline span becomes a
    # CROP, so gating it moved 306 crops onto the tally and the block count
    # did not change at all -- the fusion chain broke on the crop exactly as
    # it had on the inline. The right treatment is to drop the span
    # silently, which is a change to the caller, not here.
    if not is_emittable(tex):
        return ""
    # An inline span carries the same hazard as a display row and for the
    # same reason: it is a FRAGMENT of a line, so a `\left` whose partner sits
    # in the next span reaches the document alone. wzlxjtu-011 emitted a bare
    # `$\left[$`, which is a fatal error wherever it lands.
    return f"${balance_delims(tex.strip())}$"


def _left_margin(page: PageNode) -> float:
    """Where the body text block starts on the left.

    The most common left edge among lines, not the smallest: a display
    equation is indented, and taking the minimum would make the margin the
    equation's own left edge and hide every one of them.
    """
    edges = collections.Counter(
        round(ln.rect[0]) for ln in page.lines if not ln.rotated and ln.glyphs)
    return float(edges.most_common(1)[0][0]) if edges else page.rect[0]


def columns(page: PageNode) -> list:
    """The (left, right) bounds of each text column on this page.

    746 — A MARGIN IS A COLUMN'S PROPERTY, NOT A PAGE'S.
    `_left_margin` takes the mode of every line start and `_right_margin` the
    page-wide maximum, which are the same thing only on a one-column page.
    wzlxjtu-031 is two columns:

        left  column   starts  54, ends ~300   (28 lines)
        right column   starts 320, ends ~562   (24 lines)

    so the page margin came out 54 -- the LEFT column's, because it has more
    lines -- and every right-column line counted as "indented past the body
    margin" by 266pt, the test `is_display` uses to find a display equation.
    The right margin came out 562, so a LEFT-column equation number ending at
    300 was never flush to it and was read as mathematics instead of stripped.

    Columns are found by a gap in the sorted line starts wider than a line of
    text is tall; a one-column page yields one column and behaves exactly as
    before. Verified: wzlxjtu-031 and -033 give [(54,297),(317,562)], and
    -006, -014, -072 give a single column. 11 of the 102 documents are
    multi-column.

    WHAT THIS IS AND IS NOT WIRED INTO, with the numbers.
    The RIGHT bound is used for equation numbers, where it is correct and
    measured NEUTRAL -- no tag in a two-column document was being missed.
    The LEFT bound is NOT used by `is_display`, and that is a measurement,
    not an oversight:

        page-wide left   multi-column docs: 50 of 73 equations found
        per-column left  multi-column docs: 48 of 73   (wzlxjtu-031 +1,
                                                        others -3)

    `is_display` asks whether a line is indented past the body margin. With
    the page-wide margin every right-column line clears it by 266pt -- wrong
    in principle, and accidentally permissive in exactly the way a display in
    a narrow column needs, because such a display is often barely indented
    within its own column. Replacing it with the true column margin makes the
    test correct and the reading worse.
    
    What a column needs instead is a different question: not "is it indented"
    but "is it centred in its column" or "is it shorter than the column". That
    is a new criterion, not a new margin, and it is why the text layout worked
    in two columns while the equations did not.
    """
    lines = [ln for ln in page.lines if ln.glyphs and not ln.rotated]
    if not lines:
        return [(page.rect[0], page.rect[2])]
    size = max((g.size for ln in lines for g in ln.glyphs), default=10.0)
    starts = sorted(ln.rect[0] for ln in lines)
    cuts = [0]
    for i in range(1, len(starts)):
        if starts[i] - starts[i - 1] > 8.0 * size:
            cuts.append(i)
    cuts.append(len(starts))
    cols = []
    for a, b in zip(cuts, cuts[1:]):
        lo, hi = starts[a], starts[b - 1]
        mine = [ln for ln in lines if lo - 1 <= ln.rect[0] <= hi + 1]
        # A column is a BLOCK OF RUNNING TEXT, not any cluster of starts. Five
        # lines at least -- a stray equation number at x=525 on a one-column
        # page is three lines and was being called a column of its own.
        if len(mine) < 5:
            continue
        starts_c = collections.Counter(round(ln.rect[0]) for ln in mine)
        cols.append(float(starts_c.most_common(1)[0][0]))
    # A column's right edge is bounded by the NEXT column's left. Taking it
    # from the lines themselves cannot work on a mixed page: wzlxjtu-031 puts
    # a full-width section above a two-column body, so its left-column lines
    # end at 300 (17 of them) AND at 560 (42), and neither the mode nor the
    # maximum is the column's margin.
    right = max(ln.rect[2] for ln in lines)
    cols.sort()
    bounds = []
    for i, lo in enumerate(cols):
        hi = (cols[i + 1] - 2.0 * size) if i + 1 < len(cols) else right
        bounds.append((lo, hi))
    # Anything too narrow to be a text column is not one -- a run of equation
    # numbers at the right margin clusters like a column and is 15pt wide.
    page_w = page.rect[2] - page.rect[0]
    bounds = [b for b in bounds if b[1] - b[0] >= 0.20 * page_w]
    # And each column must hold a real share of the page's lines. Counting
    # start-CLUSTERS was not enough: wzlxjtu-009 put 4 lines and -052 put 2
    # in their supposed second column against 29 and 22 in the first, and
    # treating those pages as two-column cost 3 equations.
    bounds = [b for b in bounds
              if sum(1 for ln in lines if b[0] - 1 <= ln.rect[0] <= b[1] + 1)
              >= max(8, 0.15 * len(lines))]
    if not bounds:
        return [(_left_margin(page), _right_margin(page))]
    return [(bounds[0][0], right)] if len(bounds) == 1 else bounds


_CENTRED_OK = os.environ.get("PDF2MMD_CENTRED", "1") != "0"
_COLS_CACHE: dict = {}


def column_of(page: PageNode, ln: LineNode) -> tuple:
    """The (left, right) bounds of the column this line sits in."""
    ck = id(page)
    cols = _COLS_CACHE.get(ck)
    if cols is None:
        cols = _COLS_CACHE[ck] = columns(page)
    if len(cols) == 1:
        return cols[0]
    cx = 0.5 * (ln.rect[0] + ln.rect[2])
    best = min(cols, key=lambda c: 0.0 if c[0] <= cx <= c[1]
               else min(abs(cx - c[0]), abs(cx - c[1])))
    return best


def is_display(ln: LineNode, left: float,
               right: float | None = None) -> bool:
    """True if this line is a displayed equation on its own.

    Two conditions, both needed. It must be INDENTED past the body margin,
    which is what centring a display equation does; and it must carry no
    prose, since a sentence with inline maths is not a display. An equation
    number is tolerated -- `(1.4)` sits at the right margin and is not prose.
    """
    if ln.rotated or not ln.glyphs:
        return False
    size = max(g.size for g in ln.glyphs)
    # 737 — the indent threshold, as a measured constant rather than a hair.
    #
    # wzlxjtu-006's second display begins with a `V` at x=86.2 on a page whose
    # body margin is 72.0 and whose type is 12pt: indented 14.2pt against a
    # test demanding more than 14.4. It failed by a TENTH OF A POINT, and a
    # display equation that fails here is emitted as an inline `$...$` in the
    # middle of the prose -- it does not become a crop, it does not appear in
    # any equation list, it simply stops being an equation.
    #
    # Swept over the 102 documents: 1.2 -> 1.1 -> 1.0 leaves the equations
    # delivered whole (41), the dialect-correct count (60) and the crops (418)
    # all unchanged, and recovers 5 display blocks and 8 fractions. One quad
    # of indent is the weakest claim that still separates a display from a
    # paragraph.
    #
    # 748 — HALF A QUAD, now that the margin is the COLUMN's. A display is
    # centred, so its indent is half the slack in its line, and in a 243pt
    # revtex column that slack is small: wzlxjtu-033's right-column display
    # starts at 326.4 against a column margin of 317.0 -- indented 9.4pt
    # against a 9.96pt test. Nine lines across the four twocolumn documents
    # failed by margins of that order, and none was gained.
    #
    # Safe at 0.5 because body text sits AT its column margin, indent zero,
    # and `is_display` refuses prose regardless. Measured over the corpus
    # with the per-column margin:
    #
    #     1.0 em   59 whole   82 correct   190 fractions
    #     0.5 em   61 whole   84 correct   201 fractions
    #
    # and on the four `twocolumn` documents, 33 of 51 -> 35 of 51.
    _IND = float(os.environ.get("PDF2MMD_INDENT", "0.5"))
    if getattr(ln, "forced_display", False):
        # 734 -- claimed by the continuation row below it. The prose test
        # below still runs, so this promotes maths and never a sentence.
        pass
    elif ln.rect[0] <= left + _IND * size:
        # 747 — OR CENTRED IN ITS COLUMN, which is what a display IS.
        #
        # Indentation is a one-column proxy for centring: with a wide text
        # block, a centred equation starts well right of the margin. In a
        # 243pt revtex column it need not, and the four twocolumn documents
        # in this corpus (030-033) set every one of their 51 displays as a
        # plain `equation` (23) or `align` (28) inside a column -- no
        # `widetext`, no `strip`, no `figure*`, nothing full-width.
        #
        # Centring is measured with the equation NUMBER excluded, because the
        # tag sits at the column's right margin and would make every numbered
        # display look flush-right rather than centred.
        if _CENTRED_OK and right is not None:
            gs = [g for g in ln.glyphs if g.text.strip()]
            tag = set(map(id, equation_number(ln, right)))
            body = [g for g in gs if id(g) not in tag]
            if not body:
                return False
            x0 = min(g.rect[0] for g in body)
            x1 = max(g.rect[2] for g in body)
            lgap, rgap = x0 - left, right - x1
            # 762 -- A WIDE DISPLAY IS STILL CENTRED, with barely any gap
            # to show for it. wzlxjtu-031's eleventh equation fills its
            # 245pt column: lgap 3.70, rgap 3.69 -- as symmetric as a
            # measurement gets, and a tenth of the em this test demanded on
            # each side. It was emitted as an inline `$...$` in the middle
            # of the prose, which is the 737 failure again: not a crop, not
            # in any equation list, simply no longer an equation.
            #
            # The floor was never what separates a display from prose --
            # the prose test below does that, and refuses any line with a
            # word on it. What the floor protects against is calling a
            # flush line centred, and a flush line has one gap at zero, so
            # the SYMMETRY carries the claim. Swept over the corpus:
            #
            #     1.00 em   correct 174   matched 314   crops 231
            #     0.35 em   correct 175   matched 315   crops 231
            #     0.25 em   correct 175   matched 315   crops 231
            #     0.00 em   correct 175   matched 315   crops 231
            #
            # Flat from 0 to 0.35 and it costs an equation at 0.6, so this
            # is not a threshold being tuned to one document. 0.25 em --
            # half the indent rule above, comfortably under 031's 0.37.
            _GAP = float(os.environ.get("PDF2MMD_CENTRE_GAP", "0.25"))
            if (lgap > _GAP * size and rgap > _GAP * size
                    and abs(lgap - rgap) <= 0.5 * max(lgap, rgap)):
                pass                       # centred: it is a display
            else:
                return False
        else:
            return False
    for sp in ln.spans:
        if sp.kind != "text":
            continue
        word = docmodel._run_text(sp.glyphs).strip()
        if re.fullmatch(r"[(\[]?[\d.]+[)\]]?", word):
            continue                      # an equation number
        if len(re.findall(r"[A-Za-z]", word)) > 3:
            return False                  # prose: not a display
    return any(sp.kind == "math" for sp in ln.spans)


def _right_margin(page: PageNode) -> float:
    """Where the body text block ends on the right.

    Taken as the largest right edge among full-width text lines, which is the
    measure a line has to fall short of to have ended its paragraph.
    """
    edges = [ln.rect[2] for ln in page.lines
             if not ln.rotated and ln.glyphs]
    return max(edges) if edges else page.rect[2]





def _link_at(page: PageNode, rect) -> "docmodel.LinkNode | None":
    """The link annotation covering this span, if any."""
    cx = 0.5 * (rect[0] + rect[2])
    cy = 0.5 * (rect[1] + rect[3])
    for ln in page.links:
        if ln.rect[0] <= cx <= ln.rect[2] and ln.rect[1] <= cy <= ln.rect[3]:
            return ln
    return None



def _link_target(link) -> str | None:
    if link is None:
        return None
    if link.uri:
        return link.uri
    if link.dest:
        return "#" + link.dest
    return None


def _linked_text(span, page: PageNode, word_gap: float) -> str:
    """The span's text, with the part a link COVERS wrapped.

    Only the glyphs inside the annotation rectangle are wrapped. Testing the
    span's centre instead swept up whatever shared the run: a footnote marker
    became part of its URL, `[1http://tiramisu-compiler.org/]`, and a trailing
    comma landed inside the citation, `[[39],]`.

    A citation carries the author's own BibTeX key, so `[22]` becomes
    `[[22]](#cite.polly)` -- the key survives into the Markdown instead of
    being discarded with the annotation.
    """
    glyphs = sorted(span.glyphs, key=lambda g: g.rect[0])
    if not glyphs:
        return ""

    def covering(g):
        if not page.links:
            return None
        cx = 0.5 * (g.rect[0] + g.rect[2])
        cy = 0.5 * (g.rect[1] + g.rect[3])
        for ln in page.links:
            if (ln.rect[0] <= cx <= ln.rect[2]
                    and ln.rect[1] <= cy <= ln.rect[3]):
                return ln
        return None

    # A RAISED, script-size glyph with no base is a marker -- a footnote
    # reference, not an exponent. Measured: size 5.98 against a 7.97 line and
    # a baseline 2.81pt higher, with a NORMAL advance (2.989) and a 0.50pt gap
    # to the next glyph. There is no missing space to restore: the PDF has
    # none, and the right rendering is a superscript.
    size = span.line_size or max(g.size for g in glyphs)
    bases = [g.baseline for g in glyphs]
    line_base = max(set(bases), key=bases.count)

    def raised(g) -> bool:
        return (g.size <= 0.85 * size
                and g.baseline >= line_base + 0.15 * size)

    # A marker is ISOLATED. Several raised runs alternating with ordinary
    # glyphs is not a row of footnote references -- it is two text blocks at
    # different baselines that were merged into one row, and wrapping each
    # fragment produces `L<sup>H</sup>e<sup>i</sup>v<sup>g</sup>`. Marking
    # none of them keeps the damage visible as plain text instead of dressing
    # it up.
    runs_up = 0
    prev_up = False
    for g in glyphs:
        up = raised(g)
        if up and not prev_up:
            runs_up += 1
        prev_up = up
    if runs_up > 2:
        def raised(g) -> bool:      # noqa: F811 - deliberate override
            return False

    out: list[str] = []
    run: list = []
    run_key = None

    def flush():
        if not run:
            return
        text = _escape_text(docmodel._run_text(run, word_gap))
        link, is_up = run_key
        if is_up and text.strip():
            text = f"<sup>{text}</sup>"
        target = _link_target(link)
        out.append(f"[{text}]({target})" if target and text.strip() else text)
        run.clear()

    for g in glyphs:
        key = (covering(g), raised(g))
        if run_key is None or key != run_key:
            flush()
            run_key = key
        run.append(g)
    flush()
    return "".join(out)


def _mostly_inside(rect, boxes, frac: float = 0.7) -> bool:
    """Is this span mostly covered by one of the crop rectangles?

    Centre-in-box was too coarse: a small crop of a stray radical overlapped
    the word `only` enough to contain its centre, and the word vanished from
    the prose. A span is part of a picture only if the picture really covers
    it.
    """
    w = max(rect[2] - rect[0], 0.01)
    h = max(rect[3] - rect[1], 0.01)
    area = w * h
    for b in boxes:
        ox = min(rect[2], b[2]) - max(rect[0], b[0])
        oy = min(rect[3], b[3]) - max(rect[1], b[1])
        if ox > 0 and oy > 0 and (ox * oy) / area >= frac:
            return True
    return False


def _crop_clusters(page: PageNode):
    """Merge deferred rectangles that OVERLAP into one crop each.

    A matrix is one object drawn as several baseline rows inside built-up
    fences. Each row defers separately, and because the tall fence glyphs
    belong to every row's rectangle the crops overlap on the page -- four
    stacked images for one `\\begin{array}`. Overlapping rectangles are one
    region: the first span in reading order carries the merged crop and the
    rest emit nothing.

    Returns {span_id: rect} for the carriers and {span_id: None} for the rest.
    """
    spans = [sp for ln in page.lines for sp in ln.spans
             if sp.kind == "math" and docmodel.span_latex(sp) is None]
    if len(spans) < 2:
        return {sp.id: sp.rect for sp in spans}

    boxes = {sp.id: list(sp.rect) for sp in spans}
    order = sorted(spans, key=lambda s: (-s.rect[3], s.rect[0]))
    parent = {sp.id: sp.id for sp in spans}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    changed = True
    while changed:
        changed = False
        ids = list({find(sp.id) for sp in spans})
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = boxes[ids[i]], boxes[ids[j]]
                if (a[0] < b[2] and b[0] < a[2]
                        and a[1] < b[3] and b[1] < a[3]):
                    ra, rb = find(ids[i]), find(ids[j])
                    parent[rb] = ra
                    boxes[ra] = [min(a[0], b[0]), min(a[1], b[1]),
                                 max(a[2], b[2]), max(a[3], b[3])]
                    changed = True
                    break
            if changed:
                break

    out: dict = {}
    seen: set = set()
    for sp in order:
        root = find(sp.id)
        if root in seen:
            out[sp.id] = None
        else:
            seen.add(root)
            out[sp.id] = tuple(boxes[root])
    return out



# `[^\W\d_]` is "any Unicode letter". Spelling the class out as A-Za-zÀ-ÿ
# missed the LIGATURES a typesetter emits as single glyphs -- `difﬁ-cult`
# breaks after U+FB01, and 31 such words stayed broken.
_LETTER = r"[^\W\d_]"
_HYPHEN_END = re.compile(rf"({_LETTER}{{2,}})[-\u00ad]$")
_WORD_START = re.compile(rf"^({_LETTER}+)([^\w].*)?$", re.S)


def dehyphenate(text: str, vocabulary: set[str] | None = None) -> str:
    """Rejoin words broken across a line by the typesetter's hyphen.

    `sci-\nentific` is one word; the hyphen belongs to the line break, not to
    the word. Measured against pdftotext on one paper: 138 words left broken
    here, 0 there.

    A hyphen at a line end is ambiguous -- `well-\nknown` keeps its hyphen.
    The evidence that settles it is whether the document uses the HYPHENATED
    form elsewhere, mid-line, where no line break forced it: `top-left` and
    `web-based` do, `compara-ble` and `iden-tify` do not.

    Requiring evidence for the JOINED form instead was the wrong way round
    and left 45 real breaks standing -- in a six-page paper a word often
    appears exactly once, in the sentence where it happened to be broken.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    carry: str | None = None
    while i < len(lines):
        # A join can produce a line that ITSELF ends in a hyphen, because the
        # line it absorbed ended in one. Appending straight away left those
        # unexamined, so a second pass over the output found more work.
        cur = carry if carry is not None else lines[i]
        carry = None
        m = _HYPHEN_END.search(cur.rstrip())
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        n = _WORD_START.match(nxt.strip()) if m else None
        # The continuation must start LOWERCASE. Widening the class to any
        # Unicode letter (for ligatures) dropped that, and `end-\nNew` would
        # have joined across a sentence boundary.
        if (m and n and n.group(1)[:1].islower()
                and not cur.lstrip().startswith("```")):
            joined = m.group(1) + n.group(1)
            compound = f"{m.group(1).lower()}-{n.group(1).lower()}"
            if vocabulary is None or compound not in vocabulary:
                head = cur.rstrip()[: m.start()]
                rest = nxt.strip()[len(n.group(1)):]
                carry = head + joined + rest
                i += 1
                continue
        out.append(cur)
        i += 1
    if carry is not None:
        out.append(carry)
    return "\n".join(out)


def _vocabulary(text: str) -> set[str]:
    """Hyphenated compounds the document writes MID-LINE.

    A hyphen the typesetter inserted at a line break never appears mid-line;
    a real compound does. That is the evidence for keeping a hyphen.
    """
    flat = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return {m.group(0).lower() for m in
            re.finditer(rf"{_LETTER}{{2,}}-{_LETTER}{{2,}}", flat)
            if "\n" not in m.group(0)}


def _column_margin(page: PageNode, line, fallback: float) -> float:
    """The right edge that this line's own column justifies to.

    Taken from the lines that START at the same place: a block of running
    text shares a left edge and justifies to a common right edge, whatever
    the rest of the page does.
    """
    key = round(line.rect[0] / 12.0)
    edges = [round(ln.rect[2] / 6.0) * 6.0 for ln in page.lines
             if ln.glyphs and round(ln.rect[0] / 12.0) == key]
    if len(edges) < 3:
        return fallback
    # The MODE, not the maximum: justified text clusters at its margin, and
    # one long line -- a full-width heading sharing the same left edge --
    # would otherwise set the margin for the whole block.
    return max(set(edges), key=edges.count)


def _is_gutter_only(group, fence_size: float) -> bool:
    """Is this row nothing but a listing's line number?

    A blank line inside a listing still gets a number from the layout tool,
    so the row carries the gutter glyph and no code. Measured: the gutter is
    4.98pt roman at x=305 while the code is 7.97pt NimbusMonL -- a different
    size AND a different face.

    Treating such a row as ordinary text closes the code fence and reopens it
    on the next line, chopping one listing into three:

        ```
        1 // Declare the iterators i, j and c.
        2 Var i(0, N-2), j(0, M-2), c(0, 3);
        ```
        3
        ```
        4 Computation bx(i, j, c), by(i, j, c);
        ```

    The number is the layout tool's, not the author's -- which is why Mathpix
    drops it deliberately -- so the blank line is what belongs in the output.
    """
    glyphs = [g for ln in group for g in ln.glyphs]
    if not glyphs or len(glyphs) > 4:
        return False
    if not all(g.text.strip().isdigit() for g in glyphs if g.text.strip()):
        return False
    if any(texmap.is_monospace(g.fontname) for g in glyphs):
        return False
    return max(g.size for g in glyphs) <= 0.8 * max(fence_size, 1.0)


def _all_deferred(lines) -> bool:
    """True if this group is maths and NONE of it could be projected."""
    saw = False
    for ln in lines:
        for sp in ln.spans:
            if sp.kind == "math":
                saw = True
                if docmodel.span_latex(sp) is not None:
                    return False
            else:
                word = docmodel._run_text(sp.glyphs, sp.word_gap).strip()
                if len(re.findall(r"[A-Za-z]", word)) > 3:
                    return False      # prose: not a stranded formula
    return saw


def _fuse_deferred_blocks(groups, left: float):
    """Join consecutive unprojectable display rows into ONE block.

    A matrix is a single object drawn as several baseline rows inside built-up
    fences. Deferring each row separately produced a stack of crops that
    OVERLAP on the page -- four of them for one `\begin{array}` -- because the
    tall fence glyphs belong to every row's rectangle. One crop per matrix is
    both correct and readable.
    """
    out: list = []
    run: list = []

    def flush():
        if not run:
            return
        if len(run) == 1:
            out.append((0, run[0]))
        else:
            merged = [ln for lines in run for ln in lines]
            out.append((0, merged))
        run.clear()

    for lvl, lines in groups:
        if lvl == 0 and _all_deferred(lines) and lines \
                and min(ln.rect[0] for ln in lines) > left + 4.0:
            run.append(lines)
            continue
        flush()
        out.append((lvl, lines))
    flush()
    return out


def _strip_gutter(glyphs, fence_size: float):
    """Drop a listing's line-number glyphs from a code line.

    The number is the layout tool's, not the author's -- `lstlisting`
    generates it -- which is why Mathpix omits it. Dropping it is therefore a
    defensible default for some consumers, but it must be all or nothing: a
    listing showing SOME of its numbers is worse than one showing none.
    """
    kept = [g for g in glyphs
            if texmap.is_monospace(g.fontname)
            or g.size > 0.8 * max(fence_size, 1.0)]
    return kept or glyphs


#: 734 — A ROW THAT BEGINS WITH A BINARY OPERATOR IS A CONTINUATION.
#:
#: `is_display` judges one line at a time, and its test is INDENT. That works
#: when every row of a display is indented, and a multi-row display is not
#: obliged to be: an author who pulls the continuation left (wzlxjtu-043 sets
#: `\hspace{-0.15cm}` on it) leaves the FIRST row barely indented and the
#: SECOND row indented far more. Measured on that page, column margin 397px,
#: 12pt type:
#:
#:     eq 1   row 1 x=427 (indent 30)   row 2 x=489    both display    correct
#:     eq 2   row 1 x=409 (indent 12)   row 2 x=507    row 1 INLINE    wrong
#:     eq 3   row 1 x=409 (indent 12)   row 2 x=507    row 1 INLINE    wrong
#:
#: The head of the equation -- the part carrying `\delta_1^c(0) =`, which is
#: what names it -- was read CORRECTLY and then emitted as an inline `$...$`
#: in the middle of the prose, while its own continuation stood beside it as
#: a display. Nothing was lost; the equation was cut in half.
#:
#: The evidence that fixes it is not a threshold. A row beginning `-`, `+` or
#: `=` CANNOT BEGIN AN EQUATION: a binary operator needs a left operand, and
#: the only place that operand can be is the line above. So a recognised
#: display row that starts with one claims the line above it, provided that
#: line is maths and not prose and stands directly over it.
#:
#: Walked upward, so a display of three rows claims both.
_CONTINUATION_HEAD = set("-+=<>±∓≤≥≈≡∼⩽⩾−")


def _starts_with_binary_operator(ln: "LineNode") -> bool:
    gs = [g for g in ln.glyphs if g.text and g.text.strip()]
    if not gs:
        return False
    first = min(gs, key=lambda g: g.rect[0])
    t = first.text.strip()
    return len(t) == 1 and t in _CONTINUATION_HEAD


def _is_prose(ln: "LineNode") -> bool:
    for sp in ln.spans:
        if sp.kind != "text":
            continue
        word = docmodel._run_text(sp.glyphs).strip()
        if re.fullmatch(r"[(\[]?[\d.]+[)\]]?", word):
            continue
        if len(re.findall(r"[A-Za-z]", word)) > 3:
            return True
    return False


def absorb_equation_numbers(page: PageNode) -> int:
    r"""Join a line that is ONLY an equation number to the display it labels.

    739 -- wzlxjtu-027 sets two numbered equations one under the other:

        L3  y=387  x= 932..1123   \bar\psi_A = \psi_A^\dagger \gamma_7
        L5  y=398  x=1823..1875   (1)
        L4  y=566  x= 924..1131   (\gamma_7)^\dagger = -\gamma_7
        L6  y=572  x=1823..1875   (2)

    Each number is on its equation's own band -- 11px apart in 12pt type --
    but 700px to the right of it, so band-building kept them as separate
    lines. Everything downstream then read the page wrong in two ways at
    once:

      * L3 and L4 became ADJACENT DISPLAY LINES WITH NOTHING BETWEEN THEM,
        so the run pass fused them into a single `aligned`. Two equations
        became one.
      * the numbers survived as lines of their own. `to_markdown` drops such
        a line, so the number was LOST; `to_latex` had no such rule, so it
        emitted `(1)` and `(2)` as loose prose after the two `equation`
        environments -- the number printed twice, once by LaTeX and once as
        text.

    Rejoined here, before anything groups or emits, both follow: a display
    carrying its own number cannot be a row of the one above it, and the
    number is attached to the equation it belongs to rather than floating.

    The test is deliberately narrow -- the line must be NOTHING but a number
    by `equation_number`'s own reckoning (parenthesised, at the column's
    right margin, behind a gap), it must overlap the display's vertical
    band, and it must lie to its right.
    """
    lines = [ln for ln in page.lines if not ln.rotated and ln.glyphs]
    joined = 0
    for tagln in list(lines):
        body = [g for g in tagln.glyphs if g.text.strip()]
        if not body:
            continue
        tag = equation_number(tagln, column_of(page, tagln)[1])
        if len(tag) != len(body):
            continue                       # not a number on its own
        mid = 0.5 * (tagln.rect[1] + tagln.rect[3])
        host = None
        for ln in lines:
            if ln is tagln or not ln.glyphs:
                continue
            if ln.rect[2] > tagln.rect[0]:
                continue                   # not to the left of the number
            if not (ln.rect[1] <= mid <= ln.rect[3]):
                continue                   # not on this band
            if not any(sp.kind == "math" for sp in ln.spans):
                continue
            if host is None or ln.rect[2] > host.rect[2]:
                host = ln                  # the nearest one to its left
        if host is None:
            continue
        host.glyphs.extend(tagln.glyphs)
        host.glyphs.sort(key=lambda g: g.rect[0])
        host.rect = (host.rect[0], min(host.rect[1], tagln.rect[1]),
                     max(host.rect[2], tagln.rect[2]),
                     max(host.rect[3], tagln.rect[3]))
        page.lines.remove(tagln)
        lines.remove(tagln)
        joined += 1
    return joined


def mark_display_continuations(page: PageNode) -> int:
    """Promote the head of a display whose continuation was recognised alone.

    Returns how many lines were promoted. Sets `forced_display` on the line,
    which `is_display` accepts in place of the indent test -- the prose test
    still runs, so a sentence is never promoted.
    """
    lines = [ln for ln in page.lines if not ln.rotated and ln.glyphs]
    n = 0
    for i, ln in enumerate(lines):
        if i == 0 or not _starts_with_binary_operator(ln):
            continue
        if not is_display(ln, *column_of(page, ln)):
            continue
        j = i - 1
        while j >= 0:
            up = lines[j]
            if not any(sp.kind == "math" for sp in up.spans) or _is_prose(up):
                break
            size = max(g.size for g in up.glyphs)
            # directly above: the rows of one display share its leading
            if up.rect[1] - ln.rect[3] > 1.5 * size:
                break
            if is_display(up, *column_of(page, up)):
                break                      # already a display; nothing to do
            up.forced_display = True
            n += 1
            if not _starts_with_binary_operator(up):
                break                      # this one is the head
            j -= 1
    return n


def to_markdown(pages: list[PageNode], doc_id: str = "pdfdrill",
                base: str = "http://localhost:8000",
                px_per_pt: float = DEFAULT_PX_PER_PT,
                page_separator: str = "\n---\n",
                crop_deferred: bool = True,
                keep_rotated: bool = False,
                line_numbers: bool = True,
                join_hyphens: bool = True) -> str:
    """Mathpix-flavoured Markdown: LaTeX where we have it, a crop where we don't."""
    for _p in pages:
        absorb_equation_numbers(_p)
        mark_display_continuations(_p)
    fp = profile(pages)
    grouped = {p.page: g for p, g in _merge_heading_runs(pages, fp)}

    # 750 — A LINE THAT IS NOTHING BUT AN EQUATION NUMBER LEAVES THE FLOW.
    #
    # The tag is a LABEL, not content, and the reader already strips one that
    # shares a line with its mathematics. A display set on its own line puts
    # its number on a line of its own, and that one survived: wzlxjtu-031
    # reached the document as `$C = \sum ... V_{m}^{s}$` followed by a bare
    # `(1)` -- correct mathematics with a stray number after it.
    #
    # Dropped here, before any emitter sees it, so the markdown and the LaTeX
    # agree. 7 such lines on that page alone.
    for _pg in pages:
        kept = []
        for lvl, group in grouped.get(_pg.page, []):
            live = []
            for ln in group:
                body = [g for g in ln.glyphs if g.text.strip()]
                tag = equation_number(ln, column_of(_pg, ln)[1])
                if body and len(tag) == len(body):
                    continue                  # the whole line is the number
                live.append(ln)
            if live:
                kept.append((lvl, live))
        grouped[_pg.page] = kept
    out: list[str] = []
    for p in pages:
        if page_separator:
            out.append(page_separator)
        if p.invisible:
            out.append(f"*[page {p.page}: OCR text layer; not projected]*")
            continue
        margin = _right_margin(p)
        left = _left_margin(p)
        # The bottom of the display block last emitted, so an adjacent one
        # can join it rather than opening a new `$$`.
        last_display = None
        crops = _crop_clusters(p)
        # The page's usual LEADING. A gap wider than this is the author
        # separating things -- a caption from the paragraph after it, one
        # block from the next -- and Markdown needs a blank line to keep them
        # apart, since it joins adjacent lines by design.
        # Measured from CONSECUTIVE lines in reading order, which is
        # column-major, so both lines of a pair are in the same column.
        # Taking the sorted set of all row tops instead mixed the columns
        # together: on a two-column page the small offset BETWEEN the
        # columns became the modal gap -- 1.7pt against a real leading of
        # 10.9 -- so every line looked separated and every line became its
        # own paragraph.
        gaps = [a.rect[3] - b.rect[3]
                for a, b in zip(p.lines, p.lines[1:])
                if a.glyphs and b.glyphs and 0 < a.rect[3] - b.rect[3] < 60]
        leading = (max(set(round(g, 1) for g in gaps),
                       key=[round(g, 1) for g in gaps].count)
                   if gaps else 0.0)
        prev_top = None
        # Consecutive verbatim lines are ONE fenced block. Emitted as ordinary
        # lines each becomes its own paragraph, so a code listing arrives with
        # a blank line between every statement.
        fence_open = False
        fence_size = 0.0
        # Everything a crop covers is IN the picture. Emitting the text spans
        # of those lines as well duplicates them beside the image as stray
        # fragments -- `arbitrary ,` and a lone `0` next to a matrix that
        # already shows both.
        crop_boxes = [r for r in crops.values() if r is not None]
        # A figure belongs to a COLUMN, like a line. Placing it by y alone
        # put it at the top of the page while its caption -- correctly read
        # with the right column -- landed forty lines later. It is emitted
        # when the flow reaches a line of the same column below it.
        lefts = [ln.rect[0] for ln in p.lines if ln.glyphs]
        rights = [ln.rect[2] for ln in p.lines if ln.glyphs]
        _tw = (max(rights) - min(lefts)) if lefts else 1.0
        _mid = 0.5 * (min(lefts) + max(rights)) if lefts else 0.0

        def _col_of(rect) -> int:
            if (rect[2] - rect[0]) > 0.7 * _tw:
                return 2
            return 0 if 0.5 * (rect[0] + rect[2]) < _mid else 1

        # DISPLAY RUNS, decided in one pass BEFORE anything is emitted.
        #
        # Fusing incrementally during emission meant any material between two
        # display rows broke the chain -- an inline fragment, a crop -- and
        # incremental emission cannot see past it. Measured: 91.pdf stayed at
        # 25 blocks for 2 authored equations because `$\bigl($` sat between
        # its rows.
        #
        # Adjacency is computed over the DISPLAY groups ALONE, in page order,
        # so what lies between them is irrelevant to whether they belong to
        # one equation. This is the refactor 721 said was needed instead of
        # another threshold.
        # 730 — THE LOOK-AHEAD, replacing the vertical-gap threshold.
        #
        # Nothing inside a display says where it stops. The line AFTER it
        # announces itself, by starting at the body margin rather than the
        # display indent. That is the only statement of a display's end that
        # exists on the page, and it is the rule used here.
        #
        # The gap rule this replaces asked "are these two display rows close
        # enough vertically" (-1.5*size .. 2.0*size). It got both directions
        # wrong. A fraction, a sum's limits or a tall delimiter pushes two
        # rows of ONE equation further apart than 2.0*size, so the equation
        # split; and nothing stopped two genuinely separate displays with
        # prose between them from fusing, because the scan deliberately
        # looked only at display groups and ignored everything between.
        #
        # Measured over the 421 gold display equations of the PDF2LaTeX set:
        # stacked equations (fraction / operator limits / stacked rows) were
        # delivered whole 2 times in 281 under the gap rule.
        #
        # What may close a run, then, is exactly one thing: a return to the
        # body margin. An indented fragment (`$\bigl($`) does not -- it is
        # still inside the display, which is why 91.pdf's rows fell apart.
        # A crop does not. A heading does, and so does the page end.
        # ONE guard remains beside the margin rule, for the case the margin
        # cannot see: two displays with NOTHING between them -- no prose, no
        # fragment -- which is a real shape (a lemma's two equations) and
        # which the margin rule alone would fuse. It is a vertical gap, but a
        # generous one: rows of a single equation sit within about one
        # display leading of each other, while two equations are separated by
        # that plus a display skip. Swept over the gold set below.
        run_of: dict[int, int] = {}
        run_id = 0
        open_run = False
        prev_bottom = None
        _GAP = float(os.environ.get("PDF2MMD_RUN_GAP", "3.0"))

        def _at_margin(group) -> bool:
            """Does any line of this group BEGIN at the body margin?"""
            for ln in group:
                if ln.rotated or not ln.glyphs:
                    continue
                size = max(g.size for g in ln.glyphs)
                if ln.rect[0] <= left + 1.2 * size:
                    return True
            return False

        for gi, (lvl, group) in enumerate(grouped[p.page]):
            if not group:
                continue
            if not lvl and all(is_display(ln, *column_of(p, ln))
                               for ln in group):
                top = group[0].rect[3]
                size = max((g.size for ln in group for g in ln.glyphs),
                           default=10.0)
                if open_run and prev_bottom is not None \
                        and prev_bottom - top > _GAP * size:
                    open_run = False
                if not open_run:
                    run_id += 1
                    open_run = True
                run_of[gi] = run_id
                prev_bottom = group[-1].rect[1]
                # 739 -- A DISPLAY THAT CARRIES ITS OWN NUMBER IS AN EQUATION,
                # NOT A ROW. Two numbered equations set one under the other
                # are adjacent display lines with nothing between them, and
                # the run pass fused them into one `aligned` -- wzlxjtu-027
                # turned its (1) and (2) into a single two-row block, and
                # again its (5) and (6). A multi-row display carries ONE
                # number for the whole thing, so a number ends the run.
                if any(equation_number(ln, column_of(p, ln)[1])
                       for ln in group):
                    open_run = False
                continue
            # Not a display. It ends the run only if it comes back to the
            # margin -- or is a heading, which always does.
            if lvl or _at_margin(group):
                open_run = False

        run_text: dict[int, list] = {}
        pending = sorted(p.diagrams, key=lambda d: -d[3])
        for gi, (lvl, group) in enumerate(grouped[p.page]):
            top = max(ln.rect[3] for ln in group)
            gcol = _col_of((min(ln.rect[0] for ln in group),
                            min(ln.rect[1] for ln in group),
                            max(ln.rect[2] for ln in group),
                            max(ln.rect[3] for ln in group)))
            ready = [d for d in pending
                     if d[3] > top and _col_of(d) in (gcol, 2)]
            for d in ready:
                pending.remove(d)
                out.append("")
                out.append(f"![diagram]({crop_url(d, p, doc_id, base, px_per_pt)})")
                out.append("")
            chunks = []
            for ln in group:
                if ln.rotated and not keep_rotated:
                    continue
                parts: list[str] = []
                for sp in ln.spans:
                    if sp.kind == "text":
                        # Frame decoration is not content: the corner glyphs
                        # of a listing box come from a drawing font and
                        # render as `(cid:7)`.
                        if sp.glyphs and all(texmap.is_drawing(g.fontname)
                                             for g in sp.glyphs):
                            continue
                        if _mostly_inside(sp.rect, crop_boxes):
                            continue      # already inside the picture
                        parts.append(_linked_text(sp, p, sp.word_gap))
                        continue
                    covered = _mostly_inside(sp.rect, crop_boxes)
                    tex = docmodel.span_latex(sp)
                    if covered and tex is not None:
                        continue          # the crop already shows it
                    if tex is not None and is_emittable(tex) and _inline(tex):
                        parts.append(_inline(tex))
                    elif crop_deferred:
                        rect = crops.get(sp.id, sp.rect)
                        if rect is None:
                            continue          # covered by a merged crop
                        url = crop_url(rect, p, doc_id, base, px_per_pt)
                        # The node id and reason go in the image ALT text, not
                        # in an HTML comment. Markdown viewers that run a
                        # typographer turn `--` into an en dash, which breaks
                        # `<!-- ... -->` and prints the comment as visible
                        # text. Alt text survives, and is what a reader sees
                        # when the image server is not running.
                        parts.append(
                            f"![{sp.id} {docmodel.span_reason(sp)}]({url})")
                    else:
                        parts.append(docmodel.span_text(sp))
                chunks.append(_join_inline(parts))
            # Rotated lines are excluded above, so a rotated group must not
            # qualify as verbatim either: a stamp whose font happens to
            # measure as monospace would otherwise be fenced back into the
            # body it was just filtered out of.
            verb = (all(ln.verbatim for ln in group)
                    and not any(ln.rotated for ln in group))
            if fence_open and not verb and _is_gutter_only(group, fence_size):
                # A blank code line still carries its number. Emitting an
                # empty line instead loses it, and a listing that shows 1, 2,
                # 4, 6 has a hole a reader cannot explain.
                if line_numbers:
                    out.append(docmodel._run_text(
                        sorted((g for ln in group for g in ln.glyphs),
                               key=lambda g: g.rect[0])).strip())
                else:
                    out.append("")
                continue
            if verb:
                # The fence's type size must be known BEFORE the first line
                # is rendered, or that line keeps its gutter number while
                # every other line loses it.
                fence_size = fence_size or max(
                    (g.size for ln in group for g in ln.glyphs
                     if texmap.is_monospace(g.fontname)), default=10.0)
                # 781 — THE GRID, WHERE THE PAGE IS ONE.
                #
                # `_run_text` reconstructs word breaks from a gap threshold,
                # which is right for prose and wrong for code: leading space
                # is not a gap between glyphs at all, so every indent was
                # lost (measured: kept on 24% of the gold set's lines). A
                # monospace listing has been measured into a grid by
                # `listings.accumulate`, and its rows already carry both the
                # indent and the interior runs of spaces.
                _rows = [listings.listing_of(p, ln) for ln in group]
                _lst = _rows[0] if _rows and all(
                    r is not None and r is _rows[0] for r in _rows) else None
                if _lst is not None:
                    _by = {x.id: x for x in _lst.lines}
                    _emit = []
                    for ln in group:
                        x = _by.get(ln.id)
                        if x is None:
                            continue
                        # A BLANK CODE LINE IS A LINE. Its number is the only
                        # mark it leaves on the page, and that number is
                        # grouped into this row; dropping it closes up the
                        # listing and moves every line after it.
                        for n in x.blank_before:
                            _emit.append(("%d " % n) if line_numbers else "")
                        _emit.append(
                            ((("%d " % x.number) if line_numbers
                              and x.number is not None else "")
                             + " " * x.indent + x.text).rstrip())
                        for n in x.blank_after:
                            _emit.append(("%d " % n) if line_numbers else "")
                    # A blank line keeps its trailing space DELIBERATELY: the
                    # number is the gutter, not the code, and `2` on its own
                    # reads as a line whose content is the digit 2.
                    texts = _emit
                else:
                    texts = [" ".join(
                        docmodel._run_text(
                            ln.glyphs if line_numbers
                            else _strip_gutter(ln.glyphs, fence_size),
                            ln.spans[0].word_gap if ln.spans else 0)
                        for ln in group).rstrip()]
                # Frame decoration is not code: the corner glyphs of a listing
                # box come from a drawing font and render as `(cid:7)`.
                texts = [re.sub(r"\(cid:\d+\)", "", t).rstrip() for t in texts]
                if not any(t.strip() for t in texts):
                    continue
                if not fence_open:
                    out.append("")
                    # 781i — EVERYTHING MEASURED, AT THE HEAD OF THE BLOCK.
                    #
                    # In an HTML comment, because markdown has no comment
                    # of its own and a renderer must not print this. It is
                    # the same text the .tex carries behind `%`, so the two
                    # projections cannot drift apart.
                    if _lst is not None:
                        out.append("<!--")
                        out += [x.replace("--", "&#45;&#45;")
                                for x in listings.describe(_lst, doc_id)]
                        out.append("-->")
                        out.append("")
                    out.append("```" + (_lst.language if _lst is not None
                                        else ""))
                    fence_open = True
                    fence_size = max(
                        (g.size for ln in group for g in ln.glyphs
                         if texmap.is_monospace(g.fontname)), default=10.0)
                out += texts
                continue
            if fence_open:
                out.append("```")
                out.append("")
                fence_open = False

            body = " ".join(c for c in chunks if c)
            if not body.strip():
                continue
            displayable = (
                not lvl
                and all(is_display(ln, *column_of(p, ln))
                        for ln in group)
                # Every maths span must actually project. A matrix is drawn
                # as separate rows with extensible fences; each row satisfies
                # "indented, no prose" and would become its own `$$` block of
                # `0 i 0 i`, which is not an equation. If any span defers, the
                # line falls through and becomes a crop instead.
                and all(is_emittable(docmodel.span_latex(sp))
                        for ln in group for sp in ln.spans
                        if sp.kind == "math")
            )
            if displayable:
                # A display equation is a block, not an inline span. Wrapping
                # it in $$ is what makes a renderer centre it on its own line
                # instead of running it into the surrounding paragraph.
                # Walk ALL spans in order, not just the maths ones. An
                # aligned equation sets its relation symbols in a text font
                # and in their own column; emitting only maths spans dropped
                # every `=` in the document, turning `X^{-1} = \bar X = a1...`
                # into `X^{-1} X a1...`.
                pieces = []
                tagged = {id(g) for ln in group
                          for g in equation_number(ln, column_of(p, ln)[1])}
                for ln in group:
                    # 738 — A ROW WHOSE SPANS OVERLAP IN x CANNOT BE EMITTED
                    # SPAN BY SPAN, in any order.
                    #
                    # Spans are concatenated here, which assumes they tile the
                    # row left to right. They do not always: measured over the
                    # corpus, of 169 display lines carrying more than one span,
                    # 46 (27%) have their spans out of x order and 72 (43%)
                    # have spans that OVERLAP. wzlxjtu-068's fourth display:
                    #
                    #   span 0  math  x=[321.9,329.1]  'C'
                    #   span 1  text  x=[343.0,350.7]  '='
                    #   span 2  math  x=[380.1,445.1]  '0,0225·(1−δt'
                    #   span 3  text  x=[450.3,454.1]  ')'
                    #   span 4  math  x=[329.8,545.0]  'tot ∑ t ( ( sc +δt'
                    #
                    # Span 4 spans the whole row and is emitted last, so the
                    # sum and both big parens print AFTER the term they
                    # enclose. Sorting the spans by x cannot fix it -- span 4
                    # interleaves with every other span, which is what
                    # "overlapping" means.
                    #
                    # The precedent is in `docmodel_six` for fractions: "A
                    # line carrying a FRACTION cannot be segmented by x ...
                    # keep the line whole and let the structure pass do the
                    # splitting." An overlap says exactly the same thing, so
                    # the whole row goes to `to_tex` as one group and the
                    # ordering is decided there, by x, over all its glyphs.
                    _sp = [s for s in ln.spans if s.glyphs]
                    _xs = [(min(g.rect[0] for g in s.glyphs),
                            max(g.rect[2] for g in s.glyphs)) for s in _sp]
                    _ord = sorted(range(len(_sp)), key=lambda i: _xs[i][0])
                    _overlap = any(_xs[_ord[i + 1]][0] < _xs[_ord[i]][1] - 1
                                   for i in range(len(_ord) - 1))
                    # A text span of pure operators and digits is already
                    # folded into the mathematics below, so it is no reason to
                    # refuse the whole-row path -- `=` and `)` were sitting in
                    # text spans on the wzlxjtu-068 row and blocked it.
                    def _foldable(s):
                        if s.kind == "math":
                            return True
                        txt = docmodel._run_text(s.glyphs).strip()
                        return (not txt or re.fullmatch(
                            r"[-+=<>/(){}\[\],.;:|*!'\d\s]+", txt) is not None)

                    if _overlap and all(_foldable(s) for s in _sp):
                        keep = [g for s in _sp for g in s.glyphs
                                if id(g) not in tagged]
                        whole = structure.to_tex(
                            sorted(keep, key=lambda g: g.rect[0]),
                            list(ln.rules))
                        if whole:
                            pieces.append(whole)
                            continue
                    # Spans that do NOT overlap still have to be emitted
                    # left to right, and they were emitted in creation order.
                    # 46 of 169 multi-span display rows are out of x order.
                    # wzlxjtu-069's third display put `\min_{H\in\mathcal{H}
                    # (x)}` after the closing full stop -- every element
                    # present, the order wrong -- because the operator and its
                    # stacked subscript are built as a later span.
                    for sp in ([_sp[i] for i in _ord] if _sp else ln.spans):
                        if sp.glyphs and all(id(g) in tagged
                                             for g in sp.glyphs
                                             if g.text.strip()):
                            continue          # the equation number

                        if sp.kind == "math":
                            pieces.append(docmodel.span_latex(sp) or "")
                            continue
                        t = docmodel._run_text(sp.glyphs).strip()
                        if not t:
                            continue
                        if re.fullmatch(r"[-+=<>/(){}\[\],.;:|*!'\d\s]+", t):
                            pieces.append(t)          # operators and numbers
                        else:
                            pieces.append(rf"\text{{{_escape_in_text(t)}}}")
                inner = " ".join(x for x in pieces if x).strip()
                # A tag SHARING a span with the mathematics survives the span
                # filter above, so remove the token here. This strips only
                # what was positively identified by geometry -- a
                # parenthesised number, at the right margin, behind a gap of
                # more than three em -- and only when it is what the text
                # actually ends with.
                _tag = ""
                for ln in group:
                    tag = "".join(g.text for g in equation_number(
                        ln, column_of(p, ln)[1])).strip()
                    if tag and inner.rstrip().endswith(tag):
                        inner = inner.rstrip()[:-len(tag)].rstrip()
                    _tag = _tag or tag
                # 739 -- AND PUT IT BACK, AS `\tag`.
                #
                # The two projections need OPPOSITE things from the number
                # and were both doing the same thing with it. LaTeX numbers
                # an `equation` itself, so the page's own `(1)` must go --
                # printed as well it appears twice, with different values.
                # MARKDOWN NUMBERS NOTHING, so dropping it loses the label
                # the surrounding prose refers to: "substituting (3) into
                # (4)" with no (3) and no (4) anywhere on the page.
                #
                # `\tag{1}` is the one spelling that says "this equation is
                # numbered 1" without claiming to have counted it, and both
                # KaTeX and MathJax set it. MathPix emits no tag at all --
                # zero `\tag` over the whole corpus -- so this is a place
                # the projection can carry more than its reference does.
                if _tag:
                    inner = inner.rstrip() + r" \tag{%s}" % _tag.strip("()")
                extras = ""
                # A display block must SAY something. `$$ $$` and
                # `$$\bigr)$$` are not equations; they were 55 empty and
                # ~20 lone-delimiter rows of the 836 this file emitted
                # across 102 documents. Falling through here makes the line
                # a crop, which is a refusal and therefore cannot be wrong
                # in the way an emission can.
                if is_emittable(inner) and has_content(inner):
                    # FUSE with the display block immediately above when the
                    # two are adjacent on the page. A `cases`, an `align` or
                    # any multi-line display arrives as one group per LINE,
                    # and opening a new `$$` for each turned one authored
                    # equation into several blocks.
                    #
                    # Measured against the PDF2LaTeX gold set: the author's
                    # environment count is 421; this file emitted roughly
                    # four times that, while `equations.json` -- which has
                    # fused runs since 707 -- emitted 1.9x. The difference
                    # between the two outputs of the SAME tool was this.
                    top = group[0].rect[3]
                    size = max((g.size for ln in group for g in ln.glyphs),
                               default=10.0)
                    # One PLACEHOLDER per run, filled at the end.
                    #
                    # Patching `out` in place could not reach back past a
                    # crop or an inline fragment, so the run pass computed
                    # eight runs for a page while twenty-six blocks came
                    # out. The placeholder holds the run's position in the
                    # document; the text is accumulated separately and
                    # substituted once the page is done.
                    rid = run_of.get(gi)
                    if rid is not None:
                        if rid not in run_text:
                            run_text[rid] = []
                            out.append("")
                            out.append(f"\x00RUN{rid}\x00")
                            out.append("")
                        # Keep each fragment's BASELINE with it. A run holds
                        # two different things -- the rows of a multi-row
                        # display, and the pieces of a SINGLE row that the
                        # grouper split -- and only the baseline tells them
                        # apart. Without it `L^{-1}dL = Q+P` came back as
                        # `L^{-1} \\ dL = Q + P`: one line printed as two.
                        # The BASELINE, not the box top. A fragment carrying
                        # a fraction is taller than one that does not, so its
                        # `rect` top sits higher while it is on the very same
                        # line -- which is how `\mathcal{L}_{coset}` and
                        # `= -\frac{1}{4} eP...` were still printed as two
                        # rows after the box top was tried.
                        from collections import Counter as _C
                        _bl = _C(round(gg.baseline, 1)
                                 for ln2 in group for gg in ln2.glyphs)
                        _base = _bl.most_common(1)[0][0] if _bl else top
                        run_text[rid].append(
                            (_base, size, balance_delims(inner.strip())))
                        continue
                    out.append("")
                    out.append("$$")
                    out.append(balance_delims(inner.strip()))
                    out.append("$$")
                    if extras:
                        out.append(extras)
                    out.append("")
                    continue
            if lvl:
                out.append("")
                out.append("#" * lvl + " " + body)
                out.append("")
                continue
            if (prev_top is not None and leading > 0
                    and (prev_top - top) > 1.6 * leading):
                if out and out[-1].strip():
                    out.append("")
            prev_top = top
            out.append(body)
            # A line that stops well short of the right margin ended its
            # paragraph. Without this every line of an address block is
            # reflowed into one run-on paragraph, because Markdown joins
            # adjacent lines by design.
            # The margin is the one THIS line's own column justifies to, not
            # the page's widest edge. A narrow block -- an abstract set inside
            # a two-column page -- stops far short of the page margin on every
            # line, so every line looked like a paragraph end and the whole
            # abstract came out one line per paragraph.
            last = group[-1]
            size = max((g.size for g in last.glyphs), default=10.0)
            local = _column_margin(p, last, margin)
            # A line ending in a hyphen is mid-word: it cannot be the end of
            # a paragraph, whatever its length. Breaking there put a blank
            # line between the two halves and left the word broken for good.
            if (last.rect[2] < local - 1.5 * size
                    and not body.rstrip().endswith(("-", "\u00ad"))):
                out.append("")
        if fence_open:
            out.append("```")
            out.append("")
            fence_open = False
        for d in pending:
            out.append("")
            out.append(f"![diagram]({crop_url(d, p, doc_id, base, px_per_pt)})")
            out.append("")
        # Fill this page's run placeholders. Done per page, because a run
        # never spans a page break and the ids restart.
        for i, item in enumerate(out):
            if item.startswith("\x00RUN") and item.endswith("\x00"):
                rid = int(item[4:-1])
                # 732 — THE ROWS OF A FUSED RUN MUST ACTUALLY BREAK.
                #
                # The run pass gathers a multi-row display into one block,
                # which is right, and then joined the rows with a newline --
                # which LaTeX eats. wzlxjtu-009's second display is three
                # rows, `S_{AB}=...`, `N_{AB}=...`, `M^I_{AB}=...`; every
                # symbol came back, in order, run together as ONE line. The
                # content was never the problem; the row structure was
                # discarded at the last step before printing.
                frags = [f for f in run_text.get(rid, []) if f[2].strip()]
                rows: list[str] = []
                for top, size, txt in frags:
                    # same baseline as the fragment before it => same ROW,
                    # joined by a space; a new baseline => a new row.
                    if rows and abs(top - prev_top) <= 0.5 * max(size, 1.0):
                        rows[-1] = rows[-1] + " " + txt
                    else:
                        rows.append(txt)
                    prev_top = top
                if len(rows) > 1:
                    body = ("\\begin{aligned}\n" + " \\\\\n".join(rows)
                            + "\n\\end{aligned}")
                else:
                    body = rows[0] if rows else ""
                out[i] = "$$\n" + body + "\n$$" if body.strip() else ""
        out.append("")
    text = "\n".join(out)
    # Rejoin words the typesetter broke across a line. Done on the
    # finished text so the document itself supplies the evidence for
    # which joins are real.
    if join_hyphens:
        text = dehyphenate(text, _vocabulary(text))
    return text



_TEX_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
                "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
                "}": r"\}", "~": r"\textasciitilde{}",
                "^": r"\textasciicircum{}"}



def _tex_color(rgb) -> str:
    """An xcolor operand: `\\textcolor[rgb]{r,g,b}` takes values in 0..1."""
    return ",".join(f"{v:.4g}" for v in rgb)


def _fill_under(page: PageNode, rect):
    """The background fill covering this rectangle, if any."""
    cx = 0.5 * (rect[0] + rect[2])
    cy = 0.5 * (rect[1] + rect[3])
    for fl in page.fills:
        if (fl.rect[0] <= cx <= fl.rect[2] and fl.rect[1] <= cy <= fl.rect[3]
                and fl.color):
            return fl.color
    return None


def _escape_tex(t: str) -> str:
    """Escape TeX specials in prose destined for a .tex file.

    Markdown only needed `$` guarded; LaTeX needs all ten. A code listing
    containing `\n` was emitted as a raw control sequence, so the document
    would not compile -- found by the package check, which reported `\n`,
    `\nSum` and friends as commands defined by no package.
    """
    return "".join(_TEX_SPECIAL.get(c, c) for c in t)


#: TeX specials that a TEXT run may contain and `\text{}` cannot.
#:
#: 754 -- prose inside a formula is wrapped in `\text{...}` and was put there
#: VERBATIM. wzlxjtu-073 sets `m_{ij} = \#\{k : (i,j,k) \in J\}`, and the `#`
#: reached the output as `\text{#}` -- a parameter character, which is
#: "Illegal parameter number" and takes the whole cell down. `_` is the same
#: hazard and the one you flagged first: an index named `gb_imp` inside
#: `\text{}` is "Missing $ inserted".
#:
#: NOT `\`, `{` or `}`: those arrive here only from a glyph the reader
#: projected, and rewriting them would break a run that is already LaTeX.
_TEXT_SPECIAL = {"#": r"\#", "%": r"\%", "&": r"\&", "_": r"\_",
                 "$": r"\$", "~": r"\textasciitilde{}",
                 "^": r"\textasciicircum{}"}


def _escape_in_text(t: str) -> str:
    return "".join(_TEXT_SPECIAL.get(c, c) for c in t)


def _opt(key: str, value: str) -> str:
    r"""One `lstlisting` option, braced when its value carries a bracket.

    781f — AND THE SAME TRAP A SECOND TIME. `\begin{lstlisting}[...]` ends
    its optional argument at the first unbraced `]`, so

        morekeywords=[1]{float,for},keywordstyle=[1]{\color{lstclr0}}

    ends at `[1]` and everything after it is silently dropped: the file
    still compiles, the listing still sets, and NOTHING IS COLOURED. It
    cost a round trip to see, because the only symptom is an absence.
    `moredelim` died of this in 781 and the lesson did not generalise --
    it is a property of the ARGUMENT, not of any one key.
    """
    if "[" in value or "]" in value:
        return "%s={%s}" % (key, value)
    return "%s=%s" % (key, value)


def _style(rgb, bold: bool, italic: bool, name: str) -> str:
    r"""A `listings` style, written the way listings writes one."""
    out = []
    if rgb is not None:
        out.append(r"\color{%s}" % name)
    if bold:
        out.append(r"\bfseries")
    if italic:
        out.append(r"\itshape")
    return "".join(out)


def _listing_tex(lst, doc_id: str = "") -> str:
    r"""A measured listing, written as the `lstlisting` that would set it.

    781 — THE LaTeX PROJECTION OF A LISTING HAD NO LISTING IN IT.

    Every code line went through the same span loop as prose, so a projected
    `.tex` said

        1 float b1[M], b2[M], out[N][M], avg[N][M]
        \textcolor[rgb]{0.5,0.5,0.5}{2 a = 1.5}
        3 for (i in 0..N)

    which compiles -- all 307 gold listings compiled -- and renders as ONE
    JUSTIFIED PARAGRAPH. The line breaks and the indentation, which in a
    listing are the content, are gone before LaTeX ever sees the file.

    781e — AND THE BODY IS THE PROGRAM, SO NOTHING GOES IN IT.

    The first repair carried colour with `moredelim` markers -- `!<for>!`
    written into the code. That is backwards for a listing. A listing is
    not an equation: an equation wants markup, and code wants a body a
    compiler could be handed unchanged. The styling is a HEADER property
    and `lstlisting` already has the vocabulary for it --
    `keywordstyle` with `morekeywords`, `commentstyle`, `stringstyle` --
    so the words go in the options and the body stays exactly what was
    read off the page.

    Everything written here was measured by `listings.accumulate`: the type
    size, the line numbers and their first value and step, the styled
    words, the comment and string styles, the background.
    `columns=fullflexible` + `keepspaces=true` is what makes LaTeX set the
    spaces we counted rather than re-space the line itself.
    """
    opts = [r"basicstyle=\ttfamily\fontsize{%.1f}{%.1f}\selectfont"
            % (lst.size, 1.2 * lst.size),
            "columns=fullflexible", "keepspaces=true"]
    if lst.language:
        opts.append("language=%s" % lst.language)
    if lst.numbers:
        opts += ["numbers=left", "firstnumber=%d" % lst.firstnumber,
                 "stepnumber=%d" % lst.stepnumber, r"numberstyle=\tiny"]
    decls: list[str] = []
    seen: dict = {}

    def colour(rgb) -> str:
        if rgb not in seen:
            seen[rgb] = "lstclr%d" % len(seen)
            decls.append(r"\definecolor{%s}{rgb}{%s}"
                         % (seen[rgb], _tex_color(rgb)))
        return seen[rgb]

    # The styled words, grouped by the style they were given: one
    # `keywordstyle` per group, which is how listings numbers them.
    groups: dict = {}
    for word, rgb, bold, italic in lst.keywords:
        # A keyword list is written INSIDE the environment's optional
        # argument, so a word carrying a brace or a bracket does not make a
        # bad listing -- it makes an unreadable file. Refuse it here as
        # well as upstream: one such word cost lst-095 its whole compile.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", word):
            continue
        groups.setdefault((rgb, bold, italic), []).append(word)
    for i, (style, words) in enumerate(sorted(groups.items(),
                                              key=lambda kv: -len(kv[1])), 1):
        rgb, bold, italic = style
        name = colour(rgb) if rgb is not None else ""
        opts.append(_opt("morekeywords",
                         "[%d]{%s}" % (i, ",".join(sorted(set(words))))))
        opts.append(_opt("keywordstyle",
                         "[%d]{%s}" % (i, _style(rgb, bold, italic, name))))
    for kind, key in (("comment", "commentstyle"), ("string", "stringstyle")):
        st = lst.style_of(kind)
        if st is None:
            continue
        rgb, bold, italic = st
        name = colour(rgb) if rgb is not None else ""
        opts.append(_opt(key, "{%s}" % _style(rgb, bold, italic, name)))
    if lst.background:
        opts.append(r"backgroundcolor=\color{%s}" % colour(lst.background))
    note = ["%% " + x for x in listings.describe(lst, doc_id)]
    return "\n".join(note + decls
                      + [r"\begin{lstlisting}[" + ",".join(opts) + "]"]
                      + [t for _n, t in lst.rows()]
                      + [r"\end{lstlisting}"])


def _flush_eq(out: list, rows: list) -> None:
    r"""Emit the rows collected for one display as a single environment."""
    if not rows:
        return
    if len(rows) == 1:
        out.append(r"\begin{equation}")
        out.append(rows[0])
        out.append(r"\end{equation}")
    else:
        out.append(r"\begin{equation}")
        out.append(r"\begin{aligned}")
        out.append(" \\\\\n".join(rows))
        out.append(r"\end{aligned}")
        out.append(r"\end{equation}")
    rows.clear()


def to_latex(pages: list[PageNode], doc_id: str = "pdfdrill",
             base: str = "http://localhost:8000",
             px_per_pt: float = DEFAULT_PX_PER_PT,
             preamble: bool = True,
             unicode_fonts: bool = False) -> str:
    """LaTeX using the same crop URLs inside \\includegraphics, as Mathpix does.

    With a PREAMBLE derived from the symbols actually used. We can do this
    because every symbol we emit was chosen from a known font, and the font
    says which package defines it -- the glyph/package correlation Mathpix
    did not keep. A document with no fraktur does not load amsfonts.
    """
    for _p in pages:
        absorb_equation_numbers(_p)
        mark_display_continuations(_p)
    fp = profile(pages)
    sect = {1: "section", 2: "subsection", 3: "subsubsection"}
    out: list[str] = []
    pending: list[str] = []
    prev_bottom = None
    for p in pages:
        out.append(f"% ---- page {p.page} ----")
        out.append(r"\newpage")
        _done: set = set()
        for ln in p.lines:
            # A code listing is projected whole, from the grid measured on
            # the page, not line by line through the prose path.
            _lst = listings.listing_of(p, ln)
            if _lst is not None:
                if id(_lst) not in _done:
                    _done.add(id(_lst))
                    _flush_eq(out, pending)
                    pending = []
                    out.append(_listing_tex(_lst, doc_id))
                continue
            lvl = heading_level(ln, fp)
            parts: list[str] = []
            raw: list[str] = []          # the same maths, without the `$`
            only_math = True
            # 739 -- THE NUMBER IS LaTeX'S TO PRINT, NOT OURS.
            #
            # `\begin{equation}` numbers the equation itself, so emitting the
            # page's own `(1)` puts the number in TWICE -- once as text and
            # once by LaTeX, with different values. The markdown path drops
            # the tag glyphs like this and the .tex path never did: a bare
            # `(1)` matches the "operators and numbers" test below, so it was
            # appended to the display body and came out inside the equation.
            #
            # The MARKDOWN does the opposite and shows it, because markdown
            # has no numbering of its own -- see `_tag_of` at the emitter.
            _tagged = {id(g) for g in
                       equation_number(ln, column_of(p, ln)[1])}
            for sp in ln.spans:
                if sp.glyphs and all(id(g) in _tagged for g in sp.glyphs
                                     if g.text.strip()):
                    continue
                if sp.kind == "text":
                    txt = _escape_tex(
                        docmodel._run_text(sp.glyphs, sp.word_gap))
                    # Colour goes in the LaTeX, never in the Markdown --
                    # Markdown has no way to say it, and Mathpix drops it
                    # from the .md for the same reason.
                    cols = {g.color for g in sp.glyphs if g.color}
                    if len(cols) == 1 and txt.strip():
                        txt = (rf"\textcolor[rgb]{{{_tex_color(cols.pop())}}}"
                               rf"{{{txt}}}")
                    back = _fill_under(p, sp.rect)
                    if back and txt.strip():
                        txt = (rf"\colorbox[rgb]{{{_tex_color(back)}}}"
                               rf"{{{txt}}}")
                    parts.append(txt)
                    if txt.strip():
                        # an operator or number between maths spans is part
                        # of the display; a word is not
                        if re.fullmatch(r"[-+=<>/(){}\[\],.;:|*!'\d\s]+",
                                        docmodel._run_text(sp.glyphs).strip()):
                            raw.append(docmodel._run_text(sp.glyphs).strip())
                        else:
                            only_math = False
                    continue
                tex = docmodel.span_latex(sp)
                if tex is not None and is_emittable(tex):
                    # The same hazard the markdown path was given in 738, and
                    # the .tex path never got: a span is a FRAGMENT of a line,
                    # so a `\left` whose partner lives in the next span reaches
                    # the document alone. Measured over the 102 page files, 2
                    # of them failed to compile on exactly this --
                    # `$\left[ \tanh\!\Bigl($` opening on one line and
                    # `$\right]$` closing four lines later.
                    parts.append(f"${balance_delims(tex)}$")
                    raw.append(balance_delims(tex))
                else:
                    only_math = False
                    url = crop_url(sp.rect, p, doc_id, base, px_per_pt)
                    parts.append(
                        "\n".join([
                            r"\begin{figure}[H]",
                            rf"  \includegraphics[alt={{}},max width=\textwidth]{{{url}}}",
                            rf"  % unprojected: {sp.id} {docmodel.span_reason(sp)}",
                            r"\end{figure}",
                        ])
                    )
            body = " ".join(x for x in parts if x)
            # 751 — THE LaTeX PROJECTION HAD NO DISPLAY EQUATIONS AT ALL.
            #
            # Every maths span was emitted as inline `$...$`, so a page whose
            # markdown carries 11 `$$` blocks produced a `.tex` with ZERO
            # display environments -- wzlxjtu-031's first equation reached the
            # file as `$C = \sum ... V_{m}^{s}$` in the middle of a paragraph,
            # with its `(1)` beside it.
            #
            # Markdown cannot express much more than `$$`; LaTeX can say
            # exactly what the page shows, and this is the projection that
            # should. The SAME display test the markdown uses decides it, so
            # the two agree on what a display is.
            if (not lvl and body.strip()
                    and is_display(ln, *column_of(p, ln))):
                # Built from the RAW maths, not by unwrapping the joined
                # string: a display line is usually several spans, so the
                # joined body carries several `$...$` and cannot simply
                # have its delimiters stripped.
                if only_math and raw:
                    # ROWS OF ONE DISPLAY STAY ONE DISPLAY. Emitting an
                    # `equation` per LINE turned wzlxjtu-009's three-row
                    # `S_{AB}/N_{AB}/M^I_{AB}` into three separately numbered
                    # equations, where the markdown keeps it as one `aligned`.
                    # Consecutive display lines with nothing between them and
                    # no vertical gap are rows of the same display.
                    size = max((g.size for g in ln.glyphs), default=10.0)
                    if (pending and prev_bottom is not None
                            and prev_bottom - ln.rect[3] <= 1.5 * size):
                        pending.append(" ".join(raw))
                    else:
                        _flush_eq(out, pending)
                        pending = [" ".join(raw)]
                    prev_bottom = ln.rect[1]
                    continue
            _flush_eq(out, pending)
            pending = []
            if lvl:
                out.append(rf"\{sect[lvl]}{{{body}}}")
            else:
                out.append(body)
        _flush_eq(out, pending)
        pending = []
        out.append("")
    body = "\n".join(out)
    if not preamble:
        return body

    import texpackages
    # A Private Use codepoint is a FONT'S INTERNAL SLOT, not a character: the
    # PDF's ToUnicode said this glyph has no Unicode. No font outside that
    # document has it, so it sets nothing and LaTeX only warns -- the
    # character disappears from the output and nothing says so. Removed here
    # and named in the preamble instead. (HSVA-100jahre, U+F075.)
    body, private = texpackages.strip_private_use(body)
    pkgs = texpackages.packages_for(body)
    if "\\includegraphics" in body and "graphicx" not in pkgs:
        pkgs.append("graphicx")
    # `max width=` is ADJUSTBOX's key, exported into `\includegraphics` by its
    # `export` option -- plain graphicx does not define it, and every crop
    # emitted here uses it:
    #
    #     ! Package keyval Error: max width undefined.
    #
    # Found only by running PDFs from outside the test corpus, because the
    # corpus `.tex` files have their `\includegraphics` lines commented out
    # for inspection and never reached the key. 13 of 18 outside documents
    # failed on it.
    if "max width" in body and "adjustbox" not in pkgs:
        pkgs.append("adjustbox")
    # `[H]` is the `float` package's placement, not LaTeX's own. Every crop is
    # emitted as `\begin{figure}[H]`, so a page carrying one failed to compile
    # with "! LaTeX Error: Unknown float option `H'" -- recoverable, so a PDF
    # still appeared, which is why it went unnoticed. Declared where it is
    # used, on the same condition.
    if "[H]" in body and "float" not in pkgs:
        pkgs.append("float")
    if "lstlisting" in body and "listings" not in pkgs:
        pkgs.append("listings")
    if ("\\definecolor" in body or "\\textcolor" in body
            or "\\colorbox" in body) and "xcolor" not in pkgs:
        pkgs.append("xcolor")
    if unicode_fonts:
        pkgs.append("fontspec")
    # Characters the text font does not have. Prose does not go through
    # `texmap` -- a glyph the PDF names is written out as itself and is
    # DROPPED WITH A WARNING if the font lacks it, which no one reads.
    uni_lines, uni_pkgs, uni_lost = texpackages.unicode_decls(body)
    for name in uni_pkgs:
        if name not in pkgs:
            pkgs.append(name)
    unknown = texpackages.unknown_commands(body)

    # 749 — `twocolumn` WHEN THE PAGE IS TWO COLUMNS.
    #
    # The layout is measured, not guessed: `columns()` finds the text columns
    # on each page and the four documents that declare
    # `\documentclass[twocolumn]{revtex...}` are exactly the ones it reports
    # as two-column. Markdown has no way to say this; LaTeX does, and the
    # `.tex` output is the projection that can carry it.
    #
    # NOT a reconstruction of the author's preamble -- nothing here knows
    # what class or packages the author loaded, and the docmodel does not
    # keep one (its `latex`/`latex_original` pair is macro expansion, which
    # exists precisely so that no author preamble is needed). This is what
    # the PAGE shows, written in the only place that can express it.
    twocol = any(len(columns(p)) > 1 for p in pages)
    head = [r"\documentclass[twocolumn]{article}" if twocol
            else r"\documentclass{article}"]
    for name in pkgs:
        if name == "fontspec":
            # [no-math] so fontspec leaves the maths fonts alone: the symbols
            # projected here were chosen from the document's own TeX maths
            # fonts, and letting fontspec substitute would change them.
            head.append(r"\usepackage[no-math]{fontspec}")
        else:
            head.append(r"\usepackage[export]{adjustbox}" if name == "adjustbox"
                        else rf"\usepackage{{{name}}}")
    head += uni_lines
    head += texpackages.provides_for(body)
    if uni_lost:
        head.append("% WARNING: no translation for, and no font here sets: "
                    + " ".join("U+%04X %s" % (ord(c), c) for c in uni_lost)[:400])
    if private:
        head.append("%% WARNING: %d private-use codepoint(s) removed (a font's "
                    "own slot, not a character): %s"
                    % (len(private),
                       " ".join(sorted({"U+%04X" % ord(c) for c in private}))[:200]))
    if unknown:
        # Surfaced, not shipped: Mathpix output that will not compile is the
        # failure this exists to avoid.
        head.append("% WARNING: commands with no known package: "
                    + " ".join(sorted(r"\\" + u for u in unknown))[:400])
    head.append(r"\begin{document}")
    # A document whose body is only `\newpage` compiles to NOTHING: xelatex
    # says "No pages of output", which reads as a LaTeX fault rather than as
    # "this PDF had no text". Say it on the page instead. (733.)
    if not re.search(r"[^\s\\]", re.sub(r"(?m)^\s*%.*$", "",
                                    re.sub(r"\\newpage|\\clearpage", "", body))):
        body += ("\n\\textbf{No text was read from this PDF.} It has no text "
                 "layer on the pages converted, so there was nothing for a "
                 "glyph reader to project: the page is an image and needs "
                 "OCR.\n")
    return "\n".join(head) + "\n" + body + "\n" + r"\end{document}" + "\n"


#: Line types this classifier can justify from a measurement, in the vocabulary
#: pdfdrill's docmodel modules already read (`table.py` wants `simple_cell`,
#: `header.py` wants `section_header`, `code_listing.py` wants `code`…). A type
#: not listed here is one nothing measures yet; inventing it would produce a
#: Section the document does not contain, and every projection would carry it.
LINE_TYPES = ("text", "math", "equation", "equation_number", "section_header",
              "code", "diagram", "page_info", "title", "rotated_text",
              "authors", "abstract", "caption", "table",
              "footnote")


def _listing_rows(page: PageNode) -> dict:
    """{line index: the Listing it belongs to} for every line inside one.

    `listings.accumulate` measured these on the glyph grid — the monospace cell
    width, the drawn frame, the language. A listing's lines are the one thing
    this program reads BETTER than MathPix (674/676), and they reached pdfdrill
    as undifferentiated prose because nothing carried the fact across.
    """
    rows: dict = {}
    for lst in getattr(page, "listings", None) or []:
        a, b = getattr(lst, "line_start", -1), getattr(lst, "line_end", -1)
        if a < 0 or b < a:
            continue
        for i in range(a, b + 1):
            rows[i] = lst
    return rows


def _rotation_of(ln: LineNode) -> int:
    """The line's rotation in degrees, from the glyph text matrix.

    `(a, b, c, d, e, f)` — `b` and `c` carry the rotation, and for the two
    cases that occur in documents (90 deg either way) their signs decide it.
    Anything else is reported as 0 rather than guessed at: a reader that
    rotates a crop by a wrong angle produces a picture of nothing.
    """
    g = next((g for g in ln.glyphs if g.text.strip()), None)
    if g is None:
        return 0
    a, b, c, d = (g.matrix + (0, 0, 0, 0))[:4]
    if abs(a) < 1e-6 and abs(d) < 1e-6:
        return 90 if b > 0 else 270
    return 0


def _running_lines(pages: list[PageNode]) -> set:
    """{(page number, line index)} for every running header, footer or folio.

    `page_info` in MathPix's vocabulary. On 1107.2723 the line
    `Signal & Image Processing : An International Journal (SIPIJ) Vol.2, No.2,
    June 2011` stands at the top of all 16 pages and became 16 Paragraphs,
    because nothing typed it and `text` becomes prose.

    TWO PROPERTIES, BOTH CHECKABLE WITHOUT READING THE WORDS: the line sits in
    the top or bottom margin band, and its text REPEATS across pages once the
    digits are removed — a folio changes on every page, the rest of the header
    does not. Neither alone is enough: a section heading can open a page, and a
    repeated word can appear mid-column.

    Below three pages this abstains. A line appearing on both pages of a
    two-page document is as likely to be a coincidence as a header, and the
    cost of being wrong is a paragraph deleted from the document.
    """
    if len(pages) < 3:
        return set()
    BAND = 0.15                       # of page height, top and bottom
    seen: dict = {}
    band_lines: list = []
    for p in pages:
        h = p.rect[3] - p.rect[1]
        if h <= 0:
            continue
        top_cut, bot_cut = p.rect[3] - BAND * h, p.rect[1] + BAND * h
        for i, ln in enumerate(p.lines):
            if not ln.glyphs:
                continue
            if not (ln.rect[3] >= top_cut or ln.rect[1] <= bot_cut):
                continue
            raw = docmodel._run_text(ln.glyphs).strip()
            # A bare folio normalises to nothing; it IS page_info, and the
            # repeat test cannot see it because every page differs.
            if raw and re.fullmatch(r"[\d\s.,:/–—-]+|[ivxlcdmIVXLCDM.\s]+", raw):
                band_lines.append(((p.page, i), None))
                continue
            key = re.sub(r"[^a-zäöüß]+", "", raw.lower())
            if len(key) < 6:
                continue              # too short to be evidence of anything
            seen.setdefault(key, set()).add(p.page)
            band_lines.append(((p.page, i), key))
    need = max(3, int(0.6 * len(pages)))
    out = set()
    for where, key in band_lines:
        if key is None or len(seen.get(key, ())) >= need:
            out.add(where)
    return out


def _title_lines(pages: list[PageNode]) -> set:
    """{(page number, line index)} for the document title.

    796 typed a title set on three lines as THREE `Section`s. A title on three
    lines is one title, and MathPix ships it as one `title` line — pdfdrill's
    `_extract_title` already merges consecutive ones, so emitting the type is
    the whole fix.

    Established by: the largest type size on the first page carrying text, and
    the CONSECUTIVE run of lines at that size starting from the first of them.
    Consecutive is what makes it one title rather than every large line on the
    page; the run stops at the first line that is not title-sized, which is the
    authors block or the abstract.

    Abstains when the page has no size contrast — a page set entirely in one
    size has no title to find, and calling its first lines a title would delete
    them from the prose.
    """
    for p in pages:
        sizes = [line_size(ln) for ln in p.lines if ln.glyphs and not ln.rotated]
        sizes = [s for s in sizes if s > 0]
        if len(sizes) < 4:
            continue
        top = max(sizes)
        body = collections.Counter(round(s, 1) for s in sizes).most_common(1)[0][0]
        if top < 1.15 * body:
            return set()              # no contrast: nothing here is a title
        run, started = set(), False
        for i, ln in enumerate(p.lines):
            if not ln.glyphs or ln.rotated:
                continue
            # A line of glyphs that are all whitespace has a size and no
            # text; it neither starts a title nor ends one, so it is passed
            # over rather than swept in. Two of them bracketed 1107.2723's
            # title and arrived as `title` lines with a body of " ".
            if not docmodel._run_text(ln.glyphs).strip():
                continue
            if line_size(ln) >= 0.95 * top:
                run.add((p.page, i))
                started = True
            elif started:
                break                 # the run ended; the rest is not title
        return run
    return set()


#: Headings whose block IS the abstract, by language. A label, not a guess: the
#: line must be a heading already (size rank) AND read as one of these. Extend
#: by adding the word a publisher actually prints, not a translation of it.
_ABSTRACT_LABELS = frozenset({
    "abstract", "zusammenfassung", "kurzfassung", "resume", "resumen",
    "riassunto", "sommario", "sumario", "samenvatting", "streszczenie",
    "sammanfattning", "resumo", "abstrakt", "annotacia",
})


#: What a caption's first word can be, by language. As with `_ABSTRACT_LABELS`,
#: these are words a publisher prints — extend by adding one, not by translating.
_CAPTION_LABELS = {
    "table": "table", "tabelle": "table", "tabla": "table", "tabella": "table",
    "tabel": "table", "tabela": "table", "tabell": "table",
    "figure": "figure", "fig": "figure", "abbildung": "figure", "abb": "figure",
    "figura": "figure", "figuur": "figure", "bild": "figure",
}

#: `Table 2:` / `Abbildung 3.1.` / `Fig. 4 –` — a label word, a number, and a
#: separator. The separator matters: without it `Table 2 shows that …` in
#: running prose reads as a caption, and a sentence becomes a figure.
_CAPTION_RE = re.compile(
    r"^\s*([A-Za-zÄÖÜäöü]+)\s*\.?\s*(\d+(?:[.\-]\d+)*)\s*[-:.\u2013\u2014)]",
    re.UNICODE)


def _caption_of(ln: LineNode) -> "dict | None":
    """`{"label": "table"|"figure", "number": "2"}` for a caption line, else None."""
    m = _CAPTION_RE.match(docmodel._run_text(ln.glyphs))
    if not m:
        return None
    kind = _CAPTION_LABELS.get(m.group(1).lower().rstrip("."))
    return {"label": kind, "number": m.group(2)} if kind else None


def _rule_clusters(page: PageNode) -> list:
    """Horizontal rules grouped into the bands a table draws.

    A ruled table is its rules: booktabs prints a top, a mid and a bottom, and
    the page carries nothing else of that shape at that width. Grouped by
    shared x-EXTENT first — two columns of tables interleave in y and cannot be
    separated by height alone — then by contiguity within the column.

    The gap that separates two tables is NOT reliably larger than the gap
    inside one: on 1909.00741 page 7 the body of one table is 73pt and the
    space to the next is 73pt too. So this returns candidate bands and lets the
    CAPTION decide which is which, rather than inventing a threshold that page
    already disproves.
    """
    rules = [r for ln in page.lines for r in ln.rules]
    horiz = [r for r in rules
             if (r.rect[2] - r.rect[0]) > 3 * max(r.rect[3] - r.rect[1], 0.1)]
    by_span: dict = {}
    for r in horiz:
        key = (round(r.rect[0] / 6.0), round(r.rect[2] / 6.0))
        by_span.setdefault(key, []).append(r)
    out = []
    for key, rs in by_span.items():
        if len(rs) < 2:
            continue                       # one rule is a separator, not a table
        rs.sort(key=lambda r: -r.rect[3])
        out.append(rs)
    return out


def _modal_leading(page: PageNode) -> float:
    """The page's usual line spacing — the gap a table's rows sit at, and the
    unit a bigger gap is measured against."""
    gaps = [a.rect[3] - b.rect[3]
            for a, b in zip(page.lines, page.lines[1:])
            if a.glyphs and b.glyphs and 0 < a.rect[3] - b.rect[3] < 60]
    if not gaps:
        return 0.0
    rounded = [round(g, 1) for g in gaps]
    return max(set(rounded), key=rounded.count)


def table_regions(page: PageNode) -> list:
    """The tables on this page: each a rectangle, its rules, and its caption.

    THE CAPTION IS THE ANCHOR, because the rules alone cannot say where one
    table ends and the next begins. On 1909.00741 page 7 the body of a table is
    73pt tall and the space to the next table is also 73pt: any threshold that
    splits them splits the body too. A caption does not have that problem — it
    names its table, and the next caption in the same column bounds it.

    Caption ABOVE or BELOW, because both are printed: a table caption sits
    above in most styles and a figure caption below, and a reader that assumes
    one loses the other. The caption taken is the NEAREST one in the column,
    on whichever side, that no closer rule separates from the table.

    A rule cluster with no caption yields no table. It is a rule cluster — a
    form, a letterhead, a signature line — and calling it a table would put an
    empty `tabular` into every projection of a letter.
    """
    clusters = _rule_clusters(page)
    if not clusters:
        return []
    caps = [(i, ln, c) for i, ln in enumerate(page.lines)
            if ln.glyphs and (c := _caption_of(ln)) and c["label"] == "table"]
    if not caps:
        return []
    out = []
    for rs in clusters:
        x0 = min(r.rect[0] for r in rs); x1 = max(r.rect[2] for r in rs)
        # captions in THIS column — x-overlap, not containment: a caption often
        # runs a little wider or narrower than the rules it names.
        col = [(i, ln, c) for i, ln, c in caps
               if min(ln.rect[2], x1) - max(ln.rect[0], x0) > 0.4 * (x1 - x0)]
        if not col:
            continue
        # ORDER, not the caption's own band. A caption line is often MERGED
        # with the table's header row — on 1909.00741 page 7 the line reading
        # `Table 2: Pool CL: Conservative AssessmentSystem Precisio…` is 37pt
        # tall and swallows the rules it should sit above. Its TOP is still
        # exactly where the table begins, so each caption owns the rules
        # between its own top and the next caption's top.
        col.sort(key=lambda t: -t[1].rect[3])
        for k, (ci, cln, c) in enumerate(col):
            # THE RULES SAY A TABLE IS HERE; THE CAPTIONS BOUND IT. Taking the
            # rules' own extent gave a rectangle 11.4pt tall — the band between
            # toprule and midrule — while the body sat 40pt below it, outside.
            # The band that contains a table is from its caption down to the
            # next caption in the column, and the rules inside that band are
            # what makes it a table rather than a paragraph.
            top_y = cln.rect[3]
            nxt = col[k + 1][1].rect[3] if k + 1 < len(col) else -1e9
            mine = [r for r in rs if nxt < r.rect[3] <= top_y]
            if len(mine) < 2:
                continue
            top = top_y
            # CONTAINED in this column, not merely overlapping it. The line
            # reader merges a two-column row into ONE full-width line, and such
            # a line overlaps a 240pt column by its whole width — so an overlap
            # test admitted it and the table came out 506pt wide, spanning both
            # columns. A line wider than the rules it sits under is not a row
            # of that table.
            band = [ln for ln in page.lines
                    if ln.glyphs and ln.rect[3] <= top and ln.rect[1] > nxt
                    and ln.rect[0] >= x0 - 6.0 and ln.rect[2] <= x1 + 6.0]
            band.sort(key=lambda ln: -ln.rect[3])
            # AND IT ENDS AT A GAP, not at the next caption. The next caption
            # can be most of a page away — Table 4's is 285pt below it — and a
            # band that runs that far swallows whatever sits between. A table
            # ends where its rows stop, which is the first vertical gap wider
            # than twice the leading.
            lead = _modal_leading(page) or 12.0
            inner = []
            for ln in band:
                if inner and inner[-1].rect[1] - ln.rect[3] > 2.0 * lead:
                    break
                inner.append(ln)
            last_rule = min(r.rect[1] for r in mine)
            bot = min([last_rule] + [ln.rect[1] for ln in inner])
            # PER TABLE, never back into the cluster. Widening `x0`/`x1`
            # themselves carried one table's extent into every later table in
            # the same cluster: Table 4 came out 506pt wide, spanning both
            # columns, because an earlier table had already stretched them.
            tx0 = min([x0] + [ln.rect[0] for ln in inner]) if inner else x0
            tx1 = max([x1] + [ln.rect[2] for ln in inner]) if inner else x1
            out.append({"rect": (tx0, bot, tx1, top), "rules": mine,
                        "caption_index": ci, "caption": c,
                        "lines": [page.lines.index(ln) for ln in inner]})
    return out


def _front_matter(pages: list[PageNode], fp, titles: set, running: set) -> tuple:
    """({authors lines}, {abstract lines}) — both bounded, or neither.

    These two are the reason `title` was worth doing first: each is defined by
    what SURROUNDS it, and the title is the upper bound.

    `authors` runs from the line after the title to the first heading on that
    page. `abstract` runs from the line after a heading that READS as an
    abstract label to the next heading. Both stop at something measured.

    AND BOTH ABSTAIN WHEN THE BOUND IS MISSING. A front matter with no heading
    after the title has no measurable end to its author block, and taking "the
    rest of the page" would swallow the first section of the paper. Absent is
    the correct answer; `text` is what those lines already were.

    The abstract LABEL stays `section_header`. The heading is not the abstract,
    it names it, and a consumer that wants the heading gone can drop it —
    a consumer that needs it back cannot invent it.
    """
    if not pages:
        return set(), set()
    page = next((p for p in pages if any(ln.glyphs for ln in p.lines)), None)
    if page is None:
        return set(), set()

    def is_heading(i: int, ln) -> bool:
        return bool(ln.glyphs and not ln.rotated
                    and (page.page, i) not in running
                    and (page.page, i) not in titles
                    and heading_level(ln, fp))

    idx = [i for i, ln in enumerate(page.lines)
           if ln.glyphs and docmodel._run_text(ln.glyphs).strip()]
    title_pos = [i for i in idx if (page.page, i) in titles]
    headings = [i for i in idx if is_heading(i, page.lines[i])]

    authors: set = set()
    if title_pos:
        after = [i for i in idx if i > max(title_pos)]
        stop = next((h for h in headings if h > max(title_pos)), None)
        if stop is not None:                      # bounded below by a heading
            authors = {(page.page, i) for i in after if i < stop
                       and (page.page, i) not in running}

    abstract: set = set()
    for h in headings:
        text = re.sub(r"[^a-zäöüßа-я]+", "",
                      docmodel._run_text(page.lines[h].glyphs).lower())
        if text not in _ABSTRACT_LABELS:
            continue
        nxt = next((x for x in headings if x > h), None)
        if nxt is None:
            break                                 # no end: do not guess one
        abstract = {(page.page, i) for i in idx if h < i < nxt
                    and (page.page, i) not in running}
        break
    return authors, abstract


def _footnote_lines(pages: list[PageNode], running: set) -> set:
    """{(page, line index)} for the footnote block at the foot of a page.

    A footnote is not where its MARKER is. The marker sits mid-paragraph and the
    body sits at the bottom of the column, so reading order places it wrongly
    and text matching places it on whatever prose is nearest. On 2510.04618 the
    footnote `We mention IBM CUGA as a rough contextual reference…` was absorbed
    into a Paragraph, because every line of that document is typed `text`.

    TWO MEASURED PROPERTIES, AND NOT THE ONE THE SPEC ASSUMED. The spec wrote
    "below the column's last body line, under a horizontal rule, at a size below
    body" — and that document draws NO footnote rule: its only rules are the
    table's, 300pt higher up. Requiring one would miss every footnote in it. So
    the rule is corroborating when present and never required; what is required
    is measurable without it:

        the line sits BELOW the lowest body-size line on the page, and
        its type size is SMALLER than the page's modal body size.

    Measured there: body 10.0pt, footnote 8.97pt, last body line at y 123 and
    the footnote at y 99 and 79.

    A page whose sizes are uniform has no footnote to find — abstaining is the
    answer, because calling its last lines a footnote deletes them from the
    prose.
    """
    out: set = set()
    for p in pages:
        live = [(i, ln) for i, ln in enumerate(p.lines)
                if ln.glyphs and not ln.rotated
                and docmodel._run_text(ln.glyphs).strip()
                and (p.page, i) not in running]
        if len(live) < 6:
            continue
        sizes = [line_size(ln) for _i, ln in live]
        body = collections.Counter(round(s, 1) for s in sizes).most_common(1)[0][0]
        if body <= 0:
            continue
        # PER COLUMN. On a two-column paper the left column's footnote is not
        # below the right column's last body line, so one floor for the page
        # finds nothing — 1909.00741 has four footnotes and yielded none.
        member = {}
        try:
            member = column_membership(p)
        except Exception:                        # noqa: BLE001
            member = {}
        groups: dict = {}
        for i, ln in live:
            groups.setdefault(member.get(i, 0), []).append((i, ln))
        for _col, mine in groups.items():
            # THE BODY LINE'S TOP, not its bottom. The line reader merges rows,
            # so the lowest body line on 2510.04618 page 8 is 28pt tall and its
            # BOTTOM (94.5) sits above the footnote at 99.1 — which excluded the
            # footnote's first line and kept only its second. A top is a firm
            # landmark whatever the line swallowed.
            tops = [ln.rect[3] for _i, ln in mine
                    if line_size(ln) >= 0.95 * body]
            if not tops:
                continue
            floor = min(tops)
            cand = [(i, ln) for i, ln in mine
                    if ln.rect[3] < floor and line_size(ln) < 0.95 * body]
            out.update((p.page, i) for i, _ln in cand)
    return out


def classify_lines(pages: list[PageNode]) -> dict:
    """{(page number, line index): (type, extra fields)} for the whole document.

    THE ORDER IS THE ORDER OF CERTAINTY. A listing is bounded by a drawn
    rectangle or a monospace grid and does not depend on reading the text; a
    heading is a font-size rank; a display is an indent past the body margin.
    The softest test — "these glyphs are in a maths family" — runs last, so it
    can never overrule a harder one. Anything not established stays `text`,
    which is what an unread line has always been.

    One pass over the document, because the heading test needs the document's
    FONT PROFILE and the display test needs each page's margins: deciding a
    line's type in isolation is what makes a classifier disagree with itself
    from one page to the next.
    """
    fp = profile(pages)
    # Document-level types FIRST: both are decided across pages, and both would
    # otherwise be claimed by `section_header`, which asks only about size. A
    # running header is often bold, and a title is by definition the largest
    # thing on the page.
    running = _running_lines(pages)
    titles = _title_lines(pages)
    authors, abstract = _front_matter(pages, fp, titles, running)
    footnotes = _footnote_lines(pages, running)
    out: dict = {}
    for p in pages:
        left, right = _left_margin(p), _right_margin(p)
        listings = _listing_rows(p)
        for i, ln in enumerate(p.lines):
            if not ln.glyphs:
                out[(p.page, i)] = ("text", {})
                continue
            if (p.page, i) in running:
                out[(p.page, i)] = ("page_info", {})
                continue
            if (p.page, i) in titles:
                out[(p.page, i)] = ("title", {})
                continue
            if (p.page, i) in authors:
                out[(p.page, i)] = ("authors", {})
                continue
            if (p.page, i) in abstract:
                out[(p.page, i)] = ("abstract", {})
                continue
            # A caption before a heading: `Table 2: …` set in bold can rank as
            # one, and a caption read as a section splits the document there.
            cap = _caption_of(ln)
            if cap:
                out[(p.page, i)] = ("caption",
                                    {"label": cap["label"],
                                     "number": cap["number"]})
                continue
            # AFTER caption, because a figure at the foot of a page puts its
            # caption below the last body line at a smaller size too — and the
            # caption has a LABEL, which is the harder evidence.
            if (p.page, i) in footnotes:
                out[(p.page, i)] = ("footnote", {})
                continue
            lst = listings.get(i)
            if lst is not None:
                extra = {}
                lang = getattr(lst, "language", None)
                if lang:
                    extra["language"] = lang
                out[(p.page, i)] = ("code", extra)
                continue
            level = heading_level(ln, fp)
            if level:
                out[(p.page, i)] = ("section_header", {"level": level})
                continue
            # 814 — AFTER the whole-line test, because a line that is bold all
            # the way across is an ordinary heading and `heading_level` ranks
            # it properly; only a line that is bold at the FRONT and plain
            # after a 1 em gap is a run-in heading. The line stays `text` — it
            # still holds prose — and carries where the heading ends, so
            # `to_lines_json` can emit the heading and the prose as the two
            # lines they logically are, each with its own rectangle.
            k = runin_heading(ln, fp)
            if k:
                out[(p.page, i)] = ("text", {"runin_split": k,
                                             "runin_level": _RUNIN_LEVEL})
                continue
            if ln.rotated:
                # SIDEWAYS TEXT IS ITS OWN KIND. Established by the CTM, not by
                # reading: the glyphs' text matrix is rotated off the page axis.
                # It is never part of the flow — it is a stamp, a margin note,
                # a spine title — and typing it `text` put an arXiv identifier
                # into the running prose of the paper it identifies.
                #
                # MathPix has no name for this, so the name is ours, and it
                # matches the property `pageprofile` already reports
                # (`rotated-text`). The angle rides along, because a reader
                # deciding whether to rotate a crop needs it and re-deriving it
                # from a rectangle is impossible.
                out[(p.page, i)] = ("rotated_text", {"rotation": _rotation_of(ln)})
                continue
            if is_display(ln, left, right):
                out[(p.page, i)] = ("equation", {})
                continue
            if sum(1 for g in ln.glyphs if g.is_math) >= 0.6 * len(ln.glyphs):
                out[(p.page, i)] = ("math", {})
                continue
            # LAST, THE NODE'S OWN VERDICT. `LineNode.type` is already
            # "formula" for a line the span reader read as mathematics, and it
            # is a better signal than the glyph-family count for a line of
            # prose with one inline expression in it. Dropping to a literal
            # "text" here lost all 23 formula lines of 1107.2723 — a
            # classifier that knows less than the node it is classifying.
            # `formula` is spelled `math` because that is the word pdfdrill's
            # modules read; `equation` above is the display case.
            out[(p.page, i)] = ("math" if ln.type == "formula" else "text", {})
    return out


def column_membership(page: PageNode) -> dict:
    """{line index: column number} for every line with glyphs on this page.

    The CONTAINER MathPix makes a root and we had nothing for. Its export nests
    almost everything one level down from a `column` — 528 of 1269 lines on
    1909.00741 are `column -> text` — and that nesting is not decoration: it is
    the reading order of a two-column paper, stated rather than guessed by
    whoever consumes the flat list.

    Membership is decided by the line's own x-range against the column bounds
    `columns()` already measures, by OVERLAP rather than by midpoint: a wide
    line (a title, a full-width caption) straddles both columns and belongs to
    the one it covers most, which is the answer a reader would give.
    """
    cols = columns(page)
    if not cols:
        return {}
    out: dict = {}
    for i, ln in enumerate(page.lines):
        if not ln.glyphs:
            continue
        x0, x1 = ln.rect[0], ln.rect[2]
        best, best_ov = 0, -1.0
        for k, (cl, cr) in enumerate(cols):
            ov = min(x1, cr) - max(x0, cl)
            if ov > best_ov:
                best, best_ov = k, ov
        out[i] = best
    return out


def font_report(pages: list[PageNode]) -> str:
    """Document the type sizes and fonts, and what was inferred from them.

    A PDF does not say which lines are headings. This table is the evidence
    behind that inference, so a wrong heading can be traced to the measurement
    that produced it rather than argued about.
    """
    fp = profile(pages)
    total = sum(fp.sizes.values())
    rows = ["| size (pt) | glyphs | share | rank | meaning |",
            "|---:|---:|---:|---:|---|"]
    meaning = {0: "body / smaller", 1: "###", 2: "##", 3: "#"}
    for size, n in sorted(fp.sizes.items(), key=lambda kv: -kv[1])[:12]:
        r = fp.rank(size)
        rows.append(f"| {size} | {n} | {100.0 * n / max(total, 1):.1f}% | "
                    f"{r} | {meaning[r]} |")
    frows = ["", "| font | glyphs | share | bold? |", "|---|---:|---:|:--:|"]
    ftotal = sum(fp.fonts.values())
    for f, n in fp.fonts.most_common(12):
        frows.append(f"| `{f}` | {n} | {100.0 * n / max(ftotal, 1):.1f}% | "
                     f"{'yes' if _is_bold(f) else ''} |")
    head = [
        "## Font profile",
        "",
        f"Body text: **{fp.body_size} pt** in `{fp.body_font}` "
        f"(the size most glyphs are set in, not the smallest).",
        "",
        "Heading levels are inferred from size relative to body, or from a "
        "bold-only line short enough not to be a paragraph. Nothing in the PDF "
        "states them.",
        "",
    ]
    return "\n".join(head + rows + frows) + "\n"
