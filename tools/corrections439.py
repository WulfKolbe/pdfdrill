#!/usr/bin/env python3
"""439 — corrections.html: MathPix's reading above, the accepted correction below.

One row per accepted correction. The SCAN IS SHARED — it is the same region,
so it spans both halves and the reader compares two readings of one crop
rather than two crops (437).

The basis is a COLUMN, not a filter. 438 found 32 corrections verified by ink
and one verified against the author's e-print by counting; filtering to
`verified_by: ink` would drop the strongest correction in the corpus, so the
filter is "accepted" and the column says on what evidence.

Both ink numbers are shown. One correction was accepted on a fall of 398->397,
and a reader can only judge a weak acceptance if both are on the page.
"""
import argparse, base64, html, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill.svg import (compile_to_svg, tools_available,     # noqa: E402
                          is_latex_graphic)
from pdfdrill.svg_ids import inline_body, safe_token          # noqa: E402
from pdfdrill.report_tex import sanitize_title                # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"
#: display maths, so the halves are set the way the page sets them
PRE = (r"\documentclass[border=2pt,varwidth=170mm]{standalone}"
       "\n" r"\usepackage{amsmath,amssymb,amsfonts,mathrsfs,bm}" "\n")


# 509/510 — SELECTION AND IDENTITY ARE SHARED. They used to live here, and
# report.pdf's Corrected section would have been a second implementation of
# the same idea; 422 was written because four artefacts had already drifted.
# What stays here is the RENDERING, which is genuinely different: this sets a
# pair as HTML with an inline SVG or KaTeX, and report.pdf sets it as two
# longtable rows.
from pdfdrill.corrections import (collect, identifier_for,       # noqa: E402
                                  crop_path)


def _identifier_for(rec):
    return identifier_for(rec, LIB)


def crop_for(rec):
    """The scan crop, as a data URI. The SAME image for both halves."""
    f = crop_path(rec, LIB)
    if f is None:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()


def rendered_of(latex, token):
    """SVG for a graphic, KaTeX for mathematics — decided by the content.

    439 asked for SVG on the grounds that the type change requires it, KaTeX
    being unable to set a tikzpicture. 438 then measured that NO row has
    changed type: all 33 are mathematics above and below. And
    `svg.compile_to_svg` REFUSES mathematics — `is_latex_graphic` is a hard
    guard against feeding non-graphic content to latex, and defeating it to
    render an equation would be using a tool for the thing it was built to
    exclude.

    So the cell picks: a graphic gets an inlined SVG (and will, the moment a
    reclassification produces one), mathematics gets KaTeX, which is what
    formula-report.html already uses for the same content. The reason for
    HTML over PDF stands either way.
    """
    if not latex.strip():
        return '<span class="lbl">—</span>'
    if is_latex_graphic(latex):
        r = compile_to_svg(latex, preamble=PRE, timeout=60)
        if r.get("ok"):
            return '<div class="svg">%s</div>' % (
                inline_body(r["svg"], safe_token(token)) or "")
        return '<div class="fail">did not render: %s</div>' % html.escape(
            (r.get("error") or "")[:90])
    return '<div class="katex-render">\\[%s\\]</div>' % html.escape(latex)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(pathlib.Path.home() /
                                         "pdfdrill.github.io" / "reports" /
                                         "corrections.html"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not tools_available():
        print("latex/dvisvgm not on PATH", file=sys.stderr)
        return 1
    rows = collect()
    if a.limit:
        rows = rows[:a.limit]
    print("  %d accepted corrections" % len(rows), flush=True)

    parts = ["""<!doctype html><html><head><meta charset="utf-8">
<title>Accepted corrections — pdfdrill</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.body,{delimiters:[{left:'\\\\[',right:'\\\\]',display:true}],throwOnError:false})"></script>
<style>
body{font-family:system-ui,sans-serif;margin:2em;max-width:1500px}
h1{margin-bottom:.2em} .lede{color:#444;max-width:60em}
table{border-collapse:collapse;width:100%;margin-top:1.5em}
th{background:#eef;text-align:left;padding:.4em .6em;border:1px solid #99a}
td{border:1px solid #bbb;padding:.5em .6em;vertical-align:top}
tr.before td{border-bottom:none;background:#fff}
tr.after  td{border-top:1px dashed #999;background:#f7fbf7}
td.scan{background:#fafafa;text-align:center}
.svg svg{max-width:100%;height:auto}
.k{font-family:ui-monospace,monospace;font-size:.85em}
.lbl{font-size:.75em;text-transform:uppercase;letter-spacing:.05em;color:#666}
.conf{font-family:ui-monospace,monospace}
.ink{font-family:ui-monospace,monospace;white-space:nowrap}
.fail{color:#b00;font-size:.85em}
.basis{font-size:.85em}
</style></head><body>
<h1>Accepted corrections</h1>
<p class="lede">Each row is one region read twice: <b>above</b>, what MathPix
produced; <b>below</b>, the correction that replaced it. The scan between them
is <b>the same crop</b> — the two halves are two readings of one image, not two
images. A correction appears here only if it was accepted; the
<b>basis</b> column says on what evidence, and both ink numbers are shown so a
weak acceptance is visible as one.</p>
<table><thead><tr>
<th>identifier</th><th>page</th><th>conf</th><th>reading</th>
<th>rendered</th><th>scan</th><th>basis</th><th>ink</th>
</tr></thead><tbody>"""]
    for i, r in enumerate(rows, 1):
        crop = crop_for(r)
        img = ('<img src="%s" style="max-width:100%%">' % crop) if crop else \
              '<span class="lbl">no crop</span>'
        conf = ("%.3f" % r["conf"]) if isinstance(r["conf"], (int, float)) else "—"
        ink = ("%s → %s" % (r["ink_before"], r["ink_after"])
               if r["ink_before"] is not None else "—")
        parts.append(
            '<tr class="before">'
            '<td rowspan="2"><span class="k">%s</span><br><span class="lbl">%s</span></td>'
            '<td rowspan="2">%s</td>'
            '<td class="conf">%s</td>'
            '<td><span class="lbl">MathPix</span><br><span class="k">%s</span></td>'
            '<td>%s</td>'
            '<td class="scan" rowspan="2">%s</td>'
            '<td rowspan="2" class="basis">%s<br><span class="lbl">verified by</span> %s'
            '%s</td>'
            '<td rowspan="2" class="ink">%s</td></tr>'
            % (html.escape(r["obj"]), html.escape(r["doc"][:28]),
               html.escape(str(r["page"])), conf,
               html.escape(r["before"][:400]),
               rendered_of(r["before"], r["obj"] + "b"),
               img,
               html.escape(r["basis"][:120]), html.escape(str(r["verified_by"])),
               ("<br><span class='lbl'>evidence</span> " + html.escape(r["evidence"][:80]))
               if r["evidence"] else "",
               ink))
        parts.append(
            '<tr class="after">'
            '<td class="conf">—</td>'
            '<td><span class="lbl">correction</span><br><span class="k">%s</span></td>'
            '<td>%s</td></tr>'
            % (html.escape(r["after"][:400]), rendered_of(r["after"], r["obj"] + "a")))
        print("    %2d/%d %s" % (i, len(rows), r["obj"]), flush=True)
    parts.append("</tbody></table></body></html>")
    dest = pathlib.Path(a.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(parts), encoding="utf-8")
    print("  wrote %s (%d rows, %.1f KB)" % (dest, len(rows),
                                             dest.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
