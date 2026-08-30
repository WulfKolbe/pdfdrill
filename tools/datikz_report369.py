#!/usr/bin/env python3
"""369 — the first 100 DaTikZ-V4 rows in the standard six-column report form.

Same table builder, same legend, same widths policy as every other report —
`report_tex.table_open` with six columns. Nothing new in the shape.

WHAT IS DIFFERENT IS WHAT IT MEASURES, and that is stated on the page. Every
other report puts a READING beside a PAGE: MathPix's LaTeX against MathPix's
crop of the scan. This one puts two RENDERS OF THE SAME CODE side by side —
our compile against the dataset's own PNG of the identical `tikz_code`. Any
distance is our LaTeX installation differing from theirs (fonts, tikz library
versions, pgfplots compat), never a transcription error, because there is no
transcription. It is the TikZ equivalent of the 208-expression rasteriser
measurement, and it is the floor every later TikZ comparison sits on.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import report_tex as rt                      # noqa: E402

FIX = pathlib.Path.home() / "pdfdrill-library" / "datikz-fixture"

#: 369 — stated on the page, and held there by
#: tests/test_datikz_report.py::test_the_caveat_stays_on_the_page, the same
#: way 282's caveat is. A reader who takes this for a reading comparison will
#: read our font substitutions as OCR defects.
CAVEAT = (
    "\\textbf{What this measures.} Both image columns are RENDERS OF THE "
    "SAME CODE: \\textbf{Rendered} is our standalone compile of "
    "\\texttt{tikz\\_code}, \\textbf{Scan image} is the dataset's own "
    "448$\\times$448 PNG of that identical code. Neither is a scan of a "
    "printed page and nothing here was transcribed, so any ink distance is "
    "OUR LaTeX installation differing from theirs --- fonts, tikz library "
    "versions, \\texttt{pgfplots} compat --- and never a transcription "
    "error. This is a renderer-versus-renderer FLOOR, not a reading "
    "comparison, and it is the floor every other TikZ measurement sits on. "
    "The \\textbf{Conf.} column is empty because the dataset carries no "
    "confidence value; an absent reading is not a good one (252), so it "
    "shows a dash rather than a number. \\textbf{Page} is not a page --- "
    "these rows have none --- it is the shard and row index the record came "
    "from.")


def _degenerate(png: pathlib.Path, floor: int = 8) -> bool:
    """A render under `floor` px on either axis: it compiled and shows nothing."""
    try:
        from PIL import Image
        im = Image.open(png)
        return im.width < floor or im.height < floor
    except Exception:
        return False


def widths(usable_mm: float):
    """Standard shape, but the TWO IMAGE COLUMNS ARE EQUAL (340).

    A width difference between the columns being compared puts a scale
    difference into the residual, which is exactly the number this report
    exists to produce.
    """
    span = usable_mm - 28
    ident, page, conf = 20, 22, 13     # `page` is wider: it holds "s00 r0042"
    rest = span - ident - page - conf
    img = (rest - round(rest * 0.30)) // 2      # the two compared columns
    src = rest - 2 * img                        # the remainder goes HERE
    return ident, page, conf, src, img, img


def main() -> int:
    man = json.loads((FIX / "manifest.json").read_text())
    built = json.loads((ROOT / "out" / "365.json").read_text())
    rendered = {r["id"]: r.get("rendered") for r in built["rows"]}
    errors = {r["id"]: r.get("compile_error", "") for r in built["failures"]}

    w = widths(420 - 16)                          # a3 landscape, 8mm margins
    parts = [rt.PREAMBLE % {"bbdigits": rt.MATHBB_DIGITS, "form": "",
                            "geom": "a3paper,landscape,margin=8mm",
                            "unicode": ""}]
    parts.append("\\section*{DaTikZ-V4 --- first 100 rows}\n")
    parts.append(CAVEAT + "\n\n")
    parts.append(rt.table_open("Rows", w, False, True))

    n_img = n_degen = 0
    for i, r in enumerate(man["rows"]):
        rid = r["id"]
        # Identifier: our key, with the dataset's own file_id beneath it, the
        # way an equation row carries \lowconf beneath its identifier.
        # \newline, NOT \\ — inside a p{} column `\\` ends the ROW, and
        # inside a braced group it ends it mid-group: 400 "Extra }" errors.
        ident = ("\\ident{%s}\\newline{\\tiny %s}"
                 % (rt.breakable_ident(rid),
                    rt.esc_text((r.get("file_id") or "")[:38])))
        # Page is NOT a page. Say what the number is.
        page = "{\\tiny s%s\\newline r%05d}" % ("00", i)
        conf = rt.conf_cell("")                   # absent, never invented
        code = (FIX / r["tex"]).read_text(errors="replace")
        head = "\n".join(code.splitlines()[:4])
        src = ("{\\ttfamily\\tiny %s\\newline\\textbf{%s}}"
               % (rt.esc_text(head[:180]), rt.esc_text(r["tex"])))
        rp = rendered.get(rid)
        if rp:
            # width AND height, keepaspectratio, on BOTH image cells. DTZ00077
            # compiles to a 1x231 px PDF -- a success by the did-a-PDF-appear
            # test and nothing by any other -- and `width=\linewidth` on a
            # one-pixel-wide image scales the height past TeX's limit:
            # "! Dimension too large". A degenerate render must not be able to
            # break the page it is reported on.
            rcell = ("\\includegraphics[width=\\linewidth,height=55mm,"
                     "keepaspectratio]{%s}" % rp)
            if _degenerate(FIX / rp):
                rcell += "\\newline{\\tiny\\emph{degenerate render}}"
                n_degen += 1
            n_img += 1
        else:
            rcell = ("{\\tiny\\emph{did not compile: %s}}"
                     % rt.esc_text(errors.get(rid, "?")[:60]))
        scell = ("\\includegraphics[width=\\linewidth,height=55mm,"
                 "keepaspectratio]{%s}" % r["png"]
                 if r.get("png") else "{\\tiny\\emph{(no png)}}")
        parts.append("%s & %s & %s & %s & %s & %s \\\\ \\hline\n"
                     % (ident, page, conf, src, rcell, scell))
    parts.append("\\end{longtable}\n\\end{document}\n")
    dest = FIX / "report.tex"
    dest.write_text("".join(parts), encoding="utf-8")
    print("wrote %s: %d rows, %d with a rendered cell, %d degenerate"
          % (dest, len(man["rows"]), n_img, n_degen))
    res = rt.compile_fixpoint(dest)
    if res:
        print("compiled: %d pages, %d errors, %d demoted" % res)
    else:
        print("xelatex absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
