#!/usr/bin/env python3
"""375 — a one-sentence summary of each TikZ picture, for the fourth column.

The prompt asks for a KIND from a closed list and then the dominant elements,
rather than free prose, so the sentences are comparable across rows: a column
of a hundred different opinions about what "describe this" means is not a
column, it is a hundred paragraphs.

The reply is GENERATED, never measured, and the report marks it as such.
"""
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import refine as rf                          # noqa: E402

FIX = pathlib.Path.home() / "pdfdrill-library" / "datikz-fixture"

KINDS = ("plot", "commutative diagram", "graph or network", "geometric figure",
         "circuit", "tree", "flowchart", "table-like grid", "illustration",
         "other")

SYSTEM = "You describe scientific figures from their TikZ source. One sentence."

PROMPT = """Summarise this TikZ picture in one sentence, under 20 words.
State the kind — one of: plot, commutative diagram, graph or network, geometric figure, circuit, tree, flowchart, table-like grid, illustration, other.
Then the elements that dominate it — axes, nodes, arrows, curves, labels, shading, coordinates.
Describe what is drawn. Do not describe the code, do not name TikZ libraries, do not begin with "This figure".

%s"""

#: names that mean the reply talked about the CODE rather than the picture
LIBRARIES = ("tikz", "pgfplots", "pgf", "usetikzlibrary", "\\draw", "\\node",
             "latex", "arrows.meta", "positioning", "calc", "decorations",
             "matrix", "shapes", "patterns")


def classify(text: str):
    """(kind, violations) — the kind it named, and where it broke the brief."""
    low = (text or "").strip().lower()
    kind = next((k for k in sorted(KINDS, key=len, reverse=True) if k in low),
                None)
    bad = []
    words = len(re.findall(r"\S+", text or ""))
    if words > 20:
        bad.append("over 20 words (%d)" % words)
    if any(l in low for l in LIBRARIES):
        bad.append("named a library or command")
    if low.startswith("this figure"):
        bad.append('began "This figure"')
    if kind is None:
        bad.append("named no kind from the list")
    return kind, bad


def main() -> int:
    man = json.loads((FIX / "manifest.json").read_text())
    out_path = ROOT / "out" / "375.json"
    done = {}
    if out_path.is_file():
        done = {r["id"]: r for r in json.loads(out_path.read_text())["rows"]}
    rows = []
    for i, r in enumerate(man["rows"], 1):
        rid = r["id"]
        if rid in done and done[rid].get("summary"):
            rows.append(done[rid]); continue
        code = (FIX / r["tex"]).read_text(errors="replace")
        t0 = time.time()
        txt, fin, err = rf._novita_chat(
            PROMPT % code[:6000], system=SYSTEM, model=rf.NOVITA_MODEL,
            # 16,000: minimax-m3 spends completion tokens reasoning before it
            # emits a character, and 4,000 returned an empty string with
            # finish_reason=length — a budget, not a refusal (337).
            max_tokens=16000, timeout=300)
        summary = re.sub(r"\s+", " ", (txt or "").strip())
        kind, bad = classify(summary)
        rows.append({"id": rid, "summary": summary, "kind": kind,
                     "violations": bad, "finish": fin, "api_error": err,
                     "seconds": round(time.time() - t0, 1)})
        print("  [%3d/%3d] %-10s %-20s %s"
              % (i, len(man["rows"]), rid, kind or "-",
                 ("; ".join(bad))[:44] or "ok"), flush=True)
        out_path.write_text(json.dumps({"rows": rows}, indent=1,
                                       ensure_ascii=False))
    out_path.write_text(json.dumps({"rows": rows}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
