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
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import report_tex as rt                      # noqa: E402

FIX = pathlib.Path.home() / "pdfdrill-library" / "datikz-fixture"
CACHE = pathlib.Path.home() / ".cache/huggingface/datasets/nllg___da_tik_z-v4"

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
    "from. "
    "\\textbf{Split.} These rows are V4 \\emph{train}. 92 of DaTikZ-v2's 442 "
    "test rows appear in V4's training data BY PICTURE --- the same "
    "tikzpicture body --- though not by document, because V4 rewrites every "
    "wrapper to \\texttt{standalone} and a whole-file hash therefore finds "
    "none of them. Neither release page states this. 350 V2 test rows are "
    "clean; a model measurement must use those, and this report is a "
    "renderer measurement where it does not matter. "
    "\\textbf{The LaTeX source column is GENERATED,} not measured: it holds a "
    "one-sentence summary written by a language model from the TikZ, tagged "
    "\\textcolor{genblue}{[generated]} in every cell. The source itself is "
    "unchanged and reachable through the link under each identifier. Nothing "
    "in that column is evidence about the figure; it is a reading aid.")


_PICTURE = re.compile(r"\\\\begin\\{(?:tikzpicture|tikzcd|axis|circuitikz|forest)\\}")


def _from_picture(code: str) -> str:
    """The source from the first drawing environment, not from the file.

    \\documentclass, \\usepackage[utf8]{inputenc} and the author's French
    comment are identical row to row and say nothing about the figure.
    Falls back to \\begin{document}, then to the whole file.
    """
    m = _PICTURE.search(code)
    if m:
        return code[m.start():]
    i = code.find("\\begin{document}")
    return code[i + len("\\begin{document}"):].lstrip() if i >= 0 else code


def shard_of(index: int, root: pathlib.Path) -> int:
    """Which shard a row index falls in, from dataset_info.json's own
    `shard_lengths`. The report said `s00` because a limit of 100 never
    leaves the first shard — true, and hardcoded, which are different
    things."""
    for info in sorted(root.rglob("dataset_info.json")):
        try:
            sl = (json.loads(info.read_text())["splits"]["train"]
                  .get("shard_lengths") or [])
        except Exception:
            continue
        run = 0
        for k, n in enumerate(sl):
            if index < run + n:
                return k
            run += n
    return 0


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
    sp = ROOT / "out" / "375.json"
    summaries = ({r["id"]: r for r in json.loads(sp.read_text())["rows"]}
                 if sp.is_file() else {})
    built = json.loads((ROOT / "out" / "365.json").read_text())
    rendered = {r["id"]: r.get("rendered") for r in built["rows"]}
    errors = {r["id"]: r.get("compile_error", "") for r in built["failures"]}

    w = widths(420 - 16)                          # a3 landscape, 8mm margins
    # hyperref appended to OUR document only — the shared report preamble is
    # untouched, because a link column is this report's need and not every
    # report's.
    parts = [rt.PREAMBLE % {"bbdigits": rt.MATHBB_DIGITS, "form": "",
                            "geom": "a3paper,landscape,margin=8mm",
                            "unicode": ""}]
    parts[0] = parts[0].replace(
        "\\begin{document}",
        "\\usepackage{hyperref}\n\\hypersetup{colorlinks,urlcolor=blue}\n"
        "\\definecolor{genblue}{RGB}{20,90,170}\n"
        "\\begin{document}")
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
        # 377 — everything that ADDRESSES the object stays in column 1, under
        # the identifier, in the slot an equation row uses for \lowconf: the
        # dataset's own id, then a link to the row's .tex. Column 4 is for the
        # object's CONTENT, so it stays comparable row to row and an unchanged
        # content column remains a free control (340's reasoning for the
        # marker). Page keeps what LOCATES the row in the file — shard and
        # row index — which is a different question from what names it.
        ident = ("\\ident{%s}\\newline{\\tiny %s}\\newline"
                 "\\href{run:%s}{\\ttfamily\\tiny %s}"
                 % (rt.breakable_ident(rid),
                    rt.esc_text((r.get("file_id") or "")[:30]),
                    r["tex"], rt.esc_text(r["tex"])))
        page = ("{\\tiny shard %02d\\newline row %d}"
                % (shard_of(i, CACHE), i))
        conf = rt.conf_cell("")                   # absent, never invented
        code = (FIX / r["tex"]).read_text(errors="replace")
        gen = summaries.get(rid, {})
        # Truncate from the PICTURE, not the file. Every row's first lines are
        # \documentclass and \usepackage — identical across rows and silent
        # about the figure, so the column showed the preamble and nothing else.
        head = _from_picture(code)
        # 375 — a generated one-sentence summary, MARKED as generated. The
        # code is still reachable through column 1's link, so the column
        # becomes readable without the source becoming unavailable. The
        # marker is per-cell rather than only in the caveat: a reader
        # scanning one row must not have to remember a header note.
        if gen.get("summary"):
            src = ("{\\color{genblue}\\tiny\\textbf{[generated]}}~"
                   "{\\small %s}" % rt.esc_text(gen["summary"][:400]))
        else:
            src = "{\\ttfamily\\tiny %s}" % rt.esc_text(head[:260])
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
