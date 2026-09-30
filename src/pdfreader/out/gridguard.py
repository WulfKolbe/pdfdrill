"""gridguard — can a monospace GRID be seen from LINE geometry alone?

781k — ASKED BY MATHPIX, ANSWERED WITH A NUMBER.

Their planned mitigation for the orphaned-container defect is to treat a
run of orphan code lines as an implicit code block, and its false-positive
case is prose or display maths that the model mistyped as code. The guard
they want is "a real listing is a monospace grid, and prose is not set
that way" -- but they do not read glyph advances. They have, per line, a
bounding box and the recognised text.

The line-level stand-in for the advance is

        cell = width / characters

which in a monospace face is the SAME on every row of a block, and in a
proportional face depends on which characters are on the row. So the test
is the SPREAD of that ratio across a block, and it needs nothing but the
box and the string.

    listing blocks  374    spread  median 0.0032   p90 0.0190
    prose blocks    103    spread  median 0.0816   p10 0.0247

    spread <= 0.005   listings kept 62.0%   prose wrongly kept 0.00%
    spread <= 0.010   listings kept 78.9%   prose wrongly kept 0.97%
    spread <= 0.020   listings kept 89.8%   prose wrongly kept 5.83%

AND THE GUTTER IS WHAT BREAKS IT. The first run of this measured the whole
line, line number included, and the number is a different font at a
different size -- so the ratio was never measuring one grid at all:

    gutter INCLUDED   listings median 0.059   prose median 0.082
                      spread <= 0.02 kept 40.4% of listings and 5.83%
                      of prose -- no separation worth having

Excluding it moved the listing median from 0.059 to 0.0032, a factor of
18, and turned a useless statistic into a 25x separation. Anyone
implementing this must drop the line-number column before taking the
ratio, or measure nothing.

    python3 gridguard.py
"""
import glob, statistics, sys
sys.path.insert(0, "/home/wkolbe/pdf2mmd")
from concurrent.futures import ThreadPoolExecutor
import docmodel_six as dm

def cv(v):
    if len(v) < 3: return None
    m = statistics.mean(v)
    return statistics.pstdev(v)/m if m else None

def listing_cv(f):
    try: pages = dm.build(f)
    except Exception: return []
    out = []
    for p in pages:
        for lst in p.listings:
            by = {ln.id: ln for ln in p.lines}
            r = []
            for x in lst.lines:
                ln = by.get(x.id)
                if ln is None or len(x.text) < 8: continue
                gs = [g for g in ln.glyphs if g.size >= 0.85*lst.size]
                if len(gs) < 4: continue
                w = max(g.rect[2] for g in gs) - min(g.rect[0] for g in gs)
                r.append(w / (len(x.text)))
            c = cv(r)
            if c is not None: out.append(c)
    return out

def prose_cv(f):
    try: pages = dm.build(f)
    except Exception: return []
    out, run = [], []
    def flush():
        if len(run) >= 4:
            r = []
            for ln in run:
                t = dm._run_text(ln.glyphs).strip()
                if len(t) < 8: continue
                w = max(g.rect[2] for g in ln.glyphs) - min(g.rect[0] for g in ln.glyphs)
                r.append(w/len(t))
            c = cv(r)
            if c is not None: out.append(c)
    for p in pages:
        for ln in p.lines:
            if ln.verbatim or ln.rotated or len(ln.glyphs) < 20:
                flush(); run.clear()
            else: run.append(ln)
        flush(); run.clear()
    return out

lst = sorted(glob.glob("/home/wkolbe/pdfdrill-library/lstgold/pdf/lst-*.pdf"))
doc = sorted(glob.glob("/home/wkolbe/pdfdrill-library/wzlxjtu-*/wzlxjtu-*.pdf"))[:45]
with ThreadPoolExecutor(max_workers=6) as ex:
    pos = [c for r in ex.map(listing_cv, lst) for c in r]
    neg = [c for r in ex.map(prose_cv, doc) for c in r]
f = lambda v,q: sorted(v)[int(q*len(v))-1]
print("listing blocks %4d   spread: median %.4f  p75 %.4f  p90 %.4f" %
      (len(pos), statistics.median(pos), f(pos,.75), f(pos,.90)))
print("prose blocks   %4d   spread: median %.4f  p10 %.4f  p25 %.4f" %
      (len(neg), statistics.median(neg), f(neg,.10), f(neg,.25)))
print()
for t in (0.005, 0.01, 0.02, 0.03, 0.05):
    tp = sum(1 for c in pos if c <= t)/len(pos)
    fp = sum(1 for c in neg if c <= t)/len(neg)
    print("   spread <= %.3f :  listings kept %5.1f%%   prose wrongly kept %5.2f%%"
          % (t, 100*tp, 100*fp))
