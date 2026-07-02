#!/usr/bin/env python3
"""
offline_viewer.py — turn a built DZI pyramid into a SERVER-FREE deep-zoom bundle.

The normal `viewer.html` needs the image server: OpenSeadragon is loaded from a CDN
and it fetches `manifest.json` + each `.dzi` over XHR — all blocked when the page is
opened as a local `file://` (and in a locked-down sandbox). This writer removes every
one of those network dependencies so the SAME pyramid opens with no server at all:

  1. OpenSeadragon is served from a LOCAL copy (vendor/openseadragon.min.js, copied
     into the bundle) instead of the CDN.
  2. The manifest is INLINED into the HTML as a JS literal — no fetch.
  3. Each page's DZI descriptor is passed to OSD as an inline OBJECT (parsed from the
     real `.dzi`), so OSD never XHR-fetches a `.dzi`. Tiles then load as <img> from
     relative paths, which works over file://.
  4. OSD's built-in navigation buttons (which pull PNG assets from prefixUrl) are
     disabled; a custom toolbar drives it — so no image assets are needed either.

Consumes an existing pyramid dir (`<out>/manifest.json` + `<out>/tiles/…`), as produced
by `build_pyramids.py` or `pdfdrill pyramid`. Writes `<out>/viewer_offline.html` and
copies the vendored OSD to `<out>/openseadragon.min.js`. The bundle is portable: copy
the folder anywhere and double-click viewer_offline.html.

Usage:
  python3 offline_viewer.py --out ./viewer [--title NAME]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

VENDORED_OSD = Path(__file__).resolve().parent / "vendor" / "openseadragon.min.js"
_DZI_NS = "{http://schemas.microsoft.com/deepzoom/2008}"


def _read_dzi(dzi_path: Path) -> dict:
    """Parse a Deep Zoom `.dzi` for the tile params OSD needs (Format/TileSize/Overlap)."""
    root = ET.parse(dzi_path).getroot()
    return {"format": root.get("Format", "jpg"),
            "tile": root.get("TileSize", "254"),
            "overlap": root.get("Overlap", "1")}


def _pages_from_manifest(out: Path) -> tuple[list[dict], dict]:
    """Manifest rows -> [{url, w, h}]; tile params read from the first page's .dzi."""
    manifest = json.loads((out / "manifest.json").read_text())
    rows = manifest if isinstance(manifest, list) else manifest.get("pages", [])
    if not rows:
        raise SystemExit("manifest.json lists no pages")
    params = _read_dzi(out / rows[0]["dzi"])
    pages = []
    for r in rows:
        # "tiles/page01.dzi" -> "tiles/page01_files/" (relative, file://-safe)
        url = r["dzi"][:-4] + "_files/" if r["dzi"].endswith(".dzi") else r["dzi"] + "_files/"
        pages.append({"url": url, "w": int(r["width"]), "h": int(r["height"])})
    return pages, params


def write_offline_bundle(out_dir: str | Path, title: str | None = None) -> Path:
    """Write viewer_offline.html + copy the vendored OSD into `out_dir`. Returns the html path."""
    out = Path(out_dir)
    if not (out / "manifest.json").exists():
        raise SystemExit(f"no manifest.json in {out} — build the pyramid first "
                         f"(build_pyramids.py / pdfdrill pyramid).")
    if not VENDORED_OSD.exists():
        raise SystemExit(f"vendored OpenSeadragon missing at {VENDORED_OSD}")

    pages, params = _pages_from_manifest(out)
    shutil.copy2(VENDORED_OSD, out / "openseadragon.min.js")
    meta = {"title": title or out.name, "format": params["format"],
            "tile": params["tile"], "overlap": params["overlap"], "pages": pages}
    html = _HTML.replace("__MANIFEST__", json.dumps(meta)).replace("__TITLE__", meta["title"])
    dest = out / "viewer_offline.html"
    dest.write_text(html, encoding="utf-8")
    return dest


# Static HTML/JS — braces are literal (we substitute two __TOKENS__, no str.format).
_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — DZI deep zoom (offline)</title>
<script src="openseadragon.min.js"></script>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}html,body{margin:0;height:100%;background:#0d0f12;
 color:#e6e9ee;font:14px/1.4 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow:hidden}
#bar{display:flex;align-items:center;gap:10px;height:52px;padding:0 14px;background:#16191f;border-bottom:1px solid #262b33}
#bar .t{font-weight:600}#bar .t small{color:#8a93a0;margin-left:6px;font-weight:400}.sp{flex:1}
button{background:#1e232b;color:#e6e9ee;border:1px solid #262b33;border-radius:7px;padding:6px 10px;cursor:pointer;font-size:13px}
button:hover{border-color:#6ea8fe;color:#6ea8fe}button:disabled{opacity:.35;cursor:default}
input{width:48px;text-align:center;background:#1e232b;color:#e6e9ee;border:1px solid #262b33;border-radius:7px;padding:6px 2px}
#osd{position:absolute;inset:52px 0 0 0;background:#000}.navigator{border:1px solid #262b33!important;border-radius:6px}
#hint{position:absolute;bottom:14px;left:14px;background:rgba(20,25,31,.85);border:1px solid #262b33;border-radius:8px;
 padding:8px 12px;color:#8a93a0;font-size:12px;pointer-events:none;transition:opacity .6s}
</style></head><body>
<div id="bar"><span class="t">__TITLE__ <small id="sub"></small></span><span class="sp"></span>
<button id="first" title="First">⏮</button><button id="prev" title="Prev (←)">◀</button>
<span>Pg <input id="pg" type="number" min="1" value="1"> / <span id="tot">–</span></span>
<button id="next" title="Next (→)">▶</button><button id="last" title="Last">⏭</button>
<button id="zo" title="Zoom out (-)">–</button><button id="zi" title="Zoom in (+)">+</button>
<button id="fit" title="Fit (0)">Fit</button></div>
<div id="osd"></div>
<div id="hint">Offline DZI · scroll to zoom · drag to pan · ← → pages · 0 fits · no server</div>
<script>
const MANIFEST = __MANIFEST__;
const $=i=>document.getElementById(i);
$("tot").textContent=MANIFEST.pages.length;$("pg").max=MANIFEST.pages.length;
$("sub").textContent=MANIFEST.pages.length+" page"+(MANIFEST.pages.length===1?"":"s")+" · tiled DZI · offline";
document.title=MANIFEST.title+" — DZI deep zoom (offline)";
// Inline DZI descriptors -> NO .dzi fetch. Tiles load as <img> from relative Url (file:// safe).
const tileSources = MANIFEST.pages.map(p => ({
  Image:{ xmlns:"http://schemas.microsoft.com/deepzoom/2008",
    Url:p.url, Format:MANIFEST.format, Overlap:String(MANIFEST.overlap), TileSize:String(MANIFEST.tile),
    Size:{ Width:String(p.w), Height:String(p.h) } }
}));
const viewer = OpenSeadragon({
  id:"osd", tileSources, sequenceMode:true,
  showNavigationControl:false, showSequenceControl:false,   // no prefixUrl button images needed
  showNavigator:true, navigatorPosition:"TOP_RIGHT",
  animationTime:0.4, blendTime:0.1, maxZoomPixelRatio:3, minZoomImageRatio:0.5,
  gestureSettingsMouse:{clickToZoom:false,dblClickToZoom:true},
});
const N=MANIFEST.pages.length, clamp=p=>Math.max(0,Math.min(N-1,p)), go=p=>viewer.goToPage(clamp(p));
function sync(){const p=viewer.currentPage();$("pg").value=p+1;
 $("prev").disabled=$("first").disabled=p===0;$("next").disabled=$("last").disabled=p===N-1;}
viewer.addHandler("open",sync);viewer.addHandler("page",sync);
viewer.addHandler("open-failed",e=>{document.getElementById("hint").textContent=
 "tile source failed: "+((e&&e.message)||"")+" — confirm tiles/ sits next to this file";});
$("first").onclick=()=>go(0);$("prev").onclick=()=>go(viewer.currentPage()-1);
$("next").onclick=()=>go(viewer.currentPage()+1);$("last").onclick=()=>go(N-1);
$("fit").onclick=()=>viewer.viewport.goHome();
$("zi").onclick=()=>viewer.viewport.zoomBy(1.4).applyConstraints();
$("zo").onclick=()=>viewer.viewport.zoomBy(1/1.4).applyConstraints();
$("pg").onchange=e=>go((parseInt(e.target.value,10)||1)-1);
addEventListener("keydown",e=>{if(e.target.tagName==="INPUT")return;
 if(e.key==="ArrowRight")go(viewer.currentPage()+1);else if(e.key==="ArrowLeft")go(viewer.currentPage()-1);
 else if(e.key==="0")viewer.viewport.goHome();else if(e.key==="+"||e.key==="=")$("zi").onclick();
 else if(e.key==="-")$("zo").onclick();});
setTimeout(()=>{$("hint").style.opacity=0;},4500);
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="viewer", help="pyramid dir (has manifest.json + tiles/)")
    ap.add_argument("--title", default=None, help="viewer title (default: folder name)")
    args = ap.parse_args()
    dest = write_offline_bundle(args.out, args.title)
    print(f"offline deep-zoom bundle -> {dest}")
    print("  open it directly (file://) — no server, no network. Copy the whole folder to share.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
