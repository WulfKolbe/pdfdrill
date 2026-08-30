#!/usr/bin/env python3
"""337 — can a model reproduce the annotation over a figure?

Seven-ish registered pairs (339): base file, the crop of the composed figure,
and the author's own tikzpicture. The reference render is the author's
tikzpicture compiled standalone, so the right answer is known by construction
— the same trick 332 used for the tikzcd gold set.

The prompt states position ONLY where 342 measured one. An `around` row gets a
direction and a distance from the sibling coordinates and the image's measured
extent; an `overlapping` row is told it overlaps and given no position, because
"centred above at distance d" is false for a label sitting on the figure and a
model told something false about a picture it can see is worse off than one
told nothing.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import texgraphics as tg                     # noqa: E402
from pdfdrill import region_standalone as rs               # noqa: E402
from pdfdrill import latex_source as ls                    # noqa: E402

DOC = pathlib.Path.home() / "pdfdrill-library" / "2004.05631v1"
SRC = DOC / "texsrc"
OUT = DOC / "annot337"
ZIMG = SRC / "abab828b-61e2-4095-ac03-1e28612cc14a" / "images"


def preamble():
    authored = [p for p in sorted(SRC.rglob("*.tex"))
                if not tg.is_texzip_tex(p, SRC)]
    root = next((p for p in authored
                 if "\\documentclass" in p.read_text(errors="replace")[:4000]), None)
    if root is None:
        return ""
    return ls.standalone_preamble(ls.expand_inputs(str(root), str(SRC)))


def pairs():
    matched = json.load(open(ROOT / "out" / "339.json"))["matched"]
    place = {r.get("base"): r for r in json.load(open(ROOT / "out" / "342.json"))}
    out = []
    for m in matched:
        p = place.get(m["base"], {})
        t = SRC / m["source"]
        body = tg._COMMENT.sub("", t.read_text(errors="replace"))
        call = next((c for c in tg.calls(body, source=m["source"])
                     if c["file"] == m["file"]), None)
        if call is None:
            continue
        span = tg.enclosing_span(body, call["pos"], "tikzpicture")
        if not span:
            continue
        out.append({**m, "verdict": p.get("verdict"),
                    "extent_cm": p.get("extent_cm"), "origin": p.get("origin"),
                    "author_tikz": body[span[0]:span[1]],
                    "options_raw": call["options_raw"],
                    "crop": str(ZIMG / ("abab828b-61e2-4095-ac03-1e28612cc14a-"
                                        + m["candidates"][0].split("-")[-1]))})
    return out


_NODE_AT = re.compile(r"\\node\b[^;]*?\bat\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)"
                      r"[^;]*?\{(.*?)\}\s*;", re.S)


def described(p):
    """The positional description 342 licenses, and nothing more."""
    if p["verdict"] != "around":
        return ("The annotation OVERLAPS the image: at least one element is "
                "drawn on top of the picture rather than beside it. No "
                "direction or distance is given, because none was measured.")
    ex = p.get("extent_cm") or [0, 0]
    ox, oy = (p.get("origin") or [0, 0])
    parts = []
    for m in _NODE_AT.finditer(p["author_tikz"]):
        x, y = float(m.group(1)), float(m.group(2))
        if abs(x - ox) <= ex[0] / 2 and abs(y - oy) <= ex[1] / 2:
            continue
        d = []
        if x < ox - ex[0] / 2:
            d.append("left of the image by %.2f cm" % (ox - ex[0] / 2 - x))
        elif x > ox + ex[0] / 2:
            d.append("right of the image by %.2f cm" % (x - ox - ex[0] / 2))
        if y > oy + ex[1] / 2:
            d.append("above by %.2f cm" % (y - oy - ex[1] / 2))
        elif y < oy - ex[1] / 2:
            d.append("below by %.2f cm" % (oy - ex[1] / 2 - y))
        if d:
            parts.append("one element " + " and ".join(d))
    return ("The image is %.2f cm wide and %.2f cm tall, centred at the "
            "origin. %s." % (ex[0], ex[1], "; ".join(parts) or
                             "Elements sit outside the image rectangle"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pre = preamble()
    ps = pairs()
    print("  registered pairs: %d" % len(ps), flush=True)
    for p in ps:
        png, err = rs.render("AUTHOR_" + pathlib.Path(p["base"]).stem,
                             p["author_tikz"], OUT, author_preamble=pre,
                             graphics_dir=SRC, texinputs=SRC)
        p["author_png"] = str(png) if png else None
        p["author_error"] = None if png else (err or "?")[:120]
        print("  %-30s %-12s author render %s"
              % (p["base"][-30:], p["verdict"], "ok" if png else p["author_error"][:40]),
              flush=True)
    (ROOT / "out" / "337.pairs.json").write_text(
        json.dumps(ps, indent=1, ensure_ascii=False))
    ok = sum(1 for p in ps if p["author_png"])
    print("\n  author references rendered: %d of %d" % (ok, len(ps)), flush=True)
    for p in ps:
        if p["author_png"]:
            print("\n  --- %s (%s)" % (p["base"], p["verdict"]))
            print("      %s" % described(p))


if __name__ == "__main__":
    main()
