# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/regions.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""regions - equation boxes from per-glyph decisions, and IoU matching.

Ideas from IBEM (Anitei et al., Pattern Recognit. Lett. 172, 2023), see
tests/test_ibem_regions.py.

CONTRACT
    DEPTH, HEIGHT: glyph y-extent = [base - DEPTH*size, base + HEIGHT*size]
      (no glyph heights in units.jsonl; the same rule is used for truth and
      prediction, so it cancels in IoU only to first order -- unverified).
    glyph_box(g) -> (x0, y0, x1, y1)
    regions(glyphs) -> [dict(page, box, n)]: single-link components of the
      given glyphs; two glyphs link when on the same page and their boxes are
      at most MERGE_DX*size apart horizontally AND MERGE_DY*size vertically
      (size = the larger of the two). box = union of ALL member boxes (I1).
    iou(a, b) -> float
    match(pred, gt, thr=0.7) -> dict(tp, fp, fn, pairs, missed, spurious):
      greedy one-to-one by descending IoU among same-page pairs with
      IoU >= thr; pairs = [(pred_index, gt_index, iou)], missed = unmatched
      gt records, spurious = unmatched pred records (I2: hints, not only
      counts).
    taxonomy(pred, gt, thr=0.7, inside=0.9) -> dict(gt=[class per gt],
      pred=['false' or 'overlaps' per pred], counts) - Lin et al. IJDAR 2014's
      evaluation classes, per truth region, from same-page overlaps:
        missed            no predicted region overlaps it
        merged            an overlapping prediction covers >= 2 truths (each
                          truth >= `inside` of its area inside that prediction)
        split             >= 2 overlapping predictions, each >= `inside` of its
                          area inside this truth
        correct           best overlapping prediction has IoU >= thr
        partial           best prediction lies inside the truth (>= `inside`)
        expanded          the truth lies inside the best prediction
        partial_expanded  any other overlap
      a prediction overlapping no truth is 'false'. counts = Counter of the gt
      classes plus 'false'.
"""
DEPTH, HEIGHT = 0.25, 0.75
MERGE_DX, MERGE_DY = 3.0, 1.0


def glyph_box(g):
    return (g["x0"], g["base"] - DEPTH * g["size"], g["x1"], g["base"] + HEIGHT * g["size"])


def _gap(a, b):
    return (max(0.0, max(a[0], b[0]) - min(a[2], b[2])), max(0.0, max(a[1], b[1]) - min(a[3], b[3])))


def regions(glyphs):
    boxes = [glyph_box(g) for g in glyphs]
    parent = list(range(len(glyphs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    by_page = {}
    for i, g in enumerate(glyphs):
        by_page.setdefault(g["page"], []).append(i)
    for idx in by_page.values():
        idx.sort(key=lambda i: boxes[i][0])
        for a in range(len(idx)):
            i = idx[a]
            for b in range(a + 1, len(idx)):
                j = idx[b]
                s = max(glyphs[i]["size"], glyphs[j]["size"])
                dx, dy = _gap(boxes[i], boxes[j])
                if dx <= MERGE_DX * s and dy <= MERGE_DY * s:
                    parent[find(i)] = find(j)
    comp = {}
    for i in range(len(glyphs)):
        comp.setdefault(find(i), []).append(i)
    out = []
    for members in comp.values():
        bs = [boxes[i] for i in members]
        out.append(dict(page=glyphs[members[0]]["page"], n=len(members),
                        box=(min(b[0] for b in bs), min(b[1] for b in bs),
                             max(b[2] for b in bs), max(b[3] for b in bs))))
    return sorted(out, key=lambda r: (str(r["page"]), -r["box"][3], r["box"][0]))


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
    u = area(a) + area(b) - inter
    return inter / u if u > 0 else 0.0


def match(pred, gt, thr=0.7):
    cand = sorted(((iou(p["box"], t["box"]), i, j) for i, p in enumerate(pred)
                   for j, t in enumerate(gt) if p["page"] == t["page"]), reverse=True)
    used_p, used_g, pairs = set(), set(), []
    for v, i, j in cand:
        if v < thr:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i); used_g.add(j); pairs.append((i, j, v))
    return dict(tp=len(pairs), fp=len(pred) - len(pairs), fn=len(gt) - len(pairs), pairs=pairs,
                missed=[t for j, t in enumerate(gt) if j not in used_g],
                spurious=[p for i, p in enumerate(pred) if i not in used_p])


def _inter(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def _area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def taxonomy(pred, gt, thr=0.7, inside=0.9):
    from collections import Counter
    ov = {(i, j): _inter(p["box"], t["box"]) for i, p in enumerate(pred) for j, t in enumerate(gt)
          if p["page"] == t["page"] and _inter(p["box"], t["box"]) > 0}
    pi = lambda i, j: ov[(i, j)] / (_area(pred[i]["box"]) or 1)      # share of pred inside gt
    gi = lambda i, j: ov[(i, j)] / (_area(gt[j]["box"]) or 1)        # share of gt inside pred
    covers = {i: [j for (a, j) in ov if a == i and gi(i, j) >= inside] for i in range(len(pred))}
    out = []
    for j, t in enumerate(gt):
        P = [i for (i, b) in ov if b == j]
        if not P:
            out.append("missed")
        elif any(len(covers[i]) >= 2 and j in covers[i] for i in P):
            out.append("merged")
        elif len(P) >= 2 and all(pi(i, j) >= inside for i in P):
            out.append("split")
        else:
            i = max(P, key=lambda i: iou(pred[i]["box"], t["box"]))
            if iou(pred[i]["box"], t["box"]) >= thr:
                out.append("correct")
            elif pi(i, j) >= inside:
                out.append("partial")
            elif gi(i, j) >= inside:
                out.append("expanded")
            else:
                out.append("partial_expanded")
    pc = ["overlaps" if any(a == i for (a, _) in ov) else "false" for i in range(len(pred))]
    counts = Counter(out)
    if pc.count("false"):
        counts["false"] = pc.count("false")
    return dict(gt=out, pred=pc, counts=dict(counts))
