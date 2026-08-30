#!/usr/bin/env python3
"""392 — the CEILING: the recovery prompt where the right answer is known.

A rescued MathPix figure has no reference, so "is this recovery correct" is
unanswerable on it — 281's position. A DaTikZ row has the author's own TikZ,
so the same prompt can be scored twice:

  vs AUTHOR  our compile of the model's reply against our compile of the
             author's code. Same engine, same renderer, same dpi, so a
             difference is the model's drawing and nothing else.
  vs PNG     the reply against the dataset's own 448x448 render. This is the
             looser of the two: 383 already measured our renderer against
             theirs on identical code and it is NOT zero, so this distance
             carries the renderer floor as well as the model's error.

Reporting both is the point. The gap between them is the part of any distance
that is not the model's fault.
"""
import argparse, json, pathlib, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(pathlib.Path.home() / "inkdrill"))
from pdfdrill import refine as rf                              # noqa: E402
from recover_prompt import SYSTEM, PROMPT, wrap                # noqa: E402
from inkdrill.pngio import read_png, auto_mask                 # noqa: E402
from inkdrill.mathstruct import pair_stats                     # noqa: E402

FIX = pathlib.Path.home() / "pdfdrill-library" / "datikz-fixture"
NOISE_DISTANCE, NOISE_COMP_DELTA = 7, 2


def flag_of(distance, comp_delta):
    if distance == 0:
        return "clean"
    if comp_delta > NOISE_COMP_DELTA:
        return "component"
    if distance <= NOISE_DISTANCE:
        return "noise"
    return "weak"


def five(png):
    img = read_png(png)
    m, _ = auto_mask(img.gray, img.width, img.height, 200)
    return pair_stats(m)


def compare(a, b):
    """(distance, comp_delta, flag) — inkdrill's five-tuple L1, as 382 uses."""
    fa, fb = five(a), five(b)
    K = ("components", "holes", "stacked", "centred", "offset")
    la = [fa[k] for k in K]
    lb = [fb[k] for k in K]
    d = sum(abs(x - y) for x, y in zip(la, lb))
    cd = abs(la[0] - lb[0])
    return d, cd, flag_of(d, cd), la, lb


def render(tex_text, work, stem):
    """Compile a document and rasterise it exactly as 365/389 do."""
    import datikz_report as dr
    tex = work / (stem + ".tex")
    tex.write_text(tex_text, encoding="utf-8")
    try:
        return dr.compile_one(tex, work)
    except subprocess.TimeoutExpired:
        return None, "timeout", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--out", default=str(ROOT / "out" / "392.json"))
    a = ap.parse_args()

    man = json.loads((FIX / "manifest.json").read_text())
    built = {r["id"]: r for r in json.loads((ROOT/"out"/"365.json").read_text())["rows"]}
    rows = [r for r in man["rows"]
            if r.get("png") and built.get(r["id"], {}).get("rendered")][:a.rows]
    work = pathlib.Path(tempfile.mkdtemp(prefix="recover392-"))
    out = []
    for i, r in enumerate(rows, 1):
        rid = r["id"]
        png = FIX / r["png"]
        t0 = time.time()
        txt, fin, err = rf._novita_chat(
            PROMPT, system=SYSTEM, model=rf.NOVITA_MODEL,
            max_tokens=a.max_tokens, timeout=a.timeout, crop=[png])
        rec = {"id": rid, "seconds": round(time.time() - t0, 1),
               "finish": fin, "error": err, "reply_chars": len(txt or "")}
        if not (txt or "").strip():
            rec["outcome"] = "empty reply"
            out.append(rec); print("  %2d %s EMPTY finish=%s %s" % (i, rid, fin, err[:50]), flush=True)
            continue
        (work / (rid + ".reply")).write_text(txt, encoding="utf-8")
        got, cerr, engine = render(wrap(txt), work, rid + "_model")
        rec["engine"] = engine
        if got is None:
            rec["outcome"] = "did not compile"
            rec["compile_error"] = cerr
            out.append(rec); print("  %2d %s NOCOMPILE %s" % (i, rid, cerr[:60]), flush=True)
            continue
        rec["outcome"] = "compiled"
        d1, c1, f1, la, lb = compare(got, FIX / built[rid]["rendered"])
        d2, c2, f2, _, lc = compare(got, png)
        rec.update({"vs_author": {"distance": d1, "comp_delta": c1, "flag": f1},
                    "vs_png": {"distance": d2, "comp_delta": c2, "flag": f2},
                    "model_five": la, "author_five": lb, "png_five": lc})
        out.append(rec)
        print("  %2d %s  vs author d=%-5d %-10s | vs png d=%-5d %-10s (%.0fs)"
              % (i, rid, d1, f1, d2, f2, rec["seconds"]), flush=True)
    pathlib.Path(a.out).write_text(json.dumps(
        {"rows": out, "max_tokens": a.max_tokens,
         "model": rf.NOVITA_MODEL}, indent=1), encoding="utf-8")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
