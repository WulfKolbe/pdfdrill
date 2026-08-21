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


def first_pages(tiddlers: list[dict], bibkey: str) -> dict[str, str]:
    """title -> page of the first transcluding page-bearing tiddler."""
    pat = re.compile(r"\{\{(" + re.escape(bibkey) + r"_(?:FOX?_?\w+))\|\|")
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
        m = re.match(re.escape(bibkey) + r"_(FOX?|EQ|TAB|DIA|PIC)", title)
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
\setlength{\parindent}{0pt}
\newcommand{\ident}[1]{\texttt{\tiny #1}}
\newcommand{\eqnum}[1]{{\tiny #1}}
%% 064: MathPix doubted this line. Set in the IDENTIFIER column, which is
%% machine keys already — the Source, Rendered and Scan columns stay
%% byte-identical so the consumer's per-column ink probe keeps working and
%% an unchanged column remains a free control (HANDOVER rule 16).
\newcommand{\lowconf}[1]{~{\tiny\textbf{[conf #1]}}}
%% a wide unbreakable math line must NEVER escape its cell (11 P13 reports
%% had the Scan column pushed off the page — inkdrill P16 finding): render
%% at natural size, shrink to the column only when it would overflow
\newsavebox{\fitbox}
\newcommand{\FitMath}[1]{\savebox{\fitbox}{#1}\ifdim\wd\fitbox>0.97\linewidth\resizebox{0.97\linewidth}{!}{\usebox{\fitbox}}\else\usebox{\fitbox}\fi}
\begin{document}
"""


def col_widths(usable_mm: float, with_image: bool):
    r"""(ident, page, src, rendered[, image]) widths in mm for the usable span.

    The reserve is the REAL LaTeX overhead, not a guess: 2*\tabcolsep (6pt
    each side) per column + the rules — ~22mm for 5 columns, ~18 for 4. The
    old 12mm reserve made every 5-column row ~10mm overfull ('Overfull \hbox
    in alignment', inkdrill P16 second pass)."""
    span = usable_mm - (24 if with_image else 20)
    ident, page = 20, 7
    rest = span - ident - page
    if with_image:
        src = round(rest * 0.29)
        rend = round(rest * 0.31)
        return ident, page, src, rend, rest - src - rend
    src = round(rest / 2)
    return ident, page, src, rest - src


def table_open(caption: str, widths) -> str:
    cols = "|" + "|".join("p{%smm}" % w for w in widths) + "|"
    heads = {4: ("Identifier", "Page", "LaTeX source", "Rendered"),
             5: ("Identifier", "Page", "LaTeX source", "Rendered",
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


def renderable(latex: str) -> str:
    """Return latex safe to put inside $...$, or "" when it is not.

    One malformed snippet (bh2_EQ0147 carried a stray \\end{itemize}) hung
    xelatex for 10 minutes inside a longtable cell — every snippet is
    validated here and demoted to source-only when it cannot render.
    """
    lx = re.sub(r"\s+", " ", latex).strip()
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


def row(title, latex, page, extra="", image=None, punct="", conf="") -> str:
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
    if image is not None:
        return "%s & %s & %s & %s & %s \\\\ \\hline\n" % (
            ident, esc_text(str(page)), src, math, image)
    return "%s & %s & %s & %s \\\\ \\hline\n" % (
        ident, esc_text(str(page)), src, math)


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


def build_report(tiddlers_path: Path, out: Path | None = None,
                 crops: Path | None = None, texzip: Path | None = None,
                 paper: str = "a4", landscape: bool = False,
                 px2mm: float | None = None) -> dict:
    """Generate report.tex; returns counts {equations, formulas, tables,
    unrecovered, out}."""
    import json
    path = Path(tiddlers_path)
    tiddlers = json.loads(path.read_text())
    bibkey = path.name.replace(".tiddlers.json", "")
    fo, eq, tab, dia = rows_for(tiddlers, bibkey)
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
    img_col = eq_widths[4] if crops else None
    if crops and px2mm:
        widest = 0.0
        for title, _lx, _pg, _num, wpx, _pt, _cf in eq:
            f = crops / f"{title}.jpg"
            if f.is_file():
                w = jpg_width(f) or (float(wpx) if wpx else 0)
                widest = max(widest, float(w) * px2mm)
        if widest and widest + 2 < eq_widths[4]:
            freed = eq_widths[4] - (round(widest) + 2)
            eq_widths = (eq_widths[0], eq_widths[1], eq_widths[2],
                         eq_widths[3] + freed, round(widest) + 2)
            img_col = eq_widths[4]

    out_parts = [PREAMBLE % {"geom": geom}]
    out_parts.append("\\section*{%s — formula report}\n"
                     "%d inline formulas, %d display equations, %d tables, "
                     "%d unrecovered image regions.\n"
                     % (esc_text(bibkey), len(fo), len(eq), len(tab),
                        len(dia)))
    out_parts.append(table_open("Display equations", eq_widths))
    for title, latex, page, num, wpx, punct, conf in eq:
        img = crop_cell(crops, out_dir, title, px_width=wpx,
                        px2mm=px2mm, col_mm=img_col) if crops else None
        out_parts.append(row(title, latex, page, extra=num, image=img,
                             punct=punct, conf=conf))
    out_parts.append("\\end{longtable}\n")

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
