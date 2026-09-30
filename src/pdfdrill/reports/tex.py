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


def _rendered(r: EvidenceRow, widths, out_dir, author_preamble: str = "") -> str:
    # 661 — display_safe(), not the bare gate: this is the site that backs
    # evidence-equation.pdf/evidence-formula.pdf/report.pdf (the PUBLISHED
    # surface, per docs/HANDOVER.md:25-42), and report_tex.py's OWN
    # equivalent site (row()) was switched to display_safe() for exactly
    # this reason — a raw display environment (align/gather/eqnarray/
    # alignat/flalign/multline/split) cannot typeset inside `$...$` at all
    # (measured: "Package amsmath Error: \begin{split} won't work here"),
    # so the bare gate here would leave this artifact carrying the exact
    # defect 661 exists to remove. `r.latex` itself stays untouched: only
    # this function's OWN local `safe` is mapped — `render_row()`'s `src`
    # cell reads `r.latex` directly, so the LaTeX-source column still shows
    # the reading unchanged, matching report_tex.row()'s published-form
    # decision.
    # 695a -- A LISTING IS SET, NOT COMPILED. Its body is escaped monospace
    # with its `\(…\)` spans set as real inline maths, which is what
    # `report_tex.listing_cell` has done since 616 for the lstlisting branch
    # of `region_render`. Image rows never reached it: `diagram.py` moves a
    # code listing's body out of `latex_code`, so `r.latex` is empty and this
    # cell printed "---" for 8 of 9 image rows on 1804.10694v5.
    listing = getattr(r, "listing", "")
    if listing:
        return rt.listing_cell(listing)
    # 836 — A VALUE THAT CANNOT BE SET IN A CELL IS COMPILED AS ITS OWN
    # DOCUMENT, ahead of `display_safe`, which would happily return an
    # `\xymatrix` for this cell to typeset. `display_safe` answers "is this
    # legal display maths"; xy is legal maths and still illegal HERE, because
    # it seizes the alignment machinery of the longtable around it. See
    # `rt.needs_own_document`. A FAILED separate compile REFUSES the row; it
    # does not fall back to setting the value in the cell. 50 of 64 xy rows on
    # arXiv 1102.1889 compiled standalone and 14 did not, and letting those 14
    # through cost the whole report — the first of them ends the longtable and
    # every row after it is gone. One unrenderable row must cost one row.
    if r.latex and rt.needs_own_document(r.latex):
        return rt.standalone_math(r.latex, r.identifier, Path(out_dir),
                                  col_mm=widths[4],
                                  author_preamble=author_preamble) \
            or "\\emph{(not rendered)}"
    safe = rt.display_safe(r.latex) if r.latex else ""
    # 836 — AN ENVIRONMENT THE CELL CANNOT CLOSE MUST NOT BE EMITTED. 822 wrote
    # this rule for the LaTeX projector's table cells and it is imported, not
    # copied: one rule, one place. It was never needed here while the document's
    # own packages were absent, because the row failed earlier and differently.
    # With them injected, one row's stray `\end{aligned}` closed the enclosing
    # longtable instead — "\begin{longtable} on input line 272 ended by
    # \end{aligned}" — and took every following row with it: 0 pages out.
    if safe:
        safe = rt.drop_unpaired_envs(safe)
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
               history=None, ink_bullets=False, author_preamble="") -> str:
    extra = getattr(r, "eqnum", "")
    # 669 -- `refined_flag`, unchanged from the retired path's own use of it
    # (233, `report_tex.row()`): the mark that says "this row is not
    # MathPix's own reading" belongs in the IDENTIFIER column, beside
    # `conf_flag`, for the reason 064 already established for confidence
    # (HANDOVER-RULES rule 16) -- the LaTeX-source and Rendered columns stay
    # exactly what they would otherwise be for every OTHER row, so a
    # per-column ink probe still has an unchanged control.
    ident = "\\ident{%s}%s%s%s" % (
        rt.breakable_ident(r.identifier),
        ("~\\eqnum{%s}" % rt.esc_text(extra)) if extra else "",
        rt.conf_flag(r.shown_confidence),
        rt.refined_flag(getattr(r, "refined_info", None)))
    # 709b — esc_source for the SOURCE cell only; the page cell below keeps
    # esc_text (it is not a wrapping problem and would only gain markup).
    # 695a -- the SOURCE cell of a listing is the listing, for the same
    # reason: `r.latex` is empty on a code Diagram by construction.
    source = r.latex or getattr(r, "listing", "")
    src = ("{\\ttfamily\\footnotesize %s}" % rt.esc_source(source)
           if source else "---")
    cells = [ident, rt.esc_text(r.shown_page), _conf(r, ink_bullets), src,
             _rendered(r, widths, out_dir, author_preamble)]
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
                 ink_bullets=False, author_preamble="") -> str:
    parts = []
    if kind == "formula":
        parts.append("\\noindent{\\small %s}\\\\[.6em]\n" % HOST_LINE_SENTENCE)
    heads = COLUMNS if len(widths) == 6 else COLUMNS[:-1]
    parts.append(rt.table_open(caption or CAPTIONS[kind], widths, form,
                               legend_on, heads=heads))
    for r in rows:
        parts.append(render_row(r, widths, out_dir=out_dir, px2mm=px2mm,
                                bibkey=bibkey, history=history,
                                ink_bullets=ink_bullets,
                                author_preamble=author_preamble))
    parts.append("\\end{longtable}\n")
    return "".join(parts)


def document(body: str, *, paper: str, landscape: bool, pages=None,
             title: str = "", form: bool = False, meta: dict | None = None) -> str:
    geom = "%spaper%s" % (paper, ",landscape" if landscape else "")
    # 836 — the DOCUMENT's own packages, guarded. `meta` is optional so the
    # eleven other callers of this function keep working unchanged; absent, the
    # slot is empty and the report is exactly what it was.
    pre = rt.preamble(bbdigits=rt.MATHBB_DIGITS,
                      form=rt.FORM_PREAMBLE if form else "", geom=geom,
                      pagesel=rt.pagesel_line(pages),
                      docpre=rt.document_preamble(meta or {}),
                      unicode=rt.unicode_decls(body))
    head = ("\\begin{center}{\\Large\\bfseries %s}\\end{center}\n"
            % rt.esc_text(title)) if title else ""
    return pre + head + body + "\n\\end{document}\n"
