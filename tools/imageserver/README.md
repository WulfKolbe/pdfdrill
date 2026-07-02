# tools/imageserver — local MathPix-free image stack (DZI pyramid + cdn drop-in)

Serve the `cdn.mathpix.com/cropped/…` crop URLs that pdfdrill tiddlers/reports
reference from a LOCAL Ghostscript-built 600-DPI Deep-Zoom pyramid — so the image
layer works **without MathPix**. One pyramid backs two consumers: the deep-zoom
page viewer and the region-crop server.

Files (vendored from `~/Downloads/imageserver.zip`):
- **`mathpix_server.py`** — drop-in replacement for `cdn.mathpix.com`. Serves
  `/cropped/<id>.jpg?top_left_x=…&top_left_y=…&width=…&height=…` from the pyramid
  (scaled via a loaded `lines.json` page-dims), plus `/viewer.html`, `/tiles/…`,
  `/manifest.json`, `/healthz`. Imports the single vendored cropper
  `pdfdrill.eqcrop.Pyramid` (no duplicate copy). Pure stdlib + Pillow.
- **`viewer.html`** — OpenSeadragon deep-zoom viewer over the DZI tiles.
- **`build_pyramids.py`** — reference PDF→DZI builder (pdftoppm + pyvips). NOTE:
  pdfdrill's own `pdfdrill pyramid` (Phase C) builds with **Ghostscript** (the
  gs-only rasterizer) + pyvips `dzsave`; this file is kept as the upstream
  reference.

The crop math lives in `src/pdfdrill/eqcrop.py` (vendored, Pillow-only): a `.dzi`
pyramid's full-resolution level is the 600-DPI render, and `Pyramid.crop(x0,y0,
x1,y1)` assembles a rectangle from only the tiles it overlaps (RAM-flat).

## Run

```bash
# THE sanctioned build path — Ghostscript render (the gs-only rasterizer):
pdfdrill pyramid paper.pdf [--dpi 600] [--offline]
#   --offline also writes viewer_offline.html (server-free, see below);
#   on an already-built pyramid it just adds the bundle, no rebuild.

# serve it as the local cdn + viewer
python3 tools/imageserver/mathpix_server.py --root ./paper.pdf.drill/viewer \
        --tiles ./paper.pdf.drill/viewer/tiles \
        --lines ./paper.lines.json --pyramid-dpi 600 --port 8000
# -> http://localhost:8000/viewer.html  and  /cropped/<id>.jpg?top_left_x=…
```

(`build_pyramids.py --pdf … [--offline]` still works but renders with pdftoppm —
it is the UPSTREAM REFERENCE only; pdfdrill's own path is `pdfdrill pyramid`.)

Deps: Pillow (crops) + `pyvips` & `libvips-tools` (build only) — the
`pdfdrill[imageserver]` extra. Integration plan + drillui (bun) wiring:
`docs/superpowers/specs/2026-06-30-local-image-server-dzi.md`.

## Server-free deep zoom (`viewer_offline.html`)

`viewer.html` needs the server (OpenSeadragon from a CDN + `fetch()` of the
manifest/`.dzi`, all blocked over `file://` and in a sandbox). For a **no-server**
deep-zoom viewer over the SAME pyramid:

```bash
pdfdrill pyramid paper.pdf --offline            # the gs path, bundle included
# or, on any already-built pyramid dir:
python3 offline_viewer.py --out ./viewer --title paper
# -> viewer_offline.html next to the tiles (double-click; no server, no network)
```

`offline_viewer.py` writes `viewer_offline.html` and copies the **vendored**
`vendor/openseadragon.min.js` into the bundle. It removes every network dependency:
OpenSeadragon is local, the manifest is inlined as a JS literal, and each page's DZI
descriptor is passed to OSD as an inline object (parsed from the real `.dzi`) so no
`.dzi` is XHR-fetched — tiles then load as `<img>` from relative paths, which works
over `file://`. OSD's PNG-asset nav buttons are disabled; a custom toolbar drives it.
Copy the whole `viewer/` folder anywhere and it still opens. The region-crop server
(`mathpix_server.py`) is unchanged and still needed only for the `cdn.mathpix.com`
crop URLs.
