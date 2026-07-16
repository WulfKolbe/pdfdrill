"""Fixed job configuration.

Scanner options are NOT probed or negotiated — the rig is fixed: **ADF Duplex at
300 dpi, always**. Values live here (and optionally in a ``scandrill.toml``
alongside the job) so the tuning constants scattered across scanp.sh / scand.py
have exactly one home.

Every constant carries its provenance, because they are not arbitrary: they were
tuned against real scans in the scripts named beside them.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, asdict, fields
from pathlib import Path

DEFAULT_CONFIG_NAMES = ("scandrill.toml", ".scandrill.toml")


@dataclass
class Config:
    # ---- scanner: fixed rig, not negotiated -------------------------------------
    device: str | None = None          # None = resolve at runtime (never hardcode eN)
    source: str = "ADF Duplex"         # fixed
    resolution: int = 300              # fixed; max for this rig (scanp.sh)
    mode: str = "Color"                # scanp.sh
    # A4 crop in mm — scanp.sh: -l 0 -t 0 -x 210 -y 290
    geom_l_mm: float = 0.0
    geom_t_mm: float = 0.0
    geom_x_mm: float = 210.0
    geom_y_mm: float = 290.0

    # ---- blank detection ---------------------------------------------------------
    # Raster prefilter (scanp.sh): grayscale mean of the shaved page > threshold.
    blank_threshold: float = 0.999     # scanp.sh EMPTY_THRESHOLD
    shave_px: int = 40                 # scanp.sh SHAVE_BORDER
    # Topological check (scand.py): sum of blob areas below this = empty. More
    # robust than the mean — see docs/TOPOLOGY-VS-RASTER.md.
    empty_min_ink_area: int = 2000     # scand.py EMPTY_MIN_INK_AREA
    empty_border_px: int = 24          # scand.py EMPTY_BORDER (mask scan edges)

    # ---- skew --------------------------------------------------------------------
    binarize_threshold: int = 200      # scand.py THRESHOLD (dark < 200 = ink)
    max_skew_deg: float = 8.0          # scanp.sh MAX_SKEW / scand.py MAX_SKEW_DEG
    min_skew_deg: float = 0.2          # scanp.sh MIN_SKEW (below = don't bother)
    min_rule_px: int = 150             # scand.py MIN_RULE_PX (@300dpi)
    min_area: int = 500                # scand.py MIN_AREA
    blob_conf_floor: float = 0.35      # scand.py BLOB_CONF_FLOOR: below -> Hough
    fuse_min_conf: float = 0.15        # deskew.fuse_duplex min_conf
    fuse_agree_tol_deg: float = 0.5    # deskew.fuse_duplex agree_tol_deg

    # ADF convention (pylepto "Project Decisions — user-set, do not revisit":
    # measure FRONT pages only; backs get the negated front angle, because backs
    # are too sparsely filled to measure reliably). The back is only measured as
    # a fallback when the front yielded nothing usable.
    measure_backs: bool = False
    # Half-empty guard: a side with less ink than this is too sparse for a
    # trustworthy angle — skip the calculation entirely and let fusion supply it
    # from the other side. Above empty_min_ink_area (blank) but below usable.
    skew_min_ink_area: int = 20_000
    # blobcc is pure-Python: a full 300dpi A4 side is ~8.5 MPx. Downscale for the
    # skew pass only (angle is scale-invariant); 0 disables. Rule/area thresholds
    # are scaled with it.
    skew_max_px: int = 1_500_000

    # ---- output ------------------------------------------------------------------
    lang: str = "de-DE"
    # ADF scans are always skewed, so deskew is ALWAYS applied. Rotation resamples
    # (not lossless) — raw/ is retained untouched and the angle is recorded, so the
    # decision stays auditable and re-derivable from the originals.
    apply_deskew: bool = True
    deskew_dir: str = "proc"           # deskewed copies land here; raw/ is kept

    # ---- helpers -----------------------------------------------------------------
    def geometry_args(self) -> list[str]:
        return ["-l", str(self.geom_l_mm), "-t", str(self.geom_t_mm),
                "-x", str(self.geom_x_mm), "-y", str(self.geom_y_mm)]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**d)

    @classmethod
    def load(cls, path: str | Path | None = None, *, start: str | Path = ".") -> "Config":
        """Load ``scandrill.toml`` (explicit path, or search upward from ``start``).

        Returns defaults when no file is found — the fixed rig IS the default.
        """
        if path is not None:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"config not found: {p}")
            return cls._read(p)
        here = Path(start).resolve()
        for d in (here, *here.parents):
            for name in DEFAULT_CONFIG_NAMES:
                cand = d / name
                if cand.exists():
                    return cls._read(cand)
        return cls()

    @classmethod
    def _read(cls, p: Path) -> "Config":
        data = tomllib.loads(p.read_text())
        # accept either a flat table or a [scandrill] section
        if "scandrill" in data and isinstance(data["scandrill"], dict):
            data = data["scandrill"]
        return cls.from_dict(data)


DEFAULT = Config()
