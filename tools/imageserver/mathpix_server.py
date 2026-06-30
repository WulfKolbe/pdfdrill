#!/usr/bin/env python3
"""
mathpix_server.py — serve the Deep-Zoom viewer AND resolve MathPix CDN links
locally, so a TiddlyWiki that embeds cdn.mathpix.com/cropped/... images shows
them from your own 600-DPI pyramid while this server runs.

It is a drop-in replacement for the cdn.mathpix.com host. A tiddler image such as

    https://cdn.mathpix.com/cropped/2024_08_18_...g-106.jpg?top_left_x=300&top_left_y=1450&width=900&height=120

is served by repointing the host:

    http://localhost:8000/cropped/2024_08_18_...g-106.jpg?top_left_x=300&top_left_y=1450&width=900&height=120

The query params are MathPix page-image pixels (top-left origin) — exactly the
`{top_left_x, top_left_y, width, height}` region pdfdrill reads from lines.json.
They are scaled to the pyramid's full-resolution (e.g. 600-DPI) level by the
ratio of page dimensions, then the rectangle is assembled from only the tiles it
overlaps (via eqcrop.Pyramid — RAM stays flat).

ROUTES
  /                         -> redirect to /viewer.html
  /viewer.html, /tiles/...  -> static viewer + pyramid (from --root)
  /manifest.json            -> static
  /cropped/<image_id>.jpg   -> MathPix-compatible crop (also .png)
  /healthz                  -> JSON status + a sample resolvable URL

PAGE + SCALE RESOLUTION (in order)
  page:   image_id found in a loaded lines.json  ->  its page
          else ?page=N query param
          else trailing integer of the image_id  (…g-106 -> page 106)
  scale:  lines.json page dims     -> scale = pyramid_px / mathpix_px   (exact)
          else --mathpix-dpi D      -> scale = --pyramid-dpi / D
          else 1.0                  (warns once; assumes coords already pyramid px)

USAGE
  python3 mathpix_server.py --root ./viewer --tiles ./viewer/tiles \
          --lines ./2606_26722.lines.json --pyramid-dpi 600 --port 8000

  # multiple lines.json (a folder, or repeat --lines):
  python3 mathpix_server.py --root ./viewer --tiles ./viewer/tiles --lines ./drill/
"""

import argparse, glob, io, json, os, re, sys, threading, time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

# Use the single vendored cropper (src/pdfdrill/eqcrop.py) — no duplicate copy.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
try:
    from pdfdrill.eqcrop import Pyramid             # tile-assembly crop (vendored)
except ImportError:
    try:
        from eqcrop import Pyramid                  # fallback: a sibling copy
    except ImportError:
        sys.exit("eqcrop not found (expected src/pdfdrill/eqcrop.py).")
try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")


# --------------------------------------------------------------------------- #
# lines.json index: image_id -> page, page -> MathPix px dimensions
# --------------------------------------------------------------------------- #

class MathpixIndex:
    """Maps a MathPix page image_id to its page number and pixel dimensions.

    Tolerant of lines.json shape variants: a top-level {"pages":[...]} or a bare
    list; per-page page number under page/page_number/index; image id under
    image_id/imageId/id; page px under page_width/image_width/width (+height).
    Also indexes any per-element image_id that carries its own region, so a
    param-less diagram URL can still resolve.
    """
    def __init__(self):
        self.page_of = {}        # image_id -> page_number
        self.dims = {}           # page_number -> (w_px, h_px)
        self.region_of = {}      # image_id -> (page_number, dict(tlx,tly,w,h))

    @staticmethod
    def _num(d, *keys, default=None):
        for k in keys:
            if k in d and d[k] is not None:
                try: return float(d[k])
                except (TypeError, ValueError): pass
        return default

    def add_file(self, path):
        data = json.load(open(path, encoding="utf-8"))
        pages = data.get("pages") if isinstance(data, dict) else data
        if not isinstance(pages, list):
            return
        for i, pg in enumerate(pages):
            if not isinstance(pg, dict):
                continue
            page = int(self._num(pg, "page", "page_number", "page_idx", "index",
                                  default=i + 1))
            w = self._num(pg, "page_width", "image_width", "width")
            h = self._num(pg, "page_height", "image_height", "height")
            if w and h:
                self.dims[page] = (w, h)
            img = pg.get("image_id") or pg.get("imageId") or pg.get("id")
            if img:
                self.page_of[str(img)] = page
            for line in (pg.get("lines") or pg.get("elements") or []):
                if not isinstance(line, dict):
                    continue
                lid = line.get("image_id") or line.get("imageId")
                reg = self._region(line)
                if lid and reg:
                    self.region_of[str(lid)] = (page, reg)
                    self.page_of.setdefault(str(lid), page)

    @classmethod
    def _region(cls, line):
        r = line.get("region") or line
        tlx = cls._num(r, "top_left_x", "x"); tly = cls._num(r, "top_left_y", "y")
        w = cls._num(r, "width", "w");        h = cls._num(r, "height", "h")
        if None not in (tlx, tly, w, h):
            return {"x": tlx, "y": tly, "w": w, "h": h}
        cnt = line.get("cnt") or line.get("contour")            # [[x,y],...]
        if cnt:
            xs = [p[0] for p in cnt]; ys = [p[1] for p in cnt]
            return {"x": min(xs), "y": min(ys), "w": max(xs)-min(xs), "h": max(ys)-min(ys)}
        return None

    def load(self, paths):
        n = 0
        for p in paths:
            files = (glob.glob(os.path.join(p, "*.lines.json")) +
                     glob.glob(os.path.join(p, "*.json"))) if os.path.isdir(p) else [p]
            for f in files:
                try:
                    self.add_file(f); n += 1
                except Exception as e:
                    print(f"  ! skip {f}: {e}", file=sys.stderr)
        return n


# --------------------------------------------------------------------------- #
# small thread-safe LRU byte cache for rendered crops
# --------------------------------------------------------------------------- #

class LRU:
    def __init__(self, cap=256):
        self.cap = cap; self.d = OrderedDict(); self.lock = threading.Lock()
    def get(self, k):
        with self.lock:
            if k in self.d:
                self.d.move_to_end(k); return self.d[k]
        return None
    def put(self, k, v):
        with self.lock:
            self.d[k] = v; self.d.move_to_end(k)
            while len(self.d) > self.cap:
                self.d.popitem(last=False)


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #

class Server:
    def __init__(self, args, index):
        self.args = args
        self.index = index
        self.root = os.path.abspath(args.root) if args.root else os.getcwd()
        self.tiles = os.path.abspath(args.tiles)
        self.pyramid_dpi = args.pyramid_dpi
        self.mathpix_dpi = args.mathpix_dpi
        self.cache = LRU(args.cache_entries)
        self._pyr = {}; self._pyr_lock = threading.Lock()
        self._warned_scale = False

    def pyramid(self, page):
        with self._pyr_lock:
            if page not in self._pyr:
                dzi = os.path.join(self.tiles, self.args.page_pattern.format(page=page))
                self._pyr[page] = Pyramid(dzi) if os.path.exists(dzi) else None
            return self._pyr[page]

    def resolve_crop(self, image_id, qs):
        """Return (jpeg_bytes, content_type) or raise KeyError/ValueError."""
        # --- page ---
        if image_id in self.index.page_of:
            page = self.index.page_of[image_id]
        elif "page" in qs:
            page = int(qs["page"][0])
        else:
            m = re.search(r"(\d+)\D*$", image_id)
            if not m:
                raise KeyError(f"cannot determine page for image_id {image_id!r}")
            page = int(m.group(1))

        pyr = self.pyramid(page)
        if pyr is None:
            raise KeyError(f"no pyramid for page {page}")

        # --- rectangle in MathPix px ---
        def q(name):
            return float(qs[name][0]) if name in qs else None
        tlx, tly = q("top_left_x"), q("top_left_y")
        w, h = q("width"), q("height")
        if None in (tlx, tly, w, h) and image_id in self.index.region_of:
            _, r = self.index.region_of[image_id]
            tlx, tly, w, h = r["x"], r["y"], r["w"], r["h"]
        if None in (tlx, tly, w, h):
            raise ValueError("no rectangle: need top_left_x/top_left_y/width/height "
                             "or a lines.json region for this image_id")

        # --- scale MathPix px -> pyramid px ---
        if page in self.index.dims:
            mw, mh = self.index.dims[page]
            sx, sy = pyr.W / mw, pyr.H / mh
        elif self.mathpix_dpi:
            sx = sy = self.pyramid_dpi / self.mathpix_dpi
        else:
            sx = sy = 1.0
            if not self._warned_scale:
                self._warned_scale = True
                print("  ! no lines.json page dims and no --mathpix-dpi: "
                      "assuming coords already at pyramid scale (scale=1).",
                      file=sys.stderr)

        pad = self.args.pad
        x0, y0 = tlx * sx - pad, tly * sy - pad
        x1, y1 = (tlx + w) * sx + pad, (tly + h) * sy + pad

        key = (image_id, round(x0,1), round(y0,1), round(x1,1), round(y1,1))
        hit = self.cache.get(key)
        if hit:
            return hit
        img = pyr.crop(x0, y0, x1, y1)
        if img is None:
            raise ValueError("rectangle empty after clamping to page")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.args.jpg_quality)
        out = (buf.getvalue(), "image/jpeg")
        self.cache.put(key, out)
        return out

    def static_path(self, urlpath):
        rel = unquote(urlpath.lstrip("/")) or "viewer.html"
        full = os.path.normpath(os.path.join(self.root, rel))
        if not full.startswith(self.root):           # path-traversal guard
            return None
        return full if os.path.isfile(full) else None


class Handler(BaseHTTPRequestHandler):
    server_logic: Server = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet; flip to print for debugging
        pass

    def _send(self, code, body=b"", ctype="application/octet-stream", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")   # TW on another origin
        self.send_header("Cache-Control", "public, max-age=86400")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        L = self.server_logic
        u = urlparse(self.path)
        path = u.path

        if path == "/" :
            return self._send(302, b"", "text/plain", {"Location": "/viewer.html"})

        if path == "/healthz":
            info = {"ok": True,
                    "pages_indexed": len(L.index.dims),
                    "image_ids": len(L.index.page_of),
                    "pyramid_dpi": L.pyramid_dpi,
                    "mathpix_dpi": L.mathpix_dpi,
                    "scale_mode": ("lines.json dims" if L.index.dims else
                                   "dpi ratio" if L.mathpix_dpi else "1:1 (no scale)")}
            return self._send(200, json.dumps(info, indent=2).encode(), "application/json")

        if path.startswith("/cropped/"):
            image_id = re.sub(r"\.(jpe?g|png)$", "", path[len("/cropped/"):], flags=re.I)
            image_id = unquote(image_id)
            try:
                body, ctype = L.resolve_crop(image_id, parse_qs(u.query))
                return self._send(200, body, ctype)
            except KeyError as e:
                return self._send(404, str(e).encode(), "text/plain")
            except ValueError as e:
                return self._send(400, str(e).encode(), "text/plain")
            except Exception as e:
                return self._send(500, f"crop error: {e}".encode(), "text/plain")

        # static (viewer.html, manifest.json, tiles/*)
        full = L.static_path(path)
        if not full:
            return self._send(404, b"not found", "text/plain")
        import mimetypes
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".dzi"):       # DZI tile-source is XML (mimetypes can't guess it)
            ctype = "application/xml"
        with open(full, "rb") as f:
            return self._send(200, f.read(), ctype)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiles", required=True, help="dir with pageNN.dzi pyramids")
    ap.add_argument("--root", help="static root for the viewer (default: parent of --tiles)")
    ap.add_argument("--lines", action="append", default=[],
                    help="lines.json file or folder (repeatable) — gives exact scaling")
    ap.add_argument("--pyramid-dpi", type=float, default=600.0)
    ap.add_argument("--mathpix-dpi", type=float, default=None,
                    help="fallback scale source if no lines.json dims")
    ap.add_argument("--page-pattern", default="page{page:02d}.dzi")
    ap.add_argument("--pad", type=float, default=0.0, help="extra px margin per crop")
    ap.add_argument("--jpg-quality", type=int, default=92)
    ap.add_argument("--cache-entries", type=int, default=256)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if not args.root:
        args.root = os.path.dirname(os.path.abspath(args.tiles))

    index = MathpixIndex()
    if args.lines:
        n = index.load(args.lines)
        print(f"indexed {n} lines.json file(s): {len(index.dims)} pages, "
              f"{len(index.page_of)} image_ids, {len(index.region_of)} regions")
    else:
        print("no --lines given: scaling uses "
              + ("--mathpix-dpi" if args.mathpix_dpi else "1:1 (set --lines or --mathpix-dpi)"))

    Handler.server_logic = Server(args, index)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving viewer + MathPix resolver on http://{args.host}:{args.port}")
    print(f"  viewer:   http://{args.host}:{args.port}/viewer.html")
    print(f"  resolver: http://{args.host}:{args.port}/cropped/<image_id>.jpg?top_left_x=..&top_left_y=..&width=..&height=..")
    print("  -> repoint TiddlyWiki image host from cdn.mathpix.com to this address.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")

if __name__ == "__main__":
    main()
