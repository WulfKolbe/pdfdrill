#!/usr/bin/env python3
r"""454 — one controlled pair through the snippet API: same image minus one feature.

THE PAIR. 2103.01507 p205 — the maths side of 453's closest substantial pair
(ink distance 11 over 123 components, against a region MathPix handled as a
graphic). MathPix read it as mathematics at confidence 0.002.

THE MODIFICATION. The upper-left text is the operator name `hocolim` and its
limit subscript `Tw □S VB^C_{sub,class}`. It is masked to white. Nothing else
is touched: same file, same dimensions, same JPEG pipeline, one rectangle
painted over.

WHY TWO CALLS AND NOT ONE. The confidence on the model (0.002) came from a
PAGE process, not a snippet call. Comparing a snippet reading of the modified
crop against a page reading of the original would confound the modification
with the endpoint. Both crops go through the SAME endpoint, so the only
difference between the two readings is the rectangle.

Everything lands beside the document (447): both crops, the mask geometry, the
request as sent, the response in full, and this script copied rather than
referenced.
"""
import argparse, json, pathlib, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import callog                                    # noqa: E402
from pdfdrill import mathpix_snip as ms                        # noqa: E402

CROP = ("https://cdn.mathpix.com/cropped/81ff6df2-2368-4983-80a6-d9be0b85a83d"
        "-205.jpg?height=247&width=960&top_left_y=475&top_left_x=638")
#: The upper-left operator name and its subscript. MEASURED, not eyeballed:
#: `ink_only` on the crop finds 123 components, of which 24 form a cluster with
#: bounding box x 8..234, y 17..78, and the next ink to the right begins at
#: x=241. So this rectangle removes exactly that cluster with three pixels of
#: clearance. Three earlier masks chosen by eye each clipped `C^{*,c}_{rel@}`
#: or left the tail of the subscript behind, which would have made the pair
#: "same image minus one feature and part of another".
MASK = (0, 0, 238, 85)          # x, y, w, h


def classify(resp: dict) -> str:
    """What the response says the region IS, without interpreting it for it."""
    if resp.get("latex_styled") or resp.get("text", "").strip().startswith("\\("):
        return "maths"
    return "text/other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="2103.01507")
    ap.add_argument("--out", default=str(ROOT / "out" / "454.json"))
    a = ap.parse_args()
    D = pathlib.Path.home() / "pdfdrill-library" / a.doc
    run_id = callog.open_run(D, "snip454",
                             script=str(pathlib.Path(__file__).resolve()),
                             note="same crop minus the upper-left operator name")
    ev = callog.log_dir(D)
    orig = ev / ("%s_original.jpg" % run_id)
    mod = ev / ("%s_masked.jpg" % run_id)
    with urllib.request.urlopen(CROP, timeout=60) as r:
        orig.write_bytes(r.read())
    x, y, w, h = MASK
    subprocess.run(["magick", str(orig), "-fill", "white", "-draw",
                    "rectangle %d,%d %d,%d" % (x, y, x + w, y + h),
                    str(mod)], capture_output=True, check=False)
    print("  crops: %s  %s" % (orig.name, mod.name), flush=True)

    out = {"pair": "2103.01507 p205", "crop_url": CROP,
           "mask_xywh": list(MASK), "run_id": run_id, "readings": {}}
    for arm, path in (("original", orig), ("masked", mod)):
        payload = ms.build_payload(ms.to_src(str(path)))
        t0 = time.time()
        try:
            resp = ms.snip(str(path), timeout=180)
            err = ""
        except Exception as e:                                  # noqa: BLE001
            resp, err = {}, "%s: %s" % (type(e).__name__, e)
        secs = round(time.time() - t0, 1)
        callog.log_call(D, run_id,
                        prompt=json.dumps({k: v for k, v in payload.items()
                                           if k != "src"}, indent=1),
                        system="POST /v3/text", reply=json.dumps(resp, indent=1),
                        model="mathpix/v3/text", finish="", error=err,
                        seconds=secs, images=[str(path)], subject="p205",
                        arm=arm)
        r = {"seconds": secs, "error": err,
             "confidence": resp.get("confidence"),
             "confidence_rate": resp.get("confidence_rate"),
             "is_printed": resp.get("is_printed"),
             "text": (resp.get("text") or "")[:1200],
             "latex_styled": (resp.get("latex_styled") or "")[:1200],
             "classified": classify(resp) if resp else "(call failed)"}
        out["readings"][arm] = r
        print("  %-9s conf=%-8s rate=%-8s -> %s" %
              (arm, r["confidence"], r["confidence_rate"], r["classified"]),
              flush=True)
    callog.close_run(D, run_id, calls=2,
                     outcome="%s -> %s" % (out["readings"]["original"]["classified"],
                                           out["readings"]["masked"]["classified"]))
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote %s" % a.out)
    print("evidence %s" % callog.path_for(D, run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
