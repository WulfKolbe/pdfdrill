# Plan — MathPix-free image source: local 600-DPI DZI pyramid + cdn drop-in

**Status:** Phases A–D BUILT (commits 15c3925/78cdce1/4b163e7/fa2b0c1); Phase E
(keyless crop materialization) remains. Goal: serve the
`cdn.mathpix.com/cropped/…` crop URLs that pdfdrill tiddlers/reports reference
from a LOCAL Ghostscript-built 600-DPI Deep-Zoom pyramid, so the image layer
works **without MathPix** — and let image tiddlers reference plain `.png`/`.jpg`
files (via a `.meta` sidecar) instead of `<$image>` widgets or base64.

## 1. Where CDN images are base64-embedded today (the audit)

- **`docops/projectors/common.embed_image(url)`** — the ONLY base64 path: fetches
  the URL and returns a `data:<ctype>;base64,…` URI (cached; graceful URL
  fallback). Triggered only by **`--embed`**:
  - `formula_report.py:150` (`report --embed`)
  - `comparison_html.py:157` (`compare --embed`)
  - `tiddlywiki.py` `self._uri()` → the `canonical_uri` field of **EmbeddedImage
    / Picture / Diagram / Table** tiddlers (lines ~582/600/649/672) under
    `tiddlers --embed`.
- WITHOUT `--embed`, those tiddlers keep the **live `cdn.mathpix.com/cropped/…`
  URL** in `canonical_uri`, rendered by the `PIC`/`DIA` templates
  (`<$image source={{!!canonical_uri}}>`). So today the image layer is either
  (a) live-CDN, or (b) base64-inlined — both depend on MathPix having produced
  the crop. The local pyramid replaces (a)'s host.

## 2. Image-file tiddlers in tiddlers.json (`.png` + `.meta`, `{{name}}`)

TiddlyWiki renders an **image-type tiddler** by its own view template, so
transcluding `{{Title}}` (no `<$image>`) shows the image when the tiddler is:

```json
{ "title": "2603_FIG_03",
  "type": "image/png",
  "_canonical_uri": "2603_FIG_03.png" }      // external file, same folder
```

Key points:
- The field is **`_canonical_uri`** (leading underscore — TiddlyWiki's external-
  body pointer), NOT pdfdrill's current `canonical_uri`.
- `text` is empty/absent; the bytes live in the sibling `.png`.
- In the **file system adaptor** form this is exactly the user's `image.png` +
  `image.png.meta` pair: `image.png` (bytes) + `image.png.meta`
  (`title: …\ntype: image/png\n`). The `_canonical_uri` is implied by the file.
- So `tiddlers_to_md.py` must, for an image tiddler, write the IMAGE BYTES as
  `<title>.png` (not a `.md`) + `<title>.png.meta`. (Today it only sidecars
  text/code fields; image tiddlers need byte output keyed on `type: image/*`.)

## 3. The toolkit (`~/Downloads/imageserver.zip`)

- **`build_pyramids.py`** — renders a PDF to per-page **DZI** pyramids; deepest
  level = the full render, so a 600-DPI build gives a 600-DPI full-res level.
  Uses `pdftoppm` + `pyvips.dzsave` today → **switch to Ghostscript** (our gs-only
  rasterizer) for the render step; vips only for `dzsave` tiling.
- **`eqcrop.py`** — `Pyramid` class: assemble an arbitrary rectangle from only the
  tiles it overlaps (RAM-flat). Coordinate model matches ours: pt/px/norm,
  top-left origin = pdfplumber/MathPix.
- **`mathpix_server.py`** — **drop-in `cdn.mathpix.com` replacement**: serves
  `/cropped/<image_id>.jpg?top_left_x=…&top_left_y=…&width=…&height=…` from the
  pyramid. Resolves page (from a loaded lines.json `image_id→page`, else `?page=`,
  else trailing int of the id) and scale (lines.json page dims → `pyramid_px /
  mathpix_px`, exact). Routes: `/cropped/…`, `/viewer.html`, `/tiles/…`,
  `/manifest.json`, `/healthz`. Pure stdlib + Pillow + eqcrop.
- **`ahois_600dpi_viewer/`** — OpenSeadragon-style DZI viewer (`viewer.html` +
  `manifest.json` + `tiles/`).

## 4. Step-by-step integration

**Phase A — image-file tiddlers (small, self-contained, do first).**
1. Emit a real image tiddler for EmbeddedImage/Picture (and rendered crops):
   `type: image/png|jpeg` + `_canonical_uri: <title>.<ext>`, empty text; keep the
   existing `<$image>` PIC/DIA path only as a fallback for live-CDN mode.
2. `tiddlers_to_md.py`: when `type` starts with `image/`, write the image BYTES to
   `<title>.<ext>` (+ `<title>.<ext>.meta`) instead of a `.md`. Source bytes from:
   a local file (`_canonical_uri`), an extracted embedded image
   (`pdfdrill extractimages`), or a fetched/served crop.
3. Test: an image tiddler round-trips to `name.png` + `name.png.meta`,
   transcludable as `{{name}}`.

**Phase B — vendor the pyramid toolkit.**
4. Vendor `eqcrop.py` (the `Pyramid` cropper) into `src/pdfdrill/` (pure-Python,
   the one piece pdfdrill itself needs to crop locally). Keep `mathpix_server.py`
   + the viewer under `tools/imageserver/` (a runnable server, like drillui).
5. `[imageserver]` extra: `pyvips` (dzsave) + `pillow`; system `libvips-tools`.
   `bootstrap.sh`/`doctor` note them. gs is already required.

**Phase C — `pdfdrill pyramid` (build the local pyramid).**
6. `pdfdrill pyramid <pdf> [--dpi 600]`: render each page with **gs at 600 DPI**
   (reuse `pdf_reading.rasterize`/`render_page`, the gs-only path — replaces
   build_pyramids' pdftoppm), `dzsave` to `<drill>/viewer/tiles/pageNN.*`, write
   `manifest.json`. Record the pyramid in the sidecar.

**Phase D — serve crops locally (cdn drop-in). DONE (fa2b0c1).**
7. ✅ `pdfdrill imageserve <pdf> [--port 8000] [--dpi N] [--background]`: runs
   `mathpix_server.py` over the doc's `<drill>/viewer/` pyramid + its `lines.json`
   (exact scale). Any tiddler whose `canonical_uri` host is `cdn.mathpix.com`
   resolves at `localhost:8000`. Graceful "run `pdfdrill pyramid` first".
   `drillui_bridge.ts` lazily spawns it (IMG_PORT = bridge port + 1) and proxies
   `/cropped,/tiles,/viewer.html,/manifest.json` so the browser sees one
   same-origin host; the hello `viewer` field adds a deep-zoom Output link.
8. (Still opt-in, NOT yet built) a tiddler-rewrite mode (`tiddlers --image-host
   localhost:8000`, or a projector param) that repoints `cdn.mathpix.com` → the
   local host in `canonical_uri`, so an offline wiki shows the local crops. Keep
   the cdn URL as the default; rewrite is opt-in. **Roll this into Phase E** (the
   keyless path materializes `_canonical_uri` directly, making the rewrite moot
   for no-MathPix docs; the rewrite only matters for an existing MathPix wiki).

**Phase E — keyless crop materialization (the real MathPix-free win).**
9. For a doc with NO MathPix lines.json: build the pyramid from gs, and for each
   model object that needs an image (Picture/Diagram/Equation), `eqcrop` the
   region from the pyramid to a local `.png`, attach it as the image tiddler's
   `_canonical_uri` (Phase A). This gives gold 600-DPI crops with zero MathPix —
   the regions come from pdfplumber/the model geometry.

## 4b. drillui integration — viewer + cdn crops, one pyramid (the bun version)

How the **pyramid PDF viewer** and the **local cdn image server** work together
for a non-MathPix user, given drillui's actual shape:
- **`drillui_bridge.ts`** (Bun, :8787): routes `/ws` (→ a `drillui_chat.py <doc>`
  subprocess per socket), `/artifact?path=` (one file under `ART_ROOTS` = the doc
  dir + `~/Downloads`), `/open` (host browser), else the terminal HTML. It KNOWS
  the doc → `DOC_DIR`, so it can locate `<doc>.drill/viewer/`.
- **`drillui_term.html`**: xterm + an **Outputs panel** of `open ↗` (new tab) /
  `save ⤓` links; `open <url|file>` routes through `/open` or `/artifact`. No
  inline image/iframe today — artifacts open in a tab.
- **`drillui_chat.py`**: runs pdfdrill subcommands by name on the doc.

**The unification: ONE 600-DPI gs DZI pyramid, TWO consumers.**
`<doc>.drill/viewer/` (tiles + manifest) backs both (a) the **deep-zoom page
viewer** (`viewer.html`/OpenSeadragon over the tiles — the "pyramid PDF viewer")
and (b) the **crop server** (`/cropped/<id>?top_left_x=…` = a sub-rectangle
assembled from the SAME tiles via `eqcrop`). A crop is just the viewer's pyramid
at a page + sub-extent.

**Wiring (the `/artifact` single-file route can't serve a tile tree or assemble
crops — both are dynamic), recommended = proxy to a pdfdrill sidecar:**
1. The bridge lazily spawns **`pdfdrill imageserve <doc> --port 8000`**
   (mathpix_server over `<doc>.drill/viewer/` + the lines.json/model regions)
   when the doc has a `viewer/`.
2. The bridge gains **proxy routes** `/cropped/*`, `/tiles/*`, `/viewer.html`,
   `/manifest.json` → `http://127.0.0.1:8000<path>`. Everything is then
   **same-origin on :8787** (no CORS, one URL for the user).
3. **Non-MathPix image URLs are LOCAL by construction:** pdfdrill emits the
   figure/equation image tiddlers' crop URLs as `/cropped/page-<n>?top_left_x=…`
   (region from the MODEL/pdfplumber geometry, Phase E) pointing at the bridge
   origin — so they resolve from the gs pyramid with zero MathPix. (If a MathPix
   lines.json IS present, the same proxy serves the `cdn.mathpix.com`-shaped ids;
   the opt-in host-rewrite repoints them to the local origin.)
4. **UI:** the Outputs panel gets a **`viewer`** entry (opens `/viewer.html` →
   deep-zoom page browser); inline figure/equation crops render from the
   same-origin `/cropped/…` URLs (in report.html, or optionally inline in the
   rail). **Two-way nav:** a crop deep-links into the viewer at its page+rect
   (`viewer.html?page=12&rect=x,y,w,h`, an OpenSeadragon viewport); the viewer's
   manifest + the model's per-object regions are the same coordinate space.

**REPL flow for the non-MathPix user:** `pyramid <doc>` (build gs DZI) → bridge
auto-starts `imageserve` → Outputs shows `viewer` + every figure/equation crop
resolves locally. No MathPix, no live CDN.

Alternative (no sidecar): the bridge serves `viewer/` statically and shells
`eqcrop` per `/cropped` request — pulls the Python crop into the bun process via
subprocess; simpler topology, a subprocess per crop. The sidecar proxy is
preferred (one warm process, mathpix_server already written).

## 5. Notes / decisions to confirm with the user
- **gs for the pyramid render** (not pdftoppm) — consistent with the gs-only
  rasterizer + the 600-DPI fidelity evidence. dzsave (vips) does the tiling only.
- Server stays **external** (`tools/imageserver/`, like drillui) — not imported by
  pdfdrill; pdfdrill only vendors `eqcrop` for in-process crops.
- `_canonical_uri` (with underscore) is the TiddlyWiki external-image field; our
  current `canonical_uri` is a pdfdrill field read by the `<$image>` template.
  Phase A introduces the underscore form for the no-widget `{{name}}` transclude.
