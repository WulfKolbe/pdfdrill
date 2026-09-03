"""528 — the four counts, correctly. Supersedes 527's \\Perp numbers.

THE BUG IN 527: the pattern was `\\\\(Perp|...)\\b`. The usage is
`\\Perp_{P}`, and `_` is a word character, so `\\b` failed on every
subscripted occurrence — which is nearly all of them. 527 reported 36 where
there are 139, and said five of six spellings were absent when all are
present.
"""
import sys, json, re, pathlib, collections
sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")
from pdfdrill import report_tex as rt
from pdfdrill import taskout

D = pathlib.Path.home() / "pdfdrill-library" / "2010.14265"
FAM = re.compile(r"\\(Perp|nVdash|nvdash|measuredangle)(?![a-zA-Z])")
out = {}

def n(s):
    return len(FAM.findall(s or ""))

# ---- authoritative: MathPix's own output, the `text` field, parsed
lj = json.loads((D / "2010.14265.lines.json").read_text())
text_occ = 0
spell = collections.Counter()
lines_hit = 0
by_type = collections.Counter()
for pg in lj.get("pages") or []:
    for ln in pg.get("lines") or []:
        m = FAM.findall(ln.get("text") or "")
        if m:
            text_occ += len(m)
            spell.update(m)
            lines_hit += 1
            by_type[ln.get("type")] += len(m)
out["authoritative_lines_json_text_field"] = text_occ
out["spellings"] = dict(spell.most_common())
out["distinct_lines"] = lines_hit
out["by_line_type"] = dict(by_type.most_common())

# ---- every artefact, parsed where it is JSON, raw where it is not
tids = json.loads(list(D.glob("*.tiddlers.json"))[0].read_text())
tf = collections.Counter()
kind = collections.Counter()
for x in tids:
    for k, v in x.items():
        if isinstance(v, str) and n(v):
            tf[k] += n(v)
            ti = x.get("title", "")
            kind[("FO" if "_FO" in ti else "EQ" if "_EQ" in ti
                  else "TAB" if "_TAB" in ti else "prose")] += n(v)
out["tiddlers_by_field"] = dict(tf.most_common())
out["tiddlers_by_row_kind"] = dict(kind.most_common())

raw = {}
for label, p in (("md", D / "2010.14265.md"),
                 ("inspect.html", D / "2010.14265.inspect.html"),
                 ("formula-report.html", D / "formula-report.html"),
                 ("compare.html", D / "compare.html"),
                 ("report.tex", D / "report.tex")):
    if p.is_file():
        t = p.read_text(encoding="utf-8", errors="replace")
        # inspect.html embeds JSON-escaped content: \\Perp
        raw[label] = {"single": len(FAM.findall(t)),
                      "escaped": len(re.findall(
                          r"\\\\(?:Perp|nVdash|nvdash|measuredangle)(?![a-zA-Z])", t))}
out["raw_files"] = raw

# ---- what reaches the row set
tp = list(D.glob("*.tiddlers.json"))[0]
fo, eq, tab, dia = rt.rows_for(tids, rt.resolve_bibkey(tp))
out["report_rows"] = {}
for name, rows in (("equations", eq), ("formulas", fo), ("tables", tab),
                   ("image_regions", dia)):
    out["report_rows"][name] = {
        "rows": len(rows),
        "rows_carrying": sum(1 for r in rows if n(r[1])),
        "occurrences": sum(n(r[1]) for r in rows)}

# published report.pdf
import subprocess
pdf = D / "report.pdf"
txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                     text=True).stdout if pdf.is_file() else ""
out["published_report_pdf_occurrences"] = n(txt)

taskout.save_script(D, 528, pathlib.Path(__file__).read_text(),
                    name="script_corrected.py")
taskout.save_json(D, 528, "corrected", out)
print(json.dumps(out, indent=1))
print("\nwritten:")
print(taskout.report_lines(D, 528))
