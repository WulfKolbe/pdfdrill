"""527 — corpus: what fraction of maths lives in text lines, not math lines.

Rule 19: script and result under ~/pdfdrill-library/out/527/.

A MathPix line carries a `type`. Display maths is `type == "math"`. Inline
maths is a $...$ span INSIDE a line of some other type — overwhelmingly
`text`. Both are maths; only one of them reaches an artefact that shows a
confidence, because a Formula tiddler carries none of its own.
"""
import sys, json, re, pathlib, collections
sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")
from pdfdrill import taskout

LIB = pathlib.Path.home() / "pdfdrill-library"
# $...$ and \( ... \), non-greedy, skipping escaped \$
INLINE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$|\\\((.+?)\\\)", re.S)

docs = 0
math_lines = 0
inline_spans = 0
math_chars = 0
inline_chars = 0
lines_total = 0
by_hosttype = collections.Counter()
per_doc = []

for d in sorted(LIB.iterdir()):
    if not d.is_dir():
        continue
    lj = list(d.glob("*.lines.json"))
    if not lj:
        continue
    try:
        j = json.loads(lj[0].read_text(encoding="utf-8", errors="replace"))
    except Exception:
        continue
    pages = j.get("pages") or []
    if not pages:
        continue
    docs += 1
    dm = di = dmc = dic = 0
    for pg in pages:
        for ln in pg.get("lines") or []:
            lines_total += 1
            t = ln.get("type")
            txt = ln.get("text") or ""
            if t == "math":
                dm += 1
                dmc += len(txt)
                continue
            for m in INLINE.finditer(txt):
                body = m.group(1) or m.group(2) or ""
                di += 1
                dic += len(body)
                by_hosttype[t] += 1
    math_lines += dm; inline_spans += di
    math_chars += dmc; inline_chars += dic
    per_doc.append({"doc": d.name, "math_lines": dm, "inline_spans": di,
                    "math_chars": dmc, "inline_chars": dic})

tot_items = math_lines + inline_spans
tot_chars = math_chars + inline_chars
summary = {
    "documents": docs,
    "lines_total": lines_total,
    "display_math_lines": math_lines,
    "inline_spans_in_non_math_lines": inline_spans,
    "pct_of_maths_ITEMS_that_are_inline":
        round(100.0 * inline_spans / tot_items, 1) if tot_items else None,
    "display_math_chars": math_chars,
    "inline_math_chars": inline_chars,
    "pct_of_maths_CHARS_that_are_inline":
        round(100.0 * inline_chars / tot_chars, 1) if tot_chars else None,
    "inline_host_line_types": dict(by_hosttype.most_common(10)),
    "docs_where_inline_exceeds_display":
        sum(1 for r in per_doc if r["inline_spans"] > r["math_lines"]),
}
taskout.save_script(None, 527, pathlib.Path(__file__).read_text(),
                    name="corpus_script.py")
taskout.save_json(None, 527, "corpus", {"summary": summary, "per_doc": per_doc})
print(json.dumps(summary, indent=1))
print("\nwritten:")
print(taskout.report_lines(None, 527))
