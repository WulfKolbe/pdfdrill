r"""865 — THE REPORT WHOSE SUBJECT IS A LIST.

`reporttex`, `evidence`, `residuals`, `compare` all take a document. They hold
its lock, write fixed names beside its PDF, and answer about it. A list
spanning twenty folders has no such home, and InftyDB — (image, LaTeX) pairs
with no PDF behind them — has no document at all. So this module's subject is
`eqlist`'s file.

WHERE IT WRITES, AND WHY THAT IS NOT A LOOPHOLE. The one-writer rule exists
because every build command writes FIXED NAMES BESIDE THE PDF, so two
processes on one document interleave rather than collide (`doclock.hold`, 72
handlers, and a test that fails if a new one does not take the lock). This
command writes beside the LIST — `<list>.table.tex`, `<list>.marks-request.json`,
`<list>-crops/` — and never into a document folder. It therefore needs no doc
lock, and must not be "fixed" later by giving it one: a lock named after a PDF
would let two different lists serialise on an unrelated document while two
runs of the SAME list still collided. It reads documents; it writes only to
its own output directory.

AND IT READS ONLY. No `lines.json` is rewritten, no model rebuilt, no
`equations.json` re-emitted. Every inkdrill mark set hashes the reading
through `measured_against`, so re-emitting one invalidates the measurement
even when the new reading means the same thing (863). The crops are cut from
the PDF into this command's own directory, which is not an identity anyone
hashes (`report-crops/` is — 667's `crop_sha256` — and is untouched here).

THE MARKS REQUEST is the other half of the user's ask: the generator produces
"the reports and the inkdrill updates". inkdrill cannot be handed bare rows,
because it votes the scale PER DOCUMENT on up to 400 of that document's rows
and calibrates its thresholds from the confidently placed ones — sigma26-078
calibrated on n_ref 78, sigma26-080 REFUSED with 7. A list of 20 rows per
document would give it ~5 reference rows and every document would refuse. So
the request names, per document, the population to reason from, the resolvable
inputs and their hashes, and the subset to mark.

AND THAT POPULATION IS KIND-FILTERED, which the first subset got wrong. It is
not the document's whole row set for a display list: sigma26-080 holds 1,976
inline rows and 74 display, so calibrating on all 2,050 draws the reference
rows from the inline single letters — 409 of 415 sampled failed the margin
test and the document refused. Both halves of this were learned from a
refusal, in opposite directions: too few rows refuses, and the wrong KIND of
rows refuses too. A refusal at the kind-filtered population means "too few
equations of this kind in this document", which is information rather than
noise. Selection and calibration are different scopes and the file says so.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import report_tex as rt
from . import tex as T


def _rect_cell(r: dict) -> str:
    """The page and the rectangle, in the list's DECLARED frame.

    Not converted. Mapping 250 dpi regions onto another raster is per page and
    per axis (CropBox vs MediaBox; 654 found 4 of 21 documents with a CropBox
    inset) and belongs to whoever owns the target raster.
    """
    ident = r.get("identity") or {}
    reg = ident.get("region") or {}
    if not reg:
        return "---"
    # `\newline`, NOT `\\`. Inside a braced group in a `p{}` column, `\\` ends
    # the table ROW while the group is still open — 400 errors and every one of
    # the 171 math rows demoted to source-only, because the fixpoint attributes
    # the failure to the row it lands in. The three-line cell was mine; the
    # equations were fine.
    return ("{\\ttfamily\\scriptsize p%s\\newline %s,%s\\newline %s$\\times$%s}"
            % (ident.get("page"), reg.get("top_left_x"), reg.get("top_left_y"),
               reg.get("width"), reg.get("height")))


def _crops_for(data: dict, out_dir: Path, dpi: int = 400) -> dict:
    """Cut one crop per listed row, document by document.

    Returns {(document, label): Path}. A document whose PDF or page dimensions
    cannot be established contributes no crops rather than wrong ones — the
    rule `render_regions` already states for a page missing from `dims`.
    """
    from ..pdf_reading import render_regions
    from ..eqlist import PX_PER_PT
    import subprocess

    made: dict = {}
    by_doc: dict = {}
    for r in data.get("rows") or []:
        if r.get("lane") != "pdf" or not (r.get("identity") or {}).get("region"):
            continue
        by_doc.setdefault(r["document"], []).append(r)

    refs = {d.get("document"): d for d in (data.get("documents") or [])}
    for doc, rows in sorted(by_doc.items()):
        ref = (refs.get(doc) or {}).get("inputs", {}).get("pdf")
        if not ref:
            continue
        pdf = Path(ref["path"])
        if not pdf.exists():
            continue
        # Page dimensions in the list's frame, from the PDF itself.
        try:
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                  text=True, timeout=60).stdout
            size = [l for l in info.splitlines() if l.startswith("Page size")][0]
            wpt, hpt = float(size.split()[2]), float(size.split()[4])
        except Exception:                                    # noqa: BLE001
            continue
        dims = {}
        want: dict = {}
        dest = out_dir / f"{doc}-crops"
        for r in rows:
            ident = r["identity"]
            page, reg = ident.get("page"), ident["region"]
            if not page:
                continue
            dims[page] = (int(round(wpt * PX_PER_PT)),
                          int(round(hpt * PX_PER_PT)))
            name = f"{doc}-{r.get('label') or r.get('no')}.jpg"
            want.setdefault(page, []).append(
                (dest / name, (reg["top_left_x"], reg["top_left_y"],
                               reg["width"], reg["height"]),
                 (doc, r.get("label"))))
            made[(doc, r.get("label"))] = dest / name
        if want:
            try:
                render_regions(pdf, dest, want, dims, dpi=dpi)
            except Exception:                                # noqa: BLE001
                for k in list(made):
                    if k[0] == doc:
                        made.pop(k, None)
    return {k: v for k, v in made.items() if v.exists()}


def render(data: dict, out_dir: Path, *, crops: bool = True,
           paper: str = "a3", landscape: bool = True,
           dpi: int = 400) -> tuple:
    r"""(tex, stats) — the list as a LaTeX table.

    One row per listed equation: document, equation no, page rectangle (and
    the crop when one could be cut), the LaTeX source, and the LaTeX
    rendered. Exactly the four columns the job named, plus the render, which
    is the column that makes the table a check rather than a listing — a row
    whose source will not typeset says so in print.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = data.get("rows") or []
    cut = _crops_for(data, out_dir, dpi=dpi) if crops else {}

    # Column widths, in mm, for the six columns below. a3 landscape = 420mm.
    total = 400.0 if (paper == "a3" and landscape) else 270.0
    w_doc, w_no, w_rect, w_crop = 34.0, 14.0, 26.0, 52.0
    rest = total - (w_doc + w_no + w_rect + w_crop) - 24.0
    w_src = rest * 0.52
    w_ren = rest - w_src

    head = (
        "\\begin{longtable}{|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|"
        "p{%.0fmm}|p{%.0fmm}|}\n\\hline\n"
        # THE HEADERS SAY WHAT EACH CELL IS FOR, NOT MERELY WHAT IT IS.
        # `crop | LaTeX | rendered` was accurate and useless: a reader had to
        # work out that the table is a comparison at all, and which two of the
        # three columns are the two sides of it. psred read the built PDF and
        # had to reconstruct "so it's a crop-vs-reader comparison" from the
        # content. Columns 4 and 6 ARE the comparison — the page's own ink
        # against the reader's LaTeX set in type — and column 5 is the
        # evidence for whatever they disagree about.
        "\\textbf{document} & \\textbf{eq no} & \\textbf{page / rect} & "
        "\\textbf{PDF (the page's own ink)} & \\textbf{reader's LaTeX} & "
        "\\textbf{reader's LaTeX, typeset} "
        "\\\\ \\hline\n\\endhead\n"
        % (w_doc, w_no, w_rect, w_crop, w_src, w_ren))

    parts = [head]
    stats = {"rows": 0, "rendered": 0, "not_rendered": 0, "no_latex": 0,
             "cropped": 0, "uncropped": 0}
    for r in rows:
        stats["rows"] += 1
        latex = r.get("latex") or ""
        src = ("{\\ttfamily\\scriptsize %s}" % rt.esc_source(latex)
               if latex else "---")
        # A READING THAT LOST ITS SUBJECT IS WORSE THAN ONE THAT FAILED, and
        # the table must say so where it is read. `Q = .` typesets, so the
        # rendered column shows a tidy equation asserting that Q equals
        # nothing; nothing else on the row contradicts it, and the row claims
        # confidence 1.0 because confidence counts projected SPANS and the
        # dropped figure was never a span.
        if r.get("lost_operand"):
            src += ("\\par{\\footnotesize\\bfseries [lost operand: %s]}"
                    % rt.esc_text(r["lost_operand"]))
        if not latex:
            stats["no_latex"] += 1
            ren = "---"
        else:
            safe = rt.display_safe(latex)
            if safe:
                stats["rendered"] += 1
                ren = "$\\displaystyle %s$" % safe if r.get("kind") == "display" \
                    else "$%s$" % safe
            else:
                stats["not_rendered"] += 1
                ren = "\\emph{(not rendered)}"
        img = cut.get((r.get("document"), r.get("label")))
        if img:
            stats["cropped"] += 1
            # A path relative to the .tex, so the document compiles wherever
            # the pair is copied to. 862: a link the compiler cannot follow is
            # worse than an honest absence.
            try:
                rel = img.relative_to(out_dir)
            except ValueError:
                rel = img
            # PIXEL-EXACT ORIGINAL SIZE, capped at the column — `reporttex`'s
            # rule, and it is not cosmetic. Scaling every crop to the column
            # width magnifies a small region by whatever factor it happens to
            # need: `\blacksquare`, a 29x38 px region, became a 50mm black
            # square occupying an entire page of this table. At 250 dpi one
            # pixel is 25.4/250 mm, so the region is drawn at the size it has.
            reg = (r.get("identity") or {}).get("region") or {}
            native = (reg.get("width") or 0) * (25.4 / 250.0)
            mm = min(w_crop - 2, native) if native else (w_crop - 2)
            crop_cell = ("\\includegraphics[width=%.2fmm]{%s}"
                         % (max(mm, 1.0), str(rel).replace("\\", "/")))
        else:
            stats["uncropped"] += 1
            crop_cell = "---"
        # The label is the LABEL — it renumbers. The identity is the
        # (document, page, region) printed in the rect column beside it, which
        # is why that column is not decoration.
        parts.append(" & ".join([
            "{\\scriptsize %s}" % rt.esc_text(r.get("document") or ""),
            # The AUTHOR'S number first when the document set one — that is
            # what "equation no" means to someone reading the paper — with
            # this pipeline's own ordinal label beneath it, small, because the
            # label renumbers and the author's number does not.
            ("{\\ttfamily\\scriptsize %s\\newline\\tiny %s}"
             % (rt.esc_text(r["number"]), rt.esc_text(r.get("label") or ""))
             if r.get("number") else
             "{\\ttfamily\\scriptsize %s}" % rt.esc_text(
                 r.get("label") or str(r.get("no") or ""))),
            _rect_cell(r), crop_cell, src, ren,
        ]) + " \\\\ \\hline\n")
    parts.append("\\end{longtable}\n")

    counts = data.get("counts") or {}
    sel = data.get("selection") or {}
    lead = [
        "\\noindent\\textbf{%s} --- %d row(s) across %d document(s)."
        % (rt.esc_text(data.get("name") or "equation list"),
           counts.get("rows", len(rows)), len(data.get("documents") or [])),
        "Regions are in the list's declared frame: %d dpi (%s px/pt), y down "
        "from the page top-left; this table does not convert them."
        % ((data.get("frame") or {}).get("dpi", 250), "250/72"),
        "Identity is (document, page, region); the \\textsf{eq no} column is a "
        "LABEL and renumbers on a re-read.",
        "\\textbf{How to read a row:} column 4 is the PDF's own ink, cut from "
        "the page --- the only thing here that is not a reading. Column 6 is "
        "column 5 set in type. So 4 against 6 is the comparison, and 5 is the "
        "evidence for any disagreement. Nothing in this table is an "
        "independent reference: column 5 comes from the reader being judged.",
    ]
    if sel.get("bounded"):
        lead.append(
            "\\textbf{This is a BOUNDED subset} (kind %s, %s per document, %s "
            "document(s)) and is not a measurement of the corpus."
            % (rt.esc_text(str(sel.get("kind"))),
               rt.esc_text(str(sel.get("per_document") or "all")),
               rt.esc_text(str(sel.get("documents_listed")))))
    body = "\n\n".join(lead) + "\n\n\\vspace{2mm}\n\n" + "".join(parts)
    doc = T.document(body, paper=paper, landscape=landscape,
                     title=data.get("name") or "Equation list")
    return doc, stats


def marks_request(data: dict) -> dict:
    """The inkdrill update: what to calibrate on, and what to mark.

    The distinction is the whole file. `calibrate_on` is the document's FULL
    row set (inkdrill votes the scale per document on up to 400 rows and
    derives its thresholds from the confidently placed ones); `mark` is the
    listed subset. Hand it only the subset and it sees ~5 reference rows per
    document and refuses — sigma26-080's n_ref 7 reproduced once per document.
    """
    by_doc: dict = {}
    for r in data.get("rows") or []:
        if r.get("lane") != "pdf":
            continue
        by_doc.setdefault(r["document"], []).append(r)

    docs = []
    for d in data.get("documents") or []:
        key = d.get("document")
        rows = by_doc.get(key) or []
        docs.append({
            "document": key,
            "folder": d.get("folder"),
            "inputs": d.get("inputs"),
            "calibrate_on": {
                # THE KIND MATTERS, and this is the correction inkdrill
                # measured after the first subset. "The document's full row
                # set" is wrong for a kind-filtered list: sigma26-080 holds
                # 1,976 inline rows and 74 display, so calibrating a DISPLAY
                # list on all 2,050 draws its reference rows from the inline
                # single letters — 409 of 415 sampled rows failed the margin
                # test and the document refused. The refusal was about which
                # rows it reasoned from, not about the document.
                "scope": ("the document's full equation set of this kind"
                          if (d.get("kind") or "any") != "any"
                          else "the document's full equation set"),
                "kind": d.get("kind") or "any",
                "rows_in_document": d.get("rows_of_kind_in_document",
                                          d.get("rows_in_document")),
                "rows_in_document_all_kinds": d.get("rows_in_document"),
            },
            "mark": [{
                # IDENTITY first, because it is what a mark attaches to.
                "identity": r.get("identity"),
                "label": r.get("label"),
                "latex_sha16": r.get("latex_sha16"),
                "kind": r.get("kind"),
                "crop": r.get("crop"),
            } for r in rows],
        })
    return {
        "schema": "pdfdrill.eqlist.marks-request/1",
        "list": data.get("name"),
        "frame": data.get("frame"),
        "identity": data.get("identity"),
        "note": "calibrate_on names the population to reason from — the "
                "document's full set OF THE LISTED KIND — and `mark` is the "
                "listed subset of it. Both halves were learned by a refusal: a "
                "20-row list per document yields ~5 reference rows and refuses; "
                "and calibrating a display list on a document that is 96% "
                "inline refuses too, for the opposite reason. A refusal at the "
                "kind-filtered population means 'too few equations of this kind "
                "in this document', which is information.",
        "counts": {"documents": len(docs),
                   "rows_to_mark": sum(len(d["mark"]) for d in docs)},
        "documents": docs,
    }


def write(data: dict, out_dir: Path, *, crops: bool = True,
          paper: str = "a3", landscape: bool = True, dpi: int = 400) -> dict:
    """Write `<name>.table.tex` and `<name>.marks-request.json`. Returns stats."""
    from ..model_io import _atomic_write
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = data.get("name") or "eqlist"
    doc, stats = render(data, out_dir, crops=crops, paper=paper,
                        landscape=landscape, dpi=dpi)
    tex = out_dir / f"{name}.table.tex"
    _atomic_write(tex, doc)
    req = out_dir / f"{name}.marks-request.json"
    _atomic_write(req, json.dumps(marks_request(data), indent=1))
    stats["tex"] = tex
    stats["marks_request"] = req
    return stats
