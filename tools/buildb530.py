"""530 — build B for one document: three columns, LaTeX, everything."""
import sys, json, pathlib, subprocess, re, time
sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")
from pdfdrill import report_tex as rt
from pdfdrill import taskout

D = pathlib.Path.home() / "pdfdrill-library" / "2010.14265"
OUT = taskout.task_dir(D, 530)
tp = list(D.glob("*.tiddlers.json"))[0]
tids = json.loads(tp.read_text())
bib = rt.resolve_bibkey(tp)
lines = D / "2010.14265.lines.json"
ink = rt.load_ink(D / "report.ink.json") if (D / "report.ink.json").is_file() else {}

t0 = time.time()
rows = rt.b_rows(tids, bib, D, lines_path=lines, ink=ink)
counts = {}
for r in rows:
    counts[r["kind"]] = counts.get(r["kind"], 0) + 1
withpage = sum(1 for r in rows if r["kind"] == "formula" and r.get("page"))
withconf = sum(1 for r in rows if r["kind"] == "formula" and r.get("conf"))
withreg = sum(1 for r in rows if r["kind"] == "formula" and r.get("region"))
marked = sum(1 for r in rows if r.get("state"))

# --- FO crops from the HOST LINE's region: give inline formulas a picture
crops = D / "report-crops"
pseudo = []
for r in rows:
    if r["kind"] == "formula" and r.get("region") and r.get("page"):
        d = {"title": r["identifier"], "page": str(r["page"])}
        d.update({k: v for k, v in r["region"].items()})
        pseudo.append(d)
pdf = D / "2010.14265.pdf"
rendered = (0, 0, 0)
if pseudo:
    rendered = rt.render_crops(pseudo, crops, pdf, kinds=("_FO",))

px2mm = rt.auto_px2mm(pdf)
geom = "a3paper,landscape"
body = rt.b_tex(rows, crops=crops, out_dir=OUT, px2mm=px2mm, bibkey=bib)
pre = rt.PREAMBLE % {"bbdigits": rt.MATHBB_DIGITS, "form": "", "geom": geom,
                     "unicode": rt.unicode_decls(body)}
title = ("\\begin{center}{\\Large\\bfseries %s}\\\\[.4em]"
         "{\\small B --- every row, three columns: the LaTeX MathPix "
         "returned, that LaTeX rendered through this document's own "
         "preamble, and the picture it was read from.}\\end{center}\n"
         % rt.esc_text(bib))
tex = OUT / "B.tex"
tex.write_text(pre + title + body + "\n\\end{document}\n")

res = rt.compile_fixpoint(tex)
pages = errors = demoted = None
if res:
    pages, errors, demoted = res

summary = {"rows_total": len(rows), "rows_by_kind": counts,
           "formula_rows_with_page": withpage,
           "formula_rows_with_host_confidence": withconf,
           "formula_rows_with_host_region": withreg,
           "rows_marked_with_an_A_state": marked,
           "fo_crops_rendered": list(rendered),
           "pages": pages, "errors": errors, "demoted": demoted,
           "seconds": round(time.time() - t0, 1)}
taskout.save_script(D, 530, pathlib.Path(__file__).read_text())
taskout.save_json(D, 530, "summary", summary)
print(json.dumps(summary, indent=1))
print("\nwritten:")
print(taskout.report_lines(D, 530))
