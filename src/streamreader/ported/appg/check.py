# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# pdf2mmd2: featjudge's tools/appg_forward_check.py (psred origin/master 56cf8f6)
# on pdf2mmd2's own glyph reading instead of featjudge's synth.extract.
"""Appendix G Rule 18 forward, with TeX's true inputs, against the baselines
pdf2mmd2's glyph reader reports (T-0036).

    pdf2mmd2-appg-check [--jobs N] [--cache DIR] SAMPLE...

SAMPLE is `roundtrip` (psred's 100 formulas, tests/fixtures/psred) or
`vol01:OFFSET` (every 15th row of MathPix volume 1 from OFFSET: featjudge's
dev sample is 0, its test sample 7).

Per formula: texroles builds it (TeX's styles, nucleus kinds, relations);
`glyphs.read_pages` reads the coloured PDF; each of our glyphs gets TeX's id
(`rt_run._ids`). Per script relation, the inputs all come from TeX: the
atom's style C (fstyle), the nucleus kind, the script character's TFM
metrics (by its family and the size of its own style, from the tables in
code). Observed: the baseline difference of script and base glyph as our
reader reports them, in bp. Scope as featjudge F37: a character nucleus
whose script groups are single characters without scripts of their own;
everything else is counted as skipped, by kind.

Volume 1 is rows 0..4463 of eqlists/corpus-display-mathpix.eqlist.json
(MathPix's LaTeX, display rows): the one document boundary between 4462 and
4470 rows, the bounds featjudge's two samples of 298 rows each allow; all
120 formulas of featjudge's mathpix-vol01-relcompare120 lie inside it.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import PT_TO_BP, forward as F, inverse as I, params

STEP = 15
VOL01_ROWS = 4464
EQLIST = (Path.home() / "pdfdrill-library" / "eqlists"
          / "corpus-display-mathpix.eqlist.json")
ROUNDTRIP = (Path(__file__).resolve().parents[4] / "tests" / "fixtures"
             / "psred" / "roundtrip_sample.json")


def sample(name: str) -> list[str]:
    if name == "roundtrip":
        return [f["latex"] for f in
                json.loads(ROUNDTRIP.read_text())["formulas"]]
    if name.startswith("vol01:"):
        rows = json.loads(EQLIST.read_text())["rows"][:VOL01_ROWS]
        rows = [r for r in rows if r.get("kind") == "display" and r.get("latex")]
        return [r["latex"] for r in rows[int(name[6:])::STEP]]
    raise SystemExit(f"unknown sample {name}")


def record(latex: str, workdir: str) -> dict:
    """What scoring needs, from TeX and from our reader."""
    from ... import glyphs
    from .. import adapter, rt_run, texroles as TR
    rec: dict = dict(latex=latex)
    try:
        r = TR.build(latex, workdir)
    except Exception as e:                               # noqa: BLE001
        rec.update(stage="no pdf", error=str(e)[:200])
        return rec
    pg = list(glyphs.read_pages(Path(r["pdf"]), 1, 1, ink=True))[0]
    gl = adapter.encoding_glyphs(pg.glyphs, pg.height)
    rec.update(stage="ok", layout_identical=r["layout_identical"],
               glyphs=[dict(name=g["name"], x0=g["x0"], base=g["base"],
                            size=g["size"], glyph=g["glyph"]) for g in gl],
               ids=rt_run._ids(gl, r["glyphs"]),
               roles={str(k): v for k, v in r["roles"].items()},
               truth=r["truth"])
    return rec


def _job(args):
    key, latex, cache = args
    path = Path(cache) / f"{key}.json"
    if path.exists():
        return key, json.loads(path.read_text())
    with tempfile.TemporaryDirectory() as d:
        rec = record(latex, d)
    path.write_text(json.dumps(rec))
    return key, rec


def chars(P: dict, fam: int, size: str) -> dict | None:
    """TFM metrics (wd, ht, dp, ic) pt by code of family `fam` at `size`,
    from the font tables in code."""
    font = P["fonts"].get(f"{fam}/{size}")
    if font is None:
        return None
    f = I._tfm(font, round(P["sizes"][size], 2))
    if f is None:
        return None
    return {c: (ch.width / 65536, ch.height / 65536, ch.depth / 65536,
                ch.italic / 65536) for c, ch in f.chars.items()}


def score(recs: dict, P: dict) -> tuple[list[dict], collections.Counter]:
    skip: collections.Counter = collections.Counter()
    rows = []
    for key, v in recs.items():
        if v["stage"] != "ok":
            skip["no pdf"] += 1
            continue
        if not v["layout_identical"]:
            skip["layout changed by colouring"] += 1
            continue
        gl, roles = v["glyphs"], {int(i): r for i, r in v["roles"].items()}
        idx = {i: k for k, i in enumerate(v["ids"]) if i}
        groups = collections.defaultdict(list)
        for i, r in roles.items():
            rel = r["role"][3:] if r["role"].startswith("in-") else r["role"]
            if rel in ("sup", "sub") and r["base"] is not None:
                groups[(r["base"], rel)].append(i)
        for t in v["truth"]:
            if t["rel"] not in ("sup", "sub"):
                continue
            b, s = t["base"], t["script"]
            rb = roles[b]
            if rb.get("nuc") != "char":
                skip[f"nucleus {rb.get('nuc')}"] += 1
                continue
            mine = groups[(b, t["rel"])]
            other = groups.get((b, "sub" if t["rel"] == "sup" else "sup"), [])
            if len(mine) != 1 or len(other) > 1:
                skip["script group of several chars"] += 1
                continue
            if any(r["base"] in mine + other for r in roles.values()):
                skip["script with scripts of its own"] += 1
                continue
            if b not in idx or s not in idx:
                skip["glyph not read by pdf2mmd2"] += 1
                continue

            def box(i):
                r = roles[i]
                m = (chars(P, r["fam"], F.size(r["fstyle"])) or {}).get(r["char"])
                return None if m is None else dict(h=m[1], d=m[2])
            sup = box(s if t["rel"] == "sup" else other[0]) if (
                t["rel"] == "sup" or other) else None
            sub = box(s if t["rel"] == "sub" else other[0]) if (
                t["rel"] == "sub" or other) else None
            if ((t["rel"] == "sup" and sup is None)
                    or (t["rel"] == "sub" and sub is None)
                    or (other and (sup is None or sub is None))):
                skip["no TFM metrics for the script font"] += 1
                continue
            C = rb["fstyle"]
            pr = F.rule18(dict(char=True, h=0.0, d=0.0), sup, sub, C, P)
            pred = (pr["u"] if t["rel"] == "sup" else pr["v"]) * PT_TO_BP
            a, c = gl[idx[b]], gl[idx[s]]
            obs = (c["base"] - a["base"]) if t["rel"] == "sup" else (
                a["base"] - c["base"])
            rows.append(dict(key=key, rel=t["rel"], C=C,
                             steps="+".join(pr["steps"]), both=bool(other),
                             pred=pred, obs=obs, res=obs - pred,
                             latex=v["latex"][:90]))
    return rows, skip


def report(rows: list[dict], skip: collections.Counter) -> str:
    n = len(rows)
    out = [f"scored {n}   skipped {sum(skip.values())}: "
           + ", ".join(f"{k} {c}" for k, c in skip.most_common())]
    for tol in (0.005, 0.01, 0.03):
        out.append(f"  |obs - pred| <= {tol} bp: "
                   f"{sum(abs(r['res']) <= tol for r in rows)} of {n}")
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["rel"], r["C"], r["steps"])].append(r)
    out.append(f"{'rel':4s} {'C':3s} {'steps':18s} {'n':>5s} {'<=0.01bp':>8s}  max|res|")
    for k in sorted(by, key=lambda k: -len(by[k])):
        rs = by[k]
        out.append(f"{k[0]:4s} {k[1]:3s} {k[2]:18s} {len(rs):5d} "
                   f"{sum(abs(r['res']) <= 0.01 for r in rs):8d}  "
                   f"{max(abs(r['res']) for r in rs):.3f}")
    bad = sorted((r for r in rows if abs(r["res"]) > 0.01),
                 key=lambda r: -abs(r["res"]))
    out.append(f"largest misses ({len(bad)} over 0.01 bp):")
    for r in bad[:12]:
        out.append(f"  {r['rel']} C={r['C']} {r['steps']} pred {r['pred']:.3f} "
                   f"obs {r['obs']:.3f}  {r['key']}  {r['latex']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pdf2mmd2-appg-check",
                                 description=__doc__.split("\n\n")[0])
    ap.add_argument("samples", nargs="+")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--cache", default="out/appg/cache",
                    help="one JSON per formula; reused when present")
    a = ap.parse_args(argv)
    work = []
    for name in a.samples:
        d = Path(a.cache) / name.replace(":", "-")
        d.mkdir(parents=True, exist_ok=True)
        work += [(f"{name.replace(':', '-')}/{k}", latex, a.cache)
                 for k, latex in enumerate(sample(name))]
    with ProcessPoolExecutor(a.jobs) as ex:
        recs = dict(ex.map(_job, work, chunksize=1))
    print(report(*score(recs, params.default())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
