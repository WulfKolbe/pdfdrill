#!/usr/bin/env python3
"""378 — measure the DTZ report's last two columns with inkdrill.

BOTH COLUMNS ARE RENDERS OF THE SAME CODE. This is a renderer-versus-renderer
FLOOR: any distance is our LaTeX installation differing from the dataset's —
fonts, tikz library versions, pgfplots compat — never a transcription error.
It is the number 281 needs before "this recovered figure matches" can mean
anything.

The 320 cross-check is done first and it caught a real defect: the report
declared 6 columns and inkdrill's lattice read 5, because the table overflowed
the page and the last column's right rule was clipped at the paper edge. A
clipped rule is not a column boundary, so inkdrill was reporting what was
there. Narrowing the columns produced 7 rules and the two views now agree.
"""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import regionink as ri                       # noqa: E402
from pdfdrill.inkconvert import flag_of, NOISE_DISTANCE, NOISE_COMP_DELTA  # noqa: E402

FIX = pathlib.Path.home() / "pdfdrill-library" / "datikz-fixture"
WORK = FIX / "inkwork"


def main() -> int:
    rep = FIX / "report.pdf"
    sel = ri.reportpages_json(rep, columns=6, table=1, header="every", timeout=1800)
    pages = sel.get("pages") or []
    per = {int(k): len(v) for k, v in (sel.get("rows") or {}).items()}
    print("  %d pages, %d rows detected" % (len(pages), sum(per.values())), flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    out, t0 = [], time.time()
    for i, pg in enumerate(pages, 1):
        a = ri._render(rep, pg, 300, WORK)
        b = ri._render(rep, pg, 600, WORK)
        rows = ri.compare_page(a, b, pg, 1800)
        want = per.get(pg, 0)
        # compare has no header rule and returns it as data; the legend is
        # emitted as \endfoot/\endlastfoot and repeats per page (322).
        if len(rows) == want + 1:
            rows = rows[1:]
        if rows:
            rows = rows[:-1]                      # the legend footer
        out.extend(rows)
        if i % 5 == 0:
            print("  ... %d/%d pages, %d rows, %.0fs"
                  % (i, len(pages), len(out), time.time() - t0), flush=True)
    recs = []
    for r in out:
        d = sum(abs(x - y) for x, y in zip(r["L"], r["R"]))
        cd = abs(r["L"][0] - r["R"][0])
        recs.append({"page": r["page"], "line": r["line"], "L": r["L"],
                     "R": r["R"], "distance": d, "comp_delta": cd,
                     "flag": flag_of(d, cd, bool(r.get("a_eq_b")))})
    (ROOT / "out" / "378.json").write_text(json.dumps({"rows": recs}, indent=1))
    print("measured %d rows" % len(recs), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
