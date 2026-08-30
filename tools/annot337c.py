#!/usr/bin/env python3
"""337 — retry the budget-starved row, then score every reply by ink.

The score is inkdrill's own: both renders go into a two-column longtable,
which is compiled and measured with `inkdrill compare`, so the number is the
same five-tuple L1 the whole project scores ink with rather than a new metric
invented for this one measurement.
"""
import json, pathlib, re, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import refine as rf, region_standalone as rs                 # noqa: E402
from pdfdrill import texgraphics as tg, latex_source as ls                 # noqa: E402
from pdfdrill import regionink as ri                                       # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from annot337b import SYSTEM, TEMPLATE, described                          # noqa: E402

DOC = pathlib.Path.home() / "pdfdrill-library" / "2004.05631v1"
SRC = DOC / "texsrc"; OUT = DOC / "annot337"


def main():
    ps = json.load(open(ROOT/"out"/"337.replies.json"))
    authored = [p for p in sorted(SRC.rglob("*.tex")) if not tg.is_texzip_tex(p, SRC)]
    root = next(p for p in authored if "\\documentclass" in p.read_text(errors="replace")[:4000])
    pre = ls.standalone_preamble(ls.expand_inputs(str(root), str(SRC)))
    for p in ps:
        if p.get("model_png") or p.get("finish") != "length":
            continue
        print("  retrying %s with a larger budget..." % p["base"], flush=True)
        prompt = TEMPLATE.format(opts=p["options_raw"] or "", name=p["file"],
                                 position=described(p))
        txt, fin, err = rf._novita_chat(prompt, system=SYSTEM, model=rf.NOVITA_MODEL,
                                        max_tokens=16000, timeout=600,
                                        crop=[SRC/p["base"], p["crop"]])
        p["reply"], p["finish"], p["api_error"] = txt, fin, err
        body = re.sub(r"^```[a-z]*\n?|```$", "", (txt or "").strip(), flags=re.M).strip()
        p["annotation"] = body
        if body:
            tikz = ("\\begin{tikzpicture}\n\\node at (0,0) {\\includegraphics[%s]{%s}};\n%s\n"
                    "\\end{tikzpicture}" % (p["options_raw"] or "", p["file"], body))
            png, cerr = rs.render("MODEL_"+pathlib.Path(p["base"]).stem, tikz, OUT,
                                  author_preamble=pre, graphics_dir=SRC, texinputs=SRC)
            p["model_png"] = str(png) if png else None
            p["compile_error"] = None if png else (cerr or "?")[:120]
        print("     -> %s (%d chars, %s)" % ("compiled" if p.get("model_png") else "failed",
                                             len(txt or ""), fin), flush=True)

    scored = [p for p in ps if p.get("model_png") and p.get("author_png")]
    rows = "".join(
        "\\ident{%s} & \\includegraphics[width=70mm]{%s} & "
        "\\includegraphics[width=70mm]{%s} \\\\ \\hline\n"
        % (pathlib.Path(p["base"]).stem.replace("_", "\\_"),
           p["author_png"], p["model_png"])
        for p in scored)
    tex = ("\\documentclass[a3paper,landscape]{article}\n"
           "\\usepackage[a3paper,landscape,margin=8mm]{geometry}\n"
           "\\usepackage{graphicx,longtable}\n"
           "\\newcommand{\\ident}[1]{\\texttt{#1}}\n\\begin{document}\n"
           "\\begin{longtable}{|p{40mm}|p{75mm}|p{75mm}|}\n\\hline\n"
           "\\textbf{Identifier} & \\textbf{Author} & \\textbf{Model} \\\\\n"
           "\\hline\\endhead\n" + rows + "\\end{longtable}\n\\end{document}\n")
    cmp_dir = OUT / "score"; cmp_dir.mkdir(parents=True, exist_ok=True)
    (cmp_dir/"score.tex").write_text(tex)
    subprocess.run(["xelatex","-interaction=nonstopmode","score.tex"],
                   cwd=cmp_dir, capture_output=True, timeout=900)
    pdf = cmp_dir/"score.pdf"
    print("\n  comparison sheet: %s (%s)" % (pdf, "built" if pdf.is_file() else "FAILED"), flush=True)
    if pdf.is_file():
        sel = ri.reportpages_json(pdf, columns=3, table=1, header="every", timeout=900)
        pages = sel.get("pages") or []
        allrows = []
        for pg in pages:
            a = ri._render(pdf, pg, 300, cmp_dir); b = ri._render(pdf, pg, 600, cmp_dir)
            r = ri.compare_page(a, b, pg, 900)
            exp = len((sel.get("rows") or {}).get(str(pg), []))
            if len(r) == exp + 1: r = r[1:]
            allrows.extend(r)
        for p, r in zip(scored, allrows):
            p["ink"] = {"L": r["L"], "R": r["R"],
                        "distance": sum(abs(x-y) for x, y in zip(r["L"], r["R"]))}
        print("  measured %d rows against %d scored pairs" % (len(allrows), len(scored)))
    json.dump(ps, open(ROOT/"out"/"337.replies.json","w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
