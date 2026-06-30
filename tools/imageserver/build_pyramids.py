#!/usr/bin/env python3
"""
build_pyramids.py — render a PDF to per-page Deep Zoom (DZI) pyramids.

The deepest pyramid level is the full render, so a 600-DPI build gives a
600-DPI full-resolution level that eqcrop.py reads from.

Requires: poppler (pdftoppm) and libvips/pyvips.
  apt-get install poppler-utils libvips-tools && pip install pyvips pillow

Usage:
  python3 build_pyramids.py --pdf paper.pdf --out ./viewer --dpi 600
"""
import argparse, glob, json, math, os, shutil, subprocess, sys, tempfile

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", default="viewer", help="output dir (tiles/ + manifest.json)")
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--quality", type=int, default=88, help="JPEG tile quality")
    ap.add_argument("--tile-size", type=int, default=254)
    ap.add_argument("--overlap", type=int, default=1)
    args = ap.parse_args()

    try:
        import pyvips
    except ImportError:
        sys.exit("pyvips not installed:  pip install pyvips  (and apt install libvips-tools)")
    if not shutil.which("pdftoppm"):
        sys.exit("pdftoppm not found:  apt-get install poppler-utils")

    tiles_dir = os.path.join(args.out, "tiles")
    os.makedirs(tiles_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Rendering {args.pdf} @ {args.dpi} DPI ...")
        subprocess.run(["pdftoppm", "-png", "-r", str(args.dpi), args.pdf,
                        os.path.join(tmp, "page")], check=True)
        pngs = sorted(glob.glob(os.path.join(tmp, "page-*.png")))
        if not pngs:
            sys.exit("no pages rendered")
        manifest = []
        for i, p in enumerate(pngs, 1):
            name = f"page{i:02d}"
            img = pyvips.Image.new_from_file(p, access="sequential")
            img.dzsave(os.path.join(tiles_dir, name), layout="dz",
                       suffix=f".jpg[Q={args.quality}]",
                       tile_size=args.tile_size, overlap=args.overlap)
            levels = math.ceil(math.log2(max(img.width, img.height))) + 1
            manifest.append({"page": i, "dzi": f"tiles/{name}.dzi",
                             "width": img.width, "height": img.height, "levels": levels})
            print(f"  {name}: {img.width}x{img.height}  {levels} levels")
    json.dump(manifest, open(os.path.join(args.out, "manifest.json"), "w"), indent=2)
    print(f"done: {len(manifest)} pyramids -> {tiles_dir}  (full-res level = {args.dpi} DPI)")

if __name__ == "__main__":
    main()
