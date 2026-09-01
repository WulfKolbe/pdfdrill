#!/usr/bin/env python3
"""LaTeX formula report (report.tex) — the compilable analog of
formula-report.html, generated from a <bibkey>.tiddlers.json.

CLI: `pdfdrill reporttex <pdf>` (this module is the implementation; the
legacy entry `tools/make_report_tex.py` is a shim onto it).

One longtable row per math object: the full tiddler identifier, the LaTeX
source as escaped text, the rendered math, and the page of first occurrence.
Sections: inline formulas (FO/FOX), display equations (EQ, with equation
number), tables (TAB). A formula tiddler carries no page field, so first
occurrence is derived from the first page-bearing tiddler (document order)
whose text transcludes it. Stdlib only; compile with xelatex.
"""
import argparse
import json
import os
import re
from pathlib import Path

_ESC = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
        "&": r"\&", "#": r"\#", "_": r"\_", "%": r"\%",
        "^": r"\textasciicircum{}", "~": r"\textasciitilde{}"}


def esc_text(s: str) -> str:
    out = "".join(_ESC.get(c, c) for c in s)
    # Break opportunities in long token runs (the column must wrap) — BEFORE
    # the backslash, never after it. After it, a wrapped line ended with a
    # naked `\` and the next began `mathrm{e}^{...}`; copied out of the PDF
    # that is broken LaTeX which compiles to the literal letters "mathrme"
    # (user 2026-08-19, 0711.0273). Breaking before keeps every copied line
    # starting with its command intact.
    out = out.replace(r"\textbackslash{}", r"\allowbreak{}\textbackslash{}")
    # ...but NEVER a leading one: \allowbreak is \penalty0, and at the very
    # start of a p{} cell TeX happily breaks there, giving an EMPTY first
    # line in every cell whose latex begins with a backslash. Measured on
    # WDorg4: 83 pages with the leading penalty vs 60 without (+38%; the
    # corpus grew 941->1080 pages before this was found).
    if out.startswith(r"\allowbreak{}"):
        out = out[len(r"\allowbreak{}"):]
    return out


#: The TiddlyWiki projector sanitises every tiddler title through
#: `re.sub(r"[^A-Za-z0-9_\-\.]", "_", t)` (docops/projectors/tiddlywiki.py
#: `_sanitize_title`), so a bibkey with a space, a parenthesis or a `+` reaches
#: the tiddler as underscores: `1611.03955 (1)_EQ0001` is stored as
#: `1611.03955__1__EQ0001`. The report derived its prefix from the FILENAME and
#: matched the raw form, so it matched nothing and wrote an empty table — 81
#: documents library-wide, hiding 2,676 equations and 6,132 inline formulas,
#: every one of them a directory whose name carries a character the projector
#: rewrites. Kept as a copy rather than an import to avoid dragging the whole
#: docops/docmodel chain into report generation; `test_report_bibkey_sanitize`
#: asserts the two definitions agree, so the copy cannot drift.
def sanitize_title(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-\.]", "_", t)


#: 440 — the templates the TiddlyWiki projector actually emits. ONE list, so a
#: consumer that filters by template can say whether a marker it skipped is a
#: template it does not handle or a template that does not exist.
KNOWN_TEMPLATES = frozenset((
    "ABS", "CIT", "DIA", "EQ", "EQBLOCK", "FN", "FO", "FREF", "LI", "LTX",
    "PARA", "PIC", "PROOF", "SN", "TAB", "TOC"))

#: Any transclusion, whatever its template — used to find the ones a
#: template-filtered pattern silently walked past.
ANY_MARKER = re.compile(r"\{\{([^}|{]+)\|\|([A-Za-z]+)\}\}")


def unknown_markers(tiddlers: list[dict]) -> dict:
    """{template: count} for markers naming a template nothing emits.

    440. Two consumers match a FIXED SET of templates and skip everything
    else, which means an unrecognised marker produces no error, no unhandled
    token and no missing-content warning — just a row that stops being
    counted. 434's type change turns an `||EQBLOCK` into a `||DIA`, so the
    failure this makes visible is the one that change would otherwise cause.
    """
    seen: dict = {}
    for t in tiddlers:
        for m in ANY_MARKER.finditer(t.get("text", "") or ""):
            tpl = m.group(2)
            if tpl not in KNOWN_TEMPLATES:
                seen[tpl] = seen.get(tpl, 0) + 1
    return seen


def first_pages(tiddlers: list[dict], bibkey: str) -> dict[str, str]:
    """title -> page of the first transcluding page-bearing tiddler.

    440 — the pattern matches FO/FOX titles ONLY, and that is deliberate: this
    map exists as a page fallback for inline formulas, which carry no page of
    their own. Every other kind has `page` on its own tiddler.

    What it does with an unrecognised marker is therefore correct and was NOT
    correct to leave undocumented: it skips it, silently, and the caller sees
    a title with no page. `unknown_markers` above is what makes that visible
    when the template is one nothing emits.
    """
    pat = re.compile(r"\{\{(" + re.escape(sanitize_title(bibkey))
                     + r"_(?:FOX?_?\w+))\|\|")
    first: dict[str, str] = {}
    for t in tiddlers:
        page, text = t.get("page"), t.get("text", "")
        if not page or "{{" not in text:
            continue
        for m in pat.finditer(text):
            first.setdefault(m.group(1), page)
    return first


def refined_map(tiddlers) -> dict:
    """{title: {basis, verified_by, author, refined}} for VERIFIED refinements.

    233. The tiddler array carries these as evidence and does not act on them;
    choosing is this projector's job, which is why the map is built here and
    not baked into `latex` upstream.
    """
    out = {}
    for t in tiddlers:
        val = t.get("latex_refined")
        if val and t.get("refined_verified_by"):
            out[t.get("title", "")] = {
                "refined": val,
                "basis": t.get("refined_basis", ""),
                "verified_by": t.get("refined_verified_by", ""),
                "author": t.get("refined_author", ""),
                "original": t.get("latex") or "",
            }
    return out


#: a tiddler title that names an object kind — what `rows_for` looks for
TYPED_TITLE = re.compile(r"_(FOX?|EQ|TAB|DIA|PIC)\d")


def rows_for(tiddlers, bibkey, refined=None):
    fo, eq, tab, dia = [], [], [], []
    fpage = first_pages(tiddlers, bibkey)
    for t in tiddlers:
        title = t.get("title", "")
        m = re.match(re.escape(sanitize_title(bibkey))
                     + r"_(FOX?|EQ|TAB|DIA|PIC)", title)
        if not m:
            continue
        kind = m.group(1)
        latex = t.get("latex") or t.get("latex_code") or ""
        if refined and title in refined:
            # the whole of the change: one substitution, at read time
            latex = refined[title]["refined"]
        page = t.get("page") or fpage.get(title, "")
        dims = t.get("width", ""), t.get("height", "")
        # 282 — the full region, so a tex.zip image can be named by its
        # 5-tuple rather than guessed at from page + size.
        region = (t.get("page"), t.get("height"), t.get("width"),
                  t.get("top_left_y"), t.get("top_left_x"))
        if kind in ("FO", "FOX"):
            fo.append((title, latex, page, t.get("trailing_punct", "")))
        elif kind == "EQ":
            eq.append((title, latex, page, t.get("equation_number", ""),
                       t.get("width", ""), t.get("trailing_punct", ""),
                       t.get("confidence", "")))
        elif kind == "TAB":
            # 423 — a Table's LaTeX is `mathpix_text`, never `latex`. `latex`
            # is set on 0 of 5,937 Table objects corpus-wide (425), so the
            # shared expression above can only ever yield "" for this kind.
            tab.append((title, latex or t.get("mathpix_text") or "",
                        page, dims, region, t.get("confidence", "")))
        else:
            dia.append((title, latex, page, dims, region))
    return fo, eq, tab, dia


#: 284 — LaTeX carried by an image region, and what can safely be set from it.
#: Measured corpus-wide over 27,287 DIA/PIC rows: 1,788 (6.55%) carry any
#: LaTeX — tikzpicture 761, listings/other 1,018, array/align 5, tabular 4 —
#: and 25,499 carry none at all. The tex.zip is not a second source for these:
#: its diagram content is `\includegraphics` pointing at the same crop, and it
#: holds only 42 tikzpicture in 1,216 zips against 20,670 \includegraphics.
#: The environment vocabulary of image-region LaTeX, counted corpus-wide:
#:   tikzpicture 762 · tikzcd 658 · lstlisting 323 · scope 145 · minipage 37
#:   axis 17 · array 16 · tabular 12 · bmatrix 6 · pgfonlayer 6 · comment 3
#:   groupplot 3 · itemize 2 · cases 1
#:
#: An ALLOWLIST, not a guess. The first version matched only `tikzpicture` and
#: let everything else fall through to `renderable()`, which set
#: `\begin{tikzcd}…` as MATH — 658 rows of commutative diagram handed to the
#: math parser. 2208.01506 then failed to compile at all: "Environment tikzcd
#: undefined", then a cascade of "Undefined control sequence" and unbalanced
#: braces, and NO report.pdf. An unknown environment must be refused, not
#: guessed at.
_PICTURE_ENVS = ("tikzpicture", "tikzcd")
#: Renderable as mathematics.
_MATH_ENVS = ("array", "bmatrix", "pmatrix", "vmatrix", "Vmatrix", "matrix",
              "cases", "aligned", "smallmatrix")
#: `axis`/`groupplot` are pgfplots and usually want external data; `minipage`,
#: `itemize`, `comment`, `scope` and `pgfonlayer` are fragments or containers
#: that mean nothing on their own. 20-odd rows between them, all refused.
_FIRST_ENV = re.compile(r"\\begin\{([A-Za-z*]+)\}")
_LSTLISTING = re.compile(r"\\begin\{lstlisting\}(\[[^\]]*\])?", re.S)


#: A picture environment inside a longtable cell cannot use a bare `&`: the
#: table claims it as the column separator and pgf reports "Single ampersand
#: used with wrong catcode", then 239 characters land in `nullfont` and the row
#: is demoted. Measured on 2208.01506, whose 43 image rows are mostly tikzcd.
#:
#: tikz-cd has the remedy built in — `[ampersand replacement=\&]` with the body
#: escaped to match. Verified standalone: 0 errors, 0 missing characters, in a
#: longtable cell. A tikzpicture has no such option, so one carrying a bare `&`
#: (a \matrix node) is refused rather than guessed at.
_TIKZCD_OPTS = re.compile(r"^(\s*\\begin\{tikzcd\})(\[[^\]]*\])?", re.S)


def _ampersand_safe(lx: str, env: str):
    """The body made safe for a table cell, or None when it cannot be."""
    if "&" not in lx:
        return lx
    if env != "tikzcd":
        return None                     # tikzpicture \matrix — refused
    m = _TIKZCD_OPTS.match(lx)
    if not m:
        return None
    opts = (m.group(2) or "")[1:-1] if m.group(2) else ""
    opts = (opts + ", " if opts else "") + "ampersand replacement=\\&"
    rest = lx[m.end():]
    # every bare & in the body becomes \& to match the declared replacement
    rest = re.sub(r"(?<!\\)&", r"\\&", rest)
    return "%s[%s]%s" % (m.group(1), opts, rest)


def region_render(latex: str, width_mm=None) -> str:
    r"""A cell that SETS this region's LaTeX, or "" when nothing can be.

    tikzpicture   -> scaled to the column. The picture is the point.
    lstlisting    -> escaped monospace, NOT the listings environment: a
                     verbatim environment inside a longtable cell is fragile,
                     and the content is text either way.
    math-ish      -> $\displaystyle ...$ through `renderable`, which already
                     refuses what xelatex would choke on.
    anything else -> "" — better an empty cell than a row that hangs the
                     fixpoint. bh2_EQ0147 hung xelatex for ten minutes inside a
                     longtable cell, which is why `renderable` exists at all.
    """
    lx = (latex or "").strip()
    if not lx:
        return ""
    m = _FIRST_ENV.search(lx)
    env = m.group(1) if m else ""
    if env in _PICTURE_ENVS:
        box = "\\linewidth" if not width_mm else "%.1fmm" % width_mm
        body = _ampersand_safe(lx, env)
        if body is None:
            return ""
        return "\\resizebox{%s}{!}{%s}" % (box, body)
    if env == "lstlisting":
        body = _LSTLISTING.sub("", lx).replace("\\end{lstlisting}", "").strip()
        return "{\\ttfamily\\tiny %s}" % esc_text(body[:1200])
    if env and env not in _MATH_ENVS and env != "tabular":
        return ""                      # refused: see the allowlist above
    if env == "tabular":
        return "{\\tiny %s}" % lx
    safe = renderable(lx)
    if safe:
        return "\\FitMath{$\\displaystyle %s$}" % safe
    return ""


#: 284 — the regions residual, beside report.ink.json rather than inside it.
#: The equation measurement and the region measurement are different
#: populations against different comparands; merging them would put a
#: self-comparison (a duplicated row) into the same distribution as a genuine
#: rendered-against-scan pair.
REGIONS_INK = "report.regions.ink.json"

#: The row manifest the measurement joins against: one record per image row, in
#: printed order, naming what each of the two cells actually holds. Written by
#: the build because only the build knows; without it the measurement would
#: have to infer "duplicated" from the pixels, which is precisely the inference
#: 284 forbids — a self-comparison must be RECORDED as one, not deduced.
REGIONS_MANIFEST = "report.regions.json"
#: 321 — the table boundaries the BUILDER knows. inkdrill groups
#: pages into tables by contiguity plus equal column width, which
#: structurally cannot separate two ADJACENT tables of the same
#: width: 0049's equations and formulas are both 5 columns and
#: adjacent, so they group as one run and the ordinal stops being
#: the longtable index. Nothing in the rendered page can fix that.
#: We do not have to infer it — this module emitted the tables and
#: knows where each begins, how wide it is, and which identifiers
#: it holds. Stating it is cheaper and exact.
TABLES_MANIFEST = "report.tables.json"


def _img_cell(img_path: Path, out_dir: Path, col_mm, px2mm, dims) -> str:
    """An \\includegraphics cell sized to the column.

    Both image columns go through this: a Rendered cell sized differently from
    its Scan would put a scale difference into the residual, which is the one
    thing the two columns exist to measure.
    """
    w_mm = None
    if px2mm:
        real = jpg_width(img_path) or (dims[0] if dims else None)
        try:
            w_mm = min(float(real) * px2mm, col_mm)
        except (TypeError, ValueError):
            w_mm = None
    size = ("width=%.1fmm" % w_mm) if w_mm else "width=\\linewidth"
    try:
        rel = img_path.resolve().relative_to(out_dir)
    except ValueError:
        rel = img_path
    return "\\includegraphics[%s]{%s}" % (size, str(rel).replace("\\", "/"))


def texzip_images(texzip_dir: Path):
    """Index a tex.zip expansion by the FULL region 5-tuple.

    out/279 measured what these filenames are:

        <process-id>-<page>_<height>_<width>_<top_left_y>_<top_left_x>.jpg

    and verified the four numbers after the page ARE the region — 20,276 of
    20,287 filenames match a region in their own document's lines.json exactly,
    99.95%. So the association is a dictionary lookup on a key both sides hold,
    not a guess.

    This used to key on `(page, height, width)` and fall back to "any image on
    that page". Three figures of the same size on one page collided, and the
    page fallback attached the FIRST image on a page to every unmatched row on
    it — a named source that could be the wrong picture, which is worse than
    none.

    Returns `(by_region, n_images)`. `n_images` matters: 285 of 1,216 corpus
    tex.zips hold no image at all, and an empty zip must not read like a failed
    lookup.
    """
    by_region, n = {}, 0
    for img in sorted(texzip_dir.rglob("*.jpg")) + \
               sorted(texzip_dir.rglob("*.png")):
        n += 1
        m = re.search(r"-(\d+)_(\d+)_(\d+)_(\d+)_(\d+)\.\w+$", img.name)
        if not m:
            continue
        by_region[tuple(int(x) for x in m.groups())] = img
    return by_region, n


def jpg_width(path: Path):
    """Actual pixel width of the (possibly trimmed) crop; None without PIL."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size[0]
    except Exception:
        return None


def crop_cell(crops_dir: Path | None, out_dir: Path, title: str,
              px_width="", px2mm=None, col_mm=None,
              bibkey: str = "", history: "list[str] | None" = None) -> str:
    """An \\includegraphics cell for the tiddler's downloaded CDN crop.

    With px2mm (mm per MathPix page pixel) and the region's pixel width the
    crop is set at its EXACT original physical size, capped at the column
    width; otherwise it fills the column.
    """
    if not crops_dir:
        return "---"
    img = crop_file(crops_dir, title, bibkey, history)
    if img is None:
        return "---"
    try:
        rel = img.relative_to(out_dir)
    except ValueError:
        rel = img
    size = "width=\\linewidth"
    if px2mm:
        try:
            real = jpg_width(img)
            w_mm = float(real if real else px_width) * px2mm
            # 4mm clearance: a crop flush against the column rule bridges
            # to it at raster dpi and MERGES the lattice holes (inkdrill
            # P16 third pass, 1205.3463v2 — 15 touching scanlines)
            if col_mm and w_mm > col_mm - 4:
                w_mm = col_mm - 4
            size = "width=%.1fmm" % w_mm
        except (TypeError, ValueError):
            pass
    return ("\\includegraphics[%s]{%s}"
            % (size, str(rel).replace("\\", "/")))


PAPER_MM = {"a4": (210, 297), "a3": (297, 420)}

MATHBB_DIGITS = r'''%% 199: BLACKBOARD-BOLD DIGITS.
%% amssymb's \mathbb is the AMS msbm font, whose blackboard glyphs cover A-Z
%% ONLY. Its digit slots hold negated turnstiles, so `\mathbb{1}` did not fail
%% -- it rendered U+22AE, "does not force", and `\mathbb{0}`/`\mathbb{2}`
%% rendered U+22AC/U+22AD. Correct source, silently wrong glyph, in 758 places
%% across 44 documents (748 of them \mathbb{1}).
%% bbm supplies blackboard digits as \mathbbm. \mathbb is redefined to
%% DISPATCH: digits to bbm, everything else to the AMS font, so every existing
%% \mathbb{R} is byte-identical to before.
\usepackage{bbm}
\let\pdfdrillamsbb\mathbb
\makeatletter
\renewcommand{\mathbb}[1]{%
  \ifcat_\ifnum9<1\noexpand#1_\else A\fi
    \mathbbm{#1}%
  \else
    \pdfdrillamsbb{#1}%
  \fi}
\makeatother
'''

PREAMBLE = r"""%% report.tex — generated by tools/make_report_tex.py; compile with xelatex
\documentclass[10pt]{article}
\usepackage[%(geom)s,margin=18mm]{geometry}
\usepackage{amsmath}
\usepackage{amssymb}
%(bbdigits)s\usepackage{longtable}
\usepackage{array}
\usepackage{graphicx}
%% mathrsfs (\mathscr) and stmaryrd (\llbracket): the SAME packages the
%% standalone renderer carries. Their absence here cost 60 demoted rows
%% corpus-wide — equations that render perfectly alone and threw
%% 'Undefined control sequence' inside the report (0707.4470: 39 errors,
%% 31 rows, every one a \mathscr).
\usepackage{mathrsfs}
\usepackage{stmaryrd}
%% 284: the image-regions section renders a region's own LaTeX beside its crop.
%% 761 corpus rows carry a tikzpicture and 1,018 carry a listing. GUARDED for
%% the same reason 221 guards \newfontfamily: an unguarded \usepackage for a
%% package this machine lacks aborts the compile and produces NO pdf, which is
%% worse than the row it would have rendered.
\IfFileExists{tikz.sty}{\usepackage{tikz}}{}
\IfFileExists{tikz-cd.sty}{\usepackage{tikz-cd}}{}
\IfFileExists{listings.sty}{\usepackage{listings}}{}
%% 442: MathPix emits \longdiv for long-division notation and NOTHING defines
%% it. 441 called this a package gap on the strength of `kpsewhich
%% longdivision.sty` finding a file; that package provides \longdivision and
%% \intlongdivision, and its `\def\longdiv@...` are internal macros with an @
%% in the name. Loading it changes nothing — measured, 0 of 7 rows.
%%
%% So it is defined here, in the one place every report shares.
%% \providecommand, not \newcommand: if a document's own preamble is ever
%% injected and defines it, that definition wins rather than aborting the
%% compile. The construction is the classic one — a close-paren against an
%% overline over the dividend.
\providecommand{\longdiv}[1]{\overline{\smash{\raise.4ex\hbox{$)$}}\,#1}}
%% 090: the Source column is \ttfamily and carries the OCR's raw Unicode.
%% Latin Modern Mono has none of it, so xelatex dropped 24,953 glyphs across
%% 1,702 reports with only a warning (out/089). DejaVu Sans Mono covers 208 of
%% the 400 code points out/088 found; the two fallback families and the
%% generated \newunicodechar lines below cover the rest.
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\setmonofont{DejaVu Sans Mono}[Scale=MatchLowercase]
\newfontfamily\fbmath{Noto Sans Math}
\newfontfamily\fbcjk{Noto Sans CJK JP}
%% 221: Bengali has no other home here. Guarded, because an unguarded
%% \newfontfamily for a font this machine lacks aborts the compile and
%% produces NO pdf — worse than the dropped glyph it exists to prevent. When
%% the font is absent the character drops as before AND glyphs_dropped() says
%% so, which is the failure we can at least see.
\IfFontExistsTF{Noto Sans Bengali}{\newfontfamily\fbbeng{Noto Sans Bengali}}{\newcommand{\fbbeng}{}}
\usepackage{newunicodechar}
%(unicode)s
\setlength{\parindent}{0pt}
\newcommand{\ident}[1]{\texttt{\tiny #1}}
%% 340 — the hand-editing surface. The argument ships as the MathPix
%% crop's own name and is overwritten with the author's figure file.
%% Harvested by `pdfdrill figpairs`, which looks for THIS macro rather
%% than for \includegraphics, so an edit is unambiguous.
\newcommand{\authorsrc}[1]{\includegraphics[width=\linewidth]{#1}}
\newcommand{\eqnum}[1]{{\tiny #1}}
%% 064: MathPix doubted this line. Set in the IDENTIFIER column, which is
%% machine keys already — the Source, Rendered and Scan columns stay
%% byte-identical so the consumer's per-column ink probe keeps working and
%% an unchanged column remains a free control (HANDOVER rule 16).
\newcommand{\lowconf}[1]{~{\tiny\textbf{[conf #1]}}}
%% 099: MathPix's confidence as its own column, colour-banded. NOT blended
%% with the ink distance into a score: they are independent instruments that
%% disagree usefully (out/063: EQ0516 reads confidence 0.041 and ink 18; a
%% combined number would have hidden which one objected).
\usepackage{xcolor}
\definecolor{confgreen}{RGB}{0,128,0}
\definecolor{confamber}{RGB}{190,120,0}
\definecolor{confred}{RGB}{190,0,0}
\newcommand{\confcell}[2]{{\footnotesize\textcolor{#1}{$\blacksquare$}\,#2}}
%% a wide unbreakable math line must NEVER escape its cell (11 P13 reports
%% had the Scan column pushed off the page — inkdrill P16 finding): render
%% at natural size, shrink to the column only when it would overflow
\newsavebox{\fitbox}
\newcommand{\FitMath}[1]{\savebox{\fitbox}{#1}\ifdim\wd\fitbox>0.97\linewidth\resizebox{0.97\linewidth}{!}{\usebox{\fitbox}}\else\usebox{\fitbox}\fi}
%(form)s\begin{document}
"""

#: 144 — the review format: confidence keeps its coloured SQUARE, the residual
#: class is a coloured BULLET (colour only — no class letter, no delta, no A/B
#: suffix; 117 refuted that taxonomy), and each row carries an AcroForm field
#: named ink.<ident>.
#:
#: The bullet and the field are not duplicates. The bullet is the COMPILE-TIME
#: mark; the field is the UPDATE CHANNEL — fill_ink_fields.py writes inkdrill's
#: residual code into it by name AFTER the PDF is built, so a fresh inkdrill run
#: refreshes the report without recompiling it.
#:
#: \special sets /NeedAppearances so a viewer rebuilds the visible field text.
#: \pdfcatalog is NOT used: it is a pdfTeX primitive and is undefined under
#: xelatex, which is the engine this report requires.
FORM_PREAMBLE = r"""
%% 146/147: the classes fill_ink_fields.py actually emits (its FLAG_CODE):
%% clean K, noise N, weak W, stable S, component C. The 134 demo used a
%% DIFFERENT vocabulary (missed/straddle/overlap/inside) that the tool never
%% produces — a legend naming those would have described classes no row can
%% ever have.
\definecolor{inkComponent}{RGB}{220,30,30}
\definecolor{inkWeak}{RGB}{230,150,20}
\definecolor{inkStable}{RGB}{40,90,220}
\definecolor{inkNoise}{RGB}{120,120,120}
\definecolor{inkClean}{RGB}{40,160,40}
\definecolor{inkUnmeasured}{RGB}{190,190,190}
\newcommand{\inkbullet}[1]{{\footnotesize\textcolor{#1}{$\bullet$}}}
"""


def col_widths(usable_mm: float, with_image: bool):
    r"""(ident, page, conf, src, rendered[, image]) widths in mm.

    The reserve is the REAL LaTeX overhead, not a guess: 2*\tabcolsep (6pt
    each side) per column + the rules — ~22mm for 5 columns, ~18 for 4. The
    old 12mm reserve made every 5-column row ~10mm overfull ('Overfull \hbox
    in alignment', inkdrill P16 second pass)."""
    # 099: the confidence column costs 13mm and one more \tabcolsep pair.
    span = usable_mm - (28 if with_image else 24)
    ident, page, conf = 20, 7, 13
    rest = span - ident - page - conf
    if with_image:
        src = round(rest * 0.29)
        rend = round(rest * 0.31)
        return ident, page, conf, src, rend, rest - src - rend
    src = round(rest / 2)
    return ident, page, conf, src, rest - src


def _table_record(caption, widths, legend: bool, endhead: bool,
                  identifiers) -> dict:
    r"""One table's boundary, as the builder knows it (321).

    `rows` is the identifier count, which is what a measurement joins
    against. `legend` matters because `legend_foot` emits the key as
    `\endfoot` AND `\endlastfoot`, so it repeats on EVERY page and a lattice
    reads it as a row — inkdrill measured exactly one extra row per page of
    the run on the two legend-bearing tables and none on the other two (320).
    `endhead` says whether the header repeats, which is the `--header
    first|every` argument a consumer must pass.
    """
    return {"caption": caption, "columns": len(widths),
            "legend": bool(legend), "endhead": bool(endhead),
            "rows": len(identifiers), "identifiers": list(identifiers)}


def table_open(caption: str, widths, form: bool = False,
               legend_on: bool = True) -> str:
    cols = "|" + "|".join("p{%smm}" % w for w in widths) + "|"
    heads = {5: ("Identifier", "Page", "Conf.", "LaTeX source", "Rendered"),
             6: ("Identifier", "Page", "Conf.", "LaTeX source", "Rendered",
                 "Scan image")}[len(widths)]
    return (
        "\\section*{%s}\n" % caption +
        "\\begin{longtable}{%s}\n\\hline\n" % cols +
        " & ".join("\\textbf{%s}" % h for h in heads) +
        " \\\\\n\\hline\\endhead\n" +
        (legend_foot(widths, form) if legend_on else ""))


def has_bare_align_marker(lx: str) -> bool:
    r"""True if a `&` or `\\` sits at BRACE DEPTH 0 — where a longtable's
    alignment scanner sees it and ends the cell (or the row).

    Braces SHIELD both: `\substack{a \\ b}` is a macro ARGUMENT, not an
    environment, and compiles happily inside a cell — measured with a probe
    longtable, 0 errors. The old check was brace-blind and demoted every
    equation with multi-line text under an integral to "(not rendered)"
    (0711.0273: 3 of 14 equations, user 2026-08-19).
    """
    i, depth, n = 0, 0, len(lx)
    while i < n:
        c = lx[i]
        if c == "\\":
            nxt = lx[i + 1] if i + 1 < n else ""
            if nxt == "\\":                      # the \\ token itself
                if depth == 0:
                    return True
                i += 2
                continue
            if nxt.isalpha():                    # control word: \substack, …
                j = i + 1
                while j < n and lx[j].isalpha():
                    j += 1
                i = j
                continue
            i += 2                               # escaped char: \{ \} \& \_ …
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "&" and depth == 0:
            return True
        i += 1
    return False


#: 128 — CJK in a MATHS value is MathPix hallucinating, not content.
#: U+2FF0–U+2FFB are Ideographic Description Characters: they are not glyphs at
#: all but a notation for DESCRIBING how an unknown ideograph is composed
#: ("⿱ 日 一" = the thing with 日 above 一). Their presence means the OCR could
#: not identify a character and emitted its recipe. 0902.0431_EQ1187 (page 200,
#: confidence 0.183) carries ⿱ ⿻ 一 日 and \zh, and is the only row in that
#: document whose glyphs xelatex silently DROPPED — a report that looks finished
#: and is missing symbols with no visible trace.
_IDC = range(0x2FF0, 0x2FFC)
#: Unified ideographs + extensions + compatibility. A maths value has no
#: business containing any of them.
_CJK_BLOCKS = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
               (0x20000, 0x2A6DF), (0x2A700, 0x2EBEF), (0x2F800, 0x2FA1F))
_ZH_CMD = re.compile(r"\\zh(?![a-zA-Z])")


def cjk_defect(latex: str) -> str:
    """Why this maths value is CJK-contaminated, or "" if it is clean.

    Reports the FIRST offender with its code point, so a caller can name the
    character rather than say "contains CJK" — the report row is useless for
    triage without knowing whether it hit an IDC (OCR gave up) or a real
    ideograph (OCR read the wrong script).
    """
    for ch in latex or "":
        c = ord(ch)
        if c in _IDC:
            return "ideographic description character U+%04X (%s)" % (c, ch)
    for ch in latex or "":
        c = ord(ch)
        if any(lo <= c <= hi for lo, hi in _CJK_BLOCKS):
            return "CJK ideograph U+%04X (%s)" % (c, ch)
    if _ZH_CMD.search(latex or ""):
        return "\\zh command"
    return ""



#: TeX math ALPHABETS are not fonts with gaps — they are alphabets. rsfs10
#: (\mathscr) and eufm10 (\mathfrak) are uppercase-only script/fraktur faces;
#: asking either for a lowercase letter drops it SILENTLY, leaving a PDF that
#: looks finished and is missing letters. `glyph_loss_advice` has said "change
#: the command, not the font" since out/219 — this is that change.
#:
#: Measured on 2103.01507, whose author wrote
#:     \DeclareMathOperator{\cMap}{\mathstscr{M\mkern-4mu a\mkern-3.5mu p}}
#: MathPix read the script "Map" off the page and transcribed it \mathscr{M a p},
#: which is a faithful reading. rsfs10 has no `a` and no `p`, so 11 of that
#: report's 12 dropped glyphs were those five rows. No fallback font reaches it
#: (the ALPHABET lacks the letter, not the font the code point) and no installed
#: face here carries lowercase script.
#:
#: So the letters the alphabet cannot set are moved OUT of it and set italic,
#: which is what an operator name looks like anyway. This touches ONLY the
#: rendered cell — the Source column still shows `\mathscr{M a p}` character for
#: character, so the page keeps saying what MathPix produced.
#: rsfs10 ONLY. The comment on `_TEX_MATH_FONTS` said "rsfs10 and eufm10 have
#: no lowercase" and eufm10 does: `$\mathfrak{m}\mathfrak{a}\mathfrak{p}$`
#: compiles with zero missing characters, and 2103.01507's own `\mathfrak{m}`
#: drew no warning in a log that names every other drop. Including it here
#: would have rewritten correct fraktur into italic to fix a defect it does not
#: have — a two-line test against the claim, before trusting it.
_ALPHABET_UPPER_ONLY = ("mathscr",)
_ALPHABET_ARG = re.compile(
    r"\\(%s)\s*\{([^{}]*)\}" % "|".join(_ALPHABET_UPPER_ONLY))


def alphabet_safe(latex: str) -> str:
    r"""Move characters a TeX math alphabet cannot set out of it.

    `\mathscr{M a p}` -> `\mathscr{M}\mathit{a}\mathit{p}`. An argument with no
    lowercase is returned untouched, so the 138 `\mathscr{F}` in the same
    document are not disturbed.
    """
    def repl(m):
        cmd, arg = m.group(1), m.group(2)
        if not re.search(r"[a-z]", arg):
            return m.group(0)
        out, run = [], []

        def flush_upper():
            if run:
                out.append("\\%s{%s}" % (cmd, "".join(run)))
                del run[:]

        for ch in arg:
            if ch.islower():
                flush_upper()
                out.append("\\mathit{%s}" % ch)
            elif ch.isspace():
                continue            # inter-letter space inside an operator name
            else:
                run.append(ch)
        flush_upper()
        return "".join(out)
    return _ALPHABET_ARG.sub(repl, latex or "")


#: float furniture MathPix sweeps in with a display it cut out of a figure
#: (483/485). `\centering` and friends take no argument; the rest take one
#: braced argument that may itself contain braces, so it is matched by
#: counting rather than by a regex.
FLOAT_FURNITURE_ARG = ("captionsetup", "caption", "label", "subcaption",
                       "captionof")
FLOAT_FURNITURE_BARE = ("centering", "raggedright", "raggedleft", "small",
                        "footnotesize", "scriptsize", "noindent")


def _drop_leading_furniture(lx: str) -> str:
    r"""Strip float furniture from the FRONT of a value, while a display follows.

    483/485. `\begin{figure} \captionsetup{labelformat=empty} \caption{Table 2.
    …} \[ … \]` is one object's display with the float it was printed in swept
    in around it. 446 already drops the leading `\begin{figure}`; what it left
    behind was the caption, and that keeps the `\[` MID-STRING, where the
    delimiter gate refuses it.

    THE GUARD IS `\[` STILL FOLLOWS. A `\caption` is only furniture when there
    is a display after it for it to be furniture AROUND; a value that is a
    caption is a caption, and is left alone.
    """
    while True:
        s = lx.lstrip()
        if "\\[" not in s:
            return lx
        for cmd in FLOAT_FURNITURE_BARE:
            if re.match(r"\\%s(?![a-zA-Z])\s*" % cmd, s):
                lx = re.sub(r"^\\%s(?![a-zA-Z])\s*" % cmd, "", s)
                break
        else:
            m = re.match(r"\\(%s)\s*(\[[^\]]*\])?\s*\{"
                         % "|".join(FLOAT_FURNITURE_ARG), s)
            if not m:
                return lx
            depth, i = 0, m.end() - 1
            while i < len(s):
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            if depth != 0:
                return lx                  # unbalanced — not ours to touch
            lx = s[i + 1:].lstrip()


def _drop_stray_closers(lx: str) -> str:
    r"""Drop unmatched `}` from the END of a value (483).

    mielke EQ0190 and EQ0453, both at confidence 1.000, read
    `\[ … . \] }`. MathPix's own lines.json for those lines is
    `'\[\n…\n\]'` — the trailing brace is NOT in their text, it is ours, and
    it is what stops the trailing-`\]` strip from anchoring. 16 rows.

    Only UNMATCHED closers go: the count is what decides, not the position.
    """
    stripped = re.sub(r"\\[{}]", "", lx.replace("\\\\", ""))
    excess = stripped.count("}") - stripped.count("{")
    while excess > 0:
        m = re.search(r"\}\s*$", lx)
        if not m:
            break
        lx = lx[:m.start()].rstrip()
        excess -= 1
    return lx


def renderable(latex: str) -> str:
    """Return latex safe to put inside $...$, or "" when it is not.

    One malformed snippet (bh2_EQ0147 carried a stray \\end{itemize}) hung
    xelatex for 10 minutes inside a longtable cell — every snippet is
    validated here and demoted to source-only when it cannot render.
    """
    lx = re.sub(r"\s+", " ", latex).strip()
    lx = alphabet_safe(lx)
    if cjk_defect(lx):
        return ""              # 128: hallucinated script never reaches xelatex
    # MathPix glues a stray environment CLOSER onto the end of display math when
    # the equation ends a list or theorem: `\[ ... \] \end{itemize}`. The
    # equation itself is intact — the closer belongs to prose that was cut away.
    # Left in place it put a \] MID-STRING, so the delimiter gate below refused
    # 24 of 0902.0431's 31 unrendered rows, at confidences up to 1.000. Drop a
    # TRAILING \end{X} only when the value carries no matching \begin{X}: an
    # environment that opens inside the math keeps its own closer.
    while True:
        m = re.search(r"\\end\{(\w+\*?)\}\s*$", lx)
        if not m:
            break
        env = re.escape(m.group(1))
        if len(re.findall(r"\\begin\{%s\}" % env, lx)) >= \
           len(re.findall(r"\\end\{%s\}" % env, lx)):
            break                          # balanced — the closer is genuine
        lx = lx[:m.start()].rstrip()
    # 446 — THE MIRROR OF THE RULE ABOVE. MathPix glues an environment OPENER
    # onto the front of display maths as readily as it glues a closer onto the
    # end: `\begin{figure} \[ … \]` on 3 of johnston's rows, where the
    # figure the equation sat in was cut away and its opener came along. The
    # closer rule was written for `\end{itemize}` and never mirrored, so a
    # leading opener left a `\[` MID-STRING and the delimiter gate below
    # refused the row — 444 then sent all three to a model, which faithfully
    # PRESERVED the wrapper every time, because a `\begin{figure}` is
    # invisible in a crop of the equation and the prompt tells it to prefer
    # the existing reading. No prompt reaches this; the rule does.
    #
    # Drop a LEADING \begin{X} only when the value carries no matching
    # \end{X}: an environment that opens and closes inside the maths keeps
    # its own opener.
    while True:
        m = re.match(r"\\begin\{(\w+\*?)\}\s*", lx)
        if not m:
            break
        env = re.escape(m.group(1))
        if len(re.findall(r"\\end\{%s\}" % env, lx)) >= \
           len(re.findall(r"\\begin\{%s\}" % env, lx)):
            break                          # balanced — the opener is genuine
        lx = lx[m.end():].lstrip()
    # plain-TeX multiline macros carry \cr internally — inside a longtable
    # cell they throw "Misplaced \cr" recovery loops the row-demotion pass
    # never reaches (live hang: 0902.0431 EQ0035, \displaylines)
    if re.search(r"\\(displaylines|eqalign(no)?|halign|cr)(?![a-zA-Z])", lx):
        return ""
    # 483/485 — what 446's opener rule left behind. Dropping the leading
    # `\begin{figure}` is not enough when a `\captionsetup` and a `\caption`
    # stand between it and the display; and a stray unmatched `}` after the
    # closing `\]` stops the trailing strip from anchoring. Both run BEFORE
    # the delimiter gate, because both exist to let it anchor.
    lx = _drop_leading_furniture(lx)
    lx = _drop_stray_closers(lx)
    # display delimiters: strip a leading \[ / trailing \]; reject mid-string
    lx = re.sub(r"^\\\[\s*", "", lx)
    lx = re.sub(r"\s*\\\]$", "", lx)
    # 446 — `\$` is an ESCAPED dollar: currency, and legal inside maths. This
    # check refused any `$` at all while the `%` check on the very next line
    # strips its escape first. Two adjacent rules, one rule each, and only one
    # of them handled the escape. 444 is the proof from outside: given
    # `\$ 151` and the crop, the model returned `\$ 151` unchanged — it
    # judged there was nothing to fix, and this gate refused its own input
    # back.
    if r"\[" in lx or r"\]" in lx or re.sub(r"\\\$", "", lx).count("$"):
        return ""
    if re.sub(r"\\%", "", lx).count("%"):
        return ""
    # brace balance, with \\ and escaped \{ \} removed first
    stripped = re.sub(r"\\[{}]", "", lx.replace("\\\\", ""))
    depth = 0
    for c in stripped:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return ""
    if depth != 0:
        return ""
    if len(re.findall(r"\\left(?![a-zA-Z])", lx)) != \
       len(re.findall(r"\\right(?![a-zA-Z])", lx)):
        return ""
    if sorted(re.findall(r"\\begin\{(\w+\*?)\}", lx)) != \
       sorted(re.findall(r"\\end\{(\w+\*?)\}", lx)):
        return ""
    # bare align markers (& or \\) at BRACE DEPTH 0 are longtable tab marks
    # -> "misplaced tab mark" error-recovery loop (live hang on 0902.0431
    # EQ0035). Environments handle their own; braces SHIELD the rest.
    stripped_env = lx
    for _ in range(6):
        reduced = re.sub(r"\\begin\{(\w+\*?)\}.*?\\end\{\1\}", " ",
                         stripped_env, flags=re.S)
        if reduced == stripped_env:
            break
        stripped_env = reduced
    if has_bare_align_marker(stripped_env):
        return ""
    return lx


def breakable_ident(title: str) -> str:
    """Long unbreakable identifiers ('1205.3463v2_EQ0001', ~40mm of tt in a
    20mm column) overprint clean ACROSS the narrow Page column and bridge its
    lattice holes away (inkdrill P16 fourth pass: the 5 failing docs were
    exactly the version-suffixed ids). Break opportunities after . and _."""
    return re.sub(r"(\.|\\_)", r"\1\\allowbreak{}", esc_text(title))


#: 064 — MathPix's confidence below this marks the row as doubted. 0.1 is
#: the user's stated threshold; at it 19 of 4,338 corpus equations flag
#: (0.4%), and the class is real — 0902.0431_EQ0516 sits at 0.041 with 19 of
#: its 48 array cells wrong or missing (out/063). The flag is advisory: the
#: row still renders, because a doubted reading is still the best reading we
#: have and hiding it would be the masked-failure defect (HANDOVER rule 11).
CONF_THRESHOLD = 0.1


def conf_flag(conf, threshold: float = CONF_THRESHOLD) -> str:
    r"""`\lowconf{0.041}` when MathPix doubted this line, else "".

    Empty for a missing or unparseable value — absence of a reading is NOT
    evidence of a good one, so it must not silently read as confident.
    """
    if conf in (None, ""):
        return ""
    try:
        v = float(conf)
    except (TypeError, ValueError):
        return ""
    return "\\lowconf{%.3f}" % v if v < threshold else ""


#: inkdrill flag -> bullet colour
_INK_COLOUR = {"component": "inkComponent", "weak": "inkWeak",
               "stable": "inkStable", "noise": "inkNoise", "clean": "inkClean",
               # a row whose render AND scan are both empty was not compared.
               # It is an ABSENT reading, not a clean one — an all-zero
               # five-tuple pair scores distance 0 and would otherwise take the
               # best class. Distinct from "no ink.json entry at all", which is
               # also inkUnmeasured but for a different reason.
               "absent": "inkUnmeasured"}


#: 241 — the credibility test, and the population it must NOT be run over.
#:
#: max/max(1,min) on the two component counts, scale-free and order-free; the
#: p90 across a document asks whether MOST rows match, which is the pairing
#: question. A per-row cap would refuse real findings, because a genuinely
#: mis-transcribed equation SHOULD differ wildly.
#:
#: I derived 3.0 from five clean documents (p90 1.03-1.07) against 0902.0431
#: (7.76) and handed it to the pages gate, which adopted it. None of the six
#: had many DEMOTED rows, so that failure mode was outside the population I
#: fitted on — and it is a false positive, not a defect: a row demoted to
#: \emph{(not rendered)} has no rendered mathematics, so its render is a tiny
#: constant against a full scan cell and the ratio is legitimately enormous.
#:
#: 2010.14265 is 62.5% demoted and reads p90 8.62 over all rows and 1.00 over
#: rendered ones. OMDoc 1.2 is 50% demoted: 9.08 and 1.08. Both would have been
#: refused as implausible measurements while being perfectly paired.
RATIO_P90_MAX = 3.0


def component_ratio_p90(rows, rendered=None) -> "float | None":
    """p90 of max/min over the two component counts, over RENDERED rows.

    `rendered` is a parallel sequence of booleans; rows that rendered nothing
    are excluded because their ratio measures the absence of a render, not a
    disagreement between two readings of the same thing.
    """
    vals = []
    for i, r in enumerate(rows):
        if rendered is not None and i < len(rendered) and not rendered[i]:
            continue
        L, R = r.get("L"), r.get("R")
        if not L or not R:
            continue
        a, b = L[0], R[0]
        vals.append(max(a, b) / max(1, min(a, b)))
    if not vals:
        return None
    vals.sort()
    return vals[min(len(vals) - 1, int(len(vals) * 0.9))]


def demoted_flags(tex_body: str) -> list:
    """Per EQ row, in table order: did it render, or is it (not rendered)?"""
    out = []
    for line in (tex_body or "").split("\n"):
        if re.search(r"\\ident\{[^&\n]*?EQ\d+\}[^&\n]*& *\d+ *&", line):
            out.append("not rendered" not in line)
    return out


def ink_join(tiddlers, bibkey: str, ink: "dict | None") -> dict:
    """How much of the ink map actually LANDS on rows of this report.

    237c. residual_colour returns inkUnmeasured for an identifier it cannot
    find, so a measurement whose identifiers do not intersect this report's
    rows renders as a fully measured report in which nothing could be
    measured. That is indistinguishable, on the page, from a document nobody
    has measured — and it is a join failure, not a result.

    The shape is a comparison whose two populations cannot overlap. A peer hit
    it the same week from the other side: 0 of 26 rows "confirmed" between an
    ink.json holding only EQ identifiers and a text layer yielding only FO
    ones. The test could not have returned a hit under any circumstances,
    including the one where everything is correct, and 0 of 26 reads exactly
    like a finding.

    So: ask whether the join CAN succeed before reporting what it found.
    """
    if not ink:
        return {"ink_rows": 0, "report_rows": 0, "matched": 0, "rate": None}
    fo, eq, tab, dia = rows_for(tiddlers, bibkey)
    titles = {r[0] for r in fo} | {r[0] for r in eq} | {r[0] for r in tab} \
        | {r[0] for r in dia}
    matched = len(set(ink) & titles)
    return {"ink_rows": len(ink), "report_rows": len(titles),
            "matched": matched,
            "rate": (matched / len(ink)) if ink else None}


def residual_colour(ident: str, ink: "dict | None") -> str:
    """Bullet colour for one row, from the MEASURED residual class.

    146: the class cannot be known during the first build — inkdrill derives it
    FROM the finished PDF by comparing the Rendered and Scan columns. So the
    first pass paints every bullet inkUnmeasured, and a second pass, fed the
    ink map that fill_ink_fields.py produced, paints the real classes.

    Colouring from confidence instead would be worse than leaving it neutral:
    it would look like a residual reading while merely restating the square
    beside it, and out/145 showed the two disagree.
    """
    if not ink:
        return "inkUnmeasured"
    rec = ink.get(ident) or {}
    return _INK_COLOUR.get(rec.get("flag"), "inkUnmeasured")


def load_ink(path) -> dict:
    """{ident: {flag, code}} from a fill_ink_fields.py --json dump."""
    import json
    d = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    return {r["id"]: {"flag": r.get("flag"), "code": r.get("code", "")}
            for r in d.get("rows", []) if r.get("id")}


#: 147 — one line under each table naming BOTH channels. The report shows two
#: independent instruments in adjacent cells and they disagree usefully
#: (out/063: EQ0516 reads confidence 0.041 and ink 18). Without a legend a
#: reader has a coloured square beside a coloured bullet and no way to know
#: they are measuring different things, which invites reading them as one
#: score — exactly what keeping them separate was for.
LEGEND_CONF = (r"\textbf{Conf.} MathPix confidence: "
               r"\textcolor{confgreen}{$\blacksquare$}\,$\geq$0.9 \quad "
               r"\textcolor{confamber}{$\blacksquare$}\,0.5--0.9 \quad "
               r"\textcolor{confred}{$\blacksquare$}\,$<$0.5 \quad "
               r"--- no value")
LEGEND_INK = (r"\textbf{Residual} render vs scan (inkdrill): "
              r"\textcolor{inkComponent}{$\bullet$}\,C component \quad "
              r"\textcolor{inkWeak}{$\bullet$}\,W weak \quad "
              r"\textcolor{inkStable}{$\bullet$}\,S stable \quad "
              r"\textcolor{inkNoise}{$\bullet$}\,N noise \quad "
              r"\textcolor{inkClean}{$\bullet$}\,K clean \quad "
              r"\textcolor{inkUnmeasured}{$\bullet$}\,not measured")


#: 180 — the reader-facing note at the top of an unmeasured report. Reader
#: facing means it says what the reader has and has not got, in words that do
#: not require knowing what a lattice is. The technical cause belongs in the
#: index tooltip, not here.
UNMEASURED_NOTE = (
    "Ink comparison not available for this document — the report's own table "
    "could not be read reliably enough to pair residual measurements with "
    "equations. MathPix confidence is shown; the residual column is absent.")

#: The SAME sentence would be a false statement about a document nobody has
#: measured: nothing failed to pair, because nothing was attempted. Asserting a
#: cause the artefact cannot verify is the defect this whole sequence has been
#: cataloguing, so the two states get two sentences.
UNRUN_NOTE = (
    "Ink comparison not available for this document — no residual measurement "
    "has been run for it. MathPix confidence is shown; the residual column is "
    "absent.")

#: 221 — the third state, and the one that is NOT an absence of data. A
#: measurement exists and is being refused, because the report it was taken
#: against is missing symbols with no visible trace. Saying "no measurement has
#: been run" here would be false; saying "could not be paired" would name the
#: wrong cause. A refusal has to say it is a refusal.
GLYPHLOSS_NOTE = (
    "Ink comparison withheld for this document — the report it was measured "
    "against dropped characters while still producing a PDF, so the render is "
    "missing symbols the scan has. Any residual would charge that gap to the "
    "extraction. MathPix confidence is shown; the residual column is absent "
    "until the report is rebuilt with the missing characters and re-measured.")

#: 181 — said, not silently omitted. A legend that lists only the confidence
#: bands looks complete; a reader has no way to know a second column exists
#: elsewhere and is missing here.
LEGEND_NO_INK = (r"\textbf{Residual} not shown for this document — no residual "
                 r"measurements are paired with these rows.")


def unmeasured_note(kind: str = "unpairable") -> str:
    """The top-of-report note.

    `kind`: 'unpairable' | 'not_run' | 'glyphs_dropped' | '' (none).
    """
    text = {"unpairable": UNMEASURED_NOTE, "not_run": UNRUN_NOTE,
            "glyphs_dropped": GLYPHLOSS_NOTE}.get(kind, "")
    if not text:
        return ""
    return ("\\begin{quote}\\small\\itshape\n%s\\end{quote}\n\\normalsize\n"
            % esc_text(text))


def legend(form: bool) -> str:
    """The legend text. Both channels when --form is on.

    `\\newline`, not `\\\\`, between the two lines: this goes inside a
    \\multicolumn p-column as a longtable footer, where `\\\\` would end the
    table ROW and split the legend across two rows.
    """
    out = "{\\scriptsize " + LEGEND_CONF
    # 181: the confidence bands ALWAYS apply, so the legend is always printed.
    # When the residual half is absent it is named as absent rather than left
    # out — the difference between "this report has one column" and "this
    # report is missing a column" is not visible from an incomplete key.
    out += r" \newline " + (LEGEND_INK if form else LEGEND_NO_INK)
    return out + "}"


def legend_foot(widths, form: bool) -> str:
    """The legend as \\endfoot AND \\endlastfoot, so it repeats on EVERY page.

    It used to be emitted once after \\end{longtable}, which put it on whichever
    page the table happened to finish on — page 26 of 26 for 0902.0431. A key
    that appears only after the last row is not a key for the 25 pages before it.

    Both hooks are needed and they are not interchangeable: \\endfoot is used on
    every page EXCEPT the last, \\endlastfoot only on the last. Supplying one
    alone leaves exactly the complementary set of pages bare.
    """
    n = len(widths)
    span = sum(widths) - 4          # inside the column rules and \\tabcolsep
    cell = "\\multicolumn{%d}{|p{%dmm}|}{%s}" % (n, span, legend(form))
    return "%s \\\\ \\hline\n\\endfoot\n%s \\\\ \\hline\n\\endlastfoot\n" % (
        cell, cell)


def conf_cell(conf) -> str:
    """099: colour-banded confidence cell. green >= 0.9, amber 0.5-0.9, red < 0.5.

    An absent value renders as a dash, never as a colour: no reading is not a
    good reading, and a blank green square would assert one.
    """
    if conf in (None, ""):
        return "---"
    try:
        v = float(conf)
    except (TypeError, ValueError):
        return "---"
    band = "confgreen" if v >= 0.9 else ("confamber" if v >= 0.5 else "confred")
    return "\\confcell{%s}{%.3f}" % (band, v)


#: 233 — the page states what it projected and on what basis. A report that
#: silently showed a corrected value would answer "what does this document
#: say" while appearing to answer "what did the OCR read", and those are the
#: two questions this report exists to keep apart.
def refined_note(refined: dict) -> str:
    if not refined:
        return ""
    by = {}
    for info in refined.values():
        k = info.get("basis") or info.get("verified_by") or "?"
        by[k] = by.get(k, 0) + 1
    how = ", ".join("%d verified against the %s" % (v, k)
                    for k, v in sorted(by.items()))
    ids = ", ".join(sorted(refined)[:6]) + (" …" if len(refined) > 6 else "")
    n = len(refined)
    text = ("%d row%s a REFINEMENT below, not the OCR reading: %s. Each is "
            "marked [refined] beside its identifier. The model is unchanged — "
            "the original reading is still what `latex` holds; this projection "
            "chose the refinement for %s. Rows: %s"
            % (n, " shows" if n == 1 else "s show", how,
               "it" if n == 1 else "them", ids))
    return ("\\begin{quote}\\small\\itshape\n%s\\end{quote}\n\\normalsize\n"
            % esc_text(text))


#: 233 — a row whose value came from a refinement says so IN THE IDENTIFIER
#: column, beside \lowconf and for the same reason (out/064, HANDOVER rule 16):
#: the Source, Rendered and Scan columns stay byte-identical to what they would
#: have been, so a per-column ink probe still works and an unchanged column
#: remains a free control. A reader must be able to see that this row is not
#: what MathPix said without the row's own pixels changing to tell them.
def refined_flag(info) -> str:
    if not info:
        return ""
    return ("~{\\tiny\\textbf{[refined: %s]}}"
            % esc_text(info.get("basis") or info.get("verified_by") or "?"))


#: 443 — a value refused ONLY because of a bare `&` or `\\` at brace depth 0.
#:
#: That check is right about the danger and wrong about the value: a `&` at
#: depth 0 is a longtable TAB MARK and hangs the compile, so it cannot go in a
#: cell — but the mathematics itself is fine. 441 compiled all four of
#: johnston's rejected rows standalone and all four produced a PDF.
#:
#: So the row stops being demoted and starts being an IMAGE, the way 423 gave
#: the tables section a Rendered column: compile the value as its own
#: document, where a `&` is an array separator and nothing else, and put the
#: result in the cell. The reader gets the mathematics rendered; the longtable
#: never sees the tab mark.
FORMULA_RULES = ("all", "unresolved", "none")


def unresolved_formulas(fo):
    r"""The formula rows a reader still has to do something about (460).

    A row qualifies when it HAS LaTeX and `renderable` refuses it — that is
    exactly the row whose Rendered cell says "(not rendered)". A row with no
    LaTeX at all is not unresolved, it is absent, and shows as a dash; a row
    that renders is done.

    Measured over the 22 published documents: 37,624 formula rows, of which 7
    qualify. The section this rule replaces was not a report of problems, it
    was a catalogue.
    """
    out = []
    for r in fo:
        latex = r[1]
        if latex and not renderable(latex):
            out.append(r)
    return out


def refused_for_align_only(latex: str) -> bool:
    """True when `renderable` refuses this ONLY over a depth-0 align marker.

    Re-runs the gate with that one check disabled. If the value passes
    everything else, the marker is the sole objection and the standalone route
    is safe; if it fails something else too, it is not, and the row demotes as
    before.
    """
    # An EMPTY value passes every check below and would come back True — and
    # `standalone_math` would then compile an empty document into a blank PNG,
    # so a row with no LaTeX would show a blank image where it should show
    # "---". Four rows of johnston did exactly that before this guard.
    if not (latex or "").strip():
        return False
    if renderable(latex):
        return False
    import re as _re
    lx = _re.sub(r"\s+", " ", latex).strip()
    lx = alphabet_safe(lx)
    if cjk_defect(lx):
        return False
    while True:
        m = _re.search(r"\\end\{(\w+\*?)\}\s*$", lx)
        if not m:
            break
        env = _re.escape(m.group(1))
        if len(_re.findall(r"\\begin\{%s\}" % env, lx)) >= \
           len(_re.findall(r"\\end\{%s\}" % env, lx)):
            break
        lx = lx[:m.start()].rstrip()
    if _re.search(r"\\(displaylines|eqalign(no)?|halign|cr)(?![a-zA-Z])", lx):
        return False
    lx = _re.sub(r"^\\\[\s*", "", lx)
    lx = _re.sub(r"\s*\\\]$", "", lx)
    if r"\[" in lx or r"\]" in lx or "$" in lx:
        return False
    if _re.sub(r"\\%", "", lx).count("%"):
        return False
    stripped = _re.sub(r"\\[{}]", "", lx.replace("\\\\", ""))
    d = 0
    for c in stripped:
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d < 0:
                return False
    if d:
        return False
    if len(_re.findall(r"\\left(?![a-zA-Z])", lx)) != \
       len(_re.findall(r"\\right(?![a-zA-Z])", lx)):
        return False
    if sorted(_re.findall(r"\\begin\{(\w+\*?)\}", lx)) != \
       sorted(_re.findall(r"\\end\{(\w+\*?)\}", lx)):
        return False
    return True                       # everything else passed: the & is it


def standalone_math(latex: str, ident: str, out_dir, col_mm: float = 100.0,
                    dpi: int = 400, timeout: int = 90) -> str:
    r"""443 — the value compiled as its OWN document, returned as an
    \includegraphics cell, or "" when it will not compile.

    Used only for `refused_for_align_only` rows: the `&` that makes the value
    illegal INSIDE a longtable cell is an ordinary array separator in a
    document of its own.
    """
    from pathlib import Path as _P
    d = _P(out_dir) / "standalone-math"
    png = d / ("%s.png" % sanitize_title(ident))
    if not png.is_file():
        try:
            from .region_standalone import render as _r
            d.mkdir(parents=True, exist_ok=True)
            # RAW, not $-wrapped: `region_standalone` decides the wrapper
            # itself (`needs_math_wrapper`), and wrapping it here made every
            # one of the four fail with "Missing $ inserted" — a double
            # wrap, reported by the renderer as if the value were malformed.
            got, _err = _r(sanitize_title(ident), latex, d,
                           dpi=dpi, timeout=timeout)
            if got is None:
                return ""
            png = _P(got)
        except Exception:
            return ""
    if not png.is_file():
        return ""
    return ("\\includegraphics[width=%smm,height=48mm,keepaspectratio]{%s}"
            % (round(col_mm - 4), png.name if png.parent.name == "" else
               "standalone-math/" + png.name))


def row(title, latex, page, extra="", image=None, punct="", conf="",
        form=False, residual="inkUnmeasured", code="", refined=None,
        standalone="") -> str:
    # identifier and equation number are machine keys, not reading
    # matter: at \tiny they stop crowding the 20mm column (and stop
    # overprinting the Page column, inkdrill P16's fourth pass).
    ident = "\\ident{%s}%s%s%s" % (breakable_ident(title),
                                   ("~\\eqnum{%s}" % esc_text(extra))
                                   if extra else "",
                                   conf_flag(conf),
                                   refined_flag(refined))
    src = "{\\ttfamily\\footnotesize %s}" % esc_text(latex) if latex else "---"
    safe = renderable(latex) if latex else ""
    # 025: the mark is set BESIDE the math, never inside it — the same
    # separation the TiddlyWiki text field makes, so the rendered cell still
    # looks like the scan while `latex` holds mathematics only.
    tail = esc_text(punct) if punct else ""
    math = ("\\FitMath{$\\displaystyle %s$}%s" % (safe, tail)) if safe \
        else (standalone if standalone
              else ("\\emph{(not rendered)}" if latex else "---"))
    cell = conf_cell(conf)
    if form:
        # 148/155: the code is SELECTABLE TEXT — a form field's value is an
        # appearance stream that pdftotext cannot see, that nobody can
        # drag-select, and that grep over the PDF misses.
        #
        # 155 removed the AcroForm field that used to sit beside this. 157
        # established that nothing in the pipeline ever re-filled it: every
        # reporttex run rebuilds from source and resets the value, so the
        # "update without recompiling" path it existed for was never taken.
        # It also duplicated this string, and viewers tint form fields pale
        # cyan — which is what 156 turned out to be reporting as a mis-coloured
        # confidence square.
        txt = ("\\,\\texttt{\\tiny %s}" % esc_text(code)) if code else ""
        cell = "%s\\hspace{0.6em}\\inkbullet{%s}%s" % (cell, residual, txt)
    if image is not None:
        return "%s & %s & %s & %s & %s & %s \\\\ \\hline\n" % (
            ident, esc_text(str(page)), cell, src, math, image)
    return "%s & %s & %s & %s & %s \\\\ \\hline\n" % (
        ident, esc_text(str(page)), cell, src, math)


def stale_pdf_for(tex: Path) -> Path | None:
    """The sibling .pdf when it is older than `tex`, else None.

    Compares the derived file against ITS SOURCE, not against the clock. A
    report.pdf can be minutes old and still be the wrong build; freshness
    relative to the corpus says nothing about whether it matches the .tex it
    claims to render.
    """
    pdf = Path(tex).with_suffix(".pdf")
    # is_file(), not exists(): a DIRECTORY named report.pdf has an mtime, and
    # an old one would otherwise be reported stale and send the reader to
    # --compile, which then fails on it. A directory is not an out-of-date
    # report; it is not a report. (Consumer's guard, which reached for
    # is_file() to ask "is there a report to measure", excluded this by
    # accident — the phrasing of the question happened to exclude the case.)
    if not pdf.is_file():
        return None            # absent .pdf is not stale, it is simply absent
    try:
        return pdf if pdf.stat().st_mtime < Path(tex).stat().st_mtime else None
    except OSError:
        return None


def auto_px2mm(pdf: Path) -> float | None:
    """mm per MathPix page pixel, from the PDF's page width (pdfinfo) and the
    lines.json first-page pixel width. None when either is unavailable."""
    import json
    import re as _re
    import subprocess
    base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
    lines = pdf.parent / f"{base}.lines.json"
    if not lines.is_file():
        return None
    try:
        d = json.loads(lines.read_text(errors="replace"))
        px = d["pages"][0]["page_width"]
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                             text=True, timeout=30).stdout
        m = _re.search(r"Page size:\s+([\d.]+) x ", out)
        return round(float(m.group(1)) * 25.4 / 72 / px, 5) if m else None
    except Exception:
        return None


#: 264 — a `--bibkey` rename renames object ids and tiddler titles but not the
#: crops on disk, which are `report-crops/<sanitised bibkey>_EQ0001.jpg` and are
#: written by `report`/`cdncrops`. The model records the keys it used to carry
#: in `meta.bibkey_history`, so the mapping is READ, not guessed: a crop is
#: looked up under the current title first, then under the same suffix with an
#: earlier bibkey. No history -> exactly the pre-264 single lookup.
def crop_file(crops_dir: "Path | None", title: str,
              bibkey: str = "", history: "list[str] | None" = None):
    """The crop for `title`, following a recorded bibkey rename. None if absent."""
    if not crops_dir or not title:
        return None
    f = crops_dir / f"{title}.jpg"
    if f.is_file() and f.stat().st_size > 500:
        return f
    cur = sanitize_title(bibkey or "")
    if not cur or not history or not title.startswith(cur):
        return None
    suffix = title[len(cur):]
    for prior in reversed(history):
        alt = crops_dir / f"{sanitize_title(prior)}{suffix}.jpg"
        if alt.is_file() and alt.stat().st_size > 500:
            return alt
    return None


def render_crops(tiddlers: list[dict], dest: Path, pdf: Path,
                 kinds=("_TAB",), dpi: int = 400, trim: bool = True):
    r"""Crop the scan for every region-bearing tiddler WITHOUT a CDN uri (461).

    `download_crops` filters for `_EQ` or `_TAB` and then skips anything whose
    `canonical_uri` is not http. Across the 21 published documents that is
    8,718 of 8,718 EQ tiddlers fetched and 0 of 351 TAB tiddlers, because
    MathPix records no crop uri for a table. The Tables section reached 423's
    six columns with its Scan column empty in every row of every document.

    The region IS on the tiddler — page, top_left_x/y, width, height — so the
    picture is recoverable from the PDF. This renders it.

    THREE THINGS THAT ARE EASY TO GET WRONG HERE:

    * MathPix regions are in ITS page-image pixels, not ours. Every coordinate
      is scaled by (raster width / that page's MathPix page_width), which is
      read PER PAGE: 11 of 305 documents in this corpus carry more than one
      page_width, and a page scaled by another page's width lands on the wrong
      part of the page and still looks like a plausible piece of it
      (refine.mathpix_page_widths).

    * A page with no recorded width is SKIPPED, not defaulted. Cropping it
      wrongly is worse than not cropping it.

    * The result is resized to the region's MathPix pixel size. `crop_cell`
      sizes an image as jpg_width x px2mm, and px2mm is mm per MATHPIX pixel;
      a 400-dpi crop left at its own width would compute ~1.6x too wide, hit
      the column cap, and silently stop being pixel-exact — the one property
      the scan column claims. Rendering high and downsampling is a better
      picture than rendering at MathPix's ~250 dpi directly.

    Returns (rendered, cached, skipped).
    """
    from . import pdf_reading
    from .refine import mathpix_page_widths
    try:
        from PIL import Image
    except Exception:
        return 0, 0, 0
    pdf = Path(pdf)
    dest = Path(dest)
    widths = mathpix_page_widths(pdf.parent)
    want: dict = {}
    rendered = cached = skipped = 0
    for t in tiddlers:
        title = t.get("title", "")
        if not any(k in title for k in kinds):
            continue
        if str(t.get("canonical_uri", "")).startswith("http"):
            continue          # the CDN has it; download_crops owns that row
        f = dest / f"{title}.jpg"
        if f.is_file() and f.stat().st_size > 500:
            cached += 1
            continue
        try:
            page = int(t.get("page"))
            box = (int(t["top_left_x"]), int(t["top_left_y"]),
                   int(t["width"]), int(t["height"]))
        except (TypeError, ValueError, KeyError):
            skipped += 1
            continue
        if box[2] <= 0 or box[3] <= 0 or page not in widths:
            skipped += 1
            continue
        want.setdefault(page, []).append((f, box))
    if not want:
        return rendered, cached, skipped
    dest.mkdir(parents=True, exist_ok=True)
    # ONE rasterize call for the pages actually needed. kohlhase-omdoc has 103
    # table rows; a Ghostscript run per row is 103 runs over ~40 pages.
    pages = sorted(want)
    shutil_rmtree_first = dest / "_pages"
    import shutil as _sh
    _sh.rmtree(shutil_rmtree_first, ignore_errors=True)
    imgs = pdf_reading.rasterize(pdf, shutil_rmtree_first, pages=pages, dpi=dpi)
    # PARSE the page out of the filename rather than zipping against the
    # request. rasterize globs its output directory, so a stale page left by a
    # crashed run would shift every pairing by one and crop each region from
    # its neighbour's page — plausible-looking and wrong.
    by_page = {}
    for f in (imgs or []):
        m = re.search(r"page-(\d+)\.", f.name)
        if m:
            by_page[int(m.group(1))] = f
    for page, jobs in want.items():
        src = by_page.get(page)
        if src is None:
            skipped += len(jobs)
            continue
        im = Image.open(src).convert("RGB")
        s = im.size[0] / float(widths[page])
        for f, (x, y, w, h) in jobs:
            x0, y0 = max(0, int(x * s)), max(0, int(y * s))
            x1 = min(im.size[0], int((x + w) * s))
            y1 = min(im.size[1], int((y + h) * s))
            if x1 <= x0 or y1 <= y0:
                skipped += 1
                continue
            im.crop((x0, y0, x1, y1)).resize((w, h), Image.LANCZOS).save(
                f, quality=92)
            if trim:
                _pad_top(f)
            rendered += 1
    # the rasterized pages are the largest thing this writes and nothing reads
    # them afterwards
    _sh.rmtree(dest / "_pages", ignore_errors=True)
    return rendered, cached, skipped


def download_crops(tiddlers: list[dict], dest: Path, trim: bool = True):
    """Fetch each EQ/TAB tiddler's CDN crop into dest/<title>.jpg (cached);
    left-trim whitespace when PIL is available. Returns (ok, cached, failed).
    Degrades cleanly when the network is blocked — the report then renders
    without the image column entries it could not fetch."""
    from .net import urlopen, NetworkBlocked
    from .env import get as _env
    # 396 — PDFDRILL_CDN_BASE redirects the fetch at a drop-in image source.
    #
    # `imageserve` is described in the manifest as "a drop-in cdn.mathpix.com
    # (/cropped/<id>?top_left_x=… assembled from the 600-DPI tiles)", and
    # `pyramid` builds what backs it. Nothing could be POINTED at it: every
    # consumer read the absolute cdn.mathpix.com URI recorded on the tiddler,
    # so the drop-in had no socket to drop into.
    #
    # It matters because those URIs expire. On 230209-algebraic_similarity
    # every one of 99 crops returns HTTP 500 — the document is drilled, its
    # model is complete, and its scan column is simply gone. The local pyramid
    # renders the same regions from the PDF at 600 dpi, which is the same
    # picture from a better source, and needs no key.
    #
    # A BASE, not a rewrite rule: only the scheme+host are replaced, so the
    # path and the crop geometry in the query string are the ones MathPix
    # recorded. Substituting any part of the geometry would silently crop
    # somewhere else.
    base = (_env("PDFDRILL_CDN_BASE", "") or "").rstrip("/")
    dest.mkdir(parents=True, exist_ok=True)
    ok = cached = failed = 0
    for t in tiddlers:
        title = t.get("title", "")
        uri = t.get("canonical_uri", "")
        if "_EQ" not in title and "_TAB" not in title:
            continue
        if not uri.startswith("http"):
            continue
        f = dest / f"{title}.jpg"
        if f.is_file() and f.stat().st_size > 500:
            # a cached crop still gets the top margin: _pad_top pads to
            # a target, so it is a no-op on one that already has it
            if trim:
                _pad_top(f)
            cached += 1
            continue
        target = uri.replace("\\&", "&")
        if base:
            from urllib.parse import urlsplit
            u = urlsplit(target)
            target = base + u.path + (("?" + u.query) if u.query else "")
        try:
            with urlopen(target, timeout=20) as r:
                f.write_bytes(r.read())
            if trim:
                _trim_left(f)
                _pad_top(f)
            ok += 1
        except NetworkBlocked:
            failed += 1
            break                       # one block message, not N
        except Exception:
            failed += 1
    return ok, cached, failed


def _trim_left(img_path: Path, margin: int = 4, thresh: int = 235) -> None:
    """Crop detected left whitespace (content-scan, small safety margin)."""
    try:
        from PIL import Image
    except Exception:
        return
    try:
        im = Image.open(img_path)
        g = im.convert("L")
        w, h = g.size
        px = g.load()
        left = 0
        for x in range(w):
            if any(px[x, y] < thresh for y in range(0, h, 2)):
                left = x
                break
        cut = max(0, left - margin)
        if cut:
            im.crop((cut, 0, w, h)).save(img_path, quality=92)
    except Exception:
        pass


def _pad_top(img_path: Path, margin: int = 2, thresh: int = 235) -> None:
    """Ensure `margin` white rows above the crop's ink.

    A crop whose ink starts in row 0 sits flush against the row rule
    above it: visually cramped, and at raster dpi the ink BRIDGES the
    rule and merges the lattice holes -- the same failure the 4mm
    horizontal clearance in `crop_cell` exists for, in the other
    axis. Measured over the corpus before this was written: 350 of
    5,882 crops (6.0%) had ink in row 0, and 649 more within the top
    three rows.

    Idempotent: it pads to a TARGET (at least `margin` white rows),
    never by a fixed amount, so re-running adds nothing.
    """
    try:
        from PIL import Image
    except Exception:
        return
    try:
        im = Image.open(img_path)
        g = im.convert("L")
        w, h = g.size
        px = g.load()
        white = 0
        for y in range(min(h, margin + 1)):
            if any(px[x, y] < thresh for x in range(0, w, 2)):
                break
            white += 1
        need = margin - white
        if need <= 0:
            return
        out = Image.new(im.mode, (w, h + need), "white")
        out.paste(im, (0, need))
        out.save(img_path, quality=92)
    except Exception:
        pass


def find_texzip(pdf: Path) -> Path | None:
    """The expanded MathPix <stem>.tex.zip (its images/ are the regions
    MathPix could NOT OCR). Expands the zip next to the PDF on first use."""
    import zipfile
    dest = pdf.parent / "texzip"
    if dest.is_dir() and any(dest.rglob("*.tex")):
        return dest
    z = pdf.parent / f"{pdf.stem}.tex.zip"
    if not z.is_file():
        return None
    try:
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        return dest
    except Exception:
        return None



#: 091 — the two shapes xelatex uses to say it threw a character away. The
#: second form is NOT a variant spelling: fontspec fonts report (U+XXXX) and
#: traditional TFM fonts report ("XXXX). out/089 matched only the first and so
#: never saw the cmmi10 losses, which were the majority. One pattern would have
#: been a check that passes because it cannot see the failure.
_GLYPH_LOST = re.compile(
    r"Missing character: There is no .+? \((?:U\+|\")[0-9A-Fa-f]+\)"
    r"|not set up for use with LaTeX")

#: 221 — the same warning, parsed: (char, code point, font). The font is what
#: decides which of two unrelated repairs applies, and the message used to name
#: only one of them.
_GLYPH_LOST_PARTS = re.compile(
    r"Missing character: There is no (.+?) \((?:U\+([0-9A-Fa-f]+)|\"([0-9A-Fa-f]+))\)"
    r"(?: in font ([^!\n]*))?")

#: TeX's own math alphabets, addressed by TFM name. A glyph missing from one of
#: these is not a Unicode coverage problem and no fallback font can reach it:
#: the ALPHABET does not contain that letter. rsfs10 (\mathscr) and eufm10
#: (\mathfrak) have no lowercase at all.
_TEX_MATH_FONTS = ("rsfs", "eufm", "eufb", "cmmi", "cmsy", "cmex", "cmbx",
                   "cmr", "msam", "msbm", "stmary", "wasy")


def glyph_loss_advice(sample: str) -> str:
    r"""The repair that actually applies to this dropped character.

    out/219 flagged the old text as wrong for 0707.4470 and this is the
    measured case: `There is no g ("67) in font rsfs10!` — hex 0x67, ASCII
    lowercase g, dropped because \mathscr's alphabet stops at Z. There is no
    code point to add and no fallback font to add it to; the advice pointed the
    reader at the one place the answer could not be. Below U+0080 the diagnosis
    inverts, and a TFM font name inverts it whatever the code point.
    """
    m = _GLYPH_LOST_PARTS.search(sample or "")
    if not m:
        return ("add the code point to report_tex._MATH_CMD or a fallback "
                "font.")
    ch, u, hexc, font = m.group(1), m.group(2), m.group(3), (m.group(4) or "")
    cp = int(u or hexc or "0", 16)
    tfm = any(f in font for f in _TEX_MATH_FONTS)
    if tfm or cp < 0x80:
        return ("%s is not a Unicode coverage problem: the character %r was "
                "set in %s, a TeX math ALPHABET that does not contain it "
                "(rsfs10 has no lowercase; eufm10, contrary to an earlier note "
                "here, does). No fallback font can reach it — change the "
                "command, not the font, which `alphabet_safe` now does for "
                "\\mathscr."
                % ("U+%04X" % cp, ch, font.strip() or "a TeX math font"))
    return ("add U+%04X to report_tex._MATH_CMD, to a fallback family's "
            "measured ranges, or to _NO_FONT for a visible marker." % cp)


class GlyphsDropped(Exception):
    """A compile that produced a PDF while silently discarding characters.

    Raised rather than warned. A dropped glyph leaves a PDF that looks
    finished, passes a page-count check and is wrong in a way no downstream
    consumer can detect — inkdrill measured such a report for half a day
    (out/070). The build must not hand that on as a success.
    """

    def __init__(self, log_path, count, sample):
        self.log_path, self.count, self.sample = log_path, count, sample
        super().__init__(
            "%s: xelatex discarded %d character(s) while still producing a "
            "PDF. First: %s. The PDF is missing symbols with no visible "
            "trace; %s"
            % (Path(log_path).name, count, sample,
               glyph_loss_advice(sample)))


def glyphs_dropped(log_path):
    """(count, first message) for characters the engine threw away, or None."""
    try:
        text = Path(log_path).read_text(errors="replace")
    except OSError:
        return None
    hits = _GLYPH_LOST.findall(text)
    if not hits:
        return None
    m = _GLYPH_LOST.search(text)
    return len(hits), m.group()[:120]


def ink_measurable(log_path) -> "tuple[bool, str]":
    """(ok, reason) — may a residual measurement of this report be trusted?

    221. The residual compares RENDERED ink against SCANNED ink. A glyph the
    engine discarded is absent from the render and present in the scan, which
    is indistinguishable from a glyph the OCR never emitted — so the number
    comes out as an extraction defect when the defect is a missing font. The
    exit code cannot carry this: xelatex wrote the PDF and returned 0, and the
    PDF is perfectly good to READ. It is only measuring that is unsound, and
    the only place that distinction is recorded is the log.

    out/213: six of eleven reports were in this state and every one of them
    exited 0.
    """
    lost = glyphs_dropped(log_path)
    if not lost:
        return True, ""
    n, sample = lost
    return False, ("%s reports %d dropped character(s) — %s. A residual "
                   "measured against this report would charge a font gap to "
                   "the extraction." % (Path(log_path).name, n, sample))


#: 240 — every report says WHEN it was written and against WHICH tree, on one
#: line, before anything else. A report arriving after a newer one is otherwise
#: indistinguishable from a current one, and that happened twice in one session:
#: a five-day-old report.compare.tsv read as fresh off a listing that printed
#: HH:MM with no date, and a published 0902.0431 whose artefacts were two days
#: apart from the library copy they were compared against.
#:
#: `base` is the commit the work started FROM, not the commit containing the
#: report — that hash cannot exist yet, because the report and the change it
#: describes land in the same commit. Naming it `base` rather than `commit` is
#: the difference between a pointer and a claim; `git log --diff-filter=A --
#: out/NNN.txt` gives the containing commit whenever anyone wants it.
#: 244 — a console report says when it was produced. Berlin local time, and
#: the offset DERIVED from the zone rather than written down: Europe/Berlin is
#: +01:00 for half the year and +02:00 for the other half, so a hard-coded one
#: is wrong on one side of every March and October.
#:
#: The abbreviation follows the offset too — MEZ at +01:00, MESZ at +02:00.
#: Printing "MEZ, +02:00" would be a label contradicting the number beside it,
#: which is the shape of defect this file keeps recording.
BERLIN = "Europe/Berlin"


def stamp(when=None) -> str:
    """`2026-08-27 10:56 (MESZ, +02:00)`"""
    import datetime
    from zoneinfo import ZoneInfo
    u = when or datetime.datetime.now(datetime.timezone.utc)
    if u.tzinfo is None:
        u = u.replace(tzinfo=datetime.timezone.utc)
    loc = u.astimezone(ZoneInfo(BERLIN))
    off = loc.strftime("%z")
    name = "MESZ" if loc.dst() else "MEZ"
    return "%s (%s, %s:%s)" % (loc.strftime("%Y-%m-%d %H:%M"), name,
                               off[:3], off[3:])


#: 237 — the build stamp. The measurement build and the reading build write
#: THE SAME filenames, so a phase-1 report is destroyed by the next phase-2
#: build and nothing on disk records which phase the survivor is. 0902.0431's
#: ink.json was measured against a 20-page --min-conf 0.9 --no-legend build and
#: now sits beside a 27-page reading build; every check anyone ran passed,
#: because a measurement build has FEWER pages and its page numbers always fit
#: inside the reading build that replaced it.
#:
#: The filenames cannot be fixed without breaking every consumer. What can be
#: fixed is that the artefact says what it is. Whoever measures a report copies
#: this block into their output as `measured_against`, and a stamp that no
#: longer matches the PDF beside it is then a detectable mismatch rather than a
#: silent one.
BUILD_STAMP = "report.build.json"

#: 237b — and the stamp had the SAME collision as the thing it stamps. It was
#: written to one name and overwritten by the next build, so a phase-2 build
#: destroyed the phase-1 stamp — the one artefact a measurement needs in order
#: to be checkable. Under two-phase the measured build and the published build
#: are different files BY CONSTRUCTION (legend off vs on), so
#: `measured_against.sha256` can never equal the published report's stamp; it
#: has to be checked against the surviving stamp OF THAT PHASE.
def phase_stamp_name(phase: str) -> str:
    return "report.build.%s.json" % phase

#: the key a MEASUREMENT writes into its own output, carrying a copy of the
#: stamp of the build it measured. Named once, here, so both sides spell it the
#: same way.
MEASURED_AGAINST = "measured_against"


def build_stamp(pdf_out: Path) -> dict:
    """Identity of a built report: what it is, not merely that it exists."""
    import hashlib
    import subprocess
    st = pdf_out.stat()
    pages = None
    try:
        out = subprocess.run(["pdfinfo", str(pdf_out)], capture_output=True,
                             text=True, timeout=60).stdout
        m = re.search(r"Pages:\s+(\d+)", out)
        pages = int(m.group(1)) if m else None
    except Exception:
        pages = None
    h = hashlib.sha256()
    with pdf_out.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    import subprocess as _sp
    try:
        commit = _sp.run(["git", "rev-parse", "--short=12", "HEAD"],
                         cwd=str(Path(__file__).resolve().parents[2]),
                         capture_output=True, text=True,
                         timeout=30).stdout.strip() or "unknown"
    except Exception:
        commit = "unknown"
    return {"pdf": pdf_out.name, "pages": pages, "bytes": st.st_size,
            "sha256": h.hexdigest(), "mtime": int(st.st_mtime),
            # 240: which tree built this. mtime orders builds; the commit says
            # what they were built FROM, which mtime cannot.
            "built_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit": commit}


MODEL_NAME = "model.docmodel.json"


def model_state(doc_dir: Path) -> dict:
    """435 — WHICH MODEL STATE a report describes.

    Nothing identified one before this. The model carries no version, no hash
    and no build time — its `meta` is bibkey, source_path, source, pages,
    num_pages, title, authors, root_id — and `report.build.json` hashed the
    REPORT PDF, so an artefact could not say what it was evidence ABOUT.

    A content hash is the right identifier and mtime is not. mtime moves on a
    no-op rewrite and can move BACKWARDS on a restore from backup; a sha256
    changes if and only if the bytes change, which is the question being
    asked. It is recorded alongside mtime and size purely so a mismatch can be
    diagnosed rather than only detected.

    A rebuild always changes it, and that is correct rather than unfortunate:
    object ids are `uuid4().hex[:12]` (docmodel/core.py:26), so no two builds
    of the same input agree — 430 measured 1 id in common out of 2,196. A
    report built against the previous model is describing objects that no
    longer exist, and should say so.
    """
    import hashlib
    m = Path(doc_dir) / MODEL_NAME
    if not m.is_file():
        return {}
    try:
        b = m.read_bytes()
    except OSError:
        return {}
    st = m.stat()
    return {"model_sha256": hashlib.sha256(b).hexdigest(),
            "model_bytes": st.st_size,
            "model_mtime": int(st.st_mtime)}


def write_build_stamp(pdf_out: Path, *, legend: bool, ink_adopted: bool,
                      prefer_refined: bool, filters: dict,
                      glyphs_dropped_count: int = 0,
                      formula_rule: str = "") -> dict:
    """Write BUILD_STAMP beside the report and return it.

    `phase` is the field a reader acts on. A build with no legend and no ink is
    what a measurement should be taken against; anything else is a reading
    build, and measuring one is the defect this exists to make visible.
    """
    import json as _json
    stamp = build_stamp(pdf_out)
    stamp.update({
        "legend": bool(legend),
        "ink_adopted": bool(ink_adopted),
        "prefer_refined": bool(prefer_refined),
        "filters": {k: v for k, v in (filters or {}).items() if v is not None},
        "glyphs_dropped": int(glyphs_dropped_count),
        "phase": ("measure" if (not legend and not ink_adopted) else "reading"),
        # 469 — which formula rule built this. 456 had to infer a report's
        # shape by parsing its own .tex; a field is cheaper and does not lie.
        "formula_rule": formula_rule or "",
        **model_state(pdf_out.parent),
    })
    body = _json.dumps(stamp, indent=1)
    # the latest build, whatever it was
    (pdf_out.parent / BUILD_STAMP).write_text(body, encoding="utf-8")
    # and a copy under this phase's own name, so a phase-1 stamp SURVIVES the
    # phase-2 build that replaces its PDF
    (pdf_out.parent / phase_stamp_name(stamp["phase"])).write_text(
        body, encoding="utf-8")
    return stamp


def measure_stamp(blob_dir: Path) -> dict:
    """The surviving stamp of this document's last phase=measure build."""
    import json as _json
    p = Path(blob_dir) / phase_stamp_name("measure")
    if not p.is_file():
        return {}
    try:
        return _json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def stamp_matches(stamp: dict, pdf_out: Path) -> "tuple[bool, str]":
    """Does a stamp still describe the PDF beside it?

    Compares bytes and sha256, not mtime: a copy preserves content and loses
    mtime, and it is the CONTENT the measurement was taken against.
    """
    if not stamp:
        return True, "no stamp"
    if not pdf_out.is_file():
        return False, "%s is gone" % pdf_out.name
    st = pdf_out.stat()
    if stamp.get("bytes") != st.st_size:
        return False, ("stamp says %s bytes, %s is %s — the build was replaced"
                       % (stamp.get("bytes"), pdf_out.name, st.st_size))
    live = build_stamp(pdf_out)
    if stamp.get("sha256") and stamp["sha256"] != live["sha256"]:
        return False, "same size, different bytes — the build was replaced"
    if stamp.get("pages") and live.get("pages") and \
            stamp["pages"] != live["pages"]:
        return False, ("stamp says %s pages, %s has %s"
                       % (stamp["pages"], pdf_out.name, live["pages"]))
    return True, "matches"




def _surviving_renders(tex_path: Path) -> int:
    """Rendered image cells still present after the fixpoint has demoted the
    rows that could not compile."""
    try:
        body = tex_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0
    i = body.find("Image regions")
    if i < 0:
        return 0
    return body.count("\\resizebox{", i) + body.count("\\FitMath{", i)




def _demote_line(line: str) -> str:
    r"""Replace whatever this row RENDERS with `(not rendered)`, leaving its
    other cells alone. Returns the line unchanged when there is nothing to
    demote.

    284 — the fixpoint used to substitute `$\displaystyle …$` and nothing else.
    An image row renders a picture as `\resizebox{…}{!}{…}`, which that pattern
    does not match, so a tikzcd carrying malformed transcription could not be
    demoted: the loop found no change to make, broke, and left the errors in
    the document. 2208.01506 line 462 is the measured case — a `\csname{op}`
    and a `\mathcal` outside math mode inside a tikzcd.
    """
    out = re.sub(r"\$\\displaystyle .*\$", r"\\emph{(not rendered)}", line)
    if out != line:
        return out
    i = line.find("\\resizebox{")
    if i < 0:
        return line
    # brace-match the third argument — a regex cannot, and the body of a
    # tikzpicture is full of braces
    j = line.find("{", line.find("}", line.find("}", i) + 1) + 1)
    if j < 0:
        return line
    depth, k = 1, j + 1
    while k < len(line) and depth:
        if line[k] == "{" and line[k - 1] != "\\":
            depth += 1
        elif line[k] == "}" and line[k - 1] != "\\":
            depth -= 1
        k += 1
    if depth:
        return line
    return line[:i] + "\\emph{(not rendered)}" + line[k:]


def compile_fixpoint(tex_path: Path, max_iter: int = 6):
    """xelatex the report; demote rows whose lines error to source-only and
    recompile until 0 errors (a malformed OCR snippet must cost its own row,
    never the document). Returns (pages, errors, demoted_rows) or None when
    xelatex is absent.

    297 — the compile runs in a PRIVATE directory. The .tex is copied there and
    the demote loop rewrites the COPY; `-output-directory` sends .aux, .log,
    .out and .pdf there too. cwd stays the document's folder so every relative
    `\\includegraphics` (crops/, standalone-regions/) still resolves — the one
    thing a naive "cd to a temp dir" breaks.

    The .aux is the reason. It is written by pass N and READ by pass N+1, so
    two builds sharing one produce a PDF whose cross-references were resolved
    against the other build's numbering: it compiles, it looks right, and every
    reference points at the wrong equation. Only the finished PDF, .log and the
    demoted .tex are copied back, the PDF through a temp name so a reader never
    opens a half-written file.
    """
    import re as _re
    import shutil
    import subprocess
    import tempfile
    if shutil.which("xelatex") is None:
        return None
    d = tex_path.parent
    work = Path(tempfile.mkdtemp(prefix="pdfdrill-tex-"))
    try:
        src_tex = work / tex_path.name
        shutil.copy2(tex_path, src_tex)
        log = src_tex.with_suffix(".log")
        cmd = ["xelatex", "-interaction=nonstopmode",
               "-output-directory", str(work), str(src_tex)]
        demoted: set[int] = set()
        pages = nerr = 0
        for _ in range(max_iter):
            subprocess.run(cmd, cwd=d, capture_output=True, timeout=1800)
            text = log.read_text(errors="replace") if log.is_file() else ""
            nerr = len(_re.findall(r"^! ", text, _re.M))
            m = _re.search(r"Output written on .*\((\d+) pages?", text)
            pages = int(m.group(1)) if m else 0
            if nerr == 0:
                break
            src = src_tex.read_text().split("\n")
            changed = False
            for n in sorted({int(x) for x in
                             _re.findall(r"^l\.(\d+)", text, _re.M)}):
                i = n - 1
                if i < len(src):
                    new = _demote_line(src[i])
                    if new != src[i]:
                        src[i] = new
                        demoted.add(n)
                        changed = True
            if not changed:
                break
            src_tex.write_text("\n".join(src))
        # final pass for longtable column alignment
        subprocess.run(cmd, cwd=d, capture_output=True, timeout=1800)
        text = log.read_text(errors="replace") if log.is_file() else ""
        nerr = len(_re.findall(r"^! ", text, _re.M))
        m = _re.search(r"Output written on .*\((\d+) pages?", text)
        pages = int(m.group(1)) if m else pages
        _publish(src_tex, tex_path, demoted)
        return pages, nerr, len(demoted)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _publish(src_tex: Path, tex_path: Path, demoted: set) -> None:
    """Copy the private build's products back beside the document.

    The .tex goes back only when the demote loop changed it, so an unchanged
    document keeps its original mtime and the staleness guards stay honest.
    """
    import shutil
    d = tex_path.parent
    if demoted:
        shutil.copy2(src_tex, tex_path)
    for suffix in (".log",):
        f = src_tex.with_suffix(suffix)
        if f.is_file():
            shutil.copy2(f, d / (tex_path.stem + suffix))
    pdf = src_tex.with_suffix(".pdf")
    if pdf.is_file():
        dest = d / (tex_path.stem + ".pdf")
        tmp = d / ("." + dest.name + ".part")
        shutil.copy2(pdf, tmp)
        os.replace(tmp, dest)             # atomic: a reader sees old or new


#: 143 — the object kinds `--types` can select, and the row list each maps to
TYPE_NAMES = ("equation", "formula", "table", "diagram")


def parse_types(spec: "str | None") -> "set[str] | None":
    """`--types equation,formula` -> {"equation","formula"}; None means all.

    Unknown names raise rather than being ignored: a typo that silently selected
    everything would produce a full-size report and look like the filter simply
    had no matches.
    """
    if not spec:
        return None
    want = {t.strip().lower() for t in spec.split(",") if t.strip()}
    bad = want - set(TYPE_NAMES)
    if bad:
        raise ValueError("unknown --types %s (known: %s)"
                         % (", ".join(sorted(bad)), ", ".join(TYPE_NAMES)))
    return want or None


def _conf_ok(conf, lo, hi) -> bool:
    """Does this row's confidence fall inside [lo, hi]?

    A row with NO confidence value fails whenever a bound is given. It cannot be
    shown to satisfy the filter, and including it would mean `--max-conf 0.5`
    returned rows of unknown confidence alongside the doubted ones — which is
    the opposite of what the flag is for. With no bounds it passes.
    """
    if lo is None and hi is None:
        return True
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return False
    if lo is not None and c < lo:
        return False
    if hi is not None and c > hi:
        return False
    return True


def resolve_bibkey(tiddlers_path: Path) -> str:
    r"""The bibkey for a tiddlers file: THE MODEL'S, not the filename's (463).

    404 learned this for `publish_ready`, which inferred the bibkey from
    `blob_dir.name`; there is a test named for it. The same inference sat in
    `build_report`, reading the bibkey off the tiddlers FILENAME, and was
    never looked at.

    462 renamed nine documents' bibkeys without renaming their folders — stem
    and bibkey have been separable since 276. So every tiddler title became
    `voloshin-hypergraph_EQ0001` while the file went on being called
    `Introduction to Graph and Hypergraph Theory (...).tiddlers.json`.
    `rows_for` matches on the bibkey prefix, matched nothing, and built a
    one-page report with no rows from a model holding 2,555 formulas and 266
    equations. It compiled. It stamped. It did that to nine documents.

    The model is the authority: `meta.bibkey` is what `renamefolder`
    retargets and what every identifier is built from. The filename is the
    fallback for a tiddlers file with no model beside it.
    """
    p = Path(tiddlers_path)
    model = p.parent / MODEL_NAME
    if model.is_file():
        try:
            import json as _json
            meta = (_json.loads(model.read_text(encoding="utf-8",
                                                errors="replace"))
                    .get("meta") or {})
            if meta.get("bibkey"):
                return str(meta["bibkey"])
        except (OSError, ValueError):
            pass
    return p.name.replace(".tiddlers.json", "")


class ReportRefused(ValueError):
    """The report would be empty for a reason that is a defect, not a fact."""


def build_report(tiddlers_path: Path, out: Path | None = None,
                 crops: Path | None = None, texzip: Path | None = None,
                 paper: str = "a4", landscape: bool = False,
                 px2mm: float | None = None,
                 min_conf: float | None = None, max_conf: float | None = None,
                 types: "set[str] | None" = None, form: bool = False,
                 ink: "dict | None" = None, legend_on: bool = True,
                 ink_state: str = "", prefer_refined: bool = False,
                 bibkey_history: "list[str] | None" = None,
                 render_regions: bool = False,
                 formulas: str = "unresolved") -> dict:
    """Generate report.tex; returns counts {equations, formulas, tables,
    unrecovered, out}.

    143 — `min_conf`/`max_conf` bound the MathPix confidence column and `types`
    selects object kinds. Both narrow the row set before any crop is sized, so a
    filtered report is smaller on disk as well as shorter.
    """
    import json
    path = Path(tiddlers_path)
    tiddlers = json.loads(path.read_text())
    bibkey = resolve_bibkey(path)
    refined = refined_map(tiddlers) if prefer_refined else {}
    fo, eq, tab, dia = rows_for(tiddlers, bibkey, refined)
    # 463 — AN EMPTY REPORT FROM A NON-EMPTY PROJECTION IS A DEFECT.
    #
    # A document with no mathematics is a fact and yields no rows. A document
    # whose tiddlers carry thousands of typed titles and yields no rows is a
    # bibkey that does not match them, and the old behaviour was to build the
    # empty report, compile it, stamp it and report success.
    if not (fo or eq or tab or dia):
        typed = [x.get("title", "") for x in tiddlers
                 if TYPED_TITLE.search(x.get("title", ""))]
        if typed:
            raise ReportRefused(
                "no rows for bibkey %r, but %d tiddlers carry typed titles "
                "(e.g. %r) — the bibkey and the titles disagree. Check "
                "meta.bibkey against the projection."
                % (bibkey, len(typed), typed[0]))
    if types is not None:
        if "equation" not in types: eq = []
        if "formula" not in types: fo = []
        if "table" not in types: tab = []
        if "diagram" not in types: dia = []
    if min_conf is not None or max_conf is not None:
        # confidence lives on EQ rows only (index 6); FO/TAB/DIA carry none, so
        # a bounded run drops them rather than mixing unknowns in with doubted
        eq = [r for r in eq if _conf_ok(r[6], min_conf, max_conf)]
        fo, tab, dia = [], [], []
    # 460 — THE FORMULAS SECTION IS NOT A CATALOGUE.
    #
    # `all` is what the report did until now. `unresolved` keeps only the rows
    # whose Rendered cell would say "(not rendered)", so the section is the
    # work still owed rather than an inventory; `none` drops it outright.
    # Under `unresolved` an empty result omits the section AND its manifest
    # record — inkmeasure joins on the "Display equations" caption alone, and
    # that table comes first, so its page range does not move.
    if formulas not in FORMULA_RULES:
        raise ValueError("formulas must be one of %s, not %r"
                         % (", ".join(FORMULA_RULES), formulas))
    fo_total = len(fo)
    fo_all = list(fo)
    if formulas == "none":
        fo = []
    elif formulas == "unresolved":
        fo = unresolved_formulas(fo)
    fo_withheld = fo_total - len(fo)

    dest = Path(out) if out else path.parent / "report.tex"
    crops = Path(crops).resolve() if crops else None
    out_dir = dest.resolve().parent

    w_mm, h_mm = PAPER_MM[paper]
    if landscape:
        w_mm, h_mm = h_mm, w_mm
    usable = w_mm - 36  # 18mm margins
    geom = "%spaper%s" % (paper, ",landscape" if landscape else "")
    eq_widths = col_widths(usable, with_image=bool(crops))
    fo_widths = col_widths(usable, with_image=False)
    img_col = eq_widths[5] if crops else None
    if crops and px2mm:
        widest = 0.0
        for title, _lx, _pg, _num, wpx, _pt, _cf in eq:
            f = crop_file(crops, title, bibkey, bibkey_history)
            if f is not None:
                w = jpg_width(f) or (float(wpx) if wpx else 0)
                widest = max(widest, float(w) * px2mm)
        if widest and widest + 2 < eq_widths[5]:
            freed = eq_widths[5] - (round(widest) + 2)
            eq_widths = (eq_widths[0], eq_widths[1], eq_widths[2],
                         eq_widths[3], eq_widths[4] + freed, round(widest) + 2)
            img_col = eq_widths[5]

    out_parts = [None]          # preamble filled in once the body is known
    # 469 — WHEN THE SECTION IS OMITTED, THE COUNT IS NOT.
    #
    # `none` is what the published profile uses, and a published report that
    # simply dropped the section would also drop the only statement that some
    # of its formulas do not render. Omitting the rows is a choice about what
    # is worth a page; omitting the fact would be a claim of cleanliness the
    # document has not earned. So the header states the unresolved count under
    # every rule, including the one that shows nothing.
    fo_says = "%d inline formulas" % fo_total
    if fo_withheld:
        if formulas == "unresolved":
            fo_says += " (%d shown: the ones that did not render)" % len(fo)
        else:
            n_un = len(unresolved_formulas(fo_all))
            fo_says += (" (section omitted; %s)"
                        % ("%d did not render" % n_un if n_un
                           else "all rendered"))
    out_parts.append("\\section*{%s — formula report}\n"
                     "%s, %d display equations, %d tables, "
                     "%d unrecovered image regions.\n"
                     % (esc_text(bibkey), fo_says, len(eq), len(tab),
                        len(dia)))
    # 180: at the TOP, where a reader decides what they are looking at, not in
    # a footer they reach after reading the table as if it were complete.
    if not form:
        out_parts.append(unmeasured_note(ink_state or "not_run"))
    out_parts.append(refined_note(refined))
    tables_manifest = []
    out_parts.append(table_open("Display equations", eq_widths, form, legend_on))
    # 099: doubted rows first. Sorting by confidence ascending puts what
    # MathPix is least sure of at the top of the table, where a reader
    # checking the document looks first. Rows with no confidence value sort
    # LAST rather than first: absence is not doubt.
    eq = sorted(eq, key=lambda r: (float(r[6]) if r[6] not in (None, "") else 2.0))
    for title, latex, page, num, wpx, punct, conf in eq:
        img = crop_cell(crops, out_dir, title, px_width=wpx,
                        px2mm=px2mm, col_mm=img_col,
                        bibkey=bibkey, history=bibkey_history) if crops else None
        sa = (standalone_math(latex, title, out_dir, col_mm=eq_widths[4])
              if refused_for_align_only(latex) else "")
        out_parts.append(row(title, latex, page, extra=num, image=img,
                             standalone=sa,
                             punct=punct, conf=conf, form=form,
                             residual=residual_colour(title, ink),
                             code=((ink or {}).get(title) or {}).get("code", ""),
                             refined=refined.get(title)))
    out_parts.append("\\end{longtable}\n")
    tables_manifest.append(_table_record(
        "Display equations", eq_widths, legend_on, True, [r[0] for r in eq]))

    # every section starts on a FRESH page: a page mixing the 5-column
    # equations table with the 4-column formulas table defeats per-page
    # column probes (inkdrill P16, the 11 short-equation docs)
    if fo:
        out_parts.append("\\clearpage\n")
        caption = ("Inline formulas (first occurrence)" if formulas == "all"
                   else "Inline formulas that did not render (%d of %d)"
                        % (len(fo), fo_total))
        out_parts.append(table_open(caption, fo_widths, form, legend_on))
        for title, latex, page, punct in fo:
            sa = (standalone_math(latex, title, out_dir, col_mm=fo_widths[4])
                  if refused_for_align_only(latex) else "")
            out_parts.append(row(title, latex, page, punct=punct, standalone=sa,
                                 refined=refined.get(title)))
        out_parts.append("\\end{longtable}\n")
        tables_manifest.append(_table_record(
            caption, fo_widths, legend_on, True, [r[0] for r in fo]))

    if tab:
        # 423 — THE SAME SIX COLUMNS AS THE EQUATIONS SECTION.
        #
        # This section had four: Identifier, Page, "Content (LaTeX source if
        # any)", Scan image. No Conf., no Rendered, and a third column that
        # merged the source with an apology when there was none. One section
        # of four with its own shape meant one logic could not cover the
        # report, and it is where the drift 422 documented began.
        #
        # Conf. is the DASH for every table row, and correctly: Table objects
        # carry no confidence prop at all — 0 of 42 on chung2019combinatorics
        # against 411 of 411 for its equations — and 252 says an absent
        # reading shows a dash rather than a colour, because a blank green
        # square would assert one.
        #
        # Rendered is the column 424 fills. It shows "(not rendered)" until
        # then, which is the same thing an equation row says when its LaTeX
        # will not compile — a state the reader already knows how to read.
        out_parts.append("\\clearpage\n")
        # the SAME width function the equations section uses, so the two
        # sections line up column for column rather than only in count.
        tab_widths = col_widths(usable, with_image=bool(crops))
        out_parts.append(table_open("Tables", tab_widths, form, legend_on))
        for title, latex, page, dims, _region, tconf in tab:
            src_cell = ("{\\ttfamily\\footnotesize %s}" % esc_text(latex)
                        ) if latex else (
                # 426 — no cross-reference. This said "see tables.html", in
                # 10,928 rows across 680 documents, and that file exists in 17
                # of them. Where it does exist it is pdfplumber's keyless
                # extraction of the page, not this row's table rendered.
                # report.pdf is the universal artefact and tables.html a rare
                # one; a reference in that direction has to dangle.
                "(no LaTeX source; %s\\,$\\times$\\,%s px region)" % dims)
            img = crop_cell(crops, out_dir, title,
                            px_width=dims[0], px2mm=px2mm,
                            col_mm=tab_widths[-1],
                            bibkey=bibkey, history=bibkey_history)
            safe = renderable(latex) if latex else ""
            rendered = ("\\FitMath{$\\displaystyle %s$}" % safe) if safe else (
                "\\emph{(not rendered)}" if latex else "---")
            out_parts.append(
                "\\ident{%s} & %s & %s & %s & %s & %s \\\\ \\hline\n"
                % (esc_text(title), esc_text(str(page)), conf_cell(tconf),
                   src_cell, rendered, img))
        out_parts.append("\\end{longtable}\n")
        tables_manifest.append(_table_record(
            "Tables", tab_widths, legend_on, True, [r[0] for r in tab]))

    named = unnamed = rendered = duplicated = 0
    manifest: list = []
    if dia:
        out_parts.append("\\clearpage\n")
        zreg, zn = ({}, 0)
        if texzip:
            zreg, zn = texzip_images(Path(texzip))
        # 340 — how many rows name each tex.zip crop, so a shared one can be
        # marked contested in the row that carries it.
        crop_claims: dict = {}
        for _t, _lx, _pg, _dm, _rg in dia:
            try:
                _f = zreg.get(tuple(int(x) for x in _rg))
            except (TypeError, ValueError):
                _f = None
            if _f is not None:
                crop_claims[_f.name] = crop_claims.get(_f.name, 0) + 1
        span = usable - 20 - 7 - 12 - 20
        # 284 (revised) — TWO image columns, and they are the LAST two, which
        # is what `inkdrill compare` defaults to. They get equal width because
        # the whole point is comparing them: a Rendered cell narrower than its
        # Scan would put a scale difference into the residual.
        # 340 — a fifth column, the hand-editing surface. It takes its width
        # from the two image columns so the row still fits: the reader compares
        # Rendered against Scan, and the new cell only has to be big enough to
        # recognise the crop in.
        dnote = round(span * 0.22)
        dauth = round(span * 0.16)
        drend = round((span - dnote - dauth) / 2)
        dimg = span - dnote - dauth - drend
        regdir = dest.parent / "standalone-regions"
        # The residual class per identifier, from a previous measurement.
        # Absent on the first pass — the class column is "---" until the
        # regions have been measured, which is the honest state rather than a
        # blank that looks like "clean".
        ink_class = {}
        try:
            _rj = dest.parent / REGIONS_INK
            if _rj.is_file():
                ink_class = {r["id"]: r.get("code") or r.get("flag") or ""
                             for r in (json.loads(_rj.read_text(
                                 encoding="utf-8")).get("rows") or [])
                             if r.get("id")}
        except Exception:
            ink_class = {}
        out_parts.append(
            "\\section*{Image regions — rendered against scan}\n"
            "Two comparable cells per row. \\textbf{Rendered}: the region's "
            "own LaTeX compiled as its OWN document, or — where no LaTeX "
            "exists — the scan again, so every row has two cells and the ink "
            "difference reads as a floor rather than as "
            "missing-versus-present. A duplicated row is marked "
            "\\emph{(dup)} and its distance is a SELF-comparison, not "
            "agreement between two sources. \\textbf{Scan}: the "
            "\\texttt{tex.zip} image whose filename region 5-tuple matches "
            "this row, else the CDN crop. The Class column carries the "
            "residual class beside MathPix's confidence, as the equation rows "
            "do. Setting a region's LaTeX does NOT say it renders to what is "
            "on the page — that is what the two columns are for, and 281 is "
            "the open question they exist to let a reader answer. A region "
            "with no LaTeX can be reconstructed with \\texttt{pdfdrill "
            "vision}; verify any LLM result against the real ink with "
            "inkdrill.\n"
            "\\begin{longtable}{|p{20mm}|p{7mm}|p{12mm}|p{%smm}|p{%smm}|"
            "p{%smm}|p{%smm}|}\n"
            "\\hline\n\\textbf{Identifier} & \\textbf{Page} & "
            "\\textbf{Class} & \\textbf{Source} & "
            "\\textbf{Author source} & \\textbf{Rendered} & "
            "\\textbf{Scan} \\\\\n"
            # NO \endhead. The header is a 6-cell row and `inkdrill compare`
            # reads it as data — one spurious measurement per page, offsetting
            # every identifier after it. Printed once, exactly one row has to
            # be dropped and the pairing can be ASSERTED rather than guessed.
            "\\hline\n" % (dnote, dauth, drend, dimg))
        for title, latex, page, dims, region in dia:
            img_path = zip_name = None
            try:
                img_path = zreg.get(tuple(int(x) for x in region))
            except (TypeError, ValueError):
                img_path = None
            if img_path is not None:
                zip_name = img_path.name
                named += 1
            else:
                unnamed += 1
            # The CROP still fills the Image column when the zip has no match:
            # the picture is what a reader compares against, and it is
            # available for every row (278 — the rectangle is stated on 100% of
            # these lines). Only the SOURCE column depends on the lookup.
            if img_path is None and crops:
                img_path = crop_file(crops, title, bibkey, bibkey_history)
            if img_path is not None:
                w_mm2 = None
                if px2mm:
                    real = jpg_width(img_path) or dims[0]
                    try:
                        w_mm2 = min(float(real) * px2mm, dimg)
                    except (TypeError, ValueError):
                        pass
                size = ("width=%.1fmm" % w_mm2) if w_mm2 else \
                    "width=\\linewidth"
                try:
                    rel = img_path.resolve().relative_to(out_dir)
                except ValueError:
                    rel = img_path
                cell = "\\includegraphics[%s]{%s}" % (
                    size, str(rel).replace("\\", "/"))
            else:
                cell = ("\\emph{(image not on disk — pass --texzip or "
                        "download the CDN crop)}")
            # 282 — a genuine ABSENCE must not read like a failed lookup.
            # 285 of 1,216 corpus tex.zips hold no image at all; saying
            # "no match" there would blame the lookup for an empty container.
            if zip_name:
                srcnote = "{\\ttfamily\\tiny %s}" % esc_text(zip_name)
            elif not texzip:
                srcnote = "\\emph{no tex.zip}"
            elif zn == 0:
                srcnote = "\\emph{tex.zip holds no images}"
            else:
                srcnote = "\\emph{no image for this region (%d in zip)}" % zn
            # RENDERED CELL. The region's own LaTeX, compiled standalone by
            # `region_standalone.render` into standalone-regions/<ident>.png.
            # Where there is none — 25,499 of 27,287 corpus rows — the SCAN is
            # repeated here, so the row still has two comparable cells and the
            # residual reads as a floor instead of missing-versus-present.
            reg_png = regdir / ("%s.png" % title)
            if render_regions and reg_png.is_file():
                rcell = _img_cell(reg_png, out_dir, drend, px2mm, dims)
                rendered += 1
                dup = False
            else:
                rcell = cell                       # the scan, repeated
                duplicated += 1
                dup = True
            klass = ink_class.get(title, "")
            ccell = ("{\\tiny %s}" % esc_text(klass)) if klass else "---"
            if dup:
                ccell += " \\emph{\\tiny(dup)}"
            manifest.append({
                "id": title, "page": str(page),
                "rendered_source": ("standalone" if not dup else "scan (duplicated)"),
                "scan_source": (zip_name if zip_name else
                                ("crop" if img_path is not None else "none")),
                "duplicated": dup,
                "has_latex": bool((latex or "").strip()),
            })
            # 340 — the editing cell. It ships holding the crop's OWN name,
            # so an untouched report shows the crop twice and a reader can see
            # at a glance which rows are still unedited. A crop claimed by
            # several rows is marked contested here rather than left for a
            # join to discover: two subfigures sharing one crop is obvious to
            # a person and invisible to a rule (339 found 14 such rows).
            if zip_name and img_path is not None:
                # the path the SCAN cell resolves, not the bare stem: the crops
                # live under texzip/<process-id>/images/ and \includegraphics
                # cannot find a name without its directory. Shipping a
                # placeholder that does not compile would make every report
                # error five times before anyone edited anything.
                try:
                    arel = img_path.resolve().relative_to(out_dir)
                except ValueError:
                    arel = img_path
                arel = str(arel).replace("\\", "/")
                if arel.lower().endswith(".jpg"):
                    arel = arel[:-4]
                acell = "\\authorsrc{%s}" % arel
                if crop_claims.get(zip_name, 0) > 1:
                    acell += ("\\\\{\\tiny\\emph{contested: %d rows share "
                              "this crop}}" % crop_claims[zip_name])
            else:
                acell = "{\\tiny\\emph{(no tex.zip crop for this row)}}"
            out_parts.append("\\ident{%s} & %s & %s & %s & %s & %s & %s "
                             "\\\\ \\hline\n"
                             % (esc_text(title), esc_text(str(page)),
                                ccell, srcnote, acell, rcell, cell))
        out_parts.append("\\end{longtable}\n")
        # NO \endhead on this one (284) — its header prints once.
        tables_manifest.append(_table_record(
            "Image regions — rendered against scan", (20, 7, 12, dnote,
             drend, dimg), False, False, [r[0] for r in dia]))

    out_parts.append("\\end{document}\n")
    # 090: the declarations depend on what the body actually contains, so the
    # preamble is written LAST and lists only the code points this document
    # needed rescuing. A report that needs none carries none.
    out_parts[0] = PREAMBLE % {"bbdigits": MATHBB_DIGITS,
                               "form": FORM_PREAMBLE if form else "",
                               "geom": geom,
                               "unicode": unicode_decls("".join(out_parts[1:]))}
    dest.write_text("".join(out_parts))
    for i, t in enumerate(tables_manifest, 1):
        t["ordinal"] = i
    (dest.parent / TABLES_MANIFEST).write_text(
        json.dumps({"bibkey": bibkey, "tables": tables_manifest}, indent=1),
        encoding="utf-8")
    if manifest:
        (dest.parent / REGIONS_MANIFEST).write_text(
            json.dumps({"bibkey": bibkey, "rows": manifest}, indent=1),
            encoding="utf-8")
    return {"equations": len(eq), "formulas": len(fo), "tables": len(tab),
            # 460 — `formulas` is what the section SHOWS. `formulas_total` is
            # what the document has and `formula_rule` says why the two
            # differ, so a caller reading only the first number cannot mistake
            # a filtered section for a short document.
            "formulas_total": fo_total, "formula_rule": formulas,
            "unrecovered": len(dia), "out": dest,
            # 282 — how many image rows name their tex.zip source, and how many
            # do not. `texzip_images` is 0 when the zip holds no images at all,
            # which is a different fact from a lookup that failed.
            "image_named": named, "image_unnamed": unnamed,
            # 284 — `image_rendered` is what was EMITTED. `image_rendered_kept`
            # is what survived the compile fixpoint, and they are not the same
            # number: on 2208.01506 all 43 rows emitted a rendered cell and 25
            # of them errored and were demoted. Reporting the first alone would
            # be reporting intent as outcome.
            "image_rendered": rendered,
            "image_duplicated": duplicated,
            "image_rendered_kept": _surviving_renders(dest),
            "texzip_images": (texzip_images(Path(texzip))[1] if texzip else 0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tiddlers")
    ap.add_argument("--out", default=None)
    ap.add_argument("--crops", default=None)
    ap.add_argument("--texzip", default=None)
    ap.add_argument("--paper", choices=("a4", "a3"), default="a4")
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--px2mm", type=float, default=None)
    args = ap.parse_args()
    r = build_report(Path(args.tiddlers), out=args.out,
                     crops=args.crops, texzip=args.texzip, paper=args.paper,
                     landscape=args.landscape, px2mm=args.px2mm)
    print(f"{r['out']}: {r['equations']} equations, {r['formulas']} formulas, "
          f"{r['tables']} tables, {r['unrecovered']} unrecovered regions")


if __name__ == "__main__":
    main()


#: DejaVu Sans Mono's coverage, as ranges read from the font file itself. Used
#: to check that an NFKC expansion lands on characters the mono font can
#: actually set — folding a glyph onto another missing glyph fixes nothing.
_COVERED_RANGES = (
    (0,0), (8,9), (13,13), (29,29), (32,126), (128,451),
    (461,483), (486,496), (500,502), (504,505), (508,545), (548,577),
    (579,581), (588,589), (592,697), (699,705), (710,713), (716,723),
    (726,734), (736,745), (750,750), (755,755), (768,831), (835,835),
    (856,856), (865,865), (884,887), (890,895), (900,906), (908,908),
    (910,929), (931,974), (976,993), (1008,1119), (1122,1123), (1138,1139),
    (1168,1179), (1186,1189), (1194,1203), (1210,1211), (1216,1220), (1223,1224),
    (1227,1228), (1231,1273), (1296,1297), (1306,1309), (1329,1366), (1369,1375),
    (1377,1415), (1417,1418), (1542,1543), (1545,1546), (1548,1548), (1557,1557),
    (1563,1563), (1567,1567), (1569,1594), (1600,1621), (1626,1626), (1632,1645),
    (1652,1652), (1657,1659), (1662,1664), (1667,1668), (1670,1671), (1681,1681),
    (1688,1688), (1700,1700), (1705,1705), (1711,1711), (1726,1726), (1740,1740),
    (1776,1785), (3647,3647), (3713,3714), (3716,3716), (3719,3720), (3722,3722),
    (3725,3725), (3732,3735), (3737,3743), (3745,3747), (3749,3749), (3751,3751),
    (3754,3755), (3757,3769), (3771,3772), (3784,3789), (4304,4348), (7426,7426),
    (7432,7433), (7444,7444), (7446,7447), (7453,7455), (7468,7470), (7472,7484),
    (7486,7515), (7522,7525), (7543,7544), (7547,7547), (7557,7557), (7579,7607),
    (7609,7615), (7680,7699), (7704,7725), (7728,7757), (7764,7779), (7784,7801),
    (7804,7833), (7835,7835), (7839,7841), (7852,7853), (7856,7857), (7862,7865),
    (7868,7869), (7878,7879), (7882,7885), (7896,7901), (7904,7909), (7912,7915),
    (7918,7925), (7928,7929), (7936,7957), (7960,7965), (7968,8005), (8008,8013),
    (8016,8023), (8025,8025), (8027,8027), (8029,8029), (8031,8061), (8064,8116),
    (8118,8132), (8134,8147), (8150,8155), (8157,8175), (8178,8180), (8182,8190),
    (8192,8202), (8208,8227), (8230,8230), (8239,8247), (8249,8250), (8252,8255),
    (8261,8265), (8267,8267), (8287,8287), (8304,8305), (8308,8334), (8336,8348),
    (8352,8373), (8376,8378), (8381,8381), (8450,8450), (8453,8453), (8461,8463),
    (8469,8471), (8473,8474), (8477,8477), (8482,8482), (8484,8484), (8486,8486),
    (8490,8491), (8494,8494), (8520,8520), (8528,8529), (8531,8543), (8585,8585),
    (8592,8723), (8725,8725), (8727,8736), (8739,8739), (8743,8749), (8756,8765),
    (8769,8809), (8813,8843), (8845,8869), (8882,8885), (8888,8888), (8898,8902),
    (8909,8913), (8922,8937), (8943,8943), (8960,8966), (8968,8981), (8984,8985),
    (8988,8993), (8997,9000), (9003,9003), (9013,9082), (9085,9085), (9088,9091),
    (9096,9099), (9109,9109), (9115,9134), (9166,9167), (9251,9251), (9472,9775),
    (9784,9867), (9872,9884), (9888,9889), (9904,9905), (9985,9988), (9990,9993),
    (9996,10023), (10025,10059), (10061,10061), (10063,10066), (10070,10070), (10072,10078),
    (10081,10101), (10132,10132), (10136,10159), (10161,10174), (10178,10178), (10181,10182),
    (10204,10204), (10208,10208), (10214,10219), (10229,10231), (10631,10632), (10647,10648),
    (10731,10731), (10746,10747), (10752,10752), (10799,10799), (10858,10859), (11013,11021),
    (11026,11034), (11364,11364), (11373,11376), (11381,11383), (11385,11386), (11388,11391),
    (11800,11800), (11807,11807), (11810,11813), (11822,11822), (42760,42774), (42779,42783),
    (42786,42791), (42889,42894), (42896,42897), (42922,42922), (43000,43001), (63173,63173),
    (64257,64258), (64338,64385), (64394,64405), (64414,64415), (64426,64429), (64488,64489),
    (64508,64511), (65136,65140), (65142,65276), (65279,65279), (65529,65533), (120154,120154),
    (120432,120483), (120822,120831),
)
_COVERED = frozenset(c for a, b in _COVERED_RANGES for c in range(a, b + 1))

#: 090 — code points the report's fonts cannot set, measured with fontTools
#: against the actual font files on this machine rather than assumed. DejaVu
#: Sans Mono covers 208 of the 400 that out/088 found; NFKC folds 120 more onto
#: covered characters; these are the remainder.
#:
#: NOTE ON THE MECHANISM. \DeclareUnicodeCharacter is an inputenc facility and
#: does NOTHING under xelatex, which is the engine these reports use. The
#: evidence is in the logs: out/089 found 0 occurrences of "not set up for use
#: with LaTeX" — inputenc's own message — across 1,702 compiles, against 24,953
#: "Missing character" warnings, which is the font layer speaking. The fix is
#: therefore newunicodechar plus real fonts, not a declaration xelatex ignores.
_FB_MATH = frozenset((
    0x200B, 0x2044, 0x20D2, 0x20D7, 0x2216, 0x2225, 0x226B, 0x22BA,
    0x23DE, 0x23DF, 0x27F9, 0x27FA, 0x2A7D,
))
_FB_CJK = frozenset((
    0x2FF1, 0x2FF4, 0x2FF8, 0x2FFA, 0x2FFB, 0x3002, 0x3009, 0x300D,
    0x300E, 0x3064, 0x30B3, 0x31D2, 0x4E00, 0x4E04, 0x4E05, 0x4E92,
    0x4F5C, 0x516B, 0x5186, 0x5341, 0x5B50, 0x5B54, 0x65E5, 0x771F,
))
#: 223 — the other half of the same measurement: code points DejaVu SERIF has
#: and DejaVu Sans Mono does not (1,042 of them). With _COVERED (mono) and
#: _MONO_ONLY_RANGES (mono minus serif), these three decide exactly which of
#: the two text fonts carries any given character, so a declaration can name
#: the one that does instead of hoping the ambient font is the right one.
_MAIN_ONLY_RANGES = (
    (0x01C4, 0x01CC), (0x01E4, 0x01E5), (0x01F1, 0x01F3), (0x01F7, 0x01F7),
    (0x01FA, 0x01FB), (0x0222, 0x0223), (0x0242, 0x0242), (0x0246, 0x024B),
    (0x024E, 0x024F), (0x02BA, 0x02BA), (0x02C2, 0x02C5), (0x02CA, 0x02CB),
    (0x02EC, 0x02EC), (0x02EF, 0x02F0), (0x02F7, 0x02F7), (0x034F, 0x034F),
    (0x0360, 0x0360), (0x0370, 0x0373), (0x03CF, 0x03CF), (0x0464, 0x0465),
    (0x046A, 0x046D), (0x0470, 0x0471), (0x0474, 0x0477), (0x048C, 0x048D),
    (0x049E, 0x04A1), (0x04A6, 0x04A7), (0x04B4, 0x04B7), (0x0512, 0x0515),
    (0x10A0, 0x10C5), (0x1D00, 0x1D01), (0x1D03, 0x1D07), (0x1D0A, 0x1D13),
    (0x1D15, 0x1D15), (0x1D18, 0x1D1C), (0x1D20, 0x1D2B), (0x1D2F, 0x1D2F),
    (0x1D3D, 0x1D3D), (0x1D5C, 0x1D61), (0x1D66, 0x1D6B), (0x1D7C, 0x1D7F),
    (0x1DB8, 0x1DB8), (0x1DC4, 0x1DC9), (0x1E14, 0x1E17), (0x1E2E, 0x1E2F),
    (0x1E4E, 0x1E53), (0x1E64, 0x1E67), (0x1E7A, 0x1E7B), (0x1E9A, 0x1E9A),
    (0x1E9C, 0x1E9E), (0x1EA2, 0x1EAB), (0x1EAE, 0x1EAF), (0x1EB2, 0x1EB5),
    (0x1EBA, 0x1EBB), (0x1EBE, 0x1EC5), (0x1EC8, 0x1EC9), (0x1ECE, 0x1ED7),
    (0x1EDE, 0x1EDF), (0x1EE6, 0x1EE7), (0x1EEC, 0x1EED), (0x1EF6, 0x1EF7),
    (0x1EFA, 0x1EFB), (0x200B, 0x200F), (0x2024, 0x2025), (0x202A, 0x202E),
    (0x2038, 0x2038), (0x2042, 0x2042), (0x2044, 0x2044), (0x204C, 0x204F),
    (0x2051, 0x2053), (0x2057, 0x2057), (0x2060, 0x2064), (0x206A, 0x206F),
    (0x2103, 0x2103), (0x2109, 0x2109), (0x2127, 0x2127), (0x2132, 0x2132),
    (0x213C, 0x2147), (0x2149, 0x2149), (0x214B, 0x214B), (0x214E, 0x214E),
    (0x2152, 0x2152), (0x2160, 0x2185), (0x2214, 0x2214), (0x2224, 0x2226),
    (0x228C, 0x228C), (0x22A6, 0x22AF), (0x23B7, 0x23B7), (0x27F0, 0x27F4),
    (0x27F8, 0x297F), (0x2A0C, 0x2A0E), (0x2B00, 0x2B04), (0x2B0E, 0x2B11),
    (0x2C60, 0x2C61), (0x2C63, 0x2C63), (0x2C67, 0x2C6C), (0x2C71, 0x2C73),
    (0x2C7B, 0x2C7B), (0x2D00, 0x2D25), (0xA644, 0xA647), (0xA650, 0xA651),
    (0xA654, 0xA657), (0xA698, 0xA699), (0xA728, 0xA741), (0xA746, 0xA747),
    (0xA74A, 0xA74B), (0xA74E, 0xA74F), (0xA768, 0xA769), (0xA77B, 0xA77C),
    (0xA780, 0xA787), (0xA7FA, 0xA7FF), (0xF400, 0xF426), (0xF428, 0xF428),
    (0xF6D1, 0xF6D1), (0xF6D4, 0xF6D4), (0xFB00, 0xFB00), (0xFB03, 0xFB06),
    (0xFE00, 0xFE0F), (0x1D434, 0x1D454), (0x1D456, 0x1D467), (0x1D538, 0x1D539),
    (0x1D53B, 0x1D53E), (0x1D540, 0x1D544), (0x1D546, 0x1D546), (0x1D54A, 0x1D550),
    (0x1D552, 0x1D559), (0x1D55B, 0x1D56B), (0x1D6A4, 0x1D6A5), (0x1D7D8, 0x1D7E1),
)


def main_has(c: int) -> bool:
    """Does the MAIN font (DejaVu Serif) carry this code point?

    Both DejaVu faces cover 0x80-0xFF completely — read off the font files,
    not assumed — so Latin-1 is unconditional.
    """
    if c < 0x100:
        return True
    if c in _COVERED and not in_ranges(c, _MONO_ONLY_RANGES):
        return True
    return in_ranges(c, _MAIN_ONLY_RANGES)


#: 221b — code points DejaVu Sans MONO has and DejaVu SERIF does not, measured
#: from both font files. This exists because the `_COVERED` branch below emits
#: \ifmmode\text{C}\else C\fi on the strength of _COVERED — which is MONO
#: coverage — while \text{} selects the MAIN font, which is serif. For these
#: 917 code points the text half is right and the math half drops the glyph.
#:
#: Mielke lost U+0644 (Arabic lam) eight times exactly this way, in math, after
#: the CJK and Bengali families were already in place. Most of the set is not
#: exotic: U+2244, U+2262, U+2300–237A and the rest of the mathematical
#: operator blocks are all mono-only here, which is to say all of them are one
#: math occurrence away from vanishing.
_MONO_ONLY_RANGES = (
    (0x02CE, 0x02CF), (0x0606, 0x0607), (0x0609, 0x060A), (0x060C, 0x060C),
    (0x0615, 0x0615), (0x061B, 0x061B), (0x061F, 0x061F), (0x0621, 0x063A),
    (0x0640, 0x0655), (0x065A, 0x065A), (0x0660, 0x066D), (0x0674, 0x0674),
    (0x0679, 0x067B), (0x067E, 0x0680), (0x0683, 0x0684), (0x0686, 0x0687),
    (0x0691, 0x0691), (0x0698, 0x0698), (0x06A4, 0x06A4), (0x06A9, 0x06A9),
    (0x06AF, 0x06AF), (0x06BE, 0x06BE), (0x06CC, 0x06CC), (0x06F0, 0x06F9),
    (0x0E81, 0x0E82), (0x0E84, 0x0E84), (0x0E87, 0x0E88), (0x0E8A, 0x0E8A),
    (0x0E8D, 0x0E8D), (0x0E94, 0x0E97), (0x0E99, 0x0E9F), (0x0EA1, 0x0EA3),
    (0x0EA5, 0x0EA5), (0x0EA7, 0x0EA7), (0x0EAA, 0x0EAB), (0x0EAD, 0x0EB9),
    (0x0EBB, 0x0EBC), (0x0EC8, 0x0ECD), (0x203F, 0x203F), (0x20A0, 0x20A5),
    (0x20A7, 0x20AB), (0x20AD, 0x20AE), (0x20B0, 0x20B0), (0x20B2, 0x20B3),
    (0x2105, 0x2105), (0x2117, 0x2117), (0x212E, 0x212E), (0x2201, 0x2201),
    (0x2205, 0x2205), (0x220A, 0x220A), (0x220D, 0x220E), (0x2234, 0x2237),
    (0x2241, 0x2241), (0x2244, 0x2247), (0x2249, 0x224F), (0x2256, 0x225F),
    (0x2262, 0x2263), (0x2266, 0x2269), (0x226D, 0x2281), (0x2288, 0x228B),
    (0x22B2, 0x22B5), (0x22B8, 0x22B8), (0x22C2, 0x22C3), (0x22C6, 0x22C6),
    (0x22CD, 0x22D1), (0x22DA, 0x22E9), (0x22EF, 0x22EF), (0x2300, 0x2301),
    (0x2303, 0x2306), (0x230C, 0x230F), (0x2312, 0x2315), (0x231C, 0x231F),
    (0x2326, 0x2327), (0x232B, 0x232B), (0x2335, 0x237A), (0x2380, 0x2383),
    (0x2388, 0x238B), (0x2395, 0x2395), (0x23CE, 0x23CE), (0x2601, 0x262F),
    (0x263D, 0x263E), (0x2648, 0x265F), (0x2668, 0x2668), (0x2670, 0x268B),
    (0x2690, 0x269C), (0x26A0, 0x26A1), (0x26B0, 0x26B1), (0x2701, 0x2704),
    (0x2706, 0x2709), (0x270C, 0x2727), (0x2729, 0x274B), (0x274D, 0x274D),
    (0x274F, 0x2752), (0x2756, 0x2756), (0x2758, 0x275E), (0x2761, 0x2775),
    (0x2794, 0x2794), (0x2798, 0x27A0), (0x27A2, 0x27AF), (0x27B1, 0x27BE),
    (0x27C2, 0x27C2), (0x27DC, 0x27DC), (0x27E6, 0x27E7), (0x27EA, 0x27EB),
    (0x2987, 0x2988), (0x2997, 0x2998), (0x29FA, 0x29FB), (0x2A00, 0x2A00),
    (0xA722, 0xA725), (0xA789, 0xA78A), (0xA78E, 0xA78E), (0xFB52, 0xFB81),
    (0xFB8A, 0xFB95), (0xFB9E, 0xFB9F), (0xFBAA, 0xFBAD), (0xFBE8, 0xFBE9),
    (0xFBFC, 0xFBFF), (0xFE70, 0xFE74), (0xFE76, 0xFEFC), (0xFEFF, 0xFEFF),
    (0x1D670, 0x1D6A3), (0x1D7F6, 0x1D7FF),
)

#: 221 — measured coverage of the two fallback FAMILIES, read from the font
#: files with fontTools exactly as _COVERED_RANGES was. Enumerating single code
#: points (_FB_CJK below lists 24) is a design that guarantees a return visit:
#: out/213 dropped U+53E3, U+5B5B and U+5B80, none of them in that list, and
#: out/219 added U+5315. A range test costs the same and cannot run out.
#:
#: These are COVERAGE, not blocks. A block test would route a character to a
#: font that does not have it, turning a dropped glyph into a dropped glyph
#: with an extra step.
_FB_CJK_RANGES = (
    (0x2E80, 0x2E99), (0x2E9B, 0x2EF3), (0x2F00, 0x2FD5), (0x2FF0, 0x2FFB),
    (0x3000, 0x303F),
    (0x3041, 0x3096), (0x3099, 0x30FF), (0x31C0, 0x31E3), (0x3400, 0x4DB5),
    (0x4E00, 0x9FEF), (0xF900, 0xFA6D), (0xFE30, 0xFE4F), (0xFF01, 0xFF65),
)
_FB_BENG_RANGES = (
    (0x0980, 0x0983), (0x0985, 0x098C), (0x098F, 0x0990), (0x0993, 0x09A8),
    (0x09AA, 0x09B0), (0x09B2, 0x09B2), (0x09B6, 0x09B9), (0x09BC, 0x09C4),
    (0x09C7, 0x09C8), (0x09CB, 0x09CE), (0x09D7, 0x09D7), (0x09DC, 0x09DD),
    (0x09DF, 0x09E3), (0x09E6, 0x09FE),
)


def in_ranges(c: int, ranges) -> bool:
    """Is code point `c` inside any (lo, hi) pair?"""
    return any(lo <= c <= hi for lo, hi in ranges)


#: Private Use Area and scripts no installed font carries. Rendered as a
#: VISIBLE marker: a glyph that vanishes without trace is exactly the failure
#: out/089 measured, and an invisible placeholder is the same failure with
#: extra steps.
_NO_FONT = frozenset((
    # 221c: U+27C28 is CJK Extension B, PLANE 2. Noto Sans CJK does not carry
    # it — checked against the font file, not assumed — and neither does
    # anything else installed. Seven Sketches drops it once. The marker is the
    # correct outcome, not a failure of the fallback: the row still differs
    # from the scan, but VISIBLY, so its residual is attributable and the
    # other 4,292 rows stay measurable.
    0x27C28,
    0x0917, 0x0926, 0x092F, 0x0930, 0x094D, 0x09A0, 0x09AA, 0x0AEA,
    0x0D24, 0x0D7C, 0x0E20, 0xE0B6, 0xE103, 0xF068, 0xF6BE, 0xF8EB,
    0xF8EC, 0xF8ED, 0xF8EE, 0xF8EF, 0xF8F0, 0xF8F1, 0xF8F2, 0xF8F3,
    0xF8F4, 0xF8F6, 0xF8F7, 0xF8F8, 0xF8F9, 0xF8FA, 0xF8FB, 0xF8FC,
    0xF8FF, 0xFE00, 0xFE01,
))



#: 090b — a Unicode math character must map to a COMMAND, not to a font.
#: \setmonofont fixes the \ttfamily Source column and does nothing inside
#: $...$, where cmmi10 applies: after the font fix, 1912.12689 still dropped
#: U+2032 ninety-four times, all of them in math. \ensuremath makes one
#: declaration correct in both modes, which a font substitution cannot be.
_MATH_CMD = {
    0x00B1: r"\pm",
    0x00B5: r"\mu",
    0x00B7: r"\cdot",
    0x00D7: r"\times",
    0x0301: r"\acute{}",
    0x0302: r"\hat{}",
    0x0303: r"\tilde{}",
    0x0304: r"\bar{}",
    0x0305: r"\bar{}",
    0x0306: r"\breve{}",
    0x0308: r"\ddot{}",
    0x0393: r"\Gamma",
    0x0394: r"\Delta",
    0x0398: r"\Theta",
    0x039B: r"\Lambda",
    0x039E: r"\Xi",
    0x03A0: r"\Pi",
    0x03A3: r"\Sigma",
    0x03A6: r"\Phi",
    0x03A8: r"\Psi",
    0x03A9: r"\Omega",
    0x03B1: r"\alpha",
    0x03B2: r"\beta",
    0x03B3: r"\gamma",
    0x03B4: r"\delta",
    0x03B5: r"\epsilon",
    0x03B6: r"\zeta",
    0x03B7: r"\eta",
    0x03B8: r"\theta",
    0x03B9: r"\iota",
    0x03BA: r"\kappa",
    0x03BB: r"\lambda",
    0x03BC: r"\mu",
    0x03BD: r"\nu",
    0x03BE: r"\xi",
    0x03C0: r"\pi",
    0x03C1: r"\rho",
    0x03C3: r"\sigma",
    0x03C4: r"\tau",
    0x03C5: r"\upsilon",
    0x03C6: r"\phi",
    0x03C7: r"\chi",
    0x03C8: r"\psi",
    0x03C9: r"\omega",
    0x2032: r"\prime",
    0x2033: r"\prime\prime",
    0x20D7: r"\vec{}",
    0x210F: r"\hbar",
    0x2111: r"\Im",
    0x2113: r"\ell",
    0x211C: r"\Re",
    0x2190: r"\leftarrow",
    0x2192: r"\to",
    0x2194: r"\leftrightarrow",
    0x21C1: r"\rightharpoondown",
    0x21D0: r"\Leftarrow",
    0x21D2: r"\Rightarrow",
    0x21D4: r"\Leftrightarrow",
    0x2200: r"\forall",
    0x2202: r"\partial",
    0x2203: r"\exists",
    0x2205: r"\emptyset",
    0x2207: r"\nabla",
    0x2208: r"\in",
    0x220F: r"\prod",
    0x2211: r"\sum",
    0x2212: r"-",
    0x2216: r"\setminus",
    0x2217: r"\ast",
    0x2218: r"\circ",
    0x221A: r"\sqrt{}",
    0x221E: r"\infty",
    0x2225: r"\parallel",
    0x2229: r"\cap",
    0x222A: r"\cup",
    0x222B: r"\int",
    0x223C: r"\sim",
    0x2248: r"\approx",
    0x2260: r"\neq",
    0x2261: r"\equiv",
    0x2264: r"\leq",
    0x2265: r"\geq",
    0x2282: r"\subset",
    0x2286: r"\subseteq",
    0x2295: r"\oplus",
    0x2297: r"\otimes",
    0x2299: r"\odot",
    0x22A5: r"\perp",
    0x22C5: r"\cdot",
}


def _tex_escape_plain(s):
    """Escape the characters an NFKC expansion can introduce."""
    M = {"#": "\\#", "$": "\\$", "%": "\\%", "&": "\\&", "_": "\\_",
         "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}",
         "^": "\\textasciicircum{}"}
    return "".join(M.get(c, c) for c in s)


def _fb(ch: str, family: str) -> str:
    r"""A \newunicodechar body that works in BOTH modes.

    221b. `{{\fbcjk 」}}` is a TEXT font switch. Inside $...$ the character is
    still set by the math machinery, which falls through to the main font — so
    the declaration fires, looks right in the source, and the glyph drops
    anyway. Mielke kept losing U+300D after it had a \fbcjk declaration, once,
    at its single math-mode occurrence. \text{} moves into text mode, where the
    switch is what it claims to be.

    This is the same lesson _MATH_CMD's note records ("\setmonofont fixes the
    \ttfamily Source column and does nothing inside $...$"), which was written
    about the font branches and then not applied to them.
    """
    return ("\\newunicodechar{%s}{\\ifmmode\\text{{\\%s %s}}\\else{\\%s %s}\\fi}"
            % (ch, family, ch, family, ch))


def unicode_decls(body):
    r"""`\newunicodechar` declarations for the non-ASCII characters in `body`.

    Emitted per document and only for what that document actually contains, so
    a report's preamble records exactly which code points it had to rescue.
    """
    import unicodedata
    seen, out = set(), []
    for ch in body:
        c = ord(ch)
        if c < 128 or c in seen:
            continue
        seen.add(c)
        if c in _MATH_CMD:
            out.append((c, "\\newunicodechar{%s}{\\ensuremath{%s}}"
                        % (ch, _MATH_CMD[c])))
            continue
        n = unicodedata.normalize("NFKC", ch)
        # Resolve the fold TRANSITIVELY. \newunicodechar{𝜎}{σ} looks correct —
        # σ is in the mono font — but the expansion lands inside $...$ where
        # cmmi10 applies and has no σ, and σ itself never appears in the body
        # so it gets no declaration of its own. Folding one missing glyph onto
        # another fixes nothing; map to the COMMAND when the target has one.
        if n != ch and len(n) == 1 and ord(n) in _MATH_CMD:
            out.append((c, "\\newunicodechar{%s}{\\ensuremath{%s}}"
                        % (ch, _MATH_CMD[ord(n)])))
        elif n != ch and n.strip() and all(ord(x) < 128 for x in n):
            out.append((c, "\\newunicodechar{%s}{%s}" % (ch, _tex_escape_plain(n))))
        elif n != ch and n.strip() and all(ord(x) < 128 or ord(x) in _COVERED for x in n):
            out.append((c, "\\newunicodechar{%s}{\\ifmmode\\text{%s}\\else %s\\fi}"
                        % (ch, n, n)))
        elif c in _FB_MATH:
            out.append((c, _fb(ch, "fbmath")))
        elif c in _FB_CJK or in_ranges(c, _FB_CJK_RANGES):
            out.append((c, _fb(ch, "fbcjk")))
        elif in_ranges(c, _FB_BENG_RANGES):
            # 221: ahead of _NO_FONT deliberately. U+09A0 and U+09AA sit in
            # that set from a measurement taken before Noto Sans Bengali was
            # installed; a real glyph beats the [U+XXXX] marker whenever one
            # exists, and the marker stays for the code points that still have
            # no font anywhere.
            out.append((c, _fb(ch, "fbbeng")))
        elif c in _NO_FONT:
            out.append((c, "\\newunicodechar{%s}{\\textbf{[U+%04X]}}" % (ch, c)))
        else:
            # 223 — resolve against the font ACTUALLY SELECTED here, and name
            # it. Three regimes, and none of them touches a site that works:
            #
            #   both fonts have it   -> unchanged. \text{} in math lands in
            #                           serif and the text half stays bare.
            #   serif only           -> \rmfamily in the text half: a no-op
            #                           wherever serif is already in force,
            #                           and a rescue in the \ttfamily Source
            #                           column, which is the only place it
            #                           was dropping.
            #   mono only            -> \ttfamily in both halves (this is 221b
            #                           unchanged; U+0644 and 916 others).
            #   neither              -> the visible marker. The fallback
            #                           families were tried above.
            #
            # The `c > 0xFF` guard that used to stand here rested on "Latin-1
            # accented letters already set correctly in the maths fonts". They
            # are not: ð (U+00F0) drops in cmmi10 44 times across 3 documents,
            # and every Latin-1 LETTER in math does the same, because cmmi10
            # holds no Latin-1 at all. The guard was reasoning about a font
            # nobody had asked.
            #
            # out/097 still holds and is why the first regime exists: a rescue
            # that touches characters which were never in danger moved six
            # 1205.3463v2 rows 1-2 units WORSE in the ink compare.
            mono, main = c in _COVERED, main_has(c)
            if main and mono:
                out.append((c, "\\newunicodechar{%s}{\\ifmmode\\text{%s}\\else %s\\fi}"
                            % (ch, ch, ch)))
            elif main:
                out.append((c, "\\newunicodechar{%s}{\\ifmmode\\text{%s}"
                               "\\else{\\rmfamily %s}\\fi}" % (ch, ch, ch)))
            elif mono:
                out.append((c, "\\newunicodechar{%s}{\\ifmmode\\text{\\ttfamily %s}"
                               "\\else{\\ttfamily %s}\\fi}" % (ch, ch, ch)))
            else:
                out.append((c, "\\newunicodechar{%s}{\\textbf{[U+%04X]}}"
                            % (ch, c)))
    return "\n".join(d for _c, d in sorted(out))


# ---------------------------------------------------------------------------
# 174 — the refined report
# ---------------------------------------------------------------------------

#: Verdict colours are the refined report's OWN, deliberately NOT the residual
#: palette. The formula report's legend defines C/W/S/N/K once for the whole
#: table in terms of inkdrill's row-level five-tuple; a refine verdict is a
#: different instrument answering a different question (did the crop-level
#: distance fall). Drawing it in `inkComponent` red would put a bullet in front
#: of a reader that the standing legend defines as something else, and nothing
#: on the page would say which instrument produced it.
REFINED_PREAMBLE = r"""
\definecolor{verdictAccepted}{RGB}{40,160,40}
\definecolor{verdictRejected}{RGB}{190,60,60}
\definecolor{verdictPending}{RGB}{120,120,120}
"""

_VERDICT_COLOUR = {
    "accepted": "verdictAccepted",
    "rejected": "verdictRejected",
    "proposed": "verdictPending",
    "selected": "verdictPending",
}

REFINED_WIDTHS = (44, 10, 14, 18, 16, 46)

#: The refined report deliberately does NOT share a prefix with `report.pdf`.
#: `report.*` in a document folder sweeps twelve files — the formula report and
#: its aux/log, two TSVs from other tools, and `report.ink.json.MISPAIRED`,
#: whose entire purpose is that it must never be republished. Quarantine by
#: rename protects against being picked by NAME; it does not protect against a
#: glob. A name that cannot collide beats a name that must be remembered.
REFINED_NAME = "refine.report.tex"


def _verdict_of(p: dict) -> tuple[str, str]:
    """(verdict, detail) for one proposal, in the words changes.json uses."""
    st = p.get("status", "?")
    if st == "selected" and p.get("propose_error"):
        return "not proposed", str(p["propose_error"])[:70]
    if st == "accepted":
        return "accepted", "ink fell"
    if st == "rejected":
        return "rejected", str(p.get("reason") or "")
    return st, str(p.get("propose_error") or p.get("measure_error") or "")


def refined_rows(changes: dict) -> list[dict]:
    """One row per refined object, worst confidence first.

    A row is included once it has been PROPOSED — that is the point at which
    the object has been refined in any sense. A row that was selected and never
    proposed is excluded: nothing was proposed for it, so there is no
    before/after to show and a row of dashes would only look like a measurement
    that came out empty.
    """
    # Every ATTEMPTED repair, including the ones that never produced a
    # proposal. A row whose model call failed was still attempted, and
    # omitting it would make the report say fewer repairs were tried than
    # were paid for. It shows with its error as the verdict and dashes for
    # the measurements it never got, which is different from a measurement
    # that came out empty.
    out = [p for p in (changes.get("proposals") or [])
           if p.get("status") in ("proposed", "accepted", "rejected")
           or (p.get("status") == "selected" and p.get("propose_error"))]
    out.sort(key=lambda p: (p.get("confidence") if isinstance(
        p.get("confidence"), (int, float)) else 1.0, p.get("id", "")))
    return out


def _num(v) -> str:
    return "---" if v is None else str(v)


def build_refined_report(changes_path: Path, out: Path | None = None,
                         paper: str = "a4", landscape: bool = False,
                         bibkey: str = "") -> dict:
    """refine.report.tex — conf | ink before | ink after | verdict per row.

    Built from `changes.json` rather than the model, because that is where the
    before/after measurements live and where a REJECTED row still exists. A
    report drawn from the model alone would show only the accepted rows and so
    would silently answer a different question — "what changed" instead of
    "what was tried, and what happened to it".
    """
    import json as _json
    cp = Path(changes_path)
    changes = _json.loads(cp.read_text(encoding="utf-8"))
    bibkey = bibkey or changes.get("bibkey") or cp.parent.name
    rows = refined_rows(changes)
    dest = Path(out) if out else cp.parent / REFINED_NAME

    geom = ("%spaper,landscape" % paper) if landscape else "%spaper" % paper
    parts = [None]
    parts.append("\\section*{%s — refined rows}\n" % esc_text(bibkey))
    counts = {}
    for p in rows:
        counts[_verdict_of(p)[0]] = counts.get(_verdict_of(p)[0], 0) + 1
    parts.append(
        "\\noindent %d refined row(s): %s.\\\\[2mm]\n" % (
            len(rows),
            ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "none"))
    parts.append(
        "\\noindent\\footnotesize\n"
        "\\textbf{Metric — CROP INK DISTANCE.} L1 between the standalone render "
        "of a value and the scan crop under its region, over two terms: number "
        "of ink components, and total topological holes. Both are scale-free, "
        "so a render and a 400\\,dpi page crop are comparable without being the "
        "same size. It FALLS as the render moves toward the scan, and a proposal "
        "is accepted only when it falls.\\\\[1mm]\n"
        "\\textbf{This is not the Residual class.} The formula report's "
        "C/W/S/N/K residual is inkdrill's row-level five-tuple measured from the "
        "finished PDF. This is a different instrument answering a different "
        "question, with its own colours: "
        "\\inkbullet{verdictAccepted}\\,accepted \\quad "
        "\\inkbullet{verdictRejected}\\,rejected \\quad "
        "\\inkbullet{verdictPending}\\,not yet judged. "
        "The two numbers are not comparable and must not be merged.\\\\[2mm]\n"
        "\\normalsize\n")

    cols = "|" + "|".join("p{%smm}" % w for w in REFINED_WIDTHS) + "|"
    heads = ("Identifier", "Page", "Conf.", "Ink before", "Ink after", "Verdict")
    parts.append("\\begin{longtable}{%s}\n\\hline\n" % cols)
    parts.append(" & ".join("\\textbf{%s}" % h for h in heads))
    parts.append(" \\\\\n\\hline\\endhead\n")

    for p in rows:
        verdict, detail = _verdict_of(p)
        conf = p.get("confidence")
        conf_s = f"{conf:.4f}" if isinstance(conf, (int, float)) else "---"
        before, after = p.get("ink_before"), p.get("ink_after")
        arrow = ""
        if isinstance(before, int) and isinstance(after, int):
            d = after - before
            arrow = " (%+d)" % d
        bullet = _VERDICT_COLOUR.get(verdict, "inkUnmeasured")
        parts.append(
            "\\ident{%s} & %s & %s & %s & %s%s & "
            "\\inkbullet{%s}\\,%s%s \\\\\n\\hline\n" % (
                esc_text(p.get("identifier") or p.get("id", "")),
                _num(p.get("page")), conf_s,
                _num(before), _num(after), esc_text(arrow),
                bullet, esc_text(verdict),
                (" \\footnotesize " + esc_text(detail)) if detail else ""))
    if not rows:
        parts.append("\\multicolumn{%d}{|l|}{no refined rows} \\\\\n\\hline\n"
                     % len(REFINED_WIDTHS))
    parts.append("\\end{longtable}\n")
    parts.append("\\end{document}\n")

    body = "".join(parts[1:])
    # FORM_PREAMBLE carries the ink colours and \inkbullet; without
    # it every bullet is an "Undefined color" error.
    parts[0] = PREAMBLE % {"bbdigits": MATHBB_DIGITS,
                           "form": FORM_PREAMBLE + REFINED_PREAMBLE,
                           "geom": geom,
                           "unicode": unicode_decls(body)}
    dest.write_text("".join(parts), encoding="utf-8")
    return {"rows": len(rows), "counts": counts, "out": dest}
