"""LaTeX rendering of evidence rows. Imports report_tex's cell helpers; it
copies nothing, so a fix there is a fix here."""
from __future__ import annotations

from pathlib import Path

from .. import report_tex as rt
from . import COLUMNS
from .rows import EvidenceRow, EquationRow

HOST_LINE_SENTENCE = (
    "The page, the confidence and the picture of an inline formula are its "
    "HOST LINE's --- a formula has none of its own. A line's confidence is "
    "not a formula's.")

CAPTIONS = {"equation": "Display equations",
            "formula": "Inline formulas (first occurrence)",
            "table": "Tables",
            "image": "Image regions"}


def widths_for(paper: str, landscape: bool, with_image: bool) -> tuple:
    w_mm, h_mm = rt.PAPER_MM[paper]
    if landscape:
        w_mm, h_mm = h_mm, w_mm
    return rt.col_widths(w_mm - 36, with_image=with_image)


def _rendered(r: EvidenceRow, widths, out_dir) -> str:
    safe = rt.renderable(r.latex) if r.latex else ""
    tail = rt.esc_text(r.trailing_punct) if r.trailing_punct else ""
    if safe:
        return "\\FitMath{$\\displaystyle %s$}%s" % (safe, tail)
    if r.latex and rt.refused_for_align_only(r.latex):
        return rt.standalone_math(r.latex, r.identifier, Path(out_dir),
                                  col_mm=widths[4])
    return "\\emph{(not rendered)}" if r.latex else "---"


def _conf(r: EvidenceRow, ink_bullets: bool) -> str:
    cell = rt.conf_cell(r.shown_confidence)
    if ink_bullets and isinstance(r, EquationRow):
        code = r.ink_code
        colour = rt._INK_COLOUR.get((r.ink or {}).get("flag"), "inkUnmeasured")
        txt = ("\\,\\texttt{\\tiny %s}" % rt.esc_text(code)) if code else ""
        cell = "%s\\hspace{0.6em}\\inkbullet{%s}%s" % (cell, colour, txt)
    return cell


def render_row(r: EvidenceRow, widths, *, out_dir, px2mm, bibkey,
               history=None, ink_bullets=False) -> str:
    extra = getattr(r, "eqnum", "")
    ident = "\\ident{%s}%s%s" % (
        rt.breakable_ident(r.identifier),
        ("~\\eqnum{%s}" % rt.esc_text(extra)) if extra else "",
        rt.conf_flag(r.shown_confidence))
    src = ("{\\ttfamily\\footnotesize %s}" % rt.esc_text(r.latex)
           if r.latex else "---")
    cells = [ident, rt.esc_text(r.shown_page), _conf(r, ink_bullets), src,
             _rendered(r, widths, out_dir)]
    if len(widths) == 6:
        if r.crop is not None:
            cells.append(rt.crop_cell(r.crop.parent, Path(out_dir), r.crop.stem,
                                      px_width=getattr(r, "px_width", ""),
                                      px2mm=px2mm, col_mm=widths[5],
                                      bibkey=bibkey, history=history))
        else:
            cells.append("---")
    return " & ".join(cells) + " \\\\ \\hline\n"


def render_table(rows: list, kind: str, *, widths, out_dir, px2mm, bibkey,
                 history=None, caption=None, legend_on=False, form=False,
                 ink_bullets=False) -> str:
    parts = []
    if kind == "formula":
        parts.append("\\noindent{\\small %s}\\\\[.6em]\n" % HOST_LINE_SENTENCE)
    heads = COLUMNS if len(widths) == 6 else COLUMNS[:-1]
    parts.append(rt.table_open(caption or CAPTIONS[kind], widths, form,
                               legend_on, heads=heads))
    for r in rows:
        parts.append(render_row(r, widths, out_dir=out_dir, px2mm=px2mm,
                                bibkey=bibkey, history=history,
                                ink_bullets=ink_bullets))
    parts.append("\\end{longtable}\n")
    return "".join(parts)


def document(body: str, *, paper: str, landscape: bool, pages=None,
             title: str = "", form: bool = False) -> str:
    geom = "%spaper%s" % (paper, ",landscape" if landscape else "")
    pre = rt.preamble(bbdigits=rt.MATHBB_DIGITS,
                      form=rt.FORM_PREAMBLE if form else "", geom=geom,
                      pagesel=rt.pagesel_line(pages),
                      unicode=rt.unicode_decls(body))
    head = ("\\begin{center}{\\Large\\bfseries %s}\\end{center}\n"
            % rt.esc_text(title)) if title else ""
    return pre + head + body + "\n\\end{document}\n"
