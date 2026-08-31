#!/usr/bin/env python3
"""407 — does the CELL route give the same class as the PAGE route?

The page route builds the report, rasterises each page at 300 and 600 dpi and
compares the two image columns as they were typeset. It costs ~4.6 s a page
and forces the two-phase build, because the class is not known until the page
exists.

The cell route compares the SAME two things one step earlier: a standalone
render of the row's LaTeX against the row's scan crop, before any report is
built. If the classes agree, the class is known before the first compile —
the second build, the phase stamp and `--no-legend` all stop being necessary,
and 382's 521 pairs/min replaces ~6 rows/min.

340 is the reason to doubt it: the in-table cells are 102 mm and 122 mm wide,
so the page route already compares two DIFFERENTLY SCALED pictures, and a
standalone render is a third scale again. This measures whether that moves
the class, not whether it moves the distance.
"""
import argparse
import collections
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(pathlib.Path.home() / "inkdrill"))
from pdfdrill import region_standalone as rs                   # noqa: E402
from pdfdrill import latex_source as ls                        # noqa: E402
from pdfdrill.inkconvert import flag_of                        # noqa: E402
from inkdrill.pngio import read_png, auto_mask                 # noqa: E402
from inkdrill.mathstruct import pair_stats                     # noqa: E402

KEYS = ("components", "holes", "stacked", "centred", "offset")


def five(png):
    img = read_png(png)
    m, _ = auto_mask(img.gray, img.width, img.height, 200)
    d = pair_stats(m)
    return [d[k] for k in KEYS]


def to_png(src: pathlib.Path, dst: pathlib.Path) -> bool:
    """Crops are JPEG; inkdrill reads ghostscript png16m only."""
    import subprocess
    subprocess.run(["magick", str(src), "-background", "white",
                    "-alpha", "remove", "-alpha", "off", "PNG24:" + str(dst)],
                   capture_output=True)
    return dst.is_file()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=str(pathlib.Path.home() /
                                         "pdfdrill-library" / "chung2019combinatorics"))
    ap.add_argument("--rows", type=int, default=50)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--out", default=str(ROOT / "out" / "407.json"))
    a = ap.parse_args()
    d = pathlib.Path(a.doc)
    ink = {r["id"]: r for r in json.loads((d / "report.ink.json").read_text())["rows"]}
    model = json.loads((d / "model.docmodel.json").read_text())
    bibkey = model["meta"]["bibkey"]
    eqs = [o for o in model["objects"] if o.get("type") == "Equation"]

    # identifier order is the report's table order, which is what ink.json keys
    ids = sorted(ink)
    work = pathlib.Path("/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/"
                        "ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da/scratchpad/w407")
    work.mkdir(parents=True, exist_ok=True)
    crops = d / "report-crops"

    # the author's preamble, expanded — 286: reading the root file alone got
    # 29 of 52 where expand_inputs got 46.
    pre = ""
    try:
        texs = sorted((d / "texsrc").rglob("*.tex")) if (d / "texsrc").is_dir() else []
        root_tex = next((t for t in texs
                         if "\\documentclass" in t.read_text(errors="replace")[:4000]), None)
        if root_tex:
            pre = ls.standalone_preamble(ls.expand_inputs(str(root_tex), str(d / "texsrc")))
    except Exception:
        pre = ""

    by_id = {}
    for o in eqs:
        p = o.get("props") or {}
        by_id.setdefault(p.get("bibkey_ident") or "", o)
    # the model does not carry the report identifier, so pair by table order
    order = [o for o in eqs]
    rows, t0 = [], time.time()
    for i, ident in enumerate(ids[:a.rows]):
        rec = {"id": ident, "page_flag": ink[ident]["flag"],
               "page_distance": ink[ident]["distance"]}
        n = int(ident.rsplit("EQ", 1)[-1]) - 1
        o = order[n] if 0 <= n < len(order) else None
        latex = ((o.get("props") or {}).get("latex") or "") if o else ""
        crop = crops / ("%s.jpg" % ident)
        if not latex.strip():
            rec["cell"] = "no latex"
        elif not crop.is_file():
            rec["cell"] = "no crop"
        else:
            png, err = rs.render(ident, latex, work, dpi=a.dpi,
                                 author_preamble=pre)
            if png is None:
                rec["cell"] = "did not compile"
                rec["error"] = (err or "")[:120]
            else:
                cpng = work / ("%s_crop.png" % ident)
                if not to_png(crop, cpng):
                    rec["cell"] = "crop unreadable"
                else:
                    L, R = five(pathlib.Path(png)), five(cpng)
                    dist = sum(abs(x - y) for x, y in zip(L, R))
                    cd = abs(L[0] - R[0])
                    # A_eq_B, the cell route's own. The page route gets
                    # `stable` from the SAME cell rasterised at 300 and 600
                    # agreeing; without an equivalent the cell route cannot
                    # produce that class at all, and comparing the two would
                    # be scoring my omission rather than the route. So render
                    # the region at a second resolution and ask the same
                    # question.
                    png2, _e2 = rs.render(ident + "_x2", latex, work,
                                          dpi=a.dpi * 2,
                                          author_preamble=pre)
                    stable = False
                    if png2 is not None:
                        stable = (five(pathlib.Path(png2)) == L)
                    rec.update(cell="measured", cell_distance=dist,
                               cell_comp_delta=cd, cell_a_eq_b=stable,
                               cell_flag=flag_of(dist, cd, stable),
                               L=L, R=R)
        rows.append(rec)
        if (i + 1) % 10 == 0:
            print("  ... %d/%d  %.0fs" % (i + 1, min(a.rows, len(ids)),
                                          time.time() - t0), flush=True)
    pathlib.Path(a.out).write_text(json.dumps(
        {"doc": str(d), "bibkey": bibkey, "dpi": a.dpi, "rows": rows}, indent=1))
    ok = [r for r in rows if r.get("cell") == "measured"]
    print("\n  rows attempted %d, measured %d" % (len(rows), len(ok)))
    print("  outcomes: %s" % dict(collections.Counter(r["cell"] for r in rows)))
    if ok:
        agree = sum(1 for r in ok if r["cell_flag"] == r["page_flag"])
        print("  SAME CLASS as the page route: %d of %d (%.1f%%)"
              % (agree, len(ok), 100 * agree / len(ok)))
        cm = collections.Counter((r["page_flag"], r["cell_flag"]) for r in ok)
        print("  page -> cell:")
        for (p, c), n in cm.most_common():
            print("    %-11s -> %-11s %3d%s" % (p, c, n, "" if p == c else "   <-- moved"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
