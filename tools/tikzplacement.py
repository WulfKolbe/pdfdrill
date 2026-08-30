#!/usr/bin/env python3
"""342 — does the annotation sit OUTSIDE the figure's rectangle, or over it?

335 found 224 inclusions with a sibling \\node or \\draw. "Annotation" is not
one shape: bothways (341) puts its two labels BETWEEN the arrows, inside the
image's own rectangle, while other figures caption from above or below. A
prompt that says "the text is above the figure" is wrong for the first kind,
and a detector that looks only around the border will miss it.

The image's extent is computable: its natural size from the file's own dpi,
scaled by the `scale=` or `width=` option, centred on the node's coordinate.
Tikz coordinates are cm by default. A sibling whose coordinate falls inside
that rectangle OVERLAPS; one outside it is placed AROUND.

Coordinates that are not numeric -- `(a.north)`, `($(x)!.5!(y)$)` -- are
counted as UNPARSED rather than guessed at.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import texgraphics as tg                     # noqa: E402
from PIL import Image                                      # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"
_AT = re.compile(r"\\node\b[^;{]*?\bat\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
_ANYNODE = re.compile(r"\\node\b")
_COORD = re.compile(r"\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")


def rendered_cm(path: pathlib.Path, opts: dict):
    """(width, height) in cm of the image as the document sets it."""
    try:
        im = Image.open(path)
    except Exception:
        return None
    # 72, NOT the file's own dpi. graphicx sizes a bitmap at 1 bp per pixel
    # unless told otherwise, and bothways proves it: a 725x538 JPEG carrying
    # 132 dpi metadata, included at scale=0.1, occupies 72.5 x 53.8 pt on
    # page 38 of the author's PDF (pdfplumber). 725/72 in x 0.1 = 72.5 pt
    # exactly; using the file's 132 gives 39.7 pt, an extent 1.83x too small,
    # which biases every verdict toward "around".
    w = im.width / 72.0 * 2.54
    h = im.height / 72.0 * 2.54
    if "scale" in opts:
        try:
            s = float(str(opts["scale"]).strip())
            return w * s, h * s
        except ValueError:
            pass
    for k in ("width", "height"):
        v = str(opts.get(k, ""))
        m = re.match(r"^([\d.]+)\s*(cm|mm|in|pt)$", v.strip())
        if m:
            n = float(m.group(1))
            cm = {"cm": n, "mm": n / 10, "in": n * 2.54, "pt": n * 2.54 / 72.27}[m.group(2)]
            return (cm, cm * h / w) if k == "width" else (cm * w / h, cm)
        if "linewidth" in v or "textwidth" in v:
            m2 = re.match(r"^([\d.]*)", v.strip())
            frac = float(m2.group(1)) if m2.group(1) else 1.0
            cm = 12.0 * frac                     # a Tufte text block, ~12 cm
            return cm, cm * h / w
    return w, h


def classify(body: str, pos: int, base: pathlib.Path, opts: dict):
    span = tg.enclosing_span(body, pos, "tikzpicture")
    if not span:
        return {"verdict": "no tikzpicture"}
    env = body[span[0]:span[1]]
    m = _AT.search(body[span[0]:pos] + body[pos:pos + 200])
    if not m:
        return {"verdict": "unparsed", "why": "image node has no numeric at()"}
    ox, oy = float(m.group(1)), float(m.group(2))
    dims = rendered_cm(base, opts)
    if not dims:
        return {"verdict": "unparsed", "why": "base image unreadable"}
    hw, hh = dims[0] / 2.0, dims[1] / 2.0
    inside = outside = unparsed = 0
    for nm in _ANYNODE.finditer(env):
        seg = env[nm.start():nm.start() + 220]
        c = _COORD.search(seg)
        # the image's OWN node, which starts ~15 chars before the
        # \includegraphics it wraps. Comparing the two offsets with a
        # 3-character tolerance never matched, so every image counted
        # itself as a sibling at distance 0 and every row came back
        # "overlapping" -- 210 of 210, which is what made it obvious.
        node_abs = span[0] + nm.start()
        if node_abs <= pos <= node_abs + len(seg):
            continue
        if not c:
            unparsed += 1
            continue
        x, y = float(c.group(1)), float(c.group(2))
        if abs(x - ox) <= hw and abs(y - oy) <= hh:
            inside += 1
        else:
            outside += 1
    return {"verdict": "overlapping" if inside else
                       ("around" if outside else "none placed"),
            "inside": inside, "outside": outside, "unparsed": unparsed,
            "extent_cm": [round(dims[0], 2), round(dims[1], 2)],
            "origin": [ox, oy]}


def main():
    rows = json.load(open(ROOT / "out" / "335.json"))
    out = []
    for r in rows:
        src = LIB / r["doc"] / "texsrc"
        texts = {}
        for h in r["hits"]:
            if not (h["siblings"] and h["base_on_disk"]):
                continue
            t = src / h["source"]
            if t not in texts:
                try:
                    texts[t] = tg._COMMENT.sub("", t.read_text(errors="replace"))
                except OSError:
                    texts[t] = ""
            body = texts[t]
            call = None
            for c in tg.calls(body, source=h["source"]):
                if c["file"] == h["file"] and c["line"] == h["line"]:
                    call = c
                    break
            if call is None:
                for c in tg.calls(body, source=h["source"]):
                    if c["file"] == h["file"]:
                        call = c
                        break
            if call is None:
                out.append({"doc": r["doc"], **h, "verdict": "unparsed",
                            "why": "call not relocated"})
                continue
            out.append({"doc": r["doc"], "file": h["file"],
                        "source": h["source"], "line": h["line"],
                        "base": h["base_on_disk"],
                        **classify(body, call["pos"], src / h["base_on_disk"],
                                   call["options"])})
    (ROOT / "out" / "342.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    import collections
    c = collections.Counter(x["verdict"] for x in out)
    print("  classified %d annotated inclusions" % len(out))
    for k, v in c.most_common():
        print("    %-16s %d" % (k, v))


if __name__ == "__main__":
    main()
