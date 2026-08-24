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


def first_pages(tiddlers: list[dict], bibkey: str) -> dict[str, str]:
    """title -> page of the first transcluding page-bearing tiddler."""
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


def rows_for(tiddlers, bibkey):
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
        page = t.get("page") or fpage.get(title, "")
        dims = t.get("width", ""), t.get("height", "")
        if kind in ("FO", "FOX"):
            fo.append((title, latex, page, t.get("trailing_punct", "")))
        elif kind == "EQ":
            eq.append((title, latex, page, t.get("equation_number", ""),
                       t.get("width", ""), t.get("trailing_punct", ""),
                       t.get("confidence", "")))
        elif kind == "TAB":
            tab.append((title, latex, page, dims))
        else:
            dia.append((title, latex, page, dims))
    return fo, eq, tab, dia


def texzip_images(texzip_dir: Path):
    """Map (page:int, height, width) and page -> image path from a MathPix
    tex.zip expansion (images named <id>-<page>_<h>_<w>_<y>_<x>.jpg)."""
    by_key, by_page = {}, {}
    for img in sorted(texzip_dir.rglob("*.jpg")) +                sorted(texzip_dir.rglob("*.png")):
        m = re.search(r"-(\d+)_(\d+)_(\d+)_\d+_\d+\.\w+$", img.name)
        if not m:
            continue
        page, h, w = (int(x) for x in m.groups())
        by_key[(page, h, w)] = img
        by_page.setdefault(page, img)
    return by_key, by_page


def jpg_width(path: Path):
    """Actual pixel width of the (possibly trimmed) crop; None without PIL."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size[0]
    except Exception:
        return None


def crop_cell(crops_dir: Path | None, out_dir: Path, title: str,
              px_width="", px2mm=None, col_mm=None) -> str:
    """An \\includegraphics cell for the tiddler's downloaded CDN crop.

    With px2mm (mm per MathPix page pixel) and the region's pixel width the
    crop is set at its EXACT original physical size, capped at the column
    width; otherwise it fills the column.
    """
    if not crops_dir:
        return "---"
    img = crops_dir / f"{title}.jpg"
    if not img.is_file() or img.stat().st_size < 500:
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

PREAMBLE = r"""%% report.tex — generated by tools/make_report_tex.py; compile with xelatex
\documentclass[10pt]{article}
\usepackage[%(geom)s,margin=18mm]{geometry}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{longtable}
\usepackage{array}
\usepackage{graphicx}
%% mathrsfs (\mathscr) and stmaryrd (\llbracket): the SAME packages the
%% standalone renderer carries. Their absence here cost 60 demoted rows
%% corpus-wide — equations that render perfectly alone and threw
%% 'Undefined control sequence' inside the report (0707.4470: 39 errors,
%% 31 rows, every one a \mathscr).
\usepackage{mathrsfs}
\usepackage{stmaryrd}
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
\usepackage{newunicodechar}
%(unicode)s
\setlength{\parindent}{0pt}
\newcommand{\ident}[1]{\texttt{\tiny #1}}
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


def table_open(caption: str, widths) -> str:
    cols = "|" + "|".join("p{%smm}" % w for w in widths) + "|"
    heads = {5: ("Identifier", "Page", "Conf.", "LaTeX source", "Rendered"),
             6: ("Identifier", "Page", "Conf.", "LaTeX source", "Rendered",
                 "Scan image")}[len(widths)]
    return (
        "\\section*{%s}\n" % caption +
        "\\begin{longtable}{%s}\n\\hline\n" % cols +
        " & ".join("\\textbf{%s}" % h for h in heads) +
        " \\\\\n\\hline\\endhead\n")


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


def renderable(latex: str) -> str:
    """Return latex safe to put inside $...$, or "" when it is not.

    One malformed snippet (bh2_EQ0147 carried a stray \\end{itemize}) hung
    xelatex for 10 minutes inside a longtable cell — every snippet is
    validated here and demoted to source-only when it cannot render.
    """
    lx = re.sub(r"\s+", " ", latex).strip()
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
    # plain-TeX multiline macros carry \cr internally — inside a longtable
    # cell they throw "Misplaced \cr" recovery loops the row-demotion pass
    # never reaches (live hang: 0902.0431 EQ0035, \displaylines)
    if re.search(r"\\(displaylines|eqalign(no)?|halign|cr)(?![a-zA-Z])", lx):
        return ""
    # display delimiters: strip a leading \[ / trailing \]; reject mid-string
    lx = re.sub(r"^\\\[\s*", "", lx)
    lx = re.sub(r"\s*\\\]$", "", lx)
    if r"\[" in lx or r"\]" in lx or "$" in lx:
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
               "stable": "inkStable", "noise": "inkNoise", "clean": "inkClean"}


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


def legend(form: bool) -> str:
    """The legend line(s) under a table. Both channels when --form is on."""
    out = "{\\scriptsize " + LEGEND_CONF
    if form:
        out += r" \\[-0.3ex] " + LEGEND_INK
    return out + "}\n\n"


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


def row(title, latex, page, extra="", image=None, punct="", conf="",
        form=False, residual="inkUnmeasured", code="") -> str:
    # identifier and equation number are machine keys, not reading
    # matter: at \tiny they stop crowding the 20mm column (and stop
    # overprinting the Page column, inkdrill P16's fourth pass).
    ident = "\\ident{%s}%s%s" % (breakable_ident(title),
                                 ("~\\eqnum{%s}" % esc_text(extra))
                                 if extra else "",
                                 conf_flag(conf))
    src = "{\\ttfamily\\footnotesize %s}" % esc_text(latex) if latex else "---"
    safe = renderable(latex) if latex else ""
    # 025: the mark is set BESIDE the math, never inside it — the same
    # separation the TiddlyWiki text field makes, so the rendered cell still
    # looks like the scan while `latex` holds mathematics only.
    tail = esc_text(punct) if punct else ""
    math = ("\\FitMath{$\\displaystyle %s$}%s" % (safe, tail)) if safe \
        else ("\\emph{(not rendered)}" if latex else "---")
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


def download_crops(tiddlers: list[dict], dest: Path, trim: bool = True):
    """Fetch each EQ/TAB tiddler's CDN crop into dest/<title>.jpg (cached);
    left-trim whitespace when PIL is available. Returns (ok, cached, failed).
    Degrades cleanly when the network is blocked — the report then renders
    without the image column entries it could not fetch."""
    from .net import urlopen, NetworkBlocked
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
        try:
            with urlopen(uri.replace("\\&", "&"), timeout=20) as r:
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
            "PDF. First: %s. The PDF is missing symbols with no visible trace; "
            "add the code point to report_tex._MATH_CMD or a fallback font."
            % (Path(log_path).name, count, sample))


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


def compile_fixpoint(tex_path: Path, max_iter: int = 6):
    """xelatex the report; demote rows whose lines error to source-only and
    recompile until 0 errors (a malformed OCR snippet must cost its own row,
    never the document). Returns (pages, errors, demoted_rows) or None when
    xelatex is absent."""
    import re as _re
    import shutil
    import subprocess
    if shutil.which("xelatex") is None:
        return None
    d, log = tex_path.parent, tex_path.with_suffix(".log")
    demoted: set[int] = set()
    pages = nerr = 0
    for _ in range(max_iter):
        subprocess.run(["xelatex", "-interaction=nonstopmode", tex_path.name],
                       cwd=d, capture_output=True, timeout=1800)
        text = log.read_text(errors="replace") if log.is_file() else ""
        nerr = len(_re.findall(r"^! ", text, _re.M))
        m = _re.search(r"Output written on .*\((\d+) pages?", text)
        pages = int(m.group(1)) if m else 0
        if nerr == 0:
            break
        src = tex_path.read_text().split("\n")
        changed = False
        for n in sorted({int(x) for x in
                         _re.findall(r"^l\.(\d+)", text, _re.M)}):
            i = n - 1
            if i < len(src):
                new = _re.sub(r"\$\\displaystyle .*\$",
                              r"\\emph{(not rendered)}", src[i])
                if new != src[i]:
                    src[i] = new
                    demoted.add(n)
                    changed = True
        if not changed:
            break
        tex_path.write_text("\n".join(src))
    # final pass for longtable column alignment
    subprocess.run(["xelatex", "-interaction=nonstopmode", tex_path.name],
                   cwd=d, capture_output=True, timeout=1800)
    text = log.read_text(errors="replace") if log.is_file() else ""
    nerr = len(_re.findall(r"^! ", text, _re.M))
    m = _re.search(r"Output written on .*\((\d+) pages?", text)
    pages = int(m.group(1)) if m else pages
    return pages, nerr, len(demoted)


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


def build_report(tiddlers_path: Path, out: Path | None = None,
                 crops: Path | None = None, texzip: Path | None = None,
                 paper: str = "a4", landscape: bool = False,
                 px2mm: float | None = None,
                 min_conf: float | None = None, max_conf: float | None = None,
                 types: "set[str] | None" = None, form: bool = False,
                 ink: "dict | None" = None) -> dict:
    """Generate report.tex; returns counts {equations, formulas, tables,
    unrecovered, out}.

    143 — `min_conf`/`max_conf` bound the MathPix confidence column and `types`
    selects object kinds. Both narrow the row set before any crop is sized, so a
    filtered report is smaller on disk as well as shorter.
    """
    import json
    path = Path(tiddlers_path)
    tiddlers = json.loads(path.read_text())
    bibkey = path.name.replace(".tiddlers.json", "")
    fo, eq, tab, dia = rows_for(tiddlers, bibkey)
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
            f = crops / f"{title}.jpg"
            if f.is_file():
                w = jpg_width(f) or (float(wpx) if wpx else 0)
                widest = max(widest, float(w) * px2mm)
        if widest and widest + 2 < eq_widths[5]:
            freed = eq_widths[5] - (round(widest) + 2)
            eq_widths = (eq_widths[0], eq_widths[1], eq_widths[2],
                         eq_widths[3], eq_widths[4] + freed, round(widest) + 2)
            img_col = eq_widths[5]

    out_parts = [None]          # preamble filled in once the body is known
    out_parts.append("\\section*{%s — formula report}\n"
                     "%d inline formulas, %d display equations, %d tables, "
                     "%d unrecovered image regions.\n"
                     % (esc_text(bibkey), len(fo), len(eq), len(tab),
                        len(dia)))
    out_parts.append(table_open("Display equations", eq_widths))
    # 099: doubted rows first. Sorting by confidence ascending puts what
    # MathPix is least sure of at the top of the table, where a reader
    # checking the document looks first. Rows with no confidence value sort
    # LAST rather than first: absence is not doubt.
    eq = sorted(eq, key=lambda r: (float(r[6]) if r[6] not in (None, "") else 2.0))
    for title, latex, page, num, wpx, punct, conf in eq:
        img = crop_cell(crops, out_dir, title, px_width=wpx,
                        px2mm=px2mm, col_mm=img_col) if crops else None
        out_parts.append(row(title, latex, page, extra=num, image=img,
                             punct=punct, conf=conf, form=form,
                             residual=residual_colour(title, ink),
                             code=((ink or {}).get(title) or {}).get("code", "")))
    out_parts.append("\\end{longtable}\n")
    out_parts.append(legend(form))

    # every section starts on a FRESH page: a page mixing the 5-column
    # equations table with the 4-column formulas table defeats per-page
    # column probes (inkdrill P16, the 11 short-equation docs)
    out_parts.append("\\clearpage\n")
    out_parts.append(table_open("Inline formulas (first occurrence)",
                                fo_widths))
    for title, latex, page, punct in fo:
        out_parts.append(row(title, latex, page, punct=punct))
    out_parts.append("\\end{longtable}\n")

    if tab:
        out_parts.append("\\clearpage\n")
        span = usable - 20 - 26 - 9
        ts = round(span * 0.5)
        tim = span - ts
        out_parts.append(
            "\\section*{Tables}\n\\begin{longtable}"
            "{|p{26mm}|p{9mm}|p{%smm}|p{%smm}|}\n\\hline\n" % (ts, tim) +
            "\\textbf{Identifier} & \\textbf{Page} & "
            "\\textbf{Content (LaTeX source if any)} & "
            "\\textbf{Scan image} \\\\\n\\hline\\endhead\n")
        for title, latex, page, dims in tab:
            body = ("{\\ttfamily\\footnotesize %s}" % esc_text(latex)
                    ) if latex else (
                "(no LaTeX source; %s\\,$\\times$\\,%s px"
                " region — see tables.html)" % dims)
            img = crop_cell(crops, out_dir, title,
                            px_width=dims[0], px2mm=px2mm, col_mm=tim)
            out_parts.append("\\ident{%s} & %s & %s & %s "
                             "\\\\ \\hline\n"
                             % (esc_text(title), esc_text(str(page)),
                                body, img))
        out_parts.append("\\end{longtable}\n")

    if dia:
        out_parts.append("\\clearpage\n")
        zkey, zpage = ({}, {})
        if texzip:
            zkey, zpage = texzip_images(Path(texzip))
        span = usable - 20 - 20 - 7
        dimg = round(span * 0.55)
        dnote = span - dimg
        out_parts.append(
            "\\section*{Unrecovered image regions — TikZ / table / "
            "failed-math candidates}\n"
            "Regions MathPix left as images (no LaTeX). Reconstruct with "
            "\\texttt{pdfdrill vision} (LLM classify + transcribe to "
            "TikZ/tabular/math); verify an LLM result against the real ink "
            "with inkdrill.\n"
            "\\begin{longtable}{|p{20mm}|p{7mm}|p{%smm}|p{%smm}|}\n"
            "\\hline\n\\textbf{Identifier} & \\textbf{Page} & "
            "\\textbf{Image} & \\textbf{Source} \\\\\n"
            "\\hline\\endhead\n" % (dimg, dnote))
        for title, latex, page, dims in dia:
            img_path = None
            try:
                key = (int(page), int(dims[1]), int(dims[0]))
                img_path = zkey.get(key) or zpage.get(int(page))
            except (TypeError, ValueError):
                pass
            if img_path is None and crops:
                cand = crops / f"{title}.jpg"
                img_path = cand if cand.is_file() else None
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
                srcnote = "tex.zip (local)" if zkey or zpage else "crops"
            else:
                cell = ("\\emph{(image not on disk — pass --texzip or "
                        "download the CDN crop)}")
                srcnote = "CDN only"
            out_parts.append("\\ident{%s} & %s & %s & %s "
                             "\\\\ \\hline\n"
                             % (esc_text(title), esc_text(str(page)),
                                cell, srcnote))
        out_parts.append("\\end{longtable}\n")

    out_parts.append("\\end{document}\n")
    # 090: the declarations depend on what the body actually contains, so the
    # preamble is written LAST and lists only the code points this document
    # needed rescuing. A report that needs none carries none.
    out_parts[0] = PREAMBLE % {"form": FORM_PREAMBLE if form else "",
                               "geom": geom,
                               "unicode": unicode_decls("".join(out_parts[1:]))}
    dest.write_text("".join(out_parts))
    return {"equations": len(eq), "formulas": len(fo), "tables": len(tab),
            "unrecovered": len(dia), "out": dest}


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
#: Private Use Area and scripts no installed font carries. Rendered as a
#: VISIBLE marker: a glyph that vanishes without trace is exactly the failure
#: out/089 measured, and an invisible placeholder is the same failure with
#: extra steps.
_NO_FONT = frozenset((
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
            out.append((c, "\\newunicodechar{%s}{{\\fbmath %s}}" % (ch, ch)))
        elif c in _FB_CJK:
            out.append((c, "\\newunicodechar{%s}{{\\fbcjk %s}}" % (ch, ch)))
        elif c in _NO_FONT:
            out.append((c, "\\newunicodechar{%s}{\\textbf{[U+%04X]}}" % (ch, c)))
        elif c in _COVERED and c > 0xFF:
            # >0xFF only. Latin-1 accented letters already set correctly in
            # the maths fonts, and wrapping them in \text moves them into a
            # different face for no reason: doing so nudged six 1205.3463v2
            # rows 1-2 units WORSE in the ink compare (out/097). A rescue that
            # touches characters which were never in danger is a regression.
            # covered by the TEXT fonts but not by cmmi10, and most of these
            # occurrences are inside $...$ where the math font applies. \text
            # moves the character out of the math font without changing what
            # it is; unconditional \ensuremath would break it in text mode.
            out.append((c, "\\newunicodechar{%s}{\\ifmmode\\text{%s}\\else %s\\fi}"
                        % (ch, ch, ch)))
    return "\n".join(d for _c, d in sorted(out))
