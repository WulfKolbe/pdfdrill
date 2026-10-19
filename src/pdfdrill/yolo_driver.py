#!/usr/bin/env python3
r"""Page layout detection, run by an OUTSIDE interpreter. Imports no pdfdrill.

This file is executed by the Python of a separate environment (torch,
doclayout-yolo, ultralytics) chosen by `yololayout.interpreter()`, never by
pdfdrill's own. It therefore imports NOTHING from pdfdrill and takes
everything on the command line: that is what makes it runnable by an
interpreter which cannot import this package at all.

    <other-python> -m pdfdrill.yolo_driver OUT_DIR PNG [PNG ...]
    <other-python> path/to/yolo_driver.py  OUT_DIR PNG [PNG ...]

Writes OUT_DIR/<stem>.yolo.tsv per image:

    model   cls   conf   x1  y1  x2  y2        (pixels of that image)

and OUT_DIR/yolo.json with the model identities. Exit 2 means the weights are
not in the local cache and downloading them was not allowed.

TWO DETECTORS, because they answer different questions
------------------------------------------------------
  layout  DocLayout-YOLO DocStructBench, imgsz 1024 — blocks: title,
          plain text, abandon (running heads and folios), figure,
          figure_caption, table, table_caption, table_footnote,
          isolate_formula, formula_caption (which IS the equation number).
  mfd     PDF-Extract-Kit's math formula detector, YOLOv8, imgsz 1888 —
          isolated AND inline ("embedding") formulas, so a formula INSIDE a
          text line gets a box too.

OFFLINE BY DEFAULT. `--allow-download` is the only way this reaches the
network, because pdfdrill routes every network call through `net.urlopen` so
that a blocked host raises a typed, host-named error; a subprocess that quietly
downloaded 300 MB of weights would be the one call that escapes that rule.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LAYOUT_REPO = "juliozhao/DocLayout-YOLO-DocStructBench"
LAYOUT_FILE = "doclayout_yolo_docstructbench_imgsz1024.pt"
#: The 1280 "2501" weights in PDF-Extract-Kit are refused by torch >= 2.6's
#: safe loading, so the 1024 DocStructBench weights are the layout model.
MFD_REPO = "opendatalab/PDF-Extract-Kit-1.0"
MFD_FILE = "models/MFD/YOLO/yolo_v8_ft.pt"

LAYOUT_IMGSZ = 1024
MFD_IMGSZ = 1888          # as MinerU runs it; below this, inline math is missed
CONF = 0.25
IOU = 0.45


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    allow = "--allow-download" in argv
    if len(args) < 2:
        sys.stderr.write(__doc__ or "")
        return 64
    out_dir, images = Path(args[0]), [Path(a) for a in args[1:]]
    out_dir.mkdir(parents=True, exist_ok=True)
    if not allow:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    try:
        from doclayout_yolo import YOLOv10
        from huggingface_hub import hf_hub_download
        from PIL import Image
        from ultralytics import YOLO
    except ImportError as exc:
        sys.stderr.write(f"yolo_driver: {exc}\n")
        return 3

    try:
        lw = hf_hub_download(LAYOUT_REPO, LAYOUT_FILE)
        mw = hf_hub_download(MFD_REPO, MFD_FILE)
    except Exception as exc:
        sys.stderr.write(
            f"yolo_driver: weights not in the local cache and download "
            f"{'failed' if allow else 'not allowed'}: {exc}\n")
        return 2

    layout, mfd = YOLOv10(lw), YOLO(mw)
    (out_dir / "yolo.json").write_text(json.dumps({
        "layout": {"repo": LAYOUT_REPO, "file": LAYOUT_FILE,
                   "imgsz": LAYOUT_IMGSZ},
        "mfd": {"repo": MFD_REPO, "file": MFD_FILE, "imgsz": MFD_IMGSZ},
        "conf": CONF, "iou": IOU,
    }, indent=1), encoding="utf-8")

    for path in images:
        with Image.open(path) as im:
            img = im.convert("RGB")
            rows = []
            for name, model, imgsz in (("layout", layout, LAYOUT_IMGSZ),
                                       ("mfd", mfd, MFD_IMGSZ)):
                res = model.predict(img, imgsz=imgsz, conf=CONF, iou=IOU,
                                    verbose=False, device="cpu")[0]
                names = res.names
                for b, c, k in zip(res.boxes.xyxy.tolist(),
                                   res.boxes.conf.tolist(),
                                   res.boxes.cls.tolist()):
                    rows.append((name, names[int(k)], round(float(c), 3),
                                 round(b[0]), round(b[1]),
                                 round(b[2]), round(b[3])))
        tsv = out_dir / f"{path.stem}.yolo.tsv"
        tmp = tsv.with_suffix(".tsv.part")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("model\tcls\tconf\tx1\ty1\tx2\ty2\n")
            for r in rows:
                fh.write("\t".join(str(v) for v in r) + "\n")
        os.replace(tmp, tsv)
        sys.stdout.write(f"{path.name}\t{len(rows)}\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
