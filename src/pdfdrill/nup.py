r"""N-UP SHEETS: one scanned sheet carrying several printed pages, and back.

WHY THIS IS A LAYER AND NOT A TUNING PARAMETER
----------------------------------------------
A scanned sheet is not always a printed page. `penev_A` is a thesis
photographed four printed pages to a sheet, in the duplex imposition — sheet 2
carries the pages MathPix's folios call `iv`, `v`, `vi`, `vii`, and sheet 8
carries `19`, `20`, `21`, `22`. 22 sheets, 88 printed pages.

Everything in the model lane assumed one printed page per sheet, and MEASURED
on penev_A that assumption cost both halves of the reading:

    the PAID stage cut six FULL-WIDTH strips, so every strip spanned all four
    printed pages and the model had to choose an order inside it. It chose
    sensibly and locally -- and the choice was per strip, so the sheet's four
    pages interleaved at the strip boundaries: 94% of MathPix's words were
    present and only 71% in its order.

    the FREE stage aligned ONE item sequence against FULL-WIDTH ink rows,
    where four printed pages share every row: 81 ink rows for 144 items on
    sheet 5, rows spanning 317 px where the line pitch is 48, and boxes
    landing on every fourth item. 474 of 3,080 reference lines boxed (15%).

No threshold reaches that, because the aligner was not inaccurate — it was
describing the wrong object. So the lane reads PRINTED pages, and this module
is the two directions of the map between them and the sheets the PDF has:

    detect/split   sheet image  -> the printed pages on it, in reading order
    merge          a reading of the printed pages -> sheet coordinates

MERGE IS NOT OPTIONAL, AND THAT IS THE DESIGN
---------------------------------------------
`page` in a lines.json indexes the PDF's OWN pages. `inspect` renders page
`page` to draw the boxes on, `crop` cuts out of that render, and `model` tells
a reader which page to turn to. A lines.json with 88 pages for a 22-page PDF
would have every one of those consumers rasterizing a page that does not
exist — the T-0024 failure class, where a box is drawn over a page that looks
right and is not. So the reading goes back to sheet coordinates before it is
written, and keeps `nup_page` to say which printed page a line came from.

For a 1-up document `detect` returns the whole sheet as its one page and
`merge` is the identity. That is deliberately the SAME code path and not a
branch: a lane with a rarely-exercised special case for the common document
is a lane whose common case is the untested one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import inkbox

Box = tuple[int, int, int, int]

#: A column (or row) of the sheet is BLANK when this share or less of it is
#: ink. Not zero: a scan's gutter carries fold shadow, dust and the bleed of
#: the facing page, and a hard zero finds no gutter on any real scan.
BLANK = 0.002

#: A blank run must be at least this share of the profile's length to be a
#: gutter. Below it, the white between two printed words qualifies.
MIN_RUN = 0.004

#: Where a gutter is looked for, as a share of the sheet. The imposition puts
#: it at the middle; these windows say how far from the middle a real one has
#: been seen to sit. The vertical window is wider because a sheet's two halves
#: are rarely the same height on the platen.
GUTTER_X = (0.40, 0.60)
GUTTER_Y = (0.35, 0.65)

#: Both sides of a candidate gutter must carry at least this share of the
#: sheet's ink. This is the test that keeps a 1-up document 1-up: a wide
#: margin, a half-empty last page or the blank verso of a plate all produce a
#: blank run near the middle, and none of them is a gutter.
SIDE_INK = 0.12

#: Reading orders for a 2x2 sheet. `column` finishes a column before moving
#: right (the duplex imposition: penev_A sheet 10 holds 27, 28, 29, 30 in that
#: order). `row` finishes a band before moving down, which is what a 4-up
#: photocopy of single sheets usually gives.
ORDERS = ("column", "row")


@dataclass
class Sheet:
    """The printed pages found on one sheet, in reading order."""
    pages: list[Box]
    #: Human-readable shape: "1-up", "2-up", "2x2", "3-up"...
    kind: str
    #: The gutters that were found, for the record and for a diagnostic.
    gutter_x: Optional[int] = None
    gutter_y: list[Optional[int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.gutter_y is None:
            self.gutter_y = []

    @property
    def n(self) -> int:
        return len(self.pages)


# --------------------------------------------------------------------------- #
#  Finding the gutter
# --------------------------------------------------------------------------- #

def blank_runs(profile, lo: int, hi: int, min_run: int) -> list[tuple[int, int]]:
    """Half-open runs of `profile < BLANK`, at least `min_run` long, in
    `[lo, hi)`."""
    out: list[tuple[int, int]] = []
    start: Optional[int] = None
    hi = min(hi, len(profile))
    for i in range(max(0, lo), hi + 1):
        blank = i < hi and float(profile[i]) < BLANK
        if blank:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_run:
                out.append((start, i))
            start = None
    return out


def middle_blank(profile, lo: int, hi: int, min_run: int) -> Optional[int]:
    """Centre of the blank run NEAREST THE MIDDLE of the whole profile, or None.

    Nearest the middle and NOT the widest, which is the detail that makes this
    work on a real page: a sparse printed page — the last page of a chapter,
    a page holding one figure — has a blank run inside it far wider than the
    gutter, and the widest-run rule puts the cut through the middle of a page's
    text. The imposition, by contrast, always puts the gutter at the middle.
    """
    runs = blank_runs(profile, lo, hi, min_run)
    if not runs:
        return None
    mid = len(profile) / 2.0

    def distance(run: tuple[int, int]) -> float:
        a, b = run
        if a <= mid <= b:
            return 0.0
        return min(abs(a - mid), abs(b - mid))

    a, b = min(runs, key=distance)
    return (a + b) // 2


def _ink_mask(gray, threshold: Optional[int] = None):
    thr = inkbox.otsu(gray) if threshold is None else int(threshold)
    return gray <= thr


def detect(gray, *, order: str = "column",
           threshold: Optional[int] = None) -> Sheet:
    """The printed pages on one sheet image, in reading order.

    Columns first (a vertical gutter near the middle), then each column's own
    horizontal gutter, which is looked for INDEPENDENTLY per column: a sheet
    whose left half holds two pages and whose right half holds one is a real
    sheet (the last sheet of a chapter), and a shape that forces both halves to
    agree reads one of them wrong.
    """
    if order not in ORDERS:
        raise ValueError(f"unknown n-up order {order!r}; expected one of {ORDERS}")
    np = inkbox._require_numpy()
    mask = _ink_mask(gray, threshold)
    h, w = mask.shape
    total = float(mask.sum())
    if total <= 0:
        return Sheet([(0, 0, w, h)], "1-up")

    cols = mask.mean(axis=0)
    gx = middle_blank(cols, int(w * GUTTER_X[0]), int(w * GUTTER_X[1]),
                      max(1, int(w * MIN_RUN)))
    if gx is not None:
        left = float(mask[:, :gx].sum()) / total
        right = float(mask[:, gx:].sum()) / total
        if min(left, right) < SIDE_INK:
            gx = None                      # a margin, not a gutter
    spans = [(0, gx), (gx, w)] if gx is not None else [(0, w)]

    columns: list[list[Box]] = []
    guts: list[Optional[int]] = []
    for x0, x1 in spans:
        # A BAND gutter is looked for only INSIDE a column a vertical gutter
        # made, and this asymmetry is the whole reliability of the detector.
        # Printed text runs across the full measure, so a blank vertical
        # channel through the middle of a page is extraordinary -- but a blank
        # horizontal band through the middle is ORDINARY: the gap between two
        # paragraphs, above a display formula, around a figure. MEASURED, with
        # the band gutter sought unconditionally: all three of killing20's
        # probe sheets, two of collatz14's and one of hilbert10's were cut in
        # half through their own text. Requiring the column first makes those
        # three documents 1-up again and still reads penev_A as 2x2, because
        # its vertical gutter is real.
        #
        # The cost is a document imposed two pages STACKED with no vertical
        # gutter, which reads as 1-up. That is the pre-existing behaviour, it
        # is rare, and `--nup 1x2` says so explicitly. A false POSITIVE cuts an
        # ordinary page through the middle of a sentence; a false negative
        # leaves the lane where it already was. They are not symmetric.
        if gx is None:
            guts.append(None)
            columns.append([(x0, 0, x1, h)])
            continue
        band = mask[:, x0:x1]
        rows = band.mean(axis=1)
        gy = middle_blank(rows, int(h * GUTTER_Y[0]), int(h * GUTTER_Y[1]),
                          max(1, int(h * MIN_RUN)))
        if gy is not None:
            bt = float(band[:gy].sum())
            bb = float(band[gy:].sum())
            if min(bt, bb) / max(1.0, bt + bb) < SIDE_INK:
                gy = None
        guts.append(gy)
        if gy is None:
            columns.append([(x0, 0, x1, h)])
        else:
            columns.append([(x0, 0, x1, gy), (x0, gy, x1, h)])

    if order == "row" and len({len(c) for c in columns}) == 1:
        pages = [c[b] for b in range(len(columns[0])) for c in columns]
    else:
        pages = [p for c in columns for p in c]

    kind = "1-up"
    if len(pages) == 2:
        kind = "2-up"
    elif len(pages) == 4 and len(columns) == 2:
        kind = "2x2"
    elif len(pages) > 1:
        kind = f"{len(pages)}-up"
    return Sheet(pages, kind, gutter_x=gx, gutter_y=guts)


# --------------------------------------------------------------------------- #
#  The DOCUMENT's shape, which is not a per-sheet question
# --------------------------------------------------------------------------- #

@dataclass
class Shape:
    """The imposition of a whole document: how many columns and bands a sheet
    is cut into, and where the cuts go when a sheet does not show them."""
    columns: int
    bands: int
    #: Median gutter positions as a SHARE of the sheet, so they survive sheets
    #: of different pixel sizes (a scan's pages differ by a few per cent).
    gutter_x: Optional[float] = None
    gutter_y: Optional[float] = None
    #: How many sheets voted for this shape, out of how many measured.
    votes: int = 0
    sheets: int = 0

    @property
    def n(self) -> int:
        return self.columns * self.bands

    @property
    def kind(self) -> str:
        if self.n == 1:
            return "1-up"
        if self.columns == 2 and self.bands == 1:
            return "2-up"
        if self.columns == 2 and self.bands == 2:
            return "2x2"
        return f"{self.columns}x{self.bands}"


def shape(grays: Iterable, *, order: str = "column") -> Shape:
    """Decide ONE imposition for the whole document, by majority of its sheets.

    MEASURED on penev_A, and the reason this is not a per-sheet decision: the
    per-sheet detector reads 19 of 22 sheets as 2x2 and the other three as
    2-up or 3-up — sheet 1 (dedication, a blank verso, the copyright notice
    and folio `iii`), sheet 3 (the end of the contents) and sheet 16. Those
    three really do carry four printed pages; what they do not carry is enough
    ink on one of the four to prove the gutter, and `SIDE_INK` rejects it.

    Trusting each sheet leaves 84 printed pages where there are 88, and the
    four it loses are each merged into a neighbour — which puts the strips
    back across a page boundary on exactly the sheets that are hardest to
    read. A sheet's own gutter is still used where it was found; the shape only
    decides HOW MANY cuts, and the document median says where they go when a
    sheet is too sparse to say.
    """
    seen: list[Sheet] = []
    for gray in grays:
        seen.append(detect(gray, order=order))
    if not seen:
        return Shape(1, 1, votes=0, sheets=0)
    counts: dict[tuple[int, int], int] = {}
    for sh in seen:
        cols = 2 if sh.gutter_x is not None else 1
        # bands = the most any one column of this sheet was cut into. A sheet
        # whose left half split and whose right half did not still votes 2:
        # one half proving the band gutter is proof the imposition has one.
        per_col = [2 if g is not None else 1 for g in (sh.gutter_y or [None])]
        bands = max(per_col) if per_col else 1
        counts[(cols, bands)] = counts.get((cols, bands), 0) + 1
    (cols, bands), votes = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    xs = [sh.gutter_x / float(_width(sh)) for sh in seen
          if sh.gutter_x is not None and _width(sh)]
    ys = [g / float(_height(sh)) for sh in seen for g in (sh.gutter_y or [])
          if g is not None and _height(sh)]
    return Shape(cols, bands,
                 gutter_x=_median(xs) if cols > 1 else None,
                 gutter_y=_median(ys) if bands > 1 else None,
                 votes=votes, sheets=len(seen))


def _width(sh: Sheet) -> int:
    return max((b[2] for b in sh.pages), default=0)


def _height(sh: Sheet) -> int:
    return max((b[3] for b in sh.pages), default=0)


def _median(xs: Sequence[float]) -> Optional[float]:
    xs = sorted(xs)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def parse_shape(spec: str) -> Optional[Shape]:
    """`"auto"` -> None (detect); `"1"` -> 1-up; `"2x2"`, `"1x2"`, `"3x1"` ->
    that imposition, columns x bands, taken on the operator's word.

    The explicit form exists for the two cases detection cannot reach: pages
    imposed STACKED with no vertical gutter (`1x2`), which the band-gutter
    rule deliberately refuses to guess, and a document this detector reads
    wrong, where an operator who can see the sheets should not have to argue
    with it.
    """
    spec = (spec or "auto").strip().lower()
    if spec in ("", "auto"):
        return None
    if spec == "1":
        return Shape(1, 1)
    if "x" in spec:
        a, _, b = spec.partition("x")
        try:
            cols, bands = int(a), int(b)
        except ValueError:
            raise ValueError(f"--nup {spec!r}: expected auto, 1, or CxB "
                             f"(columns x bands), e.g. 2x2") from None
        if cols < 1 or bands < 1 or cols * bands > 16:
            raise ValueError(f"--nup {spec!r}: columns and bands must be "
                             f"1..16 and their product at most 16")
        return Shape(cols, bands)
    raise ValueError(f"--nup {spec!r}: expected auto, 1, or CxB "
                     f"(columns x bands), e.g. 2x2")


def pages_for(gray, shp: Shape, *, order: str = "column") -> Sheet:
    """Cut one sheet into `shp.n` printed pages, preferring ITS OWN gutters.

    The shape fixes the number of cuts; this sheet's own measurement places
    them when it can, and the document median places them when it cannot. So a
    sparse sheet is cut in the right number of pieces at very nearly the right
    place, instead of being left whole.
    """
    h, w = gray.shape
    if shp.n <= 1:
        return Sheet([(0, 0, w, h)], "1-up")
    own = detect(gray, order=order)

    # Two columns is the imposition that exists, so it is the one whose cut is
    # MEASURED; anything else is divided evenly, which is what an operator who
    # typed `--nup 3x1` is asking for.
    gx = None
    if shp.columns == 2:
        gx = own.gutter_x
        if gx is None and shp.gutter_x is not None:
            gx = int(round(shp.gutter_x * w))
        if gx is None:
            gx = w // 2
        xcuts = [0, gx, w]
    else:
        xcuts = [round(i * w / shp.columns) for i in range(shp.columns + 1)]

    columns: list[list[Box]] = []
    for idx in range(len(xcuts) - 1):
        x0, x1 = xcuts[idx], xcuts[idx + 1]
        if shp.bands == 1:
            columns.append([(x0, 0, x1, h)])
            continue
        if shp.bands == 2:
            found = own.gutter_y or []
            gy = found[idx] if idx < len(found) else None
            if gy is None and shp.gutter_y is not None:
                gy = int(round(shp.gutter_y * h))
            if gy is None:
                gy = h // 2
            ycuts = [0, gy, h]
        else:
            ycuts = [round(i * h / shp.bands) for i in range(shp.bands + 1)]
        columns.append([(x0, ycuts[b], x1, ycuts[b + 1])
                        for b in range(len(ycuts) - 1)])
    if order == "row" and len({len(c) for c in columns}) == 1:
        pages = [c[b] for b in range(len(columns[0])) for c in columns]
    else:
        pages = [p for c in columns for p in c]
    return Sheet(pages, shp.kind, gutter_x=gx,
                 gutter_y=[c[0][3] if len(c) > 1 else None for c in columns])


# --------------------------------------------------------------------------- #
#  Splitting, and the map back
# --------------------------------------------------------------------------- #

def split(sheets: Sequence[tuple[int, Path]], out_dir: Path, *,
          order: str = "column", nup: str = "auto") -> dict:
    """Cut each sheet into its printed pages; return the map, and write it.

    `sheets` is (sheet_number, sheet_png) in order. `nup` is `"auto"`, `"1"`
    or `"CxB"` — see `parse_shape`. Detection runs over ALL the sheets before
    any is cut, because the imposition is a property of the document.

    The map is keyed by the printed page number, 1.. over the whole document:

        {"3": {"sheet": 1, "box": [x0, y0, x1, y1],
               "sheet_size": [w, h], "kind": "2x2"}}

    It is written to `out_dir/nup.json` because every later stage needs it and
    none of them should re-derive it: a map re-derived from a re-rendered page
    is a map that can disagree with the one the reading was made against.
    """
    from PIL import Image
    out_dir = Path(out_dir)
    forced = parse_shape(nup)
    shp = forced if forced is not None else shape(
        (inkbox.load_gray(p) for _n, p in sheets), order=order)

    # The map is computed in full BEFORE anything is written, so it can be
    # compared with the one already there.
    plan: list[tuple[int, Path, Box, str]] = []
    amap: dict[str, dict] = {}
    n = 0
    for sheet_no, png in sheets:
        with Image.open(png) as im:
            w, h = im.size
        sh = (Sheet([(0, 0, w, h)], "1-up") if shp.n <= 1
              else pages_for(inkbox.load_gray(png), shp, order=order))
        for box in sh.pages:
            n += 1
            plan.append((n, png, box, sh.kind))
            amap[str(n)] = {"sheet": sheet_no, "box": list(box),
                            "sheet_size": [w, h], "kind": sh.kind}

    # A PRINTED PAGE NUMBER IS ONLY MEANINGFUL UNDER ONE MAP. The per-page
    # Markdown the paid read writes is named for the printed page, so if the
    # map changes — a different `--nup`, a different `--nup-order`, or this
    # document read once before the split existed — page 1 means a different
    # picture than the page-1 Markdown on disk was read from, and a resumed
    # run would serve it anyway. MEASURED as a live hazard on penev_A: the
    # first reading numbered its 22 SHEETS 1..22 and the split numbers its 88
    # printed pages 1..88, so pages 1-22 would have been resumed from a
    # reading of four times as much page.
    #
    # The old directory is MOVED and not removed, because what is in it was
    # paid for. An operator who split a document two ways has both readings.
    old = out_dir / "nup.json"
    if old.is_file():
        try:
            same = load_map(old) == amap
        except (OSError, ValueError):
            same = False
        if not same:
            stamp = 1
            while (out_dir.parent / f"{out_dir.name}-was{stamp}").exists():
                stamp += 1
            out_dir.rename(out_dir.parent / f"{out_dir.name}-was{stamp}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for num, png, box, kind in plan:
        dst = out_dir / f"page-{num:04d}.png"
        if dst.is_file():
            continue
        with Image.open(png) as im:
            gray = im.convert("L")
            if box == (0, 0, gray.size[0], gray.size[1]):
                gray.save(dst)
            else:
                gray.crop(box).save(dst)
    (out_dir / "nup.json").write_text(json.dumps(amap, indent=1),
                                      encoding="utf-8")
    return amap


def load_map(path: Path) -> dict:
    return {str(k): v for k, v in
            json.loads(Path(path).read_text(encoding="utf-8")).items()}


def is_identity(amap: dict) -> bool:
    """True when every sheet holds exactly one printed page — `merge` would
    only renumber. Worth asking so a 1-up document's reading is byte-identical
    to what the lane wrote before this module existed."""
    seen: dict[int, int] = {}
    for m in amap.values():
        seen[m["sheet"]] = seen.get(m["sheet"], 0) + 1
    return all(v == 1 for v in seen.values())


def merge(doc: dict, amap: dict) -> dict:
    """A reading of the printed pages -> the same reading in SHEET coordinates.

    Every region is scaled from the printed page's own pixels into the sheet's
    and offset by the page's position on it; `nup_page` keeps the printed page
    a line came from and `line` is renumbered over the sheet in reading order.
    `cnt`, when present, travels with the region — MathPix's four-point
    polygon is the same box said twice, and a consumer reading one and not the
    other is a consumer that gets a stale answer.
    """
    pages_in = sorted(doc.get("pages") or [], key=lambda p: p.get("page", 0))
    sheets: dict[int, dict] = {}
    for p in pages_in:
        m = amap.get(str(p.get("page")))
        if m is None:                     # no map entry: pass the page through
            sheets.setdefault(p.get("page", 0), dict(p, lines=[]))
            sheets[p.get("page", 0)]["lines"].extend(p.get("lines") or [])
            continue
        x0, y0, x1, y1 = m["box"]
        sw, sh = m["sheet_size"]
        pw = p.get("page_width") or (x1 - x0) or 1
        ph = p.get("page_height") or (y1 - y0) or 1
        sx = (x1 - x0) / float(pw)
        sy = (y1 - y0) / float(ph)
        s = sheets.setdefault(m["sheet"], {
            "page": m["sheet"], "page_width": int(sw), "page_height": int(sh),
            "image_id": "", "lines": [], "parse_status": "parsed",
            "fallback_count": 0, "page_confidence": None,
            "languages_detected": [],
        })
        s["fallback_count"] = s.get("fallback_count", 0) + (
            p.get("fallback_count") or 0)
        for line in p.get("lines") or []:
            line = dict(line)
            reg = line.get("region") or {}
            if reg.get("width") or reg.get("height"):
                nx = x0 + reg.get("top_left_x", 0) * sx
                ny = y0 + reg.get("top_left_y", 0) * sy
                nw = reg.get("width", 0) * sx
                nh = reg.get("height", 0) * sy
                line["region"] = {"top_left_x": int(round(nx)),
                                  "top_left_y": int(round(ny)),
                                  "width": int(round(nw)),
                                  "height": int(round(nh))}
                line["cnt"] = [[int(round(nx)), int(round(ny))],
                               [int(round(nx + nw)), int(round(ny))],
                               [int(round(nx + nw)), int(round(ny + nh))],
                               [int(round(nx)), int(round(ny + nh))]]
            if line.get("math_regions"):
                line["math_regions"] = [
                    {"top_left_x": int(round(x0 + r.get("top_left_x", 0) * sx)),
                     "top_left_y": int(round(y0 + r.get("top_left_y", 0) * sy)),
                     "width": int(round(r.get("width", 0) * sx)),
                     "height": int(round(r.get("height", 0) * sy))}
                    for r in line["math_regions"]]
            line["nup_page"] = p.get("page")
            line["page"] = m["sheet"]
            line["line"] = len(s["lines"]) + 1
            s["lines"].append(line)
    out = {k: v for k, v in doc.items() if k != "pages"}
    out["pages"] = [sheets[k] for k in sorted(sheets)]
    return out


def folios(doc: dict) -> list[tuple[int, str]]:
    """(printed page, folio) for every `page_info` line that is only a number.

    The reading order of a 2x2 sheet cannot be read off the image — the
    imposition decides it, and both orders produce four plausible pages. What
    CAN be checked is the result: the printed folios must ascend. This is the
    evidence for `--nup-order`, and it is available only after the read, which
    is why it is a reporting function and not a detector.
    """
    out: list[tuple[int, str]] = []
    for p in doc.get("pages") or []:
        for line in p.get("lines") or []:
            if line.get("type") != "page_info":
                continue
            text = (line.get("text") or "").strip()
            if text and len(text) <= 6 and not any(c.isspace() for c in text):
                out.append((line.get("nup_page") or p.get("page"), text))
    return out


def ascending(items: Iterable[tuple[int, str]]) -> tuple[int, int]:
    """(ascending adjacent pairs, comparable adjacent pairs) over arabic
    folios. A reading order that is right gives nearly all of them."""
    nums = [(pg, int(t)) for pg, t in items if t.isdigit()]
    ok = cmp = 0
    for (p1, a), (p2, b) in zip(nums, nums[1:]):
        if p1 == p2:
            continue
        cmp += 1
        if b > a:
            ok += 1
    return ok, cmp
