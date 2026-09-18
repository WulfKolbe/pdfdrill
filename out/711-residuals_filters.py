#!/usr/bin/env python3
"""711 — the residuals list for the MathPix admin, with every filter named.

THE QUESTION: which rows does inkdrill flag where MathPix's reading plausibly
dropped mathematics the scan contains? The raw `component` class does not
answer it -- most of its rows are explained by something other than a
conversion defect, and each explanation was measured tonight rather than
assumed. The filters below are applied in this order and each one is a class
that was checked by eye before it became a rule.

  1. flag == "component"
     `crop` (709) is already excluded by construction: inkdrill's own
     REGION-OVERRUN verdict says the scan crop captured a neighbour's ink.
     17-18% of all measured rows corpus-wide.

  2. signed_delta > 0
     A NEGATIVE delta means OUR rendering carries more components than the
     scan, which cannot be MathPix dropping a symbol. Measured on six of
     them: -9, -10, -13, -3, -3, -3 all collapse to ~0 when the report page
     is rendered with `-dTextAlphaBits=4 -dGraphicsAlphaBits=4`. They are
     bilevel stroke-shattering (inkdrill HANDOVER item 11: hole instability
     75% -> 9.4% with anti-aliasing on), not findings.

  3. L != [13,6,0,0,0] and L[0] > 5
     `(not rendered)` is 13 glyphs with 6 closed counters, so that exact
     five-tuple is the demoted-row text being measured against a real
     formula. L[0] <= 5 is the same shape more loosely: our cell is blank.
     Our defect, not MathPix's.

  4. R[0] / L[0] < 2.5
     Our side rendered, but far less ink than the scan. Checked by eye on
     `Introduction to Linear and Matrix Algebra`_EQ0429 (23 vs 337, 14.7x):
     the source is a wide `\\begin{array}` matrix and `\\FitMath` SHRANK it
     to fit the column. A scaling difference, not a missing symbol.

  5. crop height < 2x the document's median crop height
     Checked by eye on the same book: EQ0040's crop is 847x418 px against a
     105 px median -- four or five printed lines in one cell. The component
     surplus is mechanical. 34-41 rows corpus-wide are this shape, and they
     dominated every unfiltered list.

WHAT THE FILTERS CANNOT DO, stated because it matters more than the count:
`wzlxjtu-095_EQ0001` (+39) and `_EQ0003` (+16) survive all five, and BOTH
were examined by eye and show the SAME mathematics in the two columns --
differing only in inter-atom spacing and stroke weight. A number cannot
tell typography from a missing symbol. This list is a candidate set to
LOOK at, never a findings list to send.

Usage: residuals_711.py [--since 'YYYY-MM-DD HH:MM'] [--min-conf 0.0]
"""
import argparse
import collections
import glob
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

LIB = Path("/home/wkolbe/pdfdrill-library")
#: fixtures and synthetic documents: not author PDFs, never a MathPix finding
SKIP = {"datikz-fixture", "testtable"}

ap = argparse.ArgumentParser()
#: 709b (24d02eb3) committed 2026-09-17 22:54:02; the 710 lanes launched minutes
#: later. READ FROM git, NOT GUESSED: a cutoff of 23:40 -- my first guess --
#: classified 71 documents measured between 22:54 and 23:40 as "stale" and
#: silently computed this whole list on a truncated population. The symptom was
#: a coverage count that would not add up (265 fresh + 12 empty != 348).
ap.add_argument("--since", default="2026-09-17 22:54",
                help="only ink files at least this fresh (the 709b escaper landed 22:54:02)")
ap.add_argument("--min-conf", type=float, default=0.0)
ap.add_argument("--out", default=str(LIB / "out" / "711-residuals.tsv"))
A = ap.parse_args()
CUT = time.mktime(time.strptime(A.since, "%Y-%m-%d %H:%M"))

AB = re.escape("\\allowbreak{}")
#: the identifier may CONTAIN \allowbreak{}, so `[^}]*` stops at the brace it
#: opens and yields '0902.\allowbreak{'. Span it, then strip.
IDENT = re.compile(r"\\ident\{((?:" + AB + r"|[^{}]|\{\})*)\}")
CONF = re.compile(r"confcell\{\w+\}\{([0-9.]+)\}")


def clean_ident(s: str) -> str:
    return s.replace("\\allowbreak{}", "").replace("\\_", "_").replace("\\", "")


def confidences(tex: Path) -> dict:
    out = {}
    if not tex.is_file():
        return out
    for line in tex.read_text(encoding="utf-8", errors="replace").splitlines():
        mi, mc = IDENT.search(line), CONF.search(line)
        if mi and mc:
            out[clean_ident(mi.group(1))] = float(mc.group(1))
    return out


def tinted(doc: Path, ident: str):
    """(is the scan crop coloured or shaded, chroma%, background luminance).

    Our Rendered cell is ALWAYS plain black on white. A print that colours a
    term, or sets it over a shaded block, carries ink our side cannot have,
    and the component delta then measures the decoration rather than a
    dropped symbol. Three shapes, all measured on candidates tonight:

      saturated colour   s42256-022-00556-7_EQ0018 -- orange/blue/green
                         highlight boxes behind each term, coloured glyphs,
                         annotation labels. 39.5% chromatic at threshold 28.
      shaded block       Introduction to Linear and Matrix Algebra_EQ0793 --
                         a blue-grey rectangle behind the submatrix and
                         behind `R`. 27.8% chromatic at threshold 12.
      pale wash          IDG1+2handout_EQ0005 -- a faint blue-grey panel in a
                         sans face. Only 0.4% chromatic even at 12, because a
                         uniform light tint has little per-pixel saturation:
                         it is caught by BACKGROUND LUMINANCE instead (235
                         against a white page's 255).

    Hence two arms. The luminance arm reads the 85th percentile, which is the
    page ground rather than the glyphs. Verified not to fire on genuinely
    white crops: wzlxjtu-095/-024, guide-tables and lie-groups all read
    chroma 0.0%, bg 255.
    """
    if Image is None:
        return False, 0.0, 255
    f = doc / "report-crops" / (ident + ".jpg")
    if not f.exists():
        return False, 0.0, 255
    try:
        im = Image.open(f).convert("RGB")
        w, h = im.size
        px = list(im.resize((min(w, 240), min(h, 70))).getdata())
    except Exception:
        return False, 0.0, 255
    n = len(px) or 1
    chroma = 100.0 * sum(1 for p in px if max(p) - min(p) > 12) / n
    lum = sorted(int(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]) for p in px)
    bg = lum[min(n - 1, int(n * 0.85))]
    return (chroma >= 8.0 or bg <= 244), chroma, bg


def crop_heights(doc: Path, rows) -> dict:
    out = {}
    if Image is None:
        return out
    for r in rows:
        f = doc / "report-crops" / (r["id"] + ".jpg")
        if f.exists():
            try:
                out[r["id"]] = Image.open(f).size[1]
            except Exception:
                pass
    return out


kept, why = [], collections.Counter()
docs = fresh = 0
for ink_path in sorted(glob.glob(str(LIB / "*" / "report.ink.json"))):
    ink = Path(ink_path)
    doc = ink.parent
    if doc.name in SKIP:
        continue
    docs += 1
    if os.path.getmtime(ink) < CUT:
        why["document not re-measured since the escaper"] += 1
        continue
    fresh += 1
    try:
        rows = json.loads(ink.read_text()).get("rows", [])
    except (OSError, ValueError):
        why["unreadable ink"] += 1
        continue
    conf = confidences(doc / "report.tex")
    hs = crop_heights(doc, rows)
    med = statistics.median(hs.values()) if len(hs) >= 5 else None
    for r in rows:
        if r.get("flag") != "component":
            continue
        L, R, sd = r.get("L"), r.get("R"), r.get("signed_delta", 0)
        if not L or not R:
            continue
        if sd <= 0:
            why["2 negative delta (our rendering denser; AA artefact)"] += 1
            continue
        if L == [13, 6, 0, 0, 0] or L[0] <= 5:
            why["3 our cell blank/demoted"] += 1
            continue
        if R[0] / max(1, L[0]) >= 2.5:
            why["4 our cell shrunk by FitMath (ratio >= 2.5x)"] += 1
            continue
        h = hs.get(r["id"])
        if med and h and h / med >= 2.0:
            why["5 multi-line crop (>= 2x the document median)"] += 1
            continue
        # 6. a COLOURED, SHADED or TINTED scan against our plain black
        # rendering -- see `tinted`. Three candidates were checked by eye and
        # all three show the SAME mathematics term for term; the delta is the
        # decoration. It removed 12 of the top 20.
        is_tinted, chroma, bg = tinted(doc, r["id"])
        if is_tinted:
            why["6 coloured/shaded/tinted scan crop"] += 1
            continue
        cf = conf.get(r["id"])
        if cf is not None and cf < A.min_conf:
            why["below --min-conf"] += 1
            continue
        kept.append({"document": doc.name, "id": r["id"], "code": r.get("code"),
                     "delta": sd, "conf": cf, "L": L, "R": R,
                     "crop_h": h, "median_h": med,
                     "page": r.get("page"), "report_page": r.get("report_page")})

kept.sort(key=lambda k: -k["delta"])
hdr = ["document", "identifier", "ink", "signed_delta", "mathpix_conf",
       "L_five_tuple", "R_five_tuple", "crop_h", "doc_median_crop_h", "page"]
lines = ["\t".join(hdr)]
for k in kept:
    lines.append("\t".join(str(x) for x in (
        k["document"], k["id"], k["code"], k["delta"],
        "" if k["conf"] is None else k["conf"],
        k["L"], k["R"], k["crop_h"] or "", int(k["median_h"] or 0), k["page"])))
Path(A.out).write_text("\n".join(lines) + "\n", encoding="utf-8")

print("documents scanned %d, re-measured since %s: %d" % (docs, A.since, fresh))
print("candidates kept: %d across %d documents" % (len(kept), len(set(k["document"] for k in kept))))
print()
print("excluded, by reason:")
for reason, n in sorted(why.items()):
    print("   %-52s %5d" % (reason, n))
print()
withc = [k for k in kept if k["conf"] is not None]
hi = [k for k in withc if k["conf"] >= 0.90]
print("with a MathPix confidence: %d   of those conf >= 0.90: %d" % (len(withc), len(hi)))
print()
print("%-34s %-24s %-8s %-6s %s" % ("document", "row", "ink", "conf", "L -> R components"))
for k in kept[:25]:
    print("%-34s %-24s %-8s %-6s %s -> %s"
          % (k["document"][:34], k["id"][-22:], k["code"],
             "" if k["conf"] is None else k["conf"], k["L"][0], k["R"][0]))
print()
print("wrote %s" % A.out)
print()
print("THE TOP ROWS STILL NEED EYES: wzlxjtu-095_EQ0001 (+39) and _EQ0003 (+16)")
print("survive every filter and are TYPOGRAPHY -- same mathematics, different")
print("spacing. A five-tuple cannot tell those apart from a dropped symbol.")
