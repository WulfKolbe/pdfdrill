# Vendored from ~/BlobTracker/blobcc.py -- streaming connected-component
# analysis with moment aggregates. Pure stdlib on purpose (no numpy), so the
# geometry pass stays keyless. Do not edit here; edit the BlobTracker
# original and re-copy.
"""
blobcc.py — streaming connected-component analysis with moment aggregates.

Pure standard library. No numpy. Mirrors the Bun/TypeScript version 1:1.

Design notes
------------
* Single pass, 8-connectivity, union-find. Emits ("closes") a blob the moment a
  scan line no longer touches it -> bounded memory on an unbounded stream.
* AGGREGATE mode: per blob we keep area, bounding box, and the first/second
  spatial moments. That is O(1) memory per blob AND gives the principal-axis
  orientation for free -> skew estimation. Optional run-length list (keep_runs)
  for reconstruction.
* AXIS-AGNOSTIC: the tracker processes abstract "lines". The reader decides
  whether a line is an image ROW (row-major scan) or an image COLUMN
  (column-major scan). Blob geometry is always stored in true image (x, y),
  so orientation/skew come out correct regardless of scan direction.

  Why scan by COLUMN: a horizontal rule (\\hline, table border) is swept along
  its length and isolated as one long high-aspect blob whose principal axis is
  the document skew angle.
"""

from __future__ import annotations
import math
from typing import Iterator, Callable, Optional


class UnionFind:
    __slots__ = ("parent", "size")

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}
        self.size: dict[int, int] = {}

    def make_set(self, x: int) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.size[x] = 1

    def find(self, x: int) -> int:
        if x not in self.parent:
            self.make_set(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # path compression
        cur = x
        while self.parent[cur] != root:
            self.parent[cur], cur = root, self.parent[cur]
        return root

    def union(self, a: int, b: int) -> int:
        """Union by size; RETURNS the surviving root."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        return ra


class Blob:
    """Moment-aggregate blob. Coordinates are true image (x, y)."""
    __slots__ = ("label", "area", "min_x", "min_y", "max_x", "max_y",
                 "sum_x", "sum_y", "sum_xx", "sum_yy", "sum_xy", "runs")

    def __init__(self, label: int) -> None:
        self.label = label
        self.area = 0
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf
        self.sum_x = 0.0
        self.sum_y = 0.0
        self.sum_xx = 0.0
        self.sum_yy = 0.0
        self.sum_xy = 0.0
        self.runs: list[tuple[int, int, int]] = []  # (y, x0, x1) in image coords

    def add_segment(self, x0: int, x1: int, y: int, keep_runs: bool) -> None:
        """Add a horizontal-in-image-space run [x0..x1] at row y."""
        n = x1 - x0 + 1
        self.area += n
        if x0 < self.min_x: self.min_x = x0
        if x1 > self.max_x: self.max_x = x1
        if y < self.min_y: self.min_y = y
        if y > self.max_y: self.max_y = y
        # closed-form moment sums over the run, no per-pixel loop:
        sx = (x0 + x1) * n / 2.0                       # Σx
        sxx = sum_sq(x0, x1)                            # Σx²
        self.sum_x += sx
        self.sum_y += y * n
        self.sum_xx += sxx
        self.sum_yy += (y * y) * n
        self.sum_xy += y * sx                          # Σ(x·y) = y·Σx for fixed y
        if keep_runs:
            self.runs.append((y, x0, x1))

    def add_vsegment(self, y0: int, y1: int, x: int, keep_runs: bool) -> None:
        """Add a vertical-in-image-space run [y0..y1] at column x (column scan)."""
        n = y1 - y0 + 1
        self.area += n
        if x < self.min_x: self.min_x = x
        if x > self.max_x: self.max_x = x
        if y0 < self.min_y: self.min_y = y0
        if y1 > self.max_y: self.max_y = y1
        sy = (y0 + y1) * n / 2.0
        syy = sum_sq(y0, y1)
        self.sum_x += x * n
        self.sum_y += sy
        self.sum_xx += (x * x) * n
        self.sum_yy += syy
        self.sum_xy += x * sy
        if keep_runs:
            self.runs.append((x, y0, y1))  # note: (line, lo, hi) in column space

    def merge(self, o: "Blob") -> None:
        self.area += o.area
        if o.min_x < self.min_x: self.min_x = o.min_x
        if o.min_y < self.min_y: self.min_y = o.min_y
        if o.max_x > self.max_x: self.max_x = o.max_x
        if o.max_y > self.max_y: self.max_y = o.max_y
        self.sum_x += o.sum_x
        self.sum_y += o.sum_y
        self.sum_xx += o.sum_xx
        self.sum_yy += o.sum_yy
        self.sum_xy += o.sum_xy
        if o.runs:
            self.runs.extend(o.runs)

    # ---- derived geometry ----
    @property
    def centroid(self) -> tuple[float, float]:
        return (self.sum_x / self.area, self.sum_y / self.area)

    @property
    def central_moments(self) -> tuple[float, float, float]:
        """Return (mu20, mu02, mu11) — central second moments / area."""
        a = self.area
        cx, cy = self.sum_x / a, self.sum_y / a
        mu20 = self.sum_xx / a - cx * cx
        mu02 = self.sum_yy / a - cy * cy
        mu11 = self.sum_xy / a - cx * cy
        return mu20, mu02, mu11

    @property
    def orientation_rad(self) -> float:
        """Angle of the principal (major) axis vs +x, in radians, range (-pi/2, pi/2]."""
        mu20, mu02, mu11 = self.central_moments
        return 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)

    @property
    def orientation_deg(self) -> float:
        return math.degrees(self.orientation_rad)

    @property
    def elongation(self) -> float:
        """Major/minor axis ratio from the covariance eigenvalues (>=1; inf for a line)."""
        mu20, mu02, mu11 = self.central_moments
        common = math.sqrt(max(0.0, (mu20 - mu02) ** 2 + 4.0 * mu11 * mu11))
        l1 = (mu20 + mu02 + common) / 2.0
        l2 = (mu20 + mu02 - common) / 2.0
        if l2 <= 1e-9:
            return math.inf
        return math.sqrt(l1 / l2)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (int(self.min_x), int(self.min_y), int(self.max_x), int(self.max_y))


def sum_sq(a: int, b: int) -> int:
    """Σ i² for i in [a..b], closed form."""
    f = lambda n: n * (n + 1) * (2 * n + 1) // 6
    lo = f(a - 1) if a > 0 else (-f(-a) if a < 0 else 0)
    return f(b) - lo


class BlobTracker:
    """
    axis = 'row' : each line is an image row; position index = x, line index = y.
    axis = 'col' : each line is an image column; position index = y, line index = x.
    Either way blob geometry is recorded in image (x, y).
    """
    def __init__(self, axis: str = "row", keep_runs: bool = False) -> None:
        assert axis in ("row", "col")
        self.axis = axis
        self.keep_runs = keep_runs
        self._next = 1
        self.uf = UnionFind()
        self.active: dict[int, Blob] = {}   # keyed by uf root, always
        self.closed: list[Blob] = []

    def _merge(self, a: int, b: int) -> int:
        ra, rb = self.uf.find(a), self.uf.find(b)
        if ra == rb:
            return ra
        root = self.uf.union(ra, rb)
        loser = rb if root == ra else ra
        keep = self.active.get(root)
        drop = self.active.get(loser)
        if drop is not None:
            if keep is not None:
                keep.merge(drop)
            else:
                drop.label = root
                self.active[root] = drop
        self.active.pop(loser, None)
        s = self.active.get(root)
        if s is not None:
            s.label = root
        return root

    def process_line(self, line: list[int], prev_labels: list[int],
                     line_index: int, length: int) -> tuple[list[int], list[Blob]]:
        cur = [0] * length

        # 1. runs along this line
        runs: list[tuple[int, int]] = []
        start = -1
        for i in range(length):
            if line[i] == 1:
                if start == -1:
                    start = i
            elif start != -1:
                runs.append((start, i - 1)); start = -1
        if start != -1:
            runs.append((start, length - 1))

        # 2. label + connect to previous line
        for s, e in runs:
            roots: set[int] = set()
            if line_index > 0:
                lo, hi = max(0, s - 1), min(length - 1, e + 1)
                for i in range(lo, hi + 1):
                    l = prev_labels[i]
                    if l > 0:
                        roots.add(self.uf.find(l))
            if not roots:
                root = self._next; self._next += 1
                self.uf.make_set(root)
                self.active[root] = Blob(root)
            else:
                it = iter(roots)
                root = next(it)
                for r in roots:
                    root = self._merge(root, r)

            blob = self.active[root]
            for i in range(s, e + 1):
                cur[i] = root
            # 3. record run with correct image-space mapping
            if self.axis == "row":
                blob.add_segment(s, e, line_index, self.keep_runs)   # x in [s,e], y=line
            else:
                blob.add_vsegment(s, e, line_index, self.keep_runs)  # y in [s,e], x=line

        # 4. closure: roots not touched this line are done
        touched = set()
        for i in range(length):
            if cur[i] > 0:
                touched.add(self.uf.find(cur[i]))
        closed_now: list[Blob] = []
        for root in [r for r in self.active if r not in touched]:
            closed_now.append(self.active.pop(root))
        self.closed.extend(closed_now)
        return cur, closed_now

    def finish(self) -> list[Blob]:
        rest = list(self.active.values())
        self.closed.extend(rest)
        self.active.clear()
        return rest


# ----------------------------------------------------------------------------
# PGM/PPM reader (binary P5/P6 and ASCII P2/P3), stdlib only.
# ----------------------------------------------------------------------------

def _read_token(buf: bytes, pos: int) -> tuple[bytes, int]:
    n = len(buf)
    while pos < n and buf[pos:pos+1].isspace():
        pos += 1
    if pos < n and buf[pos:pos+1] == b"#":            # comment to EOL
        while pos < n and buf[pos:pos+1] not in (b"\n", b"\r"):
            pos += 1
        return _read_token(buf, pos)
    start = pos
    while pos < n and not buf[pos:pos+1].isspace():
        pos += 1
    return buf[start:pos], pos


def read_pnm(path: str) -> tuple[int, int, list[int]]:
    """Return (width, height, gray[0..255] row-major)."""
    with open(path, "rb") as f:
        buf = f.read()
    magic, pos = _read_token(buf, 0)
    magic = magic.decode()
    w_tok, pos = _read_token(buf, pos); width = int(w_tok)
    h_tok, pos = _read_token(buf, pos); height = int(h_tok)
    gray: list[int] = []
    if magic in ("P5", "P6"):
        mx_tok, pos = _read_token(buf, pos); _ = int(mx_tok)
        pos += 1  # single whitespace after maxval
        data = buf[pos:]
        if magic == "P5":
            gray = list(data[: width * height])
        else:  # P6 rgb -> luma
            for i in range(width * height):
                r, g, b = data[3*i], data[3*i+1], data[3*i+2]
                gray.append((r * 299 + g * 587 + b * 114) // 1000)
    elif magic in ("P2", "P3"):
        mx_tok, pos = _read_token(buf, pos); _ = int(mx_tok)
        vals: list[int] = []
        need = width * height * (3 if magic == "P3" else 1)
        while len(vals) < need:
            t, pos = _read_token(buf, pos)
            vals.append(int(t))
        if magic == "P2":
            gray = vals
        else:
            for i in range(width * height):
                r, g, b = vals[3*i], vals[3*i+1], vals[3*i+2]
                gray.append((r * 299 + g * 587 + b * 114) // 1000)
    else:
        raise ValueError(f"unsupported PNM magic {magic!r}")
    return width, height, gray


def binarize(gray: list[int], threshold: int = 128, ink_is_dark: bool = True) -> list[int]:
    """1 = foreground (ink). Documents are dark ink on light paper by default."""
    if ink_is_dark:
        return [1 if v < threshold else 0 for v in gray]
    return [1 if v >= threshold else 0 for v in gray]


def iter_lines(binary: list[int], width: int, height: int, axis: str) -> Iterator[tuple[int, list[int]]]:
    if axis == "row":
        for y in range(height):
            base = y * width
            yield y, binary[base: base + width]
    elif axis == "col":
        for x in range(width):
            yield x, [binary[y * width + x] for y in range(height)]
    else:
        raise ValueError(axis)


def scan(binary: list[int], width: int, height: int, axis: str = "row",
         keep_runs: bool = False,
         on_close: Optional[Callable[[Blob], None]] = None) -> list[Blob]:
    t = BlobTracker(axis=axis, keep_runs=keep_runs)
    length = width if axis == "row" else height
    prev = [0] * length
    for idx, line in iter_lines(binary, width, height, axis):
        cur, closed_now = t.process_line(line, prev, idx, length)
        if on_close:
            for b in closed_now:
                on_close(b)
        prev = cur
    final = t.finish()
    if on_close:
        for b in final:
            on_close(b)
    return t.closed


# ----------------------------------------------------------------------------
# Skew estimation from rule-like blobs.
# ----------------------------------------------------------------------------

def estimate_skew_deg(blobs: list[Blob], min_elong: float = 8.0,
                      max_angle: float = 30.0, min_length: int = 20) -> Optional[float]:
    """
    Median principal-axis angle over elongated, near-horizontal blobs (rules).
    Positive = rotated counter-clockwise (PIL convention). None if no candidates.
    """
    angles: list[float] = []
    for b in blobs:
        if b.elongation < min_elong:
            continue
        # Negate: image arrays have y pointing DOWN, so a CCW page rotation
        # shows up as a negative principal-axis angle. Flip to report the
        # standard "positive = counter-clockwise" deskew angle (PIL convention).
        ang = -b.orientation_deg
        if abs(ang) > max_angle:
            continue
        if (b.max_x - b.min_x) < min_length:
            continue
        angles.append(ang)
    if not angles:
        return None
    angles.sort()
    n = len(angles)
    return angles[n // 2] if n % 2 else (angles[n//2 - 1] + angles[n//2]) / 2.0


# ----------------------------------------------------------------------------
# TiddlyWiki tiddler emit.
# ----------------------------------------------------------------------------

def blob_to_tiddler(b: Blob, prefix: str = "blob") -> dict:
    x0, y0, x1, y1 = b.box
    cx, cy = b.centroid
    elong = b.elongation
    kind = "rule" if (elong >= 8.0 and abs(b.orientation_deg) <= 30.0) else "mark"
    return {
        "title": f"{prefix}/{b.label}",
        "tags": f"blob {kind}",
        "blob.area": str(b.area),
        "blob.x0": str(x0), "blob.y0": str(y0),
        "blob.x1": str(x1), "blob.y1": str(y1),
        "blob.cx": f"{cx:.2f}", "blob.cy": f"{cy:.2f}",
        "blob.angle_deg": f"{b.orientation_deg:.3f}",
        "blob.elongation": ("inf" if math.isinf(elong) else f"{elong:.2f}"),
        "blob.kind": kind,
        "text": f"Blob {b.label}: {kind}, area {b.area}, "
                f"bbox ({x0},{y0})-({x1},{y1}), angle {b.orientation_deg:.2f}°.",
    }
