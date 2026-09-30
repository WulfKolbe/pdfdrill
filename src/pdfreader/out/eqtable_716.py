#!/usr/bin/env python3
r"""716 — the display-equation comparison as a LaTeX table, built with the
report machinery that already works.

714 built this as an HTML page with KaTeX. That was me inventing a second
pipeline beside the one this project already has. `reports/tex.py` is the
precedent and every piece of it applies here:

    rt.preamble(...)                    the package set, Unicode fallbacks
    rt.table_open(caption, widths,      a longtable, with CUSTOM heads --
                  heads=...)            the one existing caller that passes
                                        `heads` is reports/tex.py:103
    " & ".join(cells) + r" \\ \hline"   the row
    rt.display_safe(latex)              WILL this typeset? (to_inline_env
                                        mapped, then renderable)
    \FitMath{$\displaystyle ...$}       shrink an over-wide expression into
                                        its column instead of overflowing
    rt.compile_fixpoint(tex)            compile to the fixpoint

FOUR COLUMNS, as asked: No | gold | MathPix | pdf2mmd. The document is the
table's caption, which is what a caption is for here -- `table_open`'s own
comment says the caption names the POPULATION a table holds.

THE CELL GATE MATTERS MORE THAN IT LOOKS. The gold column carries real author
LaTeX (`eqnarray`, `\resizebox`, `\mathds`, `{1 \over ...}`) and pdf2mmd
carries expressions that are not valid LaTeX at all (`\midD`, `\ellmn`, a
lone `\left[`). Without `display_safe` those abort the compile rather than
showing as one marked cell. A cell that will not typeset says so, in place --
never a blank, which would be indistinguishable from "this source read
nothing here".

ROWS ARE NOT ALIGNED ACROSS COLUMNS. MathPix agrees with gold on the
equation count in 96 of 102 documents; pdf2mmd in 7. pdf2mmd splits one
display equation into several blocks, so its Nth block is not the Nth of the
others. Each column is listed in its own order and the per-document counts
are printed in the caption, so a mismatch is visible rather than implied
away.

LICENCE: golden/ is TEES, Texas A&M -- "not to be reproduced or disclosed
without written authorization". This writes a LOCAL pdf and nothing else.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

#: WHERE THE DATA IS. Code lives in this repo; the corpus does not.
#: Override either with an environment variable.
LIB = Path(os.environ.get("PDF2MMD_LIBRARY",
                          Path.home() / "pdfdrill-library"))
#: `report_tex` supplies the preamble and the demote-to-fixpoint compile.
#: It belongs to PDFDRILL, a separate repository.
sys.path.insert(0, os.environ.get("PDFDRILL_SRC",
                                  str(Path.home() / "MX/PDFDRILL/src")))
from pdfdrill import report_tex as rt          # noqa: E402

#: 759 -- `alignat` TAKES AN ARGUMENT, and was not in this list at all.
#: Audited: over the 102 gold files every display environment that occurs
#: standalone is here. `array` occurs 28 times and `split` once, and both
#: are always INSIDE one of these -- checked, zero standalone -- so they are
#: counted through the outer environment and must not be listed, or they
#: would be counted twice. `alignat*` occurs once, in wzlxjtu-082, and is
#: NOT nested: it follows the prose "The functions $p_k(h)$ are". That gold
#: equation had never been counted, and MathPix's one unmatched block in
#: that document is exactly it.
ENVS = ("equation*", "equation", "eqnarray*", "eqnarray", "align*", "align",
        "alignat*", "alignat",
        "gather*", "gather", "multline*", "multline", "displaymath")

#: `\begin{alignat*}{3}` — the column count is an ARGUMENT, not content.
_ENV_ARG = re.compile(r"^\s*\{[^{}]*\}")

#: display_safe()/renderable() judge an expression for a `$...$` cell, so a
#: display environment must first be mapped to its in-math counterpart --
#: exactly what to_inline_env does for the report's own Rendered column.
_ENV_MAP = {"eqnarray": "aligned", "eqnarray*": "aligned",
            "align": "aligned", "align*": "aligned",
            "alignat": "aligned", "alignat*": "aligned",
            "gather": "gathered", "gather*": "gathered",
            "multline": "gathered", "multline*": "gathered"}


_RESIZE = re.compile(r"\\resizebox\s*\{[^{}]*\}\s*\{[^{}]*\}\s*\{\s*\$(.*)\$\s*\}\s*$",
                     re.S)


def unbox(s: str) -> str:
    r"""Drop a `\resizebox` that wraps the whole formula, keeping the maths.

    THE AUTHOR'S SCALING IS NOT OURS. wzlxjtu-002 sets its second display as
    `\resizebox{0.88\linewidth}{!}{$\displaystyle ...$}` -- a BOX, not
    mathematics, so `$\displaystyle \resizebox{...}{$...$}$` nests `$` inside
    `$` and cannot compile: the one gold cell in the whole table that would
    not typeset.

    And `0.88\linewidth` is meaningless here anyway. It means 88% of the
    AUTHOR's column; this table sets the same formula in a third of an A3
    landscape page. Every length in a projected formula is relative to a page
    that is not the page it is being set on, which is the general form of the
    problem. `\FitMath` already shrinks an over-wide expression into its
    column, measured against THIS column, so the author's box is not only
    unusable but unnecessary.
    """
    m = _RESIZE.match(s.strip())
    return m.group(1).strip() if m else s


def strip_noise(s: str) -> str:
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    # 739 -- `\tag{3}` is the equation NUMBER, which this reader now states
    # in the markdown because markdown numbers nothing itself. It is not part
    # of the mathematics and must not decide a match.
    s = re.sub(r"\\tag\*?\{[^}]*\}", "", s)
    s = re.sub(r"\\nonumber|\\notag", "", s)
    s = re.sub(r"%.*?$", "", s, flags=re.M)
    return unbox(s.strip())


#: 764 -- `align` NUMBERS EVERY ROW, so every row is an equation.
#:
#: wzlxjtu-031's third gold equation is
#:
#:     \begin{align} A&=e^{\rho}V_1^2dz+V_0^2d\rho\\
#:                   \bar{A}&=e^{\rho}V_{-1}^2d\bar{z}-V_0^2d\rho \end{align}
#:
#: and the page it produces shows TWO numbered displays, (3) and (4). This
#: reader reads both, exactly, and emitted them as two blocks -- so one of
#: them matched the single gold row and the other was listed as matching no
#: gold equation at all. The reading was right and the measurement said it
#: was half right.
#:
#: This is the SAME rule the reader already uses (739: a display that carries
#: its own number is an equation, not a row), applied to the other side of
#: the comparison. A starred environment numbers nothing, so it stays one;
#: rows carrying `\nonumber` are continuation lines and join the numbered row
#: that follows them, which is how an author breaks one long equation.
#:
#: Over the 102 gold files this splits 18 rows out of 423 equations -- 17 in
#: `align`, 1 in `gather`, none in `eqnarray`, whose 122 occurrences in this
#: corpus are one equation each.
_NUMBERED_ENV = {"align", "eqnarray", "gather", "alignat", "flalign"}


def top_rows(body: str) -> list:
    r"""Split on `\\` at brace depth 0 and outside any nested environment.

    A regex cannot do this: `\\` inside a `cases`, an `array` or a `substack`
    is a row of THAT, not of the display around it.
    """
    rows, buf, depth, env, i = [], [], 0, 0, 0
    while i < len(body):
        c = body[i]
        if body.startswith(r"\begin{", i):
            env += 1; buf.append(body[i:i + 7]); i += 7; continue
        if body.startswith(r"\end{", i):
            env -= 1; buf.append(body[i:i + 5]); i += 5; continue
        if body.startswith("\\\\", i) and depth == 0 and env == 0:
            rows.append("".join(buf)); buf = []; i += 2
            while i < len(body) and body[i] in " \n\t":
                i += 1
            if i < len(body) and body[i] == "[":      # `\\[2mm]`, a skip
                j = body.find("]", i)
                if 0 < j < i + 12:
                    i = j + 1
            continue
        if c == "\\" and i + 1 < len(body) and not body[i + 1].isalpha():
            buf.append(body[i:i + 2]); i += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        buf.append(c); i += 1
    rows.append("".join(buf))
    return rows


def numbered_rows(env: str, body: str) -> list:
    """One entry per equation NUMBER this environment produces."""
    if env.endswith("*") or env.rstrip("*") not in _NUMBERED_ENV:
        return [body]
    rows = top_rows(body)
    if len(rows) < 2:
        return [body]
    out, pending = [], []
    for r in rows:
        pending.append(r)
        if not re.search(r"\\nonumber|\\notag", r):
            out.append("\\\\".join(pending)); pending = []
    if pending:                      # a trailing unnumbered row
        out.append("\\\\".join(pending))
    out = [r for r in out if r.strip()]
    return out or [body]


def gold_equations(tex: Path) -> list:
    """Display maths from the author's LaTeX, in document order.

    The gold sources use `\\begin{equation}` and friends, never `$$`: measured
    across all 102 -- eqnarray 122, equation 85, equation* 62, gather* 55,
    align 40, align* 36, array 28, gather 9, \\[..\\] 6, multline 4, split 1,
    and `$$` ZERO times.
    """
    t = tex.read_text(encoding="utf-8", errors="replace")
    out, seen = [], []
    for env in ENVS:
        for m in re.finditer(r"\\begin\{" + re.escape(env) + r"\}(.*?)\\end\{"
                             + re.escape(env) + r"\}", t, re.S):
            # ONLY alignat takes an argument. Stripping a leading braced
            # group from every environment ate real mathematics: wzlxjtu-026's
            # `{\cal C}^2 = 1` lost its `{\cal C}`, and the corpus correct
            # count fell by nine equations for a change that was meant to add
            # one.
            body = (_ENV_ARG.sub("", m.group(1))
                    if env.startswith("alignat") else m.group(1))
            for k, row in enumerate(numbered_rows(env, body)):
                # Ordering only: the rows of one environment keep their order
                # among themselves and stay where the environment was.
                out.append((m.start() + k, env, strip_noise(row)))
            seen.append((m.start(), m.end()))

    def covered(pos):
        return any(a <= pos < b for a, b in seen)

    for m in re.finditer(r"\\\[(.*?)\\\]", t, re.S):
        if not covered(m.start()):
            out.append((m.start(), r"\[..\]", strip_noise(m.group(1))))
            seen.append((m.start(), m.end()))

    # 736 -- A CENTRED MATHS BLOCK IS A DISPLAY EQUATION.
    #
    # wzlxjtu-003 reported zero gold equations while its page carries three,
    # and both readers found all three. The gold transcription sets them
    # without any display environment at all:
    #
    #   \begin{center}$\displaystyle \mathcal{M}=\frac{SO(4,n)}{...}$  (3)
    #   \end{center}
    #
    # That IS a display equation -- centred, on its own, with its number --
    # and this table was calling it nothing. Six documents return no gold; the
    # other five are prose pages where both readers also produce nothing, so
    # they are right. This one was a gap in the MEASUREMENT.
    #
    # Only a `center` whose content is mathematics counts. A centred FIGURE,
    # caption or heading is not an equation, so the block must carry `$...$`
    # and the text outside it must be an equation number or nothing.
    for m in re.finditer(r"\\begin\{center\}(.*?)\\end\{center\}", t, re.S):
        if covered(m.start()):
            continue
        inner = m.group(1)
        maths = re.findall(r"(?<!\\)\$(.+?)(?<!\\)\$", inner, re.S)
        if not maths:
            continue
        rest = re.sub(r"(?<!\\)\$.+?(?<!\\)\$", "", inner, flags=re.S)
        rest = re.sub(r"\(\d+(?:\.\d+)*\)|\\label\{[^}]*\}|\s+", "", rest)
        if rest:
            continue              # centred prose or a figure, not an equation
        out.append((m.start(), "center", strip_noise(" ".join(maths))))
    out.sort()
    return [(env, body) for _, env, body in out if body]


#: 755 -- AN EMPTY CELL MEANS TWO DIFFERENT THINGS.
#:
#: "no match" was printed both when a source never read an equation and when
#: it read it and set it INLINE, in a `$...$` inside a paragraph. This table
#: compares DISPLAY blocks, so the second case looked exactly like the first.
#:
#: wzlxjtu-082's fifth equation is four rows of residues. MathPix has the
#: first of those four, as inline maths in the middle of a sentence; the cell
#: said "no match" and read as a rendering failure. It is not one -- nothing
#: on that page fails to typeset. It is a reading that was demoted.
#:
#: Distinguishing the two costs nothing and says something: a source that
#: demoted a display to inline is a different defect from one that missed it.
def inline_math(md: Path) -> list:
    r"""The `$...$` spans of a markdown file, display blocks removed first."""
    if not md.is_file():
        return []
    t = md.read_text(encoding="utf-8", errors="replace")
    t = re.sub(r"^\$\$\s*$.*?^\$\$\s*$", "\n", t, flags=re.S | re.M)
    out = [strip_noise(b) for b in re.findall(r"(?<!\$)\$([^$\n]{8,})\$(?!\$)", t)]
    return [b for b in out if b]


def md_blocks(md: Path) -> list:
    r"""The display-maths blocks of a markdown file.

    758 -- `$$` IS A DELIMITER WHEREVER IT IS, not only alone on a line.
    This matched `^\$\$\s*$` at both ends, and a producer is not obliged to
    put the delimiter on a line of its own. wzlxjtu-041 opens

        a) and Assumption 4a, ... are identified:$$
        \theta_{1}^{n}=\theta_{1}^{1,0}(1) \text { and } ...
        $$

    with the OPENING `$$` glued to the prose. Invisible to that pattern, so
    the parser paired the CLOSING `$$` with the next one and captured the
    prose between them. Every equation in the document was skipped and four
    paragraphs of prose were read as equations; MathPix scored 0 of 6 there
    and the fault was here.

    wzlxjtu-071 fails the same test from the other side: one closing `$$` is
    followed by inline maths on the same line, so it was not a closer either,
    and two equations plus the prose between them came back as ONE block.

    Splitting on the delimiter instead: the odd segments are inside display
    maths. Measured over all 204 markdown files in the corpus -- 202
    unchanged, and the two that change are these two, both correct after.
    """
    if not md.is_file():
        return []
    t = md.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"(?<!\\)\$\$", t)
    return [strip_noise(b) for i, b in enumerate(parts)
            if i % 2 == 1 and strip_noise(b)]


def as_inline(env: str, body: str) -> str:
    mapped = _ENV_MAP.get(env)
    if mapped:
        return "\\begin{%s}%s\\end{%s}" % (mapped, body, mapped)
    return body


#: 744 — ROWS ARE MATCHED BY CONTENT, NOT BY POSITION.
#:
#: This file used to take the Nth block of each source for row N, and said so:
#: pdf2mmd emitted 817 blocks against the author's 421, so no pairing was
#: possible and listing each column in its own order was the honest choice.
#:
#: It is now 361 against 421, and that changes what the table is FOR -- it can
#: be read across a row. Positional pairing then becomes actively misleading:
#: one equation deferred early shifts every row below it by one, so the first
#: row is right and everything after it shows the NEXT equation's reading
#: beside this equation's gold. Which is exactly what it looked like.
#:
#: Each gold equation now draws its best match from each source, one block used
#: at most once, assigned globally best-first so a single miss cannot cascade.
#: Anything a source emitted that matched no gold equation is listed after the
#: document's rows rather than dropped, because a block with nowhere to go is a
#: finding, not noise.
_SYN = {r'\varepsilon': r'\epsilon', r'\varphi': r'\phi', r'\leqslant': r'\le',
        r'\geqslant': r'\ge', r'\leq': r'\le', r'\geq': r'\ge',
        r'\rightarrow': r'\to', r'\widehat': r'\hat', r'\overline': r'\bar',
        r'\prime': "'", r'\cdots': r'\ldots', r'\dots': r'\ldots',
        # 749 -- `\mid` and `|` are the SAME character; `\mid` only adds
        # relation spacing. Gold writes `|` for "given that" and this reader
        # writes `\mid`, so every conditional expectation differed on every
        # bar. Per row that cost 1.000 -> 0.787, and over a three-row block
        # enough to put the WHOLE BLOCK (0.445) below a SINGLE ROW (0.470):
        # wzlxjtu-065 showed only the third row of each of its two
        # equations, in the MathPix column and in ours, while both .md files
        # held all three. The same synonym was added to `canon.py` in 739;
        # this matcher never got it.
        r'\mid': '|', r'\vert': '|', r'\Vert': r'\|',
        r'\parallel': r'\|'}
# 758: `\mbox` is `\text`. Gold writes `\mbox{ and }` where MathPix writes
# `\text { and }`, and with only one of them stripped the two keys differed
# by a whole token -- wzlxjtu-041's first equation, identical in both.
_FONT = re.compile(r'\\(mathcal|mathrm|mathbb|mathbf|mathit|mathds|boldsymbol'
                   r'|bm|text|mbox|hbox|cal|bf|rm|it)\s*')
_SIZE = re.compile(r'\\(left|right|bigg?|Bigg?)(l|r|m)?(?![A-Za-z])')
_SPACE = re.compile(r'\\[,;:!>]|\\quad|\\qquad|\\hspace\{[^}]*\}|~')
_NOISE = re.compile(r'\\label\{[^}]*\}|\\notag|\\nonumber|\\displaystyle|\\!')
_ENVW = re.compile(r'\\(begin|end)\{(aligned|gathered|array|split)\}(\{[^}]*\})?')
_OVER = re.compile(r'\{\s*([^{}]*?)\s*\\over\s*([^{}]*?)\s*\}')


def key(x: str) -> str:
    """A spelling-independent form, for MATCHING only -- never for display."""
    x = _NOISE.sub("", x)
    x = _ENVW.sub("", x)
    x = _SIZE.sub("", x)
    x = _SPACE.sub("", x)
    x = _FONT.sub("", x)
    for _ in range(4):
        x = _OVER.sub(r"\\frac{\1}{\2}", x)
    for a, b in _SYN.items():
        x = x.replace(a, b)
    return re.sub(r"[{}\s&]|\\\\", "", x)


_ALIGNED = re.compile(r"\\begin\{aligned\}(.*)\\end\{aligned\}", re.S)


def units(blocks: list) -> list:
    r"""Every unit a gold equation could match: whole blocks, and their ROWS.

    745 — ONE BLOCK CAN HOLD SEVERAL GOLD EQUATIONS. A fused run is emitted as
    `\begin{aligned} ... \\ ... \end{aligned}`, and its rows may be different
    authored equations. Matching whole blocks one-to-one therefore reported
    "no match" for an equation whose text was sitting inside a block another
    equation had already claimed -- wzlxjtu-014's tenth display against a
    block holding its ninth, at 37%, with its own row right there.

    Returns (block index, row index or None, text). The whole block is offered
    as well as its rows, because a multi-row gold equation matches the block.
    """
    out = []
    for j, b in enumerate(blocks):
        out.append((j, None, b))
        m = _ALIGNED.search(b)
        rows = (m.group(1) if m else b).split(r"\\")
        if len(rows) > 1:
            for k, r in enumerate(rows):
                if r.strip():
                    out.append((j, k, r.strip()))
    return out


def align(gold: list, blocks: list) -> tuple:
    """(match per gold equation or None, indices of wholly unmatched blocks).

    A match is (block index, row index or None); `cell_text` renders it.
    """
    from difflib import SequenceMatcher
    gk = [key(b) for _, b in gold]
    cands = units(blocks)
    ck = [key(txt) for _, _, txt in cands]
    scored = []
    for i, a in enumerate(gk):
        if not a:
            continue
        for c, b in enumerate(ck):
            if not b:
                continue
            r = SequenceMatcher(None, a, b).ratio()
            if r >= 0.35:
                scored.append((r, i, c))
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))
    out = [None] * len(gold)
    taken = set()                      # (block, row) already spoken for
    def claims(c):
        j, k, _ = cands[c]
        if k is None:
            return {(j, kk) for jj, kk, _ in cands if jj == j}
        return {(j, k), (j, None)}
    for _, i, c in scored:
        if out[i] is not None:
            continue
        if claims(c) & taken:
            continue
        out[i] = (cands[c][0], cands[c][1])
        taken |= claims(c)
    touched = {j for j, _ in taken}
    return out, [j for j in range(len(blocks)) if j not in touched]


def cell_text(blocks: list, hit) -> str:
    r"""The text of a match, which may be one ROW of a block.

    A row lifted out of an `aligned` can be unbalanced on its own -- the
    `\left` that opens it may be closed on the next row -- and then the cell
    will not typeset at all. Where that happens the WHOLE block is shown
    instead: a row that cannot be rendered says less than the block it came
    from, and the point of the cell is to be read.
    """
    if hit is None:
        return ""
    j, k = hit
    if k is None:
        return blocks[j]
    m = _ALIGNED.search(blocks[j])
    rows = (m.group(1) if m else blocks[j]).split(r"\\")
    if k >= len(rows):
        return blocks[j]
    row = rows[k].strip()
    return row if rt.display_safe(row) else blocks[j]


#: 738 -- A LEADING `&` IS FATAL UNDER MATHTOOLS.
#:
#: `\begin{aligned}&\log x\end{aligned}` compiles under amsmath alone and
#: FAILS with mathtools also loaded, which this table loads:
#:
#:     ! Missing control sequence inserted.  <inserted text> \inaccessible
#:     Please don't say `\def cs{...}', say `\def\cs{...}'.
#:
#: Bisected: the trigger is an `&` as the FIRST TOKEN of the environment
#: body, and the damage then surfaces at the next `\nolimits` operator --
#: `\log`, `\sin`; `\min` is unaffected because it takes limits. An author
#: who writes `align` with the tab before the first term produces exactly
#: that shape, and gold does it often.
#:
#: One fatal row aborted the WHOLE table -- "No pages of output" -- and the
#: demote fixpoint then had to tear rows out until it compiled. That is
#: where most of the eleven "(not rendered)" came from; only three were the
#: cell's own fault.
#:
#: `{}` before the tab is enough: the first cell of an `aligned` row is
#: empty either way, so nothing moves.
_LEAD_AMP = re.compile(
    r"(\\begin\{(?:aligned|split|gathered|alignedat)\}(?:\[[^\]]*\])?"
    r"(?:\{[^}]*\})?)\s*&")


def guard_leading_amp(s: str) -> str:
    return _LEAD_AMP.sub(r"\1{}&", s)


#: 738 -- EVERY CELL JUDGED ON ITS OWN.
#:
#: `compile_fixpoint` demotes a ROW whose LINE errors, because that is all
#: xelatex reports: `l.838`, never "the second cell". Three columns share a
#: line, so a broken MathPix reading took the gold reading down with it --
#: and the gold column is the one that must never say "(not rendered)",
#: because it is the thing everything else is being compared against.
#:
#: So each cell is set ON ITS OWN LINE in a probe document and compiled once.
#: Now a line number IS a cell. A cell that fails is shown as its source,
#: marked, and its neighbours are left alone.
#:
#: Iterated, because TeX cascades: a runaway in one box can throw errors on
#: the lines after it. Each pass drops the cells already known bad and runs
#: again, so a cascade victim gets a clean second look. Converges in two or
#: three passes over this corpus.
_PROBE_MAX_PASSES = 60


def unrenderable_cells(bodies: list, preamble: str, work: Path) -> set:
    r"""Which of these `$\displaystyle` bodies will not typeset, each alone.

    ONE CULPRIT PER PASS. TeX cascades: a box that runs away throws errors on
    the lines after it too, so a pass that believed every `l.<n>` it saw
    marked innocent cells and never took the mark back. Only the FIRST
    erroring line of a pass is a verdict; everything after it may be the
    wreckage. That cell is dropped and the probe runs again, so each pass
    convicts exactly one and the rest get a clean look.
    """
    import subprocess
    todo = list(dict.fromkeys(b for b in bodies if b))
    bad: set = set()
    for _ in range(_PROBE_MAX_PASSES):
        live = [b for b in todo if b not in bad]
        if not live:
            break
        lines = [preamble]
        # the preamble is ONE list item and MANY lines; count its newlines
        first = preamble.count("\n") + 2
        lines += ["\\begingroup\\setbox0=\\hbox{$\\displaystyle " + b
                  + r"$}\endgroup" for b in live]
        lines += [r"\mbox{}", r"\end{document}", ""]
        probe = work / "cellprobe.tex"
        probe.write_text("\n".join(lines), encoding="utf-8")
        subprocess.run(["xelatex", "-interaction=nonstopmode", "-no-shell-escape",
                        "-output-directory", str(work), str(probe)],
                       capture_output=True, text=True, timeout=1800)
        log = work / "cellprobe.log"
        txt = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        hit = sorted({int(n) for n in re.findall(r"(?m)^l\.(\d+)", txt)})
        idx = [n - first for n in hit if 0 <= n - first < len(live)]
        if not idx:
            break
        bad.add(live[min(idx)])

    # 754 -- AND CONVICT NOBODY WITHOUT A TRIAL OF THEIR OWN.
    #
    # "One culprit per pass" narrows a cascade; it does not eliminate one.
    # TeX reports the line where it NOTICED a problem, which after a runaway
    # can be a later cell that is perfectly good. wzlxjtu-073's
    #
    #     m_{ij} = \text{\#} \{k : (i, j, k) \in J \}.
    #
    # was marked unrenderable, and compiles clean ALONE, under the real
    # preamble, in this probe's exact \hbox form. It was a bystander.
    #
    # Each conviction is now re-tried on its own, which is the one test with
    # no cascade in it. A cell that compiles alone is cleared. One short
    # compile per convicted cell, and there are never many.
    cleared = set()
    for _b in bad:
        probe = work / "cellone.tex"
        probe.write_text("\n".join(
            [preamble,
             r"\begingroup\setbox0=\hbox{$\displaystyle " + _b + r"$}\endgroup",
             r"\mbox{}", r"\end{document}", ""]), encoding="utf-8")
        subprocess.run(["xelatex", "-interaction=nonstopmode", "-no-shell-escape",
                        "-output-directory", str(work), str(probe)],
                       capture_output=True, text=True, timeout=600)
        log = work / "cellone.log"
        txt = (log.read_text(encoding="utf-8", errors="replace")
               if log.is_file() else "! ")
        if not re.search(r"(?m)^! ", txt):
            cleared.add(_b)
    return bad - cleared


_FITMATH = re.compile(r"\\FitMath\{\$\\displaystyle ((?:[^$\\]|\\.)*)\$\}")


def mark_unrenderable(tex: Path) -> int:
    r"""Replace every cell that will not typeset with its source, marked.

    Runs on the FINISHED document, so what is judged is exactly what will be
    compiled. Returns how many cells were marked.
    """
    doc = tex.read_text(encoding="utf-8")
    head, sep, _ = doc.partition("\\begin{document}")
    if not sep:
        return 0
    bodies = _FITMATH.findall(doc)
    bad = unrenderable_cells(bodies, head + sep, tex.parent)
    if not bad:
        return 0

    def sub(m):
        if m.group(1) not in bad:
            return m.group(0)
        return ("{\\ttfamily\\tiny %s}\\par{\\footnotesize\\itshape "
                "(will not typeset)}" % rt.esc_source(m.group(1)))

    tex.write_text(_FITMATH.sub(sub, doc), encoding="utf-8")
    return len(bad)


def cell(body: str, env: str = "") -> str:
    r"""A typeset cell, or the source marked as unrenderable -- never blank."""
    if not body:
        return "---"
    safe = guard_leading_amp(rt.display_safe(as_inline(env, body)))
    if safe:
        # amsmath reads a `[` at formula start as a positional argument --
        # "Bracket group [T_\Lambda, T_\Sigma] at formula start ... add a
        # \relax in front to hide it". Real author LaTeX opens with one
        # (a commutator), so hide it rather than let amsmath guess.
        if safe.lstrip().startswith("["):
            safe = "\\relax " + safe
        return "\\FitMath{$\\displaystyle %s$}" % safe
    # 757 -- `\\par`, NOT `\\\\`. Inside a longtable cell `\\\\` ENDS THE ROW.
    # This form was written with `\\\\[.2em]` and looked safe for two months
    # because it only ever landed in the LAST column, where ending the row
    # early is invisible. Showing the unmatched blocks put it in the THIRD
    # column of wzlxjtu-041, and the row split: `(will not typeset)` came out
    # under the No column and every cell after it shifted one to the left.
    return ("{\\ttfamily\\tiny %s}\\par{\\footnotesize\\itshape "
            "(will not typeset)}" % rt.esc_source(body))


def appendix_rows(mpx: list, m_left: list, p2m: list, p_left: list) -> list:
    """One row per leftover block: which source emitted it, and the block.

    766 -- TWO columns, and never the words "no gold". The appendix used the
    document table's four, with a gold column saying "no gold" in every row,
    and a reader searching the file for a document landed on it and read the
    DOCUMENT as having no equations and no gold.
    """
    out = []
    for src, blocks, left in (("MathPix", mpx, m_left),
                              ("pdf2mmd", p2m, p_left)):
        for j in left:
            out.append("%s & %s \\\\ \\hline\n" % (src, cell(blocks[j])))
    return out


def table_open(caption: str, widths, heads, banner: str) -> str:
    r"""`rt.table_open`, with the DOCUMENT NAME on every page it runs onto.

    765 -- wzlxjtu-031's table starts at the foot of one page with two rows
    on it and continues at the top of the next with fifteen. `longtable`
    repeats the column header there and nothing else, so the fifteen rows sat
    under `No | gold | MathPix | pdf2mmd` with no document name anywhere on
    the page -- and the two rows left behind under the heading read as the
    whole of it. Reported as "file 31 has no entries at all", which is what
    it looks like.

    A `\endfirsthead` carries the head as it was; `\endhead` gets a banner
    row above it saying which document this is and that it is a continuation.
    """
    s = rt.table_open(caption, widths, False, False, heads=heads)
    pre, sep, rest = s.partition("\\endhead\n")
    if not sep:                        # the shared helper changed shape
        return s
    cont = ("\\hline\n\\multicolumn{%d}{|l|}{\\textbf{%s — continued}}"
            " \\\\\n\\hline\n" % (len(widths), banner)
            + " & ".join("\\textbf{%s}" % h for h in heads)
            + " \\\\\n\\hline\n")
    return pre + "\\endfirsthead\n" + cont + "\\endhead\n" + rest


def provenance() -> str:
    """Which reader produced the pdf2mmd column, and when this was built.

    785 — the body of this moved to `provenance.py` so the TOOL can stamp its
    own output too. It could not before: this lived in out/, and a document's
    mmd-out therefore said nothing about which install wrote it. Two on one
    machine, and 347 GB of results could only be dated, not identified.
    """
    import datetime
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import provenance as prov
    built = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return "%s — table built %s" % (prov.stamp(), built)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(LIB / "out" / "716-equations.tex"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--paper", default="a3")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--no-unmatched", action="store_true",
                    help="omit the per-document table of blocks that match "
                         "no gold equation (they are shown by default)")
    A = ap.parse_args()

    w_mm, h_mm = rt.PAPER_MM[A.paper]
    w_mm, h_mm = h_mm, w_mm                      # landscape
    usable = w_mm - 36
    span = usable - 18                           # 4 columns of \tabcolsep + rules
    no_w = 10
    eq_w = round((span - no_w) / 3)
    widths = (no_w, eq_w, eq_w, span - no_w - 2 * eq_w)
    heads = ("No", "gold (author)", "MathPix", "pdf2mmd")

    docs = sorted(d for d in LIB.glob("wzlxjtu-*") if d.is_dir())
    if A.limit:
        docs = docs[:A.limit]

    parts, stats = [], {"docs": 0, "gold": 0, "mathpix": 0, "pdf2mmd": 0,
                        "matched_m": 0, "matched_p": 0, "left_m": 0, "left_p": 0,
                        "unrenderable": {"gold": 0, "mathpix": 0, "pdf2mmd": 0}}
    for d in docs:
        slug = d.name
        gt = next(iter(d.glob("golden/*_gt.tex")), None)
        if gt is None:
            continue
        gold = gold_equations(gt)
        mpx = md_blocks(d / (slug + ".md"))
        p2m = md_blocks(d / "pdf2mmd" / "page.md")
        if not (gold or mpx or p2m):
            continue
        stats["docs"] += 1
        stats["gold"] += len(gold)
        stats["mathpix"] += len(mpx)
        stats["pdf2mmd"] += len(p2m)
        m_at, m_left = align(gold, mpx)
        p_at, p_left = align(gold, p2m)
        caption = ("%s — gold %d; matched MathPix %d, pdf2mmd %d; "
                   "unmatched blocks MathPix %d, pdf2mmd %d"
                   % (rt.esc_text(slug), len(gold),
                      sum(1 for x in m_at if x is not None),
                      sum(1 for x in p_at if x is not None),
                      len(m_left), len(p_left)))
        parts.append(table_open(caption, widths, heads, rt.esc_text(slug)))
        NOMATCH = r"{\itshape\footnotesize no match}"
        m_inline = inline_math(d / (slug + ".md"))
        p_inline = inline_math(d / "pdf2mmd" / "page.md")

        def missing(gbody: str, spans: list) -> str:
            """What to print where a source produced no display block.

            755 -- if the mathematics is there INLINE, say so and show it.
            Anything else is "no match", which then means one thing only.
            """
            from difflib import SequenceMatcher
            a = key(gbody)
            if a and spans:
                best, at = 0.0, None
                for s in spans:
                    r = SequenceMatcher(None, a, key(s)).ratio()
                    if r > best:
                        best, at = r, s
                if best >= 0.35:
                    # `\par`, NOT `\\`. After a `\FitMath` box -- which is a
                    # `\resizebox`, not a paragraph -- a `\\` ENDS THE ROW,
                    # and the note landed in the next row's first column.
                    # The "will not typeset" form above can use `\\` because
                    # its content is plain text.
                    return (cell(at)
                            + r"\par{\itshape\footnotesize inline only, "
                            # `%` STARTS A COMMENT. Written plain it ate the
                            # closing brace and the row terminator with it:
                            # 29 "Missing } inserted" and 21 demoted rows.
                            + ("%.0f\\%% of the gold" % (100 * best)) + "}")
            return NOMATCH

        for i, (genv, gbody) in enumerate(gold):
            mbody = cell_text(mpx, m_at[i])
            pbody = cell_text(p2m, p_at[i])
            # `key` was the loop variable here and is now the matching
            # function above; shadowing it made every row raise.
            for col, b, e in (("gold", gbody, genv), ("mathpix", mbody, ""),
                              ("pdf2mmd", pbody, "")):
                if b and not rt.display_safe(as_inline(e, b)):
                    stats["unrenderable"][col] += 1
            # An empty cell now means ONE thing: that source emitted nothing
            # matching THIS equation. Before it meant that, or that the
            # columns had drifted apart, and the two are not distinguishable
            # by eye -- which is what made the table hard to inspect.
            cells = [str(i + 1), cell(gbody, genv),
                     cell(mbody) if mbody else missing(gbody, m_inline),
                     cell(pbody) if pbody else missing(gbody, p_inline)]
            parts.append(" & ".join(cells) + " \\\\ \\hline\n")
            stats["matched_m"] += 1 if m_at[i] is not None else 0
            stats["matched_p"] += 1 if p_at[i] is not None else 0
        # A block matching NO gold equation gets no row by default.
        #
        # These were listed after the document's rows, on the reasoning that a
        # block with nowhere to go is a finding rather than noise. In a table
        # whose every row exists to be read ACROSS -- gold beside the two
        # readings of it -- that is wrong: 106 of 527 rows had nothing in the
        # gold column, so there was nothing to compare them against, and they
        # broke up the run of real comparisons.
        #
        # They are still COUNTED, per document in the caption and once at the
        # end, so nothing is hidden; `--unmatched` puts the rows back for when
        # the question is "what did it emit that is not an equation at all".
        stats["left_m"] += len(m_left)
        stats["left_p"] += len(p_left)
        parts.append("\\end{longtable}\n")

        # 756 -- AND THEN SHOW THE ONES WITH NOWHERE TO GO.
        #
        # A block matching no gold equation used to get no row at all. It was
        # counted in the caption, so nothing was strictly hidden -- but 61 of
        # them (MathPix 8, pdf2mmd 53) never appeared, and a reader looking
        # for a document's Nth equation found N-1 rows and no sign of the
        # rest. Counted is not shown.
        #
        # They were interleaved with the real rows once and that WAS wrong:
        # every row of the main table exists to be read ACROSS, gold beside
        # the two readings of it, and 106 rows with an empty gold column
        # broke the run. So they go in a table of their OWN, after it, where
        # there is nothing to read across and the heading says so.
        #
        # 766 -- AND IT MUST NOT LOOK LIKE THE DOCUMENT'S OWN TABLE.
        #
        # It had the same four columns, the same heading shape and a gold
        # column reading "no gold" in every row. Searching the file for a
        # document lands on TWO sections with its name, and the second one
        # -- one row, an empty MathPix column, "no gold" -- reads as the
        # document itself having no equations and no gold. Reported twice,
        # for 041 and again for 031, whose real table above it carries all
        # seventeen equations.
        #
        # Two columns now, one row per leftover block, naming the source. It
        # cannot be read across, so it must not be shaped like something
        # that can; and the words "no gold" are gone, because they were a
        # property of the ROW, never of the document.
        if not A.no_unmatched and (m_left or p_left):
            u_w = (28, span - 28)
            parts.append(table_open(
                "%s — APPENDIX: blocks this source emitted that match no "
                "gold equation (MathPix %d, pdf2mmd %d). The document's own "
                "equations are in the table above."
                % (rt.esc_text(slug), len(m_left), len(p_left)),
                u_w, ("source", "block matching no gold equation"),
                "%s — appendix, leftover blocks" % rt.esc_text(slug)))
            parts.extend(appendix_rows(mpx, m_left, p2m, p_left))
            parts.append("\\end{longtable}\n")

    body = "".join(parts)
    title = ("Display equations — gold vs MathPix vs pdf2mmd "
             "(%d documents; gold %d, MathPix %d, pdf2mmd %d)"
             % (stats["docs"], stats["gold"], stats["mathpix"], stats["pdf2mmd"]))
    geom = "%spaper,landscape" % A.paper
    doc = (rt.preamble(bbdigits=rt.MATHBB_DIGITS, form="", geom=geom,
                       pagesel=rt.pagesel_line(None),
                       unicode=rt.unicode_decls(body))
           + "\\begin{center}{\\Large\\bfseries %s}\\end{center}\n" % rt.esc_text(title)
           + "\\begin{center}{\\footnotesize %s}\\end{center}\n"
             % rt.esc_text(provenance())
           + body + "\n\\end{document}\n")

    out = Path(A.out)
    out.write_text(doc, encoding="utf-8")
    print("documents %d   gold %d   mathpix %d   pdf2mmd %d"
          % (stats["docs"], stats["gold"], stats["mathpix"], stats["pdf2mmd"]))
    print("matched to a gold equation: MathPix %d, pdf2mmd %d of %d"
          % (stats["matched_m"], stats["matched_p"], stats["gold"]))
    print("blocks matching no gold equation: MathPix %d, pdf2mmd %d"
          % (stats["left_m"], stats["left_p"]))
    print("cells that will not typeset: %s" % stats["unrenderable"])
    print("wrote %s (%d bytes)" % (out, out.stat().st_size))
    if not A.no_compile:
        n = mark_unrenderable(out)
        print("cells marked unrenderable by the per-cell probe: %d" % n)
        c = rt.compile_fixpoint(out)
        print("compile: %r" % (c,))


if __name__ == "__main__":
    main()
