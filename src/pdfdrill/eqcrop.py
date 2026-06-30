#!/usr/bin/env python3
"""
eqcrop.py — extract rectangular image crops from a Deep Zoom (DZI) pyramid.

Given a table of geometry rows (page + rectangle) — e.g. math-equation
bounding boxes — this pulls the corresponding region out of the *pyramid*
(not the original PDF) at the pyramid's full-resolution level. It loads only
the handful of tiles each rectangle overlaps, so RAM stays flat regardless of
page size. Pure stdlib + Pillow.

The full-resolution level of a pyramid built from a 600-DPI render *is* the
600-DPI image, tiled — so crops come out at 600 DPI.

INPUT TABLE
  CSV / TSV / JSON (array of objects) / JSONL. One row per crop. Needs:
    - a page number column
    - a rectangle, given EITHER as corners (x0,y0,x1,y1) OR as x,y,w,h
  Column names are auto-detected (case-insensitive). Common spellings are
  recognised: page/p; x0,y0,x1,y1 | left,top,right,bottom | xmin,ymin,xmax,ymax;
  x,y,w,h | x,y,width,height. An optional id/label/name column is used to name
  outputs. Override any of these with the --col-* / --rect flags.

COORDINATE UNITS  (--units)
  px   pixels (default). If measured at a different DPI than the pyramid, give
       --src-dpi so they are rescaled.
  pt   PDF points (72/inch). Rescaled to the pyramid DPI automatically.
  norm fractions of the page in [0,1].

Y ORIGIN  (--origin)
  topleft     (default; pdfplumber, MathPix, image pixels)
  bottomleft  (raw PDF user space, y-up) — flipped using the page height.

EXAMPLES
  # pdfplumber-style boxes in points, top-left origin, 600-DPI pyramid:
  python3 eqcrop.py --table eqs.csv --tiles ./tiles --out ./crops \
                    --units pt --pyramid-dpi 600 --pad 6

  # pixel boxes captured at 300 DPI, extracted from a 600-DPI pyramid:
  python3 eqcrop.py --table eqs.jsonl --tiles ./tiles --out ./crops \
                    --units px --src-dpi 300 --pyramid-dpi 600

  # inspect detected columns without writing anything:
  python3 eqcrop.py --table eqs.csv --tiles ./tiles --list-cols
"""

import argparse, csv, io, json, math, os, re, sys
import xml.etree.ElementTree as ET
from functools import lru_cache

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

# --------------------------------------------------------------------------- #
# Table loading
# --------------------------------------------------------------------------- #

def load_rows(path):
    """Return a list of dict rows from csv/tsv/json/jsonl."""
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        if ext in (".json",):
            data = json.load(fh)
            if isinstance(data, dict):                       # {"rows":[...]} or single obj
                data = data.get("rows") or data.get("data") or [data]
            return [dict(r) for r in data]
        if ext in (".jsonl", ".ndjson"):
            return [json.loads(line) for line in fh if line.strip()]
        # csv / tsv / unknown -> sniff
        sample = fh.read(8192); fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel_tab if ext == ".tsv" else csv.excel
        return [dict(r) for r in csv.DictReader(fh, dialect=dialect)]


# --------------------------------------------------------------------------- #
# Column detection
# --------------------------------------------------------------------------- #

# candidate spellings -> canonical role
_PAGE   = ["page", "page_num", "pagenum", "page_no", "pageno", "pg", "p"]
_ID     = ["id", "eq_id", "equation_id", "label", "name", "eq", "equation"]
_CORNER = [("x0","y0","x1","y1"),
           ("left","top","right","bottom"),
           ("xmin","ymin","xmax","ymax"),
           ("x_min","y_min","x_max","y_max"),
           ("x1","y1","x2","y2")]
_XYWH   = [("x","y","w","h"),
           ("x","y","width","height"),
           ("left","top","width","height")]

def _find(cols_lower, names):
    for n in names:
        if n in cols_lower:
            return cols_lower[n]
    return None

def detect_columns(row, args):
    cols = list(row.keys())
    low = {c.lower().strip(): c for c in cols}

    page = args.col_page or _find(low, _PAGE)
    if not page:
        sys.exit(f"Could not find a page column. Columns: {cols}\n"
                 f"Use --col-page NAME.")

    idc = args.col_id or _find(low, _ID)

    # explicit --rect 'a,b,c,d' overrides everything (corners x0,y0,x1,y1)
    if args.rect:
        parts = [p.strip() for p in args.rect.split(",")]
        if len(parts) != 4:
            sys.exit("--rect needs 4 comma-separated column names (x0,y0,x1,y1).")
        missing = [p for p in parts if p not in cols]
        if missing:
            sys.exit(f"--rect columns not in table: {missing}")
        return {"page": page, "id": idc, "mode": "corner", "rect": tuple(parts)}

    for a, b, c, d in _CORNER:
        m = (_find(low, [a]), _find(low, [b]), _find(low, [c]), _find(low, [d]))
        if all(m):
            return {"page": page, "id": idc, "mode": "corner", "rect": m}
    for a, b, c, d in _XYWH:
        m = (_find(low, [a]), _find(low, [b]), _find(low, [c]), _find(low, [d]))
        if all(m):
            return {"page": page, "id": idc, "mode": "xywh", "rect": m}

    sys.exit(f"Could not find a rectangle in columns {cols}.\n"
             f"Provide one as x0,y0,x1,y1 / left,top,right,bottom / x,y,w,h, "
             f"or pass --rect 'x0,y0,x1,y1'.")


# --------------------------------------------------------------------------- #
# DZI geometry
# --------------------------------------------------------------------------- #

class Pyramid:
    """A single page's DZI pyramid: reads .dzi, finds the full-res level."""
    def __init__(self, dzi_path):
        self.dzi = dzi_path
        self.files_dir = re.sub(r"\.dzi$", "_files", dzi_path)
        ns = {"d": "http://schemas.microsoft.com/deepzoom/2008"}
        root = ET.parse(dzi_path).getroot()
        self.tile = int(root.get("TileSize"))
        self.overlap = int(root.get("Overlap"))
        self.fmt = root.get("Format", "jpg")
        size = root.find("d:Size", ns)
        if size is None:
            size = root.find("Size")
        self.W = int(size.get("Width"))
        self.H = int(size.get("Height"))
        # deepest level on disk (== full resolution); read it rather than compute
        levels = [int(d) for d in os.listdir(self.files_dir)
                  if d.isdigit() and os.path.isdir(os.path.join(self.files_dir, d))]
        self.level = max(levels)

    def _tile_path(self, col, row):
        return os.path.join(self.files_dir, str(self.level), f"{col}_{row}.{self.fmt}")

    def crop(self, x0, y0, x1, y1):
        """Crop the full-res level over integer box [x0,y0,x1,y1]. Returns RGB Image."""
        x0 = max(0, min(self.W, int(math.floor(x0))))
        y0 = max(0, min(self.H, int(math.floor(y0))))
        x1 = max(0, min(self.W, int(math.ceil(x1))))
        y1 = max(0, min(self.H, int(math.ceil(y1))))
        if x1 <= x0 or y1 <= y0:
            return None
        T = self.tile
        canvas = Image.new("RGB", (x1 - x0, y1 - y0), (255, 255, 255))
        c0, c1 = x0 // T, (x1 - 1) // T          # tile-columns whose core hits [x0,x1)
        r0, r1 = y0 // T, (y1 - 1) // T
        for col in range(c0, c1 + 1):
            lo = self.overlap if col > 0 else 0   # left overlap present?
            ox = col * T - lo                     # tile image top-left x in page space
            for row in range(r0, r1 + 1):
                tp = self._tile_path(col, row)
                if not os.path.exists(tp):
                    continue
                to = self.overlap if row > 0 else 0
                oy = row * T - to
                with Image.open(tp) as t:
                    canvas.paste(t.convert("RGB"), (ox - x0, oy - y0))
        return canvas


# --------------------------------------------------------------------------- #
# Coordinate conversion
# --------------------------------------------------------------------------- #

def to_px_box(vals, mode, args, W, H):
    """Convert one row's raw rectangle to a pixel box (x0,y0,x1,y1), top-left origin."""
    a, b, c, d = (float(v) for v in vals)
    if mode == "xywh":
        x0r, y0r, x1r, y1r = a, b, a + c, b + d
    else:
        x0r, y0r, x1r, y1r = a, b, c, d

    if args.units == "norm":
        pts = [(x0r * W, y0r * H), (x1r * W, y1r * H)]
    else:
        s = (args.pyramid_dpi / 72.0) if args.units == "pt" \
            else (args.pyramid_dpi / args.src_dpi if args.src_dpi else 1.0)
        pts = [(x0r * s, y0r * s), (x1r * s, y1r * s)]

    if args.origin == "bottomleft":
        pts = [(px, H - py) for px, py in pts]

    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def sanitize(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("_") or "x"

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract rectangle crops from a DZI pyramid for each table row.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--table", required=True, help="csv/tsv/json/jsonl geometry table")
    ap.add_argument("--tiles", required=True, help="directory holding pageNN.dzi files")
    ap.add_argument("--out", help="output directory for crops (required unless --dry-run/--list-cols)")
    ap.add_argument("--units", choices=["px", "pt", "norm"], default="px")
    ap.add_argument("--origin", choices=["topleft", "bottomleft"], default="topleft")
    ap.add_argument("--pyramid-dpi", type=float, default=600.0,
                    help="DPI of the pyramid's full-res level (default 600)")
    ap.add_argument("--src-dpi", type=float, default=None,
                    help="DPI the px coords were measured at (units=px); default = pyramid-dpi")
    ap.add_argument("--pad", type=float, default=0.0, help="margin in OUTPUT pixels (default 0)")
    ap.add_argument("--page-pattern", default="page{page:02d}.dzi",
                    help="how a page number maps to a .dzi filename (default page{page:02d}.dzi)")
    ap.add_argument("--col-page", help="override page column name")
    ap.add_argument("--col-id", help="override id/label column name")
    ap.add_argument("--rect", help="explicit corner columns 'x0,y0,x1,y1'")
    ap.add_argument("--format", choices=["png", "jpg"], default="png", help="output image format")
    ap.add_argument("--jpg-quality", type=int, default=95)
    ap.add_argument("--list-cols", action="store_true", help="print detected columns and exit")
    ap.add_argument("--dry-run", action="store_true", help="compute boxes, write index.csv, no images")
    args = ap.parse_args(argv)

    rows = load_rows(args.table)
    if not rows:
        sys.exit("Table is empty.")
    cmap = detect_columns(rows[0], args)

    if args.list_cols:
        print("Detected mapping:")
        for k, v in cmap.items():
            print(f"  {k:5} -> {v}")
        return

    if not args.out and not args.dry_run:
        sys.exit("--out is required (or use --dry-run).")
    if args.out:
        os.makedirs(args.out, exist_ok=True)

    @lru_cache(maxsize=64)
    def pyramid_for(page_int):
        path = os.path.join(args.tiles, args.page_pattern.format(page=page_int))
        if not os.path.exists(path):
            return None
        return Pyramid(path)

    index = []
    ok = skipped = 0
    for i, row in enumerate(rows):
        try:
            page = int(float(row[cmap["page"]]))
        except (KeyError, ValueError, TypeError):
            print(f"[row {i}] bad/missing page -> skip", file=sys.stderr); skipped += 1; continue

        pyr = pyramid_for(page)
        if pyr is None:
            print(f"[row {i}] no pyramid for page {page} -> skip", file=sys.stderr); skipped += 1; continue

        try:
            vals = [row[c] for c in cmap["rect"]]
            x0, y0, x1, y1 = to_px_box(vals, cmap["mode"], args, pyr.W, pyr.H)
        except (KeyError, ValueError, TypeError) as e:
            print(f"[row {i}] bad rectangle ({e}) -> skip", file=sys.stderr); skipped += 1; continue

        if args.pad:
            x0 -= args.pad; y0 -= args.pad; x1 += args.pad; y1 += args.pad

        ident = sanitize(row[cmap["id"]]) if cmap["id"] and row.get(cmap["id"]) else f"{i:04d}"
        fname = f"eq_p{page:02d}_{ident}.{args.format}"
        bx = (int(math.floor(max(0, min(pyr.W, x0)))), int(math.floor(max(0, min(pyr.H, y0)))),
              int(math.ceil(max(0, min(pyr.W, x1)))),  int(math.ceil(max(0, min(pyr.H, y1)))))
        index.append({"row": i, "page": page, "id": ident, "file": fname,
                      "px_x0": bx[0], "px_y0": bx[1], "px_x1": bx[2], "px_y1": bx[3],
                      "w": bx[2]-bx[0], "h": bx[3]-bx[1]})

        if args.dry_run:
            ok += 1; continue

        img = pyr.crop(x0, y0, x1, y1)
        if img is None:
            print(f"[row {i}] empty box after clamping -> skip", file=sys.stderr); skipped += 1
            index.pop(); continue
        out_path = os.path.join(args.out, fname)
        if args.format == "jpg":
            img.save(out_path, quality=args.jpg_quality)
        else:
            img.save(out_path)
        ok += 1

    # write an index mapping rows -> files + the pixel box actually used
    if args.out:
        with open(os.path.join(args.out, "index.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["row","page","id","file",
                              "px_x0","px_y0","px_x1","px_y1","w","h"])
            w.writeheader(); w.writerows(index)

    print(f"done: {ok} crops, {skipped} skipped"
          + (f"  ->  {args.out}" if args.out else "  (dry run)"))

if __name__ == "__main__":
    main()
