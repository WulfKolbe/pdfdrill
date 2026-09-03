"""527 — where 2010.14265's \\Perp family lives, and what reaches an artefact.

Written under rule 19: this script and its results sit in
<document>/out/527/ and the report names the paths.
"""
import sys, json, re, pathlib, collections
sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")
from pdfdrill import report_tex as rt
from pdfdrill import taskout

DOC = pathlib.Path.home() / "pdfdrill-library" / "2010.14265"

# the six spellings of the one conditional-independence glyph (02-mathpix.md)
PERP = re.compile(r"\\(?:Perp|nVdash|nvdash|measuredangle)\b")

out = {}

# ---- 1. model objects by type
model = json.loads((DOC / "model.docmodel.json").read_text())
objs = model.get("objects") or []
if isinstance(objs, dict):
    objs = list(objs.values())
by_type = collections.Counter(o.get("type") for o in objs)
out["model_objects_by_type"] = dict(by_type.most_common())
out["model_objects_total"] = len(objs)

# ---- 2. where the \Perp family occurs, by MathPix line type
lines = json.loads((DOC / "2010.14265.lines.json").read_text())
line_types = collections.Counter()
perp_by_linetype = collections.Counter()
for pg in lines.get("pages") or []:
    for ln in pg.get("lines") or []:
        t = ln.get("type")
        line_types[t] += 1
        txt = (ln.get("text") or "") + " " + (ln.get("text_display") or "")
        n = len(PERP.findall(txt))
        if n:
            perp_by_linetype[t] += n
out["line_types"] = dict(line_types.most_common())
out["perp_by_line_type"] = dict(perp_by_linetype.most_common())
out["perp_total_in_lines"] = sum(perp_by_linetype.values())

# ---- 3. where it occurs in the MODEL, by object type
perp_by_objtype = collections.Counter()
perp_objs = []
for o in objs:
    p = o.get("props") or {}
    blob = " ".join(str(p.get(k) or "") for k in
                    ("latex", "latex_raw", "text", "mathpix_text", "raw_text"))
    n = len(PERP.findall(blob))
    if n:
        perp_by_objtype[o.get("type")] += n
        perp_objs.append({"id": o.get("id"), "type": o.get("type"),
                          "n": n, "page": p.get("page")})
out["perp_by_object_type"] = dict(perp_by_objtype.most_common())
out["perp_total_in_model"] = sum(perp_by_objtype.values())

# ---- 4. what actually REACHES an artefact
tid_path = list(DOC.glob("*.tiddlers.json"))[0]
tids = json.loads(tid_path.read_text())
bib = rt.resolve_bibkey(tid_path)
fo, eq, tab, dia = rt.rows_for(tids, bib)

def count_rows(rows):
    tot = 0
    hit = 0
    for r in rows:
        tot += 1
        if PERP.search(r[1] or ""):
            hit += 1
    return tot, hit

out["report_rows"] = {}
for name, rows in (("equations", eq), ("formulas", fo),
                   ("tables", tab), ("image_regions", dia)):
    tot, hit = count_rows(rows)
    out["report_rows"][name] = {"rows": tot, "rows_carrying_perp": hit}

# occurrences (not rows) reaching the report's row set
occ_in_rows = sum(len(PERP.findall(r[1] or ""))
                  for rows in (fo, eq, tab, dia) for r in rows)
out["perp_occurrences_in_report_rows"] = occ_in_rows

# compare.html: display equations carrying a crop
cmp_path = DOC / "compare.html"
cmp_html = cmp_path.read_text(encoding="utf-8", errors="replace") if cmp_path.is_file() else ""
out["compare_html_perp_occurrences"] = len(PERP.findall(cmp_html))
out["compare_html_rows"] = cmp_html.count('<td class="num"')

# report.pdf: the published findings build
rp = DOC / "report.pdf"
out["report_pdf_present"] = rp.is_file()

# ---- 5. paragraphs are where it lives; do they reach anything?
out["paragraph_objects"] = by_type.get("Paragraph", 0)
out["formula_objects"] = by_type.get("Formula", 0)
out["equation_objects"] = by_type.get("Equation", 0)

taskout.save_script(DOC, 527, pathlib.Path(__file__).read_text())
taskout.save_json(DOC, 527, "perp", out)
print(json.dumps(out, indent=1)[:2600])
print("\nwritten:")
print(taskout.report_lines(DOC, 527))
