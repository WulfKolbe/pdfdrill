#!/usr/bin/env python3
"""337 — ask MiniMax for the annotation, compile it, score it by ink."""
import json, pathlib, re, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import refine as rf                          # noqa: E402
from pdfdrill import region_standalone as rs               # noqa: E402
from pdfdrill import texgraphics as tg                     # noqa: E402
from pdfdrill import latex_source as ls                    # noqa: E402

DOC = pathlib.Path.home() / "pdfdrill-library" / "2004.05631v1"
SRC = DOC / "texsrc"
OUT = DOC / "annot337"

SYSTEM = ("You read a figure and a crop of how it appears on the page, and "
          "return TikZ. Return ONLY the annotation code, no preamble, no "
          "\\begin{tikzpicture}, no \\includegraphics, no explanation.")

TEMPLATE = """The FIRST image is a figure file the author included.
The SECOND image is how that figure appears on the printed page.

The page version carries annotation the file does not: text labels, arrows or
rules the author drew over or around it with TikZ.

Inside a tikzpicture the image is already placed with
    \\node at (0,0) {{\\includegraphics[{opts}]{{{name}}}}};
Coordinates are centimetres and the image is centred on the origin.

{position}

Give me ONLY the additional TikZ lines that produce the annotation — the
\\node and \\draw statements. Do not repeat the \\includegraphics line. Do not
wrap them in tikzpicture. Do not explain."""


def described(p):
    ex = p.get("measured_cm")
    if p.get("verdict_measured") != "around" or not ex:
        return ("The annotation OVERLAPS the image: at least one element is "
                "drawn on top of the picture, not beside it. No direction or "
                "distance is given for it, because none was measured.")
    ox, oy = p.get("origin") or [0, 0]
    parts = []
    for m in re.finditer(r"\\node\b[^;]*?\bat\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)",
                         p["author_tikz"]):
        x, y = float(m.group(1)), float(m.group(2))
        if abs(x - ox) < 1e-9 and abs(y - oy) < 1e-9:
            continue
        d = []
        if x < ox - ex[0] / 2: d.append("%.2f cm to the LEFT of its edge" % (ox - ex[0]/2 - x))
        elif x > ox + ex[0] / 2: d.append("%.2f cm to the RIGHT of its edge" % (x - ox - ex[0]/2))
        if y > oy + ex[1] / 2: d.append("%.2f cm ABOVE its edge" % (y - oy - ex[1]/2))
        elif y < oy - ex[1] / 2: d.append("%.2f cm BELOW its edge" % (oy - ex[1]/2 - y))
        if d: parts.append("one element " + " and ".join(d))
    return ("The image is %.2f cm wide and %.2f cm tall. Every added element "
            "is OUTSIDE it: %s." % (ex[0], ex[1], "; ".join(parts)))


def main():
    ps = [p for p in json.load(open(ROOT/"out"/"337.pairs.json")) if p.get("author_png")]
    authored = [p for p in sorted(SRC.rglob("*.tex")) if not tg.is_texzip_tex(p, SRC)]
    root = next(p for p in authored if "\\documentclass" in p.read_text(errors="replace")[:4000])
    pre = ls.standalone_preamble(ls.expand_inputs(str(root), str(SRC)))
    for p in ps:
        prompt = TEMPLATE.format(opts=p["options_raw"] or "", name=p["file"],
                                 position=described(p))
        t0 = time.time()
        txt, fin, err = rf._novita_chat(
            prompt, system=SYSTEM, model=rf.NOVITA_MODEL, max_tokens=4000,
            timeout=300, crop=[SRC / p["base"], p["crop"]])
        p["reply"] = txt
        p["finish"] = fin
        p["api_error"] = err
        p["seconds"] = round(time.time()-t0, 1)
        body = re.sub(r"^```[a-z]*\n?|```$", "", (txt or "").strip(), flags=re.M).strip()
        p["annotation"] = body
        if body:
            tikz = ("\\begin{tikzpicture}\n\\node at (0,0) {\\includegraphics[%s]{%s}};\n%s\n"
                    "\\end{tikzpicture}" % (p["options_raw"] or "", p["file"], body))
            png, cerr = rs.render("MODEL_" + pathlib.Path(p["base"]).stem, tikz, OUT,
                                  author_preamble=pre, graphics_dir=SRC, texinputs=SRC)
            p["model_png"] = str(png) if png else None
            p["compile_error"] = None if png else (cerr or "?")[:120]
        else:
            p["model_png"] = None
            p["compile_error"] = "empty reply (%s %s)" % (fin, err)
        print("  %-28s %-12s %5.0fs reply %5d chars  %s"
              % (p["base"][-28:], p.get("verdict_measured"), p["seconds"],
                 len(txt or ""), "compiled" if p["model_png"] else p["compile_error"][:44]),
              flush=True)
    json.dump(ps, open(ROOT/"out"/"337.replies.json","w"), indent=1, ensure_ascii=False)
    print("\n  compiled %d of %d" % (sum(1 for p in ps if p["model_png"]), len(ps)))


if __name__ == "__main__":
    main()
