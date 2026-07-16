"""I-D) ADF producer — scanimage/scanp recipe, non-destructive.

Reuses the *recipe* proven by ``~/WKprivate/Scanned/scanp.sh`` (device flags,
A4 crop, thresholds, duplex pairing) but NOT its file management: raw scans are
never deleted, blank pages are recorded as ``removed_blank`` rather than removed,
and skew is measured/recorded rather than silently baked in.

See ``docs/PROPOSAL-ADF.md`` for the reasoning.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..config import Config, DEFAULT as DEFAULT_CONFIG
from ..ingest import add_path, iter_images
from ..manifest import Manifest, Page, PENDING, REMOVED_BLANK
from ..tools import DEFAULT as DEFAULT_TOOLS, SideSkew, Tools

# ---- the scanp.sh recipe --------------------------------------------------------
# The fixed rig lives in scandrill/config.py + scandrill.toml; these names remain
# as the module-level defaults so the flags have one obvious home.
RESOLUTION = DEFAULT_CONFIG.resolution        # 300 dpi, fixed
SOURCE_DUPLEX = DEFAULT_CONFIG.source         # "ADF Duplex", fixed
MODE = DEFAULT_CONFIG.mode
FMT = "png"
BATCH_PATTERN = "raw_%d.png"
RAW_GLOB = "raw_*.png"

MODEL_HINT = "OfficeJet"

# Backend preference, most-preferred first. `airscan:` (sane-airscan) is what the
# tested scripts target, so it wins; `escl:` (sane-escl) is the same eSCL protocol
# but IP-pinned (`escl:https://192.168.x.y:443`) and breaks on a DHCP change;
# `hpaio:` (HPLIP) is the last resort. Unknown backends sort after all of these.
BACKEND_PREFERENCE = ("airscan:", "escl:", "hpaio:")

_DEVICE_RE = re.compile(r"device\s+[`'\"]([^'\"`]+)['\"`]\s+is a\s+(.*)", re.I)


class ScannerError(RuntimeError):
    pass


def list_devices(timeout: float = 30.0) -> list[tuple[str, str]]:
    """Enumerate SANE devices via ``scanimage -L``.

    Tolerates the binary noise some backends emit on stdout (decode with
    ``errors="replace"``) and returns ``[(device_name, description), ...]``.
    """
    try:
        proc = subprocess.run(
            ["scanimage", "-L"], capture_output=True, timeout=timeout
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ScannerError(f"scanimage -L failed: {exc}") from exc
    text = proc.stdout.decode("utf-8", errors="replace")
    return [(m.group(1).strip(), m.group(2).strip()) for m in _DEVICE_RE.finditer(text)]


def resolve_device(
    explicit: str | None = None,
    *,
    env_device: str | None = None,
    model_hint: str | None = MODEL_HINT,
    timeout: float = 30.0,
) -> str:
    """Pick the scanner to use. NEVER hardcode ``airscan:eN:`` — the ``eN`` is a
    discovery-order index, not a stable id (which is why scanp.sh says ``e1`` and
    scand.py says ``e0``). Resolution order:

    1. ``explicit`` argument, 2. ``env_device``, 3. ``scanimage -L`` filtered by
    ``model_hint`` and ranked by :data:`BACKEND_PREFERENCE`.
    Raises ScannerError if nothing is found.

    Verified live 2026-07-15: this printer exposes all four backends at once, and
    the current index is ``airscan:e0:`` — while ``scanp.sh`` hardcodes ``e1``.
    The index really does drift; that is the whole reason this function exists.
    """
    if explicit:
        return explicit
    if env_device:
        return env_device

    devices = list_devices(timeout=timeout)
    if not devices:
        raise ScannerError("no SANE devices found (scanimage -L returned none)")

    def matches(name_desc: tuple[str, str]) -> bool:
        if not model_hint:
            return True
        blob = f"{name_desc[0]} {name_desc[1]}".lower()
        return model_hint.lower() in blob

    candidates = [d for d in devices if matches(d)] or devices

    def rank(name: str) -> int:
        for i, prefix in enumerate(BACKEND_PREFERENCE):
            if name.startswith(prefix):
                return i
        return len(BACKEND_PREFERENCE)  # unknown backends last

    return min(candidates, key=lambda nd: rank(nd[0]))[0]


def probe_sources(device: str, timeout: float = 30.0) -> list[str]:
    """Read the device's supported ``--source`` values.

    Backends may name the feeder differently, so probe rather than assume.
    Verified live on this printer: ``['Flatbed', 'ADF', 'ADF Duplex']`` — so
    scanp.sh's ``--source "ADF Duplex"`` is valid here.
    """
    try:
        proc = subprocess.run(
            ["scanimage", "-d", device, "--help"],
            capture_output=True, timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ScannerError(f"scanimage --help failed for {device!r}: {exc}") from exc
    text = proc.stdout.decode("utf-8", errors="replace")
    m = re.search(r"--source\s+([^\n]+)", text)
    if not m:
        return []
    opts = m.group(1)
    opts = re.sub(r"\[.*?\]", "", opts)  # strip the [default] marker
    return [o.strip() for o in opts.split("|") if o.strip()]


def scan_adf(
    raw_dir: str | Path,
    *,
    device: str,
    cfg: Config | None = None,
    timeout: float = 1800.0,
) -> list[Path]:
    """Run the ADF batch scan into ``raw_dir`` using the fixed-rig config.

    Returns the produced raw files in version-aware order (``sort -V``
    equivalent), matching scanp.sh's post-run glob. Does not delete anything.
    """
    cfg = cfg or DEFAULT_CONFIG
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "scanimage", "-d", device,
        "--source", cfg.source,
        "--mode", cfg.mode,
        "--resolution", str(cfg.resolution),
        "--format", FMT,
        f"--batch={raw_dir / BATCH_PATTERN}",
        *cfg.geometry_args(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ScannerError(f"scanimage failed: {exc}") from exc
    files = raw_batch_files(raw_dir)
    if proc.returncode != 0 and not files:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise ScannerError(f"scanimage exited {proc.returncode}: {err}")
    return files


def raw_batch_files(raw_dir: str | Path) -> list[Path]:
    """The raw_%d.png batch in emission order (version-aware, like `sort -V`).

    FLAT by definition: scanimage emits raw_%d.png directly into ``raw_dir``,
    while our own deskewed copies land in ``raw_dir/<deskew_dir>/`` (proc/).
    ``iter_images`` rglobs, so we must drop anything below the top level —
    otherwise ``proc/raw_1_deskewed.png`` matches ``raw_*.png`` and a re-ingest
    (``--from-dir`` on an already-deskewed batch, or a retry) counts it as a fresh
    SIDE: pages double-count AND an already-rotated image gets rotated a second
    time, which is unrecorded pixel damage. Rotation must stay the only
    pixel-touching step, applied once, from raw.
    """
    raw_dir = Path(raw_dir)
    return [p for p in iter_images(raw_dir, mask=RAW_GLOB, order="name")
            if p.parent == raw_dir]


def pair_sheets(files: list[Path]) -> list[tuple[Path, Path | None]]:
    """Pair single-pass duplex output into physical sheets.

    scanimage emits page1=sheet1-front, page2=sheet1-back, page3=sheet2-front...
    An odd trailing page is a front with no back (scand.py convention).
    """
    sheets: list[tuple[Path, Path | None]] = []
    for i in range(0, len(files), 2):
        front = files[i]
        back = files[i + 1] if i + 1 < len(files) else None
        sheets.append((front, back))
    return sheets


def ingest_raw_dir(
    manifest: Manifest,
    raw_dir: str | Path,
    *,
    device: str = "unknown",
    source: str = SOURCE_DUPLEX,
    rel_to: str | Path | None = None,
    blank_threshold: float | None = 0.999,
    duplex: bool = True,
) -> list[Page]:
    """Turn an existing raw_%d.png batch into manifest pages (the `--from-dir`
    path, identical to the live path except for who wrote the files).

    Records sheet/side provenance; blank sides get ``removed_blank`` rather than
    being deleted — scanp.sh drops a sheet only when BOTH sides are blank, but
    pdfdrill must be able to account for every removed page, so we record per side.
    """
    files = raw_batch_files(raw_dir)
    added: list[Page] = []
    if not duplex:
        for idx, f in enumerate(files, start=1):
            pg = add_path(
                manifest, f,
                origin={"kind": "adf", "device": device, "source": source,
                        "batch_index": idx, "sheet": idx, "side": "front"},
                rel_to=rel_to, blank_threshold=blank_threshold,
            )
            added.append(pg)
        return added

    for sheet_no, (front, back) in enumerate(pair_sheets(files), start=1):
        for side, path in (("front", front), ("back", back)):
            if path is None:
                continue
            pg = add_path(
                manifest, path,
                origin={
                    "kind": "adf", "device": device, "source": source,
                    "sheet": sheet_no, "side": side,
                    "batch_index": files.index(path) + 1,
                },
                rel_to=rel_to, blank_threshold=blank_threshold,
            )
            added.append(pg)
    return added


def group_sheets(pages: list[Page]) -> list[tuple[int, Page | None, Page | None]]:
    """Group ingested ADF pages back into ``(sheet_no, front, back)`` triples."""
    by_sheet: dict[int, dict[str, Page]] = {}
    for p in pages:
        sheet = p.origin.get("sheet")
        if sheet is None:
            continue
        by_sheet.setdefault(int(sheet), {})[p.origin.get("side", "front")] = p
    return [(n, s.get("front"), s.get("back")) for n, s in sorted(by_sheet.items())]


def measure_skew(
    pages: list[Page],
    *,
    job_dir: str | Path,
    cfg: Config | None = None,
    tools: Tools | None = None,
) -> int:
    """Measure and fuse skew per physical sheet, recording it on each Page.

    Per side: ONE blobcc pass → blank check (total ink area) + skew (rule-blob
    fast path, Hough fallback for text-only pages). Per sheet: the real
    ``deskew.fuse_duplex`` — a sparse back page is derived from the front,
    sign-flipped, and two confident sides are averaged by confidence.

    Nothing is rotated here: the angle is *recorded*, never applied. Rotation
    resamples every pixel and is opt-in (``Config.apply_deskew``).

    Also arbitrates blank detection: the grayscale mean set a provisional status
    at ingest; where topology is available it wins, because the mean both drops
    faint pencil pages and keeps gray-cast ones. Both signals are recorded.

    Returns the number of sides measured (0 if BlobTracker is unavailable).
    """
    cfg = cfg or DEFAULT_CONFIG
    tools = tools or DEFAULT_TOOLS
    base = Path(job_dir)
    measured = 0

    def _abs(page: Page) -> Path:
        src = Path(page.src)
        return src if src.is_absolute() else base / src

    for _sheet_no, front, back in group_sheets(pages):
        analyses: dict[str, SideSkew | None] = {}

        # FRONT first: the ADF convention measures fronts only.
        front_an = tools.analyze_side(_abs(front), cfg) if front is not None else None
        analyses["front"] = front_an
        # The back is measured ONLY as a fallback — when the front gave nothing
        # usable (blank/sparse front, printed back) there is no angle to negate.
        front_usable = bool(front_an and front_an.usable(cfg.fuse_min_conf))
        measure_back = cfg.measure_backs or not front_usable
        analyses["back"] = (
            tools.analyze_side(_abs(back), cfg, measure=measure_back)
            if back is not None else None
        )

        for side, page in (("front", front), ("back", back)):
            a = analyses.get(side)
            if page is None or a is None:
                continue
            if not a.available:
                continue
            measured += 1
            page.extra["ink_area"] = a.ink_area
            page.extra["skew_measured_deg"] = a.angle_deg
            page.extra["skew_method"] = a.method
            # topology arbitrates blankness (see docs/TOPOLOGY-VS-RASTER.md)
            page.extra["blank_by_mean"] = (
                page.blank_mean is not None and page.blank_mean > cfg.blank_threshold
            )
            page.extra["blank_by_blobs"] = a.is_blank
            page.status = REMOVED_BLANK if a.is_blank else PENDING

        fused = tools.fuse_sheet(analyses.get("front"), analyses.get("back"), cfg)
        for side, page in (("front", front), ("back", back)):
            if page is None or not (analyses.get(side) or SideSkew(available=False)).available:
                continue
            corr = (fused.front_correction_deg if side == "front"
                    else fused.back_correction_deg)
            a = analyses[side]
            page.skew_deg = corr
            page.skew_conf = a.confidence if a else None
            page.extra["skew_source"] = fused.source
            if fused.disagreement_deg is not None:
                page.extra["skew_disagreement_deg"] = round(fused.disagreement_deg, 3)
    return measured


def decide_orientation(
    readings: list[tuple[int | None, float | None]],
) -> tuple[int, int, int]:
    """Document-level orientation vote over per-page OSD readings.

    `readings` is one `(rotate_deg, confidence)` per page — `(None, None)` for a
    blank/undetected side. Returns `(deg, agree, total)`: the cardinal rotation
    (0/90/180/270) to apply to the WHOLE document, how many pages voted for it,
    and how many pages had a usable reading.

    The signal is CROSS-PAGE AGREEMENT, not any one page's confidence: an ADF
    stack is fed as a unit, so a misfeed rotates every page the same way, and OSD
    confidence on a sparse office page is low even when the reading is right (the
    reported case: three pages unanimous at 180°, confidence 8–14). A non-zero
    rotation wins only with a STRICT majority of the usable pages; a split vote
    stays upright (0) — a wrong flip is worse than none, and raw/ keeps the
    original either way."""
    votes: dict[int, int] = {}
    total = 0
    for deg, _conf in readings:
        if deg is None:
            continue
        d = int(deg) % 360
        total += 1
        votes[d] = votes.get(d, 0) + 1
    if not total:
        return 0, 0, 0
    best = max(votes, key=lambda d: votes[d])
    agree = votes[best]
    if best == 0 or agree * 2 <= total:            # need a STRICT majority to rotate
        return 0, votes.get(0, 0), total
    return best, agree, total


def measure_orientation(
    pages: list[Page],
    *,
    job_dir: str | Path,
    cfg: Config | None = None,
    tools: Tools | None = None,
) -> int:
    """Measure page orientation by OSD and record the DOC-level decision.

    Mirrors `measure_skew`: nothing is rotated here. Each non-blank page is run
    through tesseract OSD; `decide_orientation` votes across them, and the single
    document rotation (0/90/180/270) is stamped on every kept page's `extra`
    (`orientation_deg` + its own `osd_deg`/`osd_conf` + the `orientation_votes`
    tally). `apply_deskew` folds it into the rotation it already performs.

    Returns the number of pages that produced a usable OSD reading (0 when
    tesseract is absent — orientation then stays 0 and only fine deskew runs)."""
    cfg = cfg or DEFAULT_CONFIG
    tools = tools or DEFAULT_TOOLS
    base = Path(job_dir)

    per_page: list[tuple[Page, tuple[int | None, float | None]]] = []
    for page in pages:
        if page.status == REMOVED_BLANK:
            continue
        src = Path(page.src)
        if not src.is_absolute():
            src = base / src
        reading = tools.detect_orientation(src) or (None, None)
        per_page.append((page, reading))

    deg, agree, total = decide_orientation([r for _p, r in per_page])
    for page, (osd_deg, osd_conf) in per_page:
        page.extra["osd_deg"] = osd_deg
        page.extra["osd_conf"] = osd_conf
        page.extra["orientation_deg"] = deg
        page.extra["orientation_votes"] = f"{agree}/{total}"
    return total


def apply_deskew(
    pages: list[Page],
    *,
    job_dir: str | Path,
    cfg: Config | None = None,
    tools: Tools | None = None,
) -> int:
    """Rotate each page by its recorded correction, writing into ``proc/``.

    ADF scans are always skewed, so this always runs. ``raw/`` is retained
    untouched — rotation resamples every pixel, so the original stays the record
    of truth and the whole decision is re-derivable from it.

    Each page's ``src`` is repointed at the deskewed copy (assembly then embeds
    the corrected pages) while ``extra.raw_src`` keeps the original path.

    Skips (copy-free, leaves ``src`` on raw) when there is no usable angle, when
    ``|angle| < min_skew_deg`` — scanp.sh's "don't bother" floor, and rotation is
    lossy, so a no-op beats a needless resample — or when ``|angle| >
    max_skew_deg`` (scand.py refuses corrections beyond the limit rather than
    trust them). Blank/removed pages are never rotated.

    Returns the number of pages actually rotated.
    """
    cfg = cfg or DEFAULT_CONFIG
    tools = tools or DEFAULT_TOOLS
    base = Path(job_dir)
    out_dir = base / cfg.deskew_dir
    rotated = 0

    for page in pages:
        if page.status == REMOVED_BLANK:
            continue
        # Orientation (cardinal 0/90/180/270, doc-level from measure_orientation)
        # is NOT a skew angle — it always applies. Only the fine SKEW component is
        # gated by the "don't bother" floor / the max-angle limit; the two are
        # then summed and applied in ONE rotation (one resample, not two).
        orient = int(page.extra.get("orientation_deg") or 0) % 360
        skew = page.skew_deg
        skew_use = 0.0
        if skew is None:
            skew_note = "no skew angle"
        elif abs(skew) < cfg.min_skew_deg:
            skew_note = f"skew below {cfg.min_skew_deg}° floor"
        elif abs(skew) > cfg.max_skew_deg:
            skew_note = f"skew exceeds {cfg.max_skew_deg}° limit"
        else:
            skew_use = skew
            skew_note = f"deskew {skew:+.2f}°"

        total = orient + skew_use
        if total == 0:
            page.extra["deskew"] = f"{skew_note}, not rotated"
            continue

        src = Path(page.src)
        if not src.is_absolute():
            src = base / src
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / f"{src.stem}_deskewed.png"
        if not tools.rotate_image(src, dst, total):
            page.extra["deskew"] = "rotate failed"
            continue

        page.extra["raw_src"] = page.src
        if orient:
            page.extra["orientation_applied"] = orient
        page.extra["deskew"] = (f"oriented {orient}° + " if orient else "") + skew_note
        try:
            page.src = str(dst.relative_to(base))
        except ValueError:
            page.src = str(dst)
        page.skew_applied = True
        rotated += 1

    return rotated
