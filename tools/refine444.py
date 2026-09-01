#!/usr/bin/env python3
"""444 — repair the last unrendered rows, WITH and WITHOUT the error message.

The measurement is the point. 113 established variant C — the crop plus
MathPix's own reading — and warned that a run without the crop "is not variant
C, it is a fourth thing nobody measured". So the control here is variant C
exactly as refine sends it, and the treatment is variant C plus one added
line: the compile error or the gate's rejection reason. That isolates the
error message and nothing else.

Validated and ink-gated as refine does: the proposal must be `renderable`, must
compile, and must move the ink CLOSER to the scan than the original reading.
Recorded with basis "inferred".
"""
import argparse, json, pathlib, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import refine as rf                              # noqa: E402
from pdfdrill import report_tex as rt                          # noqa: E402
from pdfdrill import callog                                    # noqa: E402

ERR_LINE = """
The previous attempt to typeset that reading FAILED. The exact reason was:

  {err}

Fix what that names. Do not restructure anything the error does not mention.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="Introduction to Linear and Matrix Algebra "
                                     "(Nathaniel Johnston) (Z-Library)")
    ap.add_argument("--out", default=str(ROOT / "out" / "444.json"))
    a = ap.parse_args()
    D = pathlib.Path.home() / "pdfdrill-library" / a.doc
    rows = json.loads((ROOT / "out" / "444.rows.json").read_text())
    w = pathlib.Path(tempfile.mkdtemp(prefix="refine444-"))
    # 447 — the evidence goes BESIDE THE DOCUMENT before a single paid call.
    run_id = callog.open_run(D, "refine444",
                             script=str(pathlib.Path(__file__).resolve()),
                             note="with vs without the compile error")
    rf.set_call_log(D, run_id)
    print("  run %s" % run_id, flush=True)
    out = []
    for i, r in enumerate(rows, 1):
        rec = dict(r)
        crop = D / "report-crops" / ("%s.jpg" % r["title"])
        crop = crop if crop.is_file() else None
        # the reference: the ink of the SCAN, and of MathPix's own reading
        ref = {}
        try:
            if crop:
                png = w / ("%s_scan.png" % r["title"][-8:])
                import subprocess
                subprocess.run(["magick", str(crop), "-background", "white",
                                "-alpha", "remove", "PNG24:" + str(png)],
                               capture_output=True)
                ref = rf.ink_signature(png) if png.is_file() else {}
        except Exception as e:
            rec["ref_error"] = "%s: %s" % (type(e).__name__, e)
        base_png, base_err = rf.render_latex(r["latex"], w / ("%s_base.png" % i))
        base_sig = rf.ink_signature(base_png) if base_png else {}
        rec["ink_before"] = (rf.ink_distance(base_sig, ref)
                             if base_sig and ref else None)
        for arm in ("with_error", "without_error"):
            prompt_extra = ERR_LINE.format(err=r["reason"]) if arm == "with_error" else ""
            t0 = time.time()
            try:
                prop, err = rf.propose_one(
                    r["latex"] + prompt_extra, r.get("conf") or 0.0,
                    crop=crop, timeout=600,
                    subject=r["short"], arm=arm)
            except Exception as e:
                prop, err = "", "%s: %s" % (type(e).__name__, e)
            d = {"seconds": round(time.time() - t0, 1), "error": err,
                 "proposed": (prop or "")[:4000]}
            if not (prop or "").strip():
                d["outcome"] = "no proposal"
            elif not rt.renderable(prop):
                d["outcome"] = "rejected: renderable() refuses it"
            else:
                png, cerr = rf.render_latex(prop, w / ("%s_%s.png" % (i, arm)))
                if png is None:
                    d["outcome"] = "rejected: does not compile"
                    d["compile_error"] = cerr[:120]
                else:
                    sig = rf.ink_signature(png)
                    d["ink_after"] = rf.ink_distance(sig, ref) if ref else None
                    if not ref:
                        d["outcome"] = "cannot gate: no scan reference"
                    elif rec["ink_before"] is None:
                        d["outcome"] = ("accepted: original did not render, "
                                        "proposal does")
                    elif d["ink_after"] < rec["ink_before"]:
                        d["outcome"] = "accepted: ink falls"
                    else:
                        d["outcome"] = "rejected: ink does not fall"
            rec[arm] = d
            print("  %d %-14s %-14s %s" % (i, r["title"][-12:], arm,
                                           d.get("outcome")), flush=True)
        out.append(rec)
        pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    acc = sum(1 for r in out for k in ("with_error", "without_error")
              if str(r.get(k, {}).get("outcome", "")).startswith("accepted"))
    log = callog.close_run(D, run_id, calls=2 * len(out),
                           outcome="%d accepted of %d" % (acc, 2 * len(out)))
    print("wrote %s" % a.out)
    print("evidence %s" % log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
