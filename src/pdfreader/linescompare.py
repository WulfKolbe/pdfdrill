"""linescompare - score our LaTeX against a MathPix lines.json, region by region.

Better than comparing two Markdown files: lines.json gives MathPix's own
rectangle for every maths line, so each comparison is anchored to the same
piece of the page instead of being aligned by text similarity.

For each MathPix `math` region:
  * find our maths spans whose rectangle lies inside it
  * compare the LaTeX token multisets

Also reports DIAGRAM agreement, since lines.json types those separately.

Coordinates: lines.json is pixels, top-left origin. The docmodel is PDF points,
y up. `docmodel.PX_PER_PT` is the shared constant.
"""
from __future__ import annotations

import collections
import json
import re
import statistics
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import docmodel_six as docmodel  # noqa: E402

TOKEN = re.compile(r"\\[a-zA-Z]+|[A-Za-z0-9]|[^\s{}]")
# Spacing and font wrappers differ by convention, not by content.
DROP = {"left", "right", "quad", "qquad", "displaystyle", "limits",
        "big", "Big", "bigg", "Bigg", "bigl", "bigr", "mathrm", "mathbf",
        "boldsymbol", "operatorname", "text", "mbox", "nolimits"}
# `\bar` and `\overline` are the same accent written two ways.
SAME = {r"\bar": r"\overline", r"\widebar": r"\overline",
        r"\hat": r"\widehat", r"\tilde": r"\widetilde",
        r"\intop": r"\int", r"\ointop": r"\oint"}


def toks(s: str) -> collections.Counter:
    out: collections.Counter = collections.Counter()
    for t in TOKEN.findall(s or ""):
        t = SAME.get(t, t)
        if t.lstrip("\\") in DROP:
            continue
        out[t] += 1
    return out


def iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1])
    ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (ua + ub - inter)


def run(pdf: str, lines_json: str, first: int, last: int) -> None:
    with open(lines_json, encoding="utf-8") as fh:
        ref = {p["page"]: p for p in json.load(fh)["pages"]}
    pages = docmodel.build(pdf, range(first - 1, last))
    k = docmodel.PX_PER_PT

    scores: list[float] = []
    exact = covered = total = 0
    missing: collections.Counter = collections.Counter()
    dia_hit = dia_total = 0
    dia_iou: list[float] = []

    for p in pages:
        r = ref.get(p.page)
        if not r:
            continue
        H = p.rect[3]

        def to_px(rect):
            return (rect[0] * k, (H - rect[3]) * k,
                    rect[2] * k, (H - rect[1]) * k)

        ours = [(to_px(sp.rect), docmodel.span_latex(sp))
                for ln in p.lines for sp in ln.spans
                if sp.kind == "math" and docmodel.span_latex(sp)]
        our_dia = [to_px(d) for d in p.diagrams]

        for line in r.get("lines", []):
            reg = line.get("region") or {}
            if not reg:
                continue
            box = (reg["top_left_x"], reg["top_left_y"],
                   reg["top_left_x"] + reg["width"],
                   reg["top_left_y"] + reg["height"])
            if line["type"] == "diagram":
                dia_total += 1
                best = max((iou(d, box) for d in our_dia), default=0.0)
                dia_iou.append(best)
                if best > 0.3:
                    dia_hit += 1
                continue
            if line["type"] != "math":
                continue
            total += 1
            # Centre-inside, not full containment. Our spans absorb their
            # operators and so can extend a little past MathPix's rectangle;
            # requiring full containment dropped them and undercounted what
            # we actually produced.
            inside = [tex for rect, tex in ours
                      if box[0] - 6 <= 0.5 * (rect[0] + rect[2]) <= box[2] + 6
                      and box[1] - 6 <= 0.5 * (rect[1] + rect[3]) <= box[3] + 6]
            if not inside:
                continue
            covered += 1
            got: collections.Counter = collections.Counter()
            for t in inside:
                got += toks(t)
            want = toks(line.get("text", ""))
            if not want:
                continue
            shared = sum((got & want).values())
            scores.append(shared / sum(want.values()))
            if got == want:
                exact += 1
            for t, n in (want - got).items():
                missing[t] += n

    print(f"pages {first}-{last}")
    print(f"  MathPix maths regions      {total}")
    print(f"  we produced LaTeX inside   {covered} "
          f"({100.0 * covered / max(total, 1):.1f}%)")
    if scores:
        scores.sort()
        print(f"  token recall  median {statistics.median(scores):.2f}"
              f"   mean {statistics.mean(scores):.2f}")
        print(f"  regions >=0.9 recall       "
              f"{sum(1 for s in scores if s >= 0.9)} "
              f"({100.0 * sum(1 for s in scores if s >= 0.9) / len(scores):.1f}%)")
        print(f"  token-identical regions    {exact} "
              f"({100.0 * exact / len(scores):.1f}%)")
    print(f"  commands we most often miss: "
          f"{[t for t, _ in missing.most_common(12)]}")
    if dia_total:
        print(f"\n  MathPix diagrams {dia_total}, matched {dia_hit} "
              f"({100.0 * dia_hit / dia_total:.0f}%), "
              f"median IoU {statistics.median(dia_iou):.2f}")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
