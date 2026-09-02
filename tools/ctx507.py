#!/usr/bin/env python3
r"""507 — 487 measured on 448's six rows, with and without document context.

Same six johnston rows as 444 and 448, so the comparison joins to prior
results. Two arms over the SAME crops:

  A  revise-region            448's prompt: the crop and the existing reading
  B  revise-region-context    the same, plus the document context 487 adds

Every call is logged through 447's call log with the prompt file and its
hash (466), so which prompt produced which reply is a fact rather than a
recollection.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import callog, prompts, refine as rf, reccontext as rc   # noqa
from pdfdrill import sectionpath as sp                                  # noqa
from pdfdrill.docinspect import build_stream_index, object_geometry     # noqa

DOC = Path.home() / "pdfdrill-library" / \
    "Introduction to Linear and Matrix Algebra (Nathaniel Johnston) (Z-Library)"
SYSTEM = prompts.load("refine-propose-system")


def rows():
    tids = json.loads(next(DOC.glob("*.tiddlers.json"))
                      .read_text(encoding="utf-8", errors="replace"))
    tids = tids.get("tiddlers", tids) if isinstance(tids, dict) else tids
    by = {x.get("title", ""): x for x in tids}
    model = json.loads((DOC / "model.docmodel.json")
                       .read_text(encoding="utf-8", errors="replace"))
    sidx = build_stream_index(model)
    geo = {}
    for o in model["objects"]:
        if o["type"] not in ("Equation", "Formula"):
            continue
        pg, bb, _ = object_geometry(o, sidx)
        if pg is None or not bb:
            continue
        geo[(int(pg), int(round(bb["x"])), int(round(bb["y"])))] = o["id"]
    pdf = [p for p in DOC.glob("*.pdf") if not p.name.startswith("report")][0]
    table = sp.build(pdf, DOC / "model.docmodel.json")
    out = []
    for r in json.loads(Path("out/448.json").read_text()):
        short = r.get("short")
        full = next((k for k in by if k.endswith("_" + short)), None)
        x = by.get(full or "", {})
        key = None
        try:
            key = (int(x["page"]), int(x["top_left_x"]), int(x["top_left_y"]))
        except (KeyError, TypeError, ValueError):
            pass
        oid = geo.get(key) if key else None
        path = sp.path_for(table, int(x["page"])) if str(x.get("page") or "").isdigit() else None
        out.append({"short": short, "title": full, "latex": x.get("latex") or "",
                    "conf": x.get("confidence"), "page": x.get("page"),
                    "obj_id": oid,
                    "grade": (path or {}).get("granularity", "none"),
                    "crop": str(DOC / "report-crops" / ((full or "") + ".jpg"))})
    return out


def run():
    run_id = callog.open_run(DOC, "ctx507", note="487 measured on 448's six rows")
    rf.set_call_log(DOC, run_id)
    res = []
    for r in rows():
        crop = r["crop"] if Path(r["crop"]).is_file() else None
        ctx = rc.build(DOC, r["obj_id"], page=r["page"], k=3) if r["obj_id"] else {}
        block = rc.render(ctx)
        for arm, name in (("A_plain", "revise-region"),
                          ("B_context", "revise-region-context")):
            body = (prompts.load(name)
                    .replace("{conf}", str(r["conf"] or 0.0))
                    .replace("{latex}", r["latex"]))
            body = body.replace("{context}", block if arm == "B_context" else "")
            t0 = time.time()
            txt, finish, err = rf._novita_chat(
                body, system=SYSTEM, model=rf.NOVITA_MODEL,
                max_tokens=rf.PROPOSE_MAX_TOKENS, timeout=600, crop=crop,
                subject=r["short"], arm=arm, prompt_name=name)
            res.append({"short": r["short"], "grade": r["grade"], "arm": arm,
                        "prompt": name, "seconds": round(time.time() - t0, 1),
                        "finish": finish, "error": err,
                        "context_chars": len(block) if arm == "B_context" else 0,
                        "context_fields": sorted(ctx) if arm == "B_context" else [],
                        "before": r["latex"],
                        "after": (txt or "").strip()})
            print("  %-16s %-9s %-9s %5.0fs  %s"
                  % (r["short"], r["grade"], arm, res[-1]["seconds"],
                     (err or (txt or "")[:60].replace("\n", " "))), flush=True)
            json.dump(res, open("out/507.json", "w"), indent=1, ensure_ascii=False)
    callog.close_run(DOC, run_id, calls=len(res))
    print("run_id:", run_id)


if __name__ == "__main__":
    run()
