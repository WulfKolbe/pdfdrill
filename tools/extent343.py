#!/usr/bin/env python3
"""343 — the placement split, on extents MEASURED rather than computed.

342 computed each image's rectangle from its `scale=`/`width=` option and the
file's pixel size. 337 caught that being wrong on three of seven rows: for
`width=\\linewidth` I had hardcoded "a Tufte text block, ~12 cm", and against
pdfplumber's actual rectangles mpsapprox2 was 340 pt computed against 143
measured, psi_N2 261 against 142, pt2 408 against 222. All three flipped from
overlapping to around. An extent that is too large pulls siblings inside it,
so the error has a DIRECTION: it manufactures overlap.

The author's own compiled PDF is already in the library for every one of the
eleven documents, so the rectangle can be read instead of derived. Nothing has
to be compiled.
"""
import collections
import json
import pathlib
import re
import sys

import pdfplumber
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import texgraphics as tg                     # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"
_AT = re.compile(r"\\node\b[^;]*?\bat\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
TOL = 0.05


def measured_extents(pdf: pathlib.Path) -> dict:
    """{(px_w, px_h): (cm_w, cm_h)} for every embedded image, or None when the
    same source image is placed at DIFFERENT sizes and one rectangle cannot
    stand for it."""
    seen = collections.defaultdict(list)
    with pdfplumber.open(pdf) as doc:
        for pg in doc.pages:
            for im in pg.images:
                ss = im.get("srcsize")
                if not ss:
                    continue
                w = (im["x1"] - im["x0"]) / 72 * 2.54
                h = (im["bottom"] - im["top"]) / 72 * 2.54
                seen[tuple(ss)].append((w, h))
    out = {}
    for k, v in seen.items():
        w0, h0 = v[0]
        if all(abs(w - w0) <= TOL * max(w0, 0.01)
               and abs(h - h0) <= TOL * max(h0, 0.01) for w, h in v):
            out[k] = (round(w0, 3), round(h0, 3))
        else:
            out[k] = None                     # placed at several sizes
    return out


def main():
    rows = json.load(open(ROOT / "out" / "335.json"))
    out = []
    for r in rows:
        doc = r["doc"]
        src = LIB / doc / "texsrc"
        pdfs = [p for p in (LIB / doc).glob("*.pdf") if p.name != "report.pdf"]
        ext = measured_extents(pdfs[0]) if pdfs else {}
        print("  %-40s %d embedded sizes" % (doc[:40], len(ext)), flush=True)
        texts = {}
        for h in r["hits"]:
            if not (h["siblings"] and h["base_on_disk"]):
                continue
            rec = {"doc": doc, "base": h["base_on_disk"], "file": h["file"],
                   "source": h["source"], "line": h["line"]}
            try:
                im = Image.open(src / h["base_on_disk"])
                key = (im.width, im.height)
            except Exception:
                rec["verdict"] = "unreadable base"
                out.append(rec); continue
            if key not in ext:
                rec["verdict"] = "not embedded"
                out.append(rec); continue
            if ext[key] is None:
                rec["verdict"] = "several sizes"
                out.append(rec); continue
            ew, eh = ext[key]
            rec["extent_cm"] = [ew, eh]
            t = src / h["source"]
            if t not in texts:
                texts[t] = tg._COMMENT.sub("", t.read_text(errors="replace"))
            body = texts[t]
            call = next((c for c in tg.calls(body, source=h["source"])
                         if c["file"] == h["file"]), None)
            if call is None:
                rec["verdict"] = "call not relocated"
                out.append(rec); continue
            span = tg.enclosing_span(body, call["pos"], "tikzpicture")
            if not span:
                rec["verdict"] = "no tikzpicture"
                out.append(rec); continue
            env = body[span[0]:span[1]]
            m = _AT.search(body[span[0]:call["pos"] + 200])
            ox, oy = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
            inside = outside = 0
            for nm in _AT.finditer(env):
                x, y = float(nm.group(1)), float(nm.group(2))
                if abs(x - ox) < 1e-9 and abs(y - oy) < 1e-9:
                    continue                  # the image's own node
                if abs(x - ox) <= ew / 2 and abs(y - oy) <= eh / 2:
                    inside += 1
                else:
                    outside += 1
            rec.update(inside=inside, outside=outside, origin=[ox, oy],
                       verdict=("overlapping" if inside else
                                "around" if outside else "none placed"))
            out.append(rec)
    (ROOT / "out" / "343.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    c = collections.Counter(x["verdict"] for x in out)
    print("\n  classified %d" % len(out))
    for k, v in c.most_common():
        print("    %-20s %d" % (k, v))


if __name__ == "__main__":
    main()
