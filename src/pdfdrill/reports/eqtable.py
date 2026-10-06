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


#: Pages whose crops could not be cut, appended by `_crops_for`. A list and
#: not a flag, because "which page of which document, and why" is the only
#: form in which this is actionable — and because a silent zero was the defect
#: (ghostscript refusing pages 1553-1607 of an 11,232-page book cost 131 rows
#: their crops with nothing said).
LAST_CROP_FAILURES: list = []


def _crops_for(data: dict, out_dir: Path, dpi: int = 400, *,
               reuse_only: bool = False) -> dict:
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

    if reuse_only:
        # 884 — REUSE WHAT IS CUT AND TOUCH NO DOCUMENT. Asked for directly
        # ("create new tables without any re-run into the documents"), and it
        # is the only way to re-typeset a table whose crops took hours: the
        # normal path opens each PDF for `pdfinfo` and rasterizes every page a
        # missing crop needs, so a column reorder would pay the whole cut
        # again for an output that differs only in cell order.
        #
        # This reads the crop DIRECTORY and nothing else. No PDF is opened, no
        # page is rasterized, and `documents[].inputs.pdf` is not consulted —
        # so a table can be rebuilt for a document whose PDF has since moved.
        # A row whose crop was never cut gets no crop and the cell says so;
        # nothing here cuts one.
        for doc, rows in by_doc.items():
            dest = out_dir / f"{doc}-crops"
            for r in rows:
                name = f"{doc}-{r.get('label') or r.get('no')}.jpg"
                p = dest / name
                try:
                    if p.stat().st_size > 0:
                        made[(doc, r.get("label"))] = p
                except OSError:
                    pass
        return made

    refs = {d.get("document"): d for d in (data.get("documents") or [])}
    for doc, rows in sorted(by_doc.items()):
        ref = (refs.get(doc) or {}).get("inputs", {}).get("pdf")
        if not ref:
            continue
        pdf = Path(ref["path"])
        if not pdf.exists():
            continue
        # PAGE DIMENSIONS ARE PER PAGE. `pdfinfo` reports page 1 and this
        # used that one size for every page of the document — the same defect
        # the list itself carried until the per-page map was read: a book with
        # a differently sized cover had every region measured against the
        # cover, and 16,729 regions "extended past the page" that were
        # entirely inside it. 104 documents, all books, 6.14% of the corpus
        # list. Here the consequence is worse than a wrong number: the crop is
        # cut from the wrong rectangle, so the picture is of the wrong part of
        # the page and nothing in the output says so.
        #
        # The document entry carries `page_sizes` from the reading's own map.
        # pdfinfo stays as the fallback for a page the map does not mention
        # and for a list built before the map existed.
        sizes = (refs.get(doc) or {}).get("page_sizes") or {}
        wpt = hpt = None
        try:
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                  text=True, timeout=60).stdout
            size = [l for l in info.splitlines() if l.startswith("Page size")][0]
            wpt, hpt = float(size.split()[2]), float(size.split()[4])
        except Exception:                                    # noqa: BLE001
            if not sizes:
                continue

        def _size_pt(page) -> tuple:
            e = sizes.get(str(page)) or {}
            w, h = e.get("width_pt"), e.get("height_pt")
            return (w, h) if w and h else (wpt, hpt)

        dims = {}
        want: dict = {}
        dest = out_dir / f"{doc}-crops"
        for r in rows:
            ident = r["identity"]
            page, reg = ident.get("page"), ident["region"]
            if not page:
                continue
            w_pt, h_pt = _size_pt(page)
            if not w_pt or not h_pt:
                continue
            dims[page] = (int(round(w_pt * PX_PER_PT)),
                          int(round(h_pt * PX_PER_PT)))
            name = f"{doc}-{r.get('label') or r.get('no')}.jpg"
            made[(doc, r.get("label"))] = dest / name
            # ALREADY CUT IS ALREADY DONE. `render_regions` rasterizes every
            # page it is asked for, so without this a second pass over the
            # same list repeats the whole rasterize — and at 17,139 pages for
            # the MathPix list that is hours paid twice. It also makes the cut
            # resumable: a run killed at document 600 of 832 continues rather
            # than restarting, which at this scale is the difference between
            # an interruption and a lost afternoon.
            #
            # Existence AND non-empty: a crop file truncated by a kill is
            # worse than an absent one, because it reads as a cut that worked.
            try:
                if (dest / name).stat().st_size > 0:
                    continue
            except OSError:
                pass
            want.setdefault(page, []).append(
                (dest / name, (reg["top_left_x"], reg["top_left_y"],
                               reg["width"], reg["height"]),
                 (doc, r.get("label"))))
        if want:
            try:
                render_regions(pdf, dest, want, dims, dpi=dpi)
            except Exception as e:                           # noqa: BLE001
                # 884 — ONE BAD PAGE MUST NOT COST THE DOCUMENT'S CROPS.
                #
                # This used to pop every key for the document, which discarded
                # crops that had been cut successfully — including ones already
                # on disk from an earlier run — and said nothing. inkdrill
                # found it on 1511.08771, an 11,232-page PDF where ghostscript
                # cannot render pages 1553-1607 at any resolution: 131 rows
                # silently got no crop and the table showed them as absent
                # regions rather than as pages that would not rasterize.
                #
                # Same shape as the reader's own partial-read guard (876/882):
                # retry per page, keep what works, and RECORD what did not.
                # The blanket except was wrong twice over — it threw away good
                # work and it hid the reason.
                for page, jobs in want.items():
                    try:
                        render_regions(pdf, dest, {page: jobs}, dims, dpi=dpi)
                    except Exception as e2:                  # noqa: BLE001
                        LAST_CROP_FAILURES.append(
                            {"document": doc, "page": page,
                             "rows": len(jobs), "error": str(e2)[:120]})
                if not LAST_CROP_FAILURES or \
                        LAST_CROP_FAILURES[-1].get("document") != doc:
                    LAST_CROP_FAILURES.append(
                        {"document": doc, "page": None,
                         "rows": sum(len(j) for j in want.values()),
                         "error": str(e)[:120]})
    # `v.exists()` is the only authority on whether a crop was cut. A row whose
    # crop is missing gets "(no crop cut)" in the table, which is a true
    # statement about the picture rather than about the page.
    return {k: v for k, v in made.items() if v.exists()}


#: What a path may contain and still be usable as an `\includegraphics`
#: argument under xelatex. Deliberately narrow: the engine failed on CJK in a
#: folder name even quoted, and spaces and parentheses are long-standing
#: hazards in the same position.
_SAFE_PATH = __import__("re").compile(r"^[A-Za-z0-9._/+-]+$")


def _safe_crop(p: "Path", out_dir: "Path") -> "Path":
    r"""`p`, or an ASCII alias of it that xelatex can actually load.

    884 — THE PATH IS PART OF THE ARTEFACT. Both 16,576-row tables compiled to
    nothing (`0 page(s), 4 error(s)`) on one document whose FOLDER NAME carries
    CJK inside LaTeX markup:

        2016010446_	extbf{수...}	extbf{...}

    `\includegraphics` could not load it even quoted, the failed load left the
    picture zero-wide, and `graphics` then raised "Division by 0" and took the
    run down. 14 of the 352 documents have a name outside the safe set —
    spaces and parentheses from `foo (1)` duplicates, plus that one — and
    `display-all` compiled fine only because its 20 documents are all
    `sigma26-0NN`.

    An alias rather than a dropped cell: the crop EXISTS and is the one thing
    in the table that is not a reading, so losing it to a filename would be
    the worst available trade. Hardlink where the filesystem allows it (no
    second copy of 136 MB), copy otherwise. The name is a hash of the original
    relative path, so it is deterministic — the same crop gets the same alias
    on every rebuild, and a table can be diffed against the last one.
    """
    rel = str(p.relative_to(out_dir)) if out_dir in p.parents else str(p)
    if _SAFE_PATH.match(rel):
        return p
    import hashlib
    import os
    import shutil
    safe_dir = out_dir / "_safe-crops"
    safe_dir.mkdir(parents=True, exist_ok=True)
    alias = safe_dir / (hashlib.sha1(rel.encode("utf-8", "surrogateescape"))
                        .hexdigest()[:20] + p.suffix.lower())
    if not alias.exists():
        try:
            os.link(p, alias)
        except OSError:
            try:
                shutil.copy2(p, alias)
            except OSError:
                return p            # nothing better to offer; the cell will say so
    return alias


def render(data: dict, out_dir: Path, *, crops: bool = True,
           paper: str = "a3", landscape: bool = True,
           dpi: int = 400, reuse_crops: bool = False,
           compare: bool = False, keep_unrenderable: bool = False) -> tuple:
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
    LAST_CROP_FAILURES.clear()
    cut = (_crops_for(data, out_dir, dpi=dpi, reuse_only=reuse_crops)
           if crops else {})

    # 887 — COMPARE MODE: TWO PICTURES, NOTHING ELSE TO READ.
    #
    # Asked for in these words: "we are in a phase where the pdfreader has
    # ~30% correct output, therefore we do not need the failed pdfreader
    # output, what we need is the pdfreader's rendered LaTeX and the page
    # crops, then I can compare this images (which is fast if the difference
    # is large) and give the chat the correct LaTeX".
    #
    # So the LaTeX SOURCE column goes. It is the widest column in the table
    # (130mm of 400) and in this phase it is the thing being replaced, not the
    # thing being read — a reader transcribing the correct formula reads the
    # CROP, and our broken source beside it is a distraction that costs two
    # thirds of the page.
    #
    # And a row whose LaTeX does not typeset is EXCLUDED, because there is no
    # comparison to make: an empty render against a crop is already known
    # wrong and spending eye time on it buys nothing. Those rows are counted
    # and listed separately so they are not lost — they are the next job, not
    # this one.
    #
    # What is left is two images, adjacent, at equal width: what the reader
    # produced, and what the page actually says.
    # 888 — A REFERENCE STRING IS NOT A THIRD THING TO COMPARE.
    #
    # Asked for in these words: "The Mathpix LaTeX code is need to show the
    # chat or cli what the result should look like. The compare run over
    # pdfreader rendered Latex and th eink". So the two PICTURES are what the
    # eye compares, and the reference is the answer to dictate onward when
    # they disagree — which is why it is TEXT and not typeset. Typesetting it
    # would make it a third image to compare and defeat the point.
    #
    # Optional and per row. A row without one gets an EMPTY CELL rather than
    # the column disappearing: inkdrill's point, and it is right — a row with
    # ink, a typeset reading and no reference is one where nothing independent
    # exists to check against, and that absence is itself a finding about
    # coverage. Dropping the row would hide it.
    #
    # `reference_origin` names it in the header rather than a hardcoded
    # "MathPix", for the same reason column 4 stopped saying "reader's".
    has_ref = compare and any((r.get("reference_latex") or "").strip()
                              for r in rows)
    ref_origins = sorted({(r.get("reference_origin") or "").strip()
                          for r in rows
                          if (r.get("reference_latex") or "").strip()} - {""})
    if len(ref_origins) == 1:
        ref_who = {"mathpix": "MathPix", "mathpix-docmodel": "MathPix",
                   "glyph-reader": "pdf2mmd"}.get(ref_origins[0],
                                                  ref_origins[0])
    elif ref_origins:
        ref_who = "MIXED (" + ", ".join(ref_origins[:3]) + ")"
    else:
        ref_who = "reference"

    if compare:
        total = 400.0 if (paper == "a3" and landscape) else 270.0
        w_doc, w_no, w_rect = 30.0, 13.0, 25.0
        rest = total - (w_doc + w_no + w_rect) - (24.0 if has_ref else 20.0)
        if has_ref:
            # The two pictures keep equal width and stay adjacent; the text
            # column takes what is left. It is wider than a picture because a
            # LaTeX string wraps and a crop does not.
            w_ren = w_crop = rest * 0.30
            w_ref = rest - 2 * w_ren
        else:
            w_ren = w_crop = rest / 2.0
            w_ref = 0.0
        w_src = 0.0
    else:
        # Column widths, in mm, for the six columns below. a3 landscape = 420mm.
        total = 400.0 if (paper == "a3" and landscape) else 270.0
        w_doc, w_no, w_rect, w_crop = 34.0, 14.0, 26.0, 52.0
        rest = total - (w_doc + w_no + w_rect + w_crop) - 24.0
        w_src = rest * 0.52
        w_ren = rest - w_src

    # 886 — THE COLUMN MUST NAME ITS READER. "reader's LaTeX" was honest
    # while one table existed and became unanswerable the moment two did: a
    # MathPix table and a pdf2mmd table over the same 59,079 identities both
    # printed the same header, so the only way to tell which was in front of
    # you was to remember which file you had opened. The user asked exactly
    # that — "how can I be sure about the source of the LaTeX column" — and
    # there was no answer inside the document.
    #
    # DERIVED FROM THE ROWS, not from the list's `latex_from` label. A label
    # is a claim; `latex_origin` on each row is what the cells actually hold,
    # and if they disagree the header has to say so rather than pick one.
    origins = sorted({(r.get("latex_origin") or "").strip()
                      for r in rows if (r.get("latex") or "").strip()} - {""})
    if len(origins) == 1:
        who = {"mathpix": "MathPix", "mathpix-docmodel": "MathPix",
               "glyph-reader": "pdf2mmd"}.get(origins[0], origins[0])
    elif origins:
        who = "MIXED (" + ", ".join(origins[:3]) + ")"
    else:
        # No per-row evidence: fall back to the LIST's declaration, then to
        # the document entries. Our own `corpus-display` rows carry no
        # `latex_origin` — only the document entry does — so without this the
        # header read "an unnamed reader's LaTeX" on the one table whose
        # reader is never in doubt. Evidence first, declaration second, and
        # only then an admission of ignorance.
        decl = str(data.get("latex_from") or "")
        entry = {str((e or {}).get("latex_origin") or "")
                 for e in (data.get("documents") or [])} - {""}
        if "mathpix" in decl.lower():
            who = "MathPix"
        elif "glyph" in decl.lower() or "pdf2mmd" in decl.lower():
            who = "pdf2mmd"
        elif len(entry) == 1:
            e = entry.pop()
            who = "pdf2mmd" if e.startswith("glyph-reader") else e
        else:
            who = "an unnamed reader"

    if compare and has_ref:
        head = (
            "\\begin{longtable}{|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|"
            "p{%.0fmm}|p{%.0fmm}|}\n\\hline\n"
            "\\textbf{document} & \\textbf{eq no} & \\textbf{page / rect} & "
            "\\textbf{%s's LaTeX --- the answer, as text} & "
            "\\textbf{%s's LaTeX, typeset} & "
            "\\textbf{PDF (the page's own ink)} "
            "\\\\ \\hline\n\\endhead\n"
            % (w_doc, w_no, w_rect, w_ref, w_ren, w_crop,
               rt.esc_text(ref_who), rt.esc_text(who)))
    elif compare:
        head = (
            "\\begin{longtable}{|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|"
            "p{%.0fmm}|}\n\\hline\n"
            "\\textbf{document} & \\textbf{eq no} & \\textbf{page / rect} & "
            "\\textbf{%s's LaTeX, typeset} & "
            "\\textbf{PDF (the page's own ink)} "
            "\\\\ \\hline\n\\endhead\n"
            % (w_doc, w_no, w_rect, w_ren, w_crop,
               rt.esc_text(who)))
    else:
        head = (
            "\\begin{longtable}{|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|p{%.0fmm}|"
            "p{%.0fmm}|p{%.0fmm}|}\n\\hline\n"
            # THE HEADERS SAY WHAT EACH CELL IS FOR, NOT MERELY WHAT IT IS.
            # `crop | LaTeX | rendered` was accurate and useless: a reader had to
            # work out that the table is a comparison at all, and which two of the
            # three columns are the two sides of it. psred read the built PDF and
            # had to reconstruct "so it's a crop-vs-reader comparison" from the
            # content.
            #
            # 884 — THE CROP IS LAST AND THE TYPESET READING IS BESIDE IT. Several
            # tables now exist over the same rows with different LaTeX in them
            # (ours, MathPix's), and a measuring pass that reads the built PDF has
            # to find the same cell in each. The two columns that are compared are
            # now ADJACENT and the comparison is the last thing on the row:
            # column 5 is the reader's LaTeX set in type, column 6 is the page's
            # own ink. Source stays at 4, as the evidence for a disagreement.
            "\\textbf{document} & \\textbf{eq no} & \\textbf{page / rect} & "
            "\\textbf{%s's LaTeX} & \\textbf{%s's LaTeX, typeset} & "
            "\\textbf{PDF (the page's own ink)} "
            "\\\\ \\hline\n\\endhead\n"
            % (w_doc, w_no, w_rect, w_src, w_ren, w_crop,
               rt.esc_text(who), rt.esc_text(who)))

    parts = [head]
    stats = {"rows": 0, "rendered": 0, "not_rendered": 0, "no_latex": 0,
             "cropped": 0, "uncropped": 0,
             # A page that would not rasterize is not the same fact as a row
             # with no region, and `uncropped` cannot tell them apart.
             "crop_failures": LAST_CROP_FAILURES,
             "skipped_unrenderable": 0}
    skipped_unrenderable = 0
    for r in rows:
        # In compare mode a row with nothing to render is not a row with
        # a comparison in it. Counted, not dropped quietly.
        if compare and not keep_unrenderable:
            _lx = (r.get("latex") or "").strip()
            if not _lx or not rt.display_safe(_lx):
                skipped_unrenderable += 1
                continue
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
            img = _safe_crop(img, out_dir)
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
            # 883 — NOT A BLANK, AND NOT A DASH EITHER. An empty cell reads as
            # "the equation is blank there", which is a false statement about
            # the page rather than a missing picture; a bare `---` is merely
            # ambiguous between the two. Say which it is.
            crop_cell = r"{\tiny\emph{(no crop cut)}}"
        # THE REFERENCE, AS TEXT. `esc_source` and not `display_safe`: this
        # cell is to be read and copied, never typeset, so it keeps every
        # backslash and brace the reference actually wrote. An absent
        # reference is an empty cell, which says "nothing independent exists
        # for this row" — a true statement, and the only one available.
        if has_ref:
            _ref = (r.get("reference_latex") or "").strip()
            ref_cell = ("{\\ttfamily\\scriptsize %s}" % rt.esc_source(_ref)
                        if _ref else "{\\tiny\\emph{(no reference)}}")
            if _ref:
                stats["with_reference"] = stats.get("with_reference", 0) + 1
            else:
                stats["without_reference"] = stats.get("without_reference", 0) + 1
        else:
            ref_cell = ""
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
            # 891: text, typeset, crop — THE CROP IS ALWAYS LAST and the
            # rendered LaTeX is always the column before it, in every mode.
            # That is the standard all three table grades share, and the
            # reason the reference text sits to the LEFT of the pictures
            # rather than after them: it is read and copied, not compared.
            # The header above derives its labels from the same order and the
            # footnote below says "the LAST column" rather than a number, so
            # none of the three can drift out of step with the others.
        ] + ([_rect_cell(r), ref_cell, ren, crop_cell] if (compare and has_ref)
             else [_rect_cell(r), ren, crop_cell] if compare
             else [_rect_cell(r), src, ren, crop_cell])) + " \\\\ \\hline\n")
    stats["skipped_unrenderable"] = skipped_unrenderable
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
        "\\textbf{Columns 4 and 5 hold %s's reading.} Every row also carries "
        "its own \\textsf{latex\\_origin}; this header is derived from those "
        "fields, not from the file name, and says MIXED if they disagree. The "
        "list's own declaration is \\textsf{latex\\_from = %s}."
        % (rt.esc_text(who), rt.esc_text(str(data.get("latex_from") or
                                            "(not declared)"))),
        # 891 — THE FOOTNOTE NAMED COLUMNS THAT HAD MOVED. It said "column 6
        # is the PDF's own ink" in every mode, and in compare+reference mode
        # the ink was column 5 while 6 held the reference text. A table whose
        # own instructions point at the wrong cells is worse than one with no
        # instructions. Derived from the layout now, like the header.
        "\\textbf{How to read a row:} the LAST column is the PDF's own ink, "
        "cut from the page --- the only thing here that is not a reading. The "
        "column before it is the one before THAT set in type. So the last two "
        "are the comparison, side by side, and the text column is the "
        "evidence for any disagreement."
        + (" The answer column is %s's reading, as copyable text, and is NOT "
           "a third thing to compare." % rt.esc_text(ref_who)
           if has_ref else
           " Nothing in this table is an independent reference: the text "
           "column comes from the reader being judged."),
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
          paper: str = "a3", landscape: bool = True, dpi: int = 400,
          reuse_crops: bool = False, compare: bool = False,
          keep_unrenderable: bool = False) -> dict:
    """Write `<name>.table.tex` and `<name>.marks-request.json`. Returns stats."""
    from ..model_io import _atomic_write
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = data.get("name") or "eqlist"
    doc, stats = render(data, out_dir, crops=crops, paper=paper,
                        landscape=landscape, dpi=dpi,
                        reuse_crops=reuse_crops, compare=compare,
                        keep_unrenderable=keep_unrenderable)
    tex = out_dir / f"{name}.table.tex"
    _atomic_write(tex, doc)
    req = out_dir / f"{name}.marks-request.json"
    _atomic_write(req, json.dumps(marks_request(data), indent=1))
    stats["tex"] = tex
    stats["marks_request"] = req
    return stats
