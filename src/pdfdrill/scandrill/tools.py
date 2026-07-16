"""Integration seams to the external tools that *prepare an optimal PDF*.

Per the project brief: SCANDRILL uses pdfdrill's OCR/analysis and the parallel-dev
image tools (``pylepto`` Leptonica bindings, ``BlobTracker`` blobcc/cropmark/
deskew) **only** to produce a better PDF — none of them is the deliverable. As
those tools land inside pdfdrill they will be reachable the same way; this module
is the single place their call contracts live, so the rest of SCANDRILL never
shells out ad hoc.

Discovery is env-var driven with repo defaults, so nothing here hard-codes a
machine layout:

    PDFDRILL_HOME     (default ~/MX/PDFDRILL)      run via <home>/pdfdrill
    PYLEPTO_HOME      (default ~/pylepto)
    BLOBTRACKER_HOME  (default ~/BlobTracker)
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Config, DEFAULT as DEFAULT_CONFIG


def _home(env: str, default: str) -> Path:
    return Path(os.environ.get(env, os.path.expanduser(default)))


_MISSING = object()
_BT_CACHE: dict = {}


def _fill_for(mode: str, level: int):
    """Background fill matching the image mode (scanp.sh uses -b FFFFFF = white)."""
    if mode in ("L", "1", "I;16", "I"):
        return level
    if mode == "RGBA":
        return (level, level, level, 255)
    return (level, level, level)


def _load_gray(image: str | Path, *, max_px: int = 0):
    """Decode to a grayscale ``list[int]`` for blobcc, optionally downscaled.

    Returns ``(w, h, gray, scale)`` where ``scale`` is the linear factor applied
    (1.0 = none). blobcc's core is pure Python, so a full 300 dpi A4 side (~8.5
    MPx) is expensive; the skew **angle is scale-invariant**, so measuring on a
    reduced copy is sound — but px-denominated thresholds must be scaled by the
    caller. Reduction is BINARY-safe here because we downscale the *grayscale*
    source before binarizing (Image.BILINEAR), not a computed mask.
    """
    from PIL import Image

    with Image.open(image) as im:
        im = im.convert("L")
        w, h = im.size
        scale = 1.0
        if max_px and w * h > max_px:
            scale = (max_px / (w * h)) ** 0.5
            w, h = max(1, int(w * scale)), max(1, int(h * scale))
            im = im.resize((w, h), Image.BILINEAR)
        return w, h, list(im.tobytes()), scale


@dataclass
class SideSkew:
    """One page side's blank + skew measurement (SCANDRILL-owned, tool-agnostic)."""

    is_blank: bool = False
    ink_area: int = 0
    angle_deg: float | None = None
    method: str = "none"          # "blob" | "hough" | "none"
    confidence: float = 0.0
    n_support: int = 0
    spread_deg: float | None = None
    available: bool = True        # False when the measuring tool is missing

    def usable(self, min_conf: float = 0.15) -> bool:
        return self.angle_deg is not None and self.confidence >= min_conf


@dataclass
class SheetSkew:
    """Fused physical skew of one duplex sheet (see deskew.fuse_duplex)."""

    sheet_angle_deg: float | None = None
    front_correction_deg: float | None = None
    back_correction_deg: float | None = None
    source: str = "none"          # "both" | "front" | "back" | "*(disagree)" | "none"
    disagreement_deg: float | None = None


@dataclass
class Tools:
    pdfdrill_home: Path = None  # type: ignore[assignment]
    pylepto_home: Path = None  # type: ignore[assignment]
    blobtracker_home: Path = None  # type: ignore[assignment]

    def __post_init__(self):
        self.pdfdrill_home = self.pdfdrill_home or _home("PDFDRILL_HOME", "~/MX/PDFDRILL")
        self.pylepto_home = self.pylepto_home or _home("PYLEPTO_HOME", "~/pylepto")
        self.blobtracker_home = self.blobtracker_home or _home("BLOBTRACKER_HOME", "~/BlobTracker")

    # ---- capability report -------------------------------------------------------
    def available(self) -> dict[str, bool]:
        """What is reachable AND actually used by the pipeline.

        ``pylepto`` is listed because it is an integration target, but note it is
        **not currently wired into any pipeline path** — skew comes entirely from
        BlobTracker (blobcc fast path + Hough fallback + fuse_duplex). See
        docs/TOPOLOGY-VS-RASTER.md for where it would plug in.
        """
        return {
            "pdfdrill": (self.pdfdrill_home / "pdfdrill").exists(),
            "pdfdrill_sidecar": (self.pdfdrill_home / "src" / "pdfdrill"
                                 / "sidecar.py").exists(),
            "blobtracker_skew": (self.blobtracker_home / "deskew.py").exists(),
            "pylepto (present, NOT wired)": (self.pylepto_home / "test_skew.py").exists(),
        }

    # ---- BlobTracker: blobcc + deskew (the skew seam) ----------------------------
    def _blobtracker(self):
        """Import BlobTracker's ``blobcc`` + ``deskew`` (or None).

        BlobTracker is a flat script collection, not a package — its own
        convention is inserting the script dir into ``sys.path``, so we do the
        same. Cached: the import cost is paid once per process.
        """
        key = str(self.blobtracker_home)
        cached = _BT_CACHE.get(key, _MISSING)
        if cached is not _MISSING:
            return cached
        mods = None
        if (self.blobtracker_home / "deskew.py").exists():
            if key not in sys.path:
                sys.path.insert(0, key)
            try:
                import blobcc, deskew  # noqa: E401  (sibling-import convention)
                mods = (blobcc, deskew)
            except Exception:
                mods = None
        _BT_CACHE[key] = mods
        return mods

    def analyze_side(self, image: str | Path, cfg: Config | None = None,
                     *, measure: bool = True) -> SideSkew:
        """ONE blobcc pass per side → blank check + skew (blob fast path, Hough
        fallback), mirroring ``scand.py:analyze_side``.

        Reusing the single pass for both jobs is the point: the empty check needs
        the blob areas the skew fast path already produced.

        ``measure=False`` runs only the blank/ink check and skips the angle
        estimate — used for ADF back sides, which take ``−front`` by convention.
        A side with ink below ``cfg.skew_min_ink_area`` is *half-empty*: the
        estimate is skipped too (``method="sparse"``), because a sparse page
        yields a confident-looking but wrong angle. Either way fusion supplies
        the angle from the other side.

        Returns ``available=False`` if BlobTracker can't be imported (callers then
        fall back to the raster blank prefilter and record no angle).
        """
        cfg = cfg or DEFAULT_CONFIG
        mods = self._blobtracker()
        if mods is None:
            return SideSkew(available=False)
        blobcc, deskew = mods

        w, h, gray, scale = _load_gray(image, max_px=cfg.skew_max_px)
        binary = blobcc.binarize(gray, threshold=cfg.binarize_threshold,
                                 ink_is_dark=True)

        # Mask the scan borders: ADF edge shadow is ink-dark and would dominate
        # both the ink area and the rule blobs (scand.py EMPTY_BORDER).
        b = max(1, int(cfg.empty_border_px * scale)) if cfg.empty_border_px else 0
        if b:
            for y in range(h):
                row = y * w
                for x in range(b):
                    binary[row + x] = 0
                    binary[row + (w - 1 - x)] = 0
            for y in range(b):
                row, brow = y * w, (h - 1 - y) * w
                for x in range(w):
                    binary[row + x] = 0
                    binary[brow + x] = 0

        blobs = blobcc.scan(binary, w, h, axis="col", keep_runs=False)
        ink = sum(bl.area for bl in blobs)
        # thresholds are px-denominated at 300 dpi → scale with the downscale
        area_scale = scale * scale
        if ink < cfg.empty_min_ink_area * area_scale:
            return SideSkew(is_blank=True, ink_area=int(ink), method="none")

        if not measure:
            # ADF back side: takes −front by convention, so don't pay for (or risk)
            # an independent estimate.
            return SideSkew(is_blank=False, ink_area=int(ink), method="skipped")

        if ink < cfg.skew_min_ink_area * area_scale:
            # Half-empty: enough ink to keep the page, too little to trust an angle.
            return SideSkew(is_blank=False, ink_area=int(ink), method="sparse")

        r = deskew.estimate_skew(
            binary, w, h,
            blobs=blobs,                       # reuse the pass we already paid for
            max_angle=cfg.max_skew_deg,
            min_rule_px=max(8, int(cfg.min_rule_px * scale)),
            min_area=max(4, int(cfg.min_area * scale * scale)),
            blob_conf_floor=cfg.blob_conf_floor,
        )
        return SideSkew(
            is_blank=False, ink_area=int(ink),
            angle_deg=r.angle_deg, method=r.method,
            confidence=r.confidence, n_support=r.n_support,
            spread_deg=r.spread_deg,
        )

    def fuse_sheet(self, front: SideSkew, back: SideSkew | None,
                   cfg: Config | None = None) -> SheetSkew:
        """Fuse both sides of one sheet: ``angle(front) == −angle(back)``.

        Delegates to the real ``deskew.fuse_duplex`` — it does the
        confidence-weighted average when the sides agree, derives a weak/empty
        side from the strong one, and flags contradictions. Reimplementing that
        here would be strictly worse. Falls back to a front-only estimate if
        BlobTracker is unavailable.
        """
        cfg = cfg or DEFAULT_CONFIG
        mods = self._blobtracker()
        if mods is None:
            return SheetSkew()
        _blobcc, deskew = mods

        def to_result(s: SideSkew | None):
            if s is None or s.angle_deg is None:
                return deskew.EMPTY_RESULT
            return deskew.SkewResult(
                angle_deg=s.angle_deg, method=s.method,
                confidence=s.confidence, n_support=s.n_support,
                spread_deg=s.spread_deg,
            )

        d = deskew.fuse_duplex(
            to_result(front), to_result(back),
            min_conf=cfg.fuse_min_conf, agree_tol_deg=cfg.fuse_agree_tol_deg,
        )
        return SheetSkew(
            sheet_angle_deg=d.sheet_angle_deg,
            front_correction_deg=d.front_correction_deg,
            back_correction_deg=d.back_correction_deg,
            source=d.source, disagreement_deg=d.disagreement_deg,
        )

    # ---- applying the correction -------------------------------------------------
    def rotate_image(self, src: str | Path, dst: str | Path, correction_deg: float,
                     *, background: int = 255) -> bool:
        """Rotate ``src`` by ``correction_deg`` (ImageMagick sign: **positive =
        clockwise**) and write ``dst``. Returns True if a rotation was written.

        NOT the ``deskew`` binary: that tool re-detects the angle itself, which
        would discard the fused duplex angle and re-measure the sparse back page
        we deliberately refused to measure. We already know the angle, so we need
        a plain rotator — same call scand.py's ``emit_side`` makes to ImageMagick,
        done here with PIL (already a dependency; avoids the IM v6 ``convert`` /
        v7 ``magick`` split).

        PIL's positive is counter-clockwise, so the angle is negated on the way in.
        ``expand=False`` keeps the page dimensions uniform across the PDF; at the
        angles involved (< max_skew_deg, typically < 1°) the corner loss falls in
        the scan margin.
        """
        from PIL import Image

        with Image.open(src) as im:
            rotated = im.rotate(
                -correction_deg,                      # PIL +ve = CCW; IM +ve = CW
                resample=Image.BICUBIC,
                expand=False,
                fillcolor=_fill_for(im.mode, background),
            )
            rotated.save(dst)
        return True

    def detect_orientation(self, image: str | Path,
                           timeout: float = 30.0) -> "tuple[int, float] | None":
        """Tesseract OSD (`--psm 0`): the page's cardinal rotation to UPRIGHT.

        Returns `(rotate_deg, confidence)` where rotate_deg ∈ {0,90,180,270} is
        how many degrees CLOCKWISE to rotate the image to make text upright (the
        `Rotate:` line — same sense as `rotate_image`), and confidence is OSD's
        own score (arbitrary scale, higher better; low on sparse pages). None when
        tesseract is absent, the page has too little text for OSD, or it errors —
        so a blank/graphical side simply doesn't vote."""
        try:
            proc = subprocess.run(
                ["tesseract", str(image), "stdout", "--psm", "0"],
                capture_output=True, timeout=timeout, text=True)
        except (subprocess.SubprocessError, OSError):
            return None
        rot: int | None = None
        conf: float = 0.0
        for line in (proc.stdout or "").splitlines():
            if "Rotate:" in line:
                try:
                    rot = int(line.split(":", 1)[1].strip()) % 360
                except ValueError:
                    return None
            elif "Orientation confidence:" in line:
                try:
                    conf = float(line.split(":", 1)[1].strip())
                except ValueError:
                    conf = 0.0
        return (rot, conf) if rot is not None else None

    # ---- pdfdrill: sidecar layout + analysis -------------------------------------
    def _pdfdrill_sidecar_module(self):
        """Load pdfdrill's ``sidecar.py`` directly (or None).

        We need ``blob_dir_for`` — pdfdrill's own resolver for WHERE the sidecar
        lives, which is not simply ``<pdf>.drill.json``: a PDF sitting in a folder
        named after it (``<stem>/<stem>.pdf``, the library layout) is
        *self-contained* and uses ``<stem>/<stem>.drill.json`` instead. Getting
        that wrong writes provenance to a file pdfdrill never reads.

        Loaded from the file rather than imported as a package, so we depend on
        neither pdfdrill's ``__init__`` nor its deps (sidecar.py is stdlib-only).
        Replicating the rule here instead would guarantee drift.
        """
        key = f"sidecar:{self.pdfdrill_home}"
        cached = _BT_CACHE.get(key, _MISSING)
        if cached is not _MISSING:
            return cached
        mod = None
        path = self.pdfdrill_home / "src" / "pdfdrill" / "sidecar.py"
        if path.exists():
            try:
                import importlib.util as _u

                spec = _u.spec_from_file_location("_pd_sidecar", path)
                mod = _u.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                mod = None
        _BT_CACHE[key] = mod
        return mod

    def sidecar_path(self, pdf: str | Path) -> Path | None:
        """Where pdfdrill keeps this PDF's ``.drill.json`` (None if unavailable)."""
        mod = self._pdfdrill_sidecar_module()
        if mod is None:
            return None
        _blob_dir, json_path = mod.blob_dir_for(Path(pdf).resolve())
        return json_path

    def pdfdrill_sidecar(self, pdf: str | Path):
        """pdfdrill's OWN ``Sidecar`` object for this PDF (or None).

        Use this rather than writing the JSON ourselves. pdfdrill's ``_load()``
        only builds its default skeleton (``pdf``, ``facts``, ``evidence``,
        ``layers``, ``transitions``, …) when the file does **not** exist — so a
        sidecar we authored first would leave pdfdrill without its own keys.
        Letting its class create the file keeps that skeleton (and the version
        stamp, and the layout) pdfdrill's business, not ours.
        """
        mod = self._pdfdrill_sidecar_module()
        if mod is None:
            return None
        return mod.Sidecar(Path(pdf).resolve())

    # ---- pdfdrill: analysis to prepare an optimal PDF ----------------------------
    def run_pdfdrill(self, cmd: str, pdf: str | Path, *args: str, timeout: float = 600.0):
        """Invoke a pdfdrill subcommand (e.g. route/pageside/autosegment/ocr).

        Read-only analysis used to *inform* PDF preparation. Sets
        ``PDFDRILL_NO_PREFLIGHT=1`` so read-only automation skips the preflight
        gate. Returns the CompletedProcess; raises if pdfdrill is absent.
        """
        launcher = self.pdfdrill_home / "pdfdrill"
        if not launcher.exists():
            raise FileNotFoundError(f"pdfdrill not found at {launcher}")
        env = {**os.environ, "PDFDRILL_NO_PREFLIGHT": "1"}
        return subprocess.run(
            [str(launcher), cmd, str(pdf), *args],
            capture_output=True, text=True, timeout=timeout, env=env,
        )


# Module-level default instance for convenience.
DEFAULT = Tools()
