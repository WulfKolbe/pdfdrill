"""Image PLACEMENTS versus distinct XObjects, and per-placement resolution.

`images` reported 213 images on a handbook that has far fewer distinct ones:
object 9 is one logo placed on 109 pages. The join key everywhere is
`(page, obj_id)`, so a reused XObject is 109 unrelated records and nothing
counts the object itself.

Two numbers, never one:

  PLACEMENT  where an XObject is drawn, with its own CTM — and therefore its
             own effective resolution. Object 9 is 200 ppi on page 1 and 551
             on pages 2+, because the placement differs, not the image.
  OBJECT     the XObject itself: dimensions, colour, encoding, bytes.

Collapsing them loses whichever half you collapsed. Reuse is counted on the
object; resolution is reported per placement.

The resolution question is the actionable one. A placement whose x-ppi exceeds
the render dpi has detail the render throws away — measured 465 of 492
placements (94%) on one mosaic page-set and 109 of 228 (48%) on the handbook.
Neither "read the render" nor "read the extracted bytes" is right as a blanket
policy, because the handbook splits nearly evenly. It is a per-placement fact.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Optional


def object_key(rec: dict) -> Optional[str]:
    """The XObject identity — `"<obj> <gen>"` — independent of the page."""
    for k in ("object_id", "obj_id", "object"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, int):
            return f"{v} 0"
    obj, gen = rec.get("obj"), rec.get("gen")
    if obj is not None:
        return f"{obj} {gen if gen is not None else 0}"
    return None


def effective_ppi(rec: dict) -> Optional[float]:
    """The placement's own resolution, from `pdfimages -list` x-ppi.

    Per PLACEMENT: the same object drawn twice at different scales has two
    answers, and the larger one is not a property of the image.
    """
    for k in ("x_ppi", "xppi", "x-ppi", "ppi"):
        v = rec.get(k)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return None


def summarize(records: Iterable[dict], *, render_dpi: float) -> dict:
    """Placements, distinct objects, reuse, and how many placements out-resolve
    the render."""
    recs = [r for r in records if isinstance(r, dict)]
    keys = [object_key(r) for r in recs]
    counts = Counter(k for k in keys if k)
    ppis = [effective_ppi(r) for r in recs]
    known = [p for p in ppis if p is not None]
    above = sum(1 for p in known if p > render_dpi)
    reused = [(k, n) for k, n in counts.items() if n > 1]
    reused.sort(key=lambda kv: (-kv[1], kv[0]))
    dims: dict[str, str] = {}
    for r, k in zip(recs, keys):
        if k and k not in dims and r.get("width") and r.get("height"):
            dims[k] = f"{r['width']}x{r['height']}"
    return {
        "placements": len(recs),
        "distinct": len(counts),
        "unidentified": sum(1 for k in keys if not k),
        "reused_objects": len(reused),
        "most_reused": [{"object": k, "placements": n, "dims": dims.get(k, "")}
                        for k, n in reused[:3]],
        "ppi_known": len(known),
        "ppi_min": min(known) if known else None,
        "ppi_max": max(known) if known else None,
        "above_render_dpi": above,
        "render_dpi": render_dpi,
    }


def format_summary(s: dict) -> list[str]:
    """The two numbers, and the one that decides where image drilling reads."""
    out = [f"  {s['placements']} image placement(s), {s['distinct']} distinct "
           f"XObject(s) ({s['reused_objects']} reused)"]
    for m in s["most_reused"]:
        out.append(f"     most reused: obj {m['object']} x{m['placements']}"
                   + (f" ({m['dims']})" if m["dims"] else ""))
    if s["ppi_known"]:
        out.append(f"     effective ppi {s['ppi_min']:.0f}-{s['ppi_max']:.0f} per "
                   f"placement; {s['above_render_dpi']} of {s['ppi_known']} exceed "
                   f"the {s['render_dpi']:.0f} dpi render "
                   f"(that detail is lost if drilling reads the render)")
    if s["unidentified"]:
        out.append(f"     {s['unidentified']} placement(s) carry no object id — "
                   f"not counted as distinct")
    return out
