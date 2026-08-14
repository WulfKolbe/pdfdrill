#!/usr/bin/env python3
r"""Measure the floor: the born-digital text layer scored against gold LaTeX.

    python3 tools/mathgold_floor.py <model.docmodel.json> [...] --out DIR

Emits one `.lg` pair per gold equation, invokes LgEval on each (see
`tools/lgeval_env.sh` — LgEval is INVOKED, not vendored, and must be at the
pinned commit), and prints the aggregate.

A gold equation is one carrying a Realization with `provenance == "tex"` — the
author's own e-print LaTeX, overlaid by `pdfdrill injectlatex` — AND both
`props["region"]` and `props["page"]`, without which there is no rectangle to
read characters out of and the equation cannot be scored at all.

Two rows are reported and neither is the headline:
  single   equations with no environment — the floor's floor
  all      every gold equation, environments held out as Unresolved
Splitting an `align` block into rows to enlarge the denominator discards the
alignment structure, so it is not done.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mathgold.floor import chars_in_box, chars_to_slt, lg_pair, region_box  # noqa: E402
from mathgold.slt import parse_latex_slt  # noqa: E402

LGEVAL_HOME = Path(os.environ.get("LGEVAL_HOME", Path.home() / ".local/share/lgeval"))
LGEVAL_PIN = "9831a3c"


def gold_equations(model: dict) -> list[dict]:
    out = []
    for o in model.get("objects", []):
        if o.get("type") != "Equation":
            continue
        tex = [r for r in o.get("realizations", []) if r.get("provenance") == "tex"]
        if not tex:
            continue
        p = o.get("props", {})
        if not (p.get("region") and p.get("page")):
            continue
        latex = tex[0].get("props", {}).get("latex") or ""
        if not latex.strip():
            continue
        out.append({"obj": o, "latex": latex, "page": p["page"],
                    "region": p["region"], "refnum": p.get("refnum") or ""})
    return out


def run_lgeval(out_lg: Path, gold_lg: Path) -> dict:
    """One pair through LgEval. Returns the metric row as a dict."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(LGEVAL_HOME.parent) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-m", "lgeval.src.evallg",
                           str(out_lg), str(gold_lg)],
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return {"_error": (proc.stderr or "").strip().splitlines()[-1:] or ["failed"]}
    line = (proc.stdout or "").splitlines()
    if not line:
        return {"_error": ["no output"]}
    parts = [p.strip() for p in line[0].split(",")]
    row = {}
    for i in range(0, len(parts) - 1, 2):
        try:
            row[parts[i]] = float(parts[i + 1])
        except ValueError:
            row[parts[i]] = parts[i + 1]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", default="floor-lg")
    ap.add_argument("--no-score", action="store_true",
                    help="emit the .lg pairs but do not invoke LgEval")
    args = ap.parse_args()

    at = subprocess.run(["git", "-C", str(LGEVAL_HOME), "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
    if not args.no_score and at != LGEVAL_PIN:
        print(f"LgEval at {at or '<absent>'}, expected pinned {LGEVAL_PIN} — "
              f"see tools/lgeval_env.sh", file=sys.stderr)
        return 2

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    import pdfplumber

    rows = []
    for mp in args.models:
        mpath = Path(mp)
        model = json.loads(mpath.read_text())
        bibkey = model.get("meta", {}).get("bibkey") or mpath.parent.name
        dims = {p["page"]: (p["page_width"], p["page_height"])
                for p in model.get("meta", {}).get("pages", [])}
        pdfs = sorted(mpath.parent.glob("*.pdf"))
        pdfs = [p for p in pdfs if p.stem == bibkey] or pdfs
        if not pdfs:
            print(f"  {bibkey}: no PDF beside the model — skipped", file=sys.stderr)
            continue
        eqs = gold_equations(model)
        print(f"{bibkey}: {len(eqs)} gold equations, pdf={pdfs[0].name}")

        with pdfplumber.open(pdfs[0]) as pdf:
            for k, eq in enumerate(eqs):
                pg = eq["page"]
                if pg not in dims or pg > len(pdf.pages):
                    rows.append({"doc": bibkey, "k": k, "skip": "no page dims"})
                    continue
                page = pdf.pages[pg - 1]
                box = region_box(eq["region"], dims[pg], (page.width, page.height))
                chars = chars_in_box(page.chars, box)
                try:
                    gold = parse_latex_slt(eq["latex"])
                except ValueError as exc:
                    rows.append({"doc": bibkey, "k": k, "skip": f"parse: {exc}"})
                    continue
                floor = chars_to_slt(chars)
                gold_lg, floor_lg, stats = lg_pair(gold, floor)
                gpath = outdir / f"{bibkey}_{k:03d}.gold.lg"
                fpath = outdir / f"{bibkey}_{k:03d}.floor.lg"
                gpath.write_text(gold_lg)
                fpath.write_text(floor_lg)
                row = {"doc": bibkey, "k": k, "refnum": eq["refnum"],
                       "env": "\\begin{" in eq["latex"], **stats}
                if not args.no_score:
                    row["lg"] = run_lgeval(fpath, gpath)
                rows.append(row)

    (outdir / "rows.json").write_text(json.dumps(rows, indent=1, default=str))
    report(rows)
    return 0


def _agg(rows: list[dict], label: str) -> None:
    scored = [r for r in rows if "lg" in r and "_error" not in r["lg"]]
    if not scored:
        print(f"  {label:8s} no scored equations")
        return
    gold_nodes = sum(r["gold_nodes"] for r in scored)
    floor_nodes = sum(r["floor_nodes"] for r in scored)
    matched = sum(r["matched"] for r in scored)
    no_ink = sum(r["no_ink"] for r in scored)
    rel_gold = sum(r["lg"].get("nSegRelEdges", 0) for r in scored)
    rel_ok = sum(r["lg"].get("CorrectSegRels", 0) for r in scored)
    struct = sum(1 for r in scored if r["lg"].get("hasCorrectStructure") == 1.0)
    print(f"  {label:8s} n={len(scored):3d}"
          f"  symbol recall {matched}/{gold_nodes} = {matched / max(gold_nodes, 1):.3f}"
          f"  precision {matched}/{floor_nodes} = {matched / max(floor_nodes, 1):.3f}")
    print(f"           relations {int(rel_ok)}/{int(rel_gold)} = "
          f"{rel_ok / max(rel_gold, 1):.3f}"
          f"   expressions fully correct {struct}/{len(scored)} = "
          f"{struct / len(scored):.3f}"
          f"   gold nodes with no ink: {no_ink}")


def report(rows: list[dict]) -> None:
    skipped = [r for r in rows if "skip" in r]
    scored = [r for r in rows if "skip" not in r]
    print()
    print("THE FLOOR — pdfminer text layer vs author LaTeX, scored by LgEval")
    print(f"  population {len(rows)} gold equations; "
          f"{len(skipped)} not scorable ({len(scored)} scored)")
    for r in skipped:
        print(f"    - {r['doc']} #{r['k']}: {r['skip']}")
    _agg([r for r in scored if not r.get("env")], "single")
    _agg(scored, "all")
    unmapped: dict[str, int] = {}
    for r in scored:
        for c in r.get("unmapped", []):
            unmapped[c] = unmapped.get(c, 0) + 1
    if unmapped:
        top = sorted(unmapped.items(), key=lambda kv: -kv[1])[:12]
        print("  vocabulary gap (gold commands with no single emitted codepoint):")
        print("    " + "  ".join(f"{c}×{n}" for c, n in top))


if __name__ == "__main__":
    raise SystemExit(main())
