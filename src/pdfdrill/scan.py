"""
Scan acquisition — paper in the feeder becomes a drillable PDF.

This is the thin driver; the acquisition stack itself is VENDORED at
:mod:`pdfdrill.scandrill` (from the SCANDRILL project, absorbed so pdfdrill owns
every integration detail and no code lives outside this repo). It provides the
fixed rig — ADF duplex @300dpi, skew measured then applied, ``raw/`` retained,
blank sides RECORDED (never deleted) — and the lossless projection (``img2pdf``:
JPEG ``/DCTDecode`` verbatim, PNG ``/FlateDecode``; assembly never resamples).

Two invariants live here because breaking either fails silently:

1. **OCR is never requested.** ``assemble(ocr=False)`` is its default and we never
   override it. An OCR text layer makes :mod:`pdfdrill.ocr_router` read the scan
   as born-digital and route it to pdfminer instead of the vision lane — the scan
   would then be "extracted" from a text layer that is itself OCR output. The
   searchable underlay is a HUMAN deliverable, produced separately.
2. **assemble resolves against the RAW dir.** ``ingest_raw_dir(rel_to=raw_dir)``
   records page paths relative to ``raw/``, so ``assemble(job_dir=...)`` must get
   ``raw/`` — not the job dir. (Found by a live ADF scan: the job dir made
   assemble hunt for ``proc/raw_1_deskewed.png`` instead of
   ``raw/proc/raw_1_deskewed.png`` and die "kept page images missing".)

The acquisition deps are the OPTIONAL ``[scan]`` extra (img2pdf / pikepdf /
Pillow) plus ``scanimage`` (sane-utils); absent, every entry point degrades to a
clear message and no other route is affected. Layout under ``out_dir``::

    <job>.job/raw/          raw sides, retained
    <job>.job/raw/proc/     deskewed copies
    <job>.ingest.json       the manifest — the PDF is a projection of THIS
    <job>.pdf               the lossless projection
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

INSTALL_HINT = (
    "scan needs the acquisition deps (img2pdf / pikepdf / Pillow) and the SANE\n"
    "  tools: pip install 'pdfdrill[scan]'  +  apt-get install sane-utils")


class ScanUnavailable(RuntimeError):
    """SCANDRILL is not installed — raised with an actionable message."""


@dataclass
class ScanResult:
    """What one acquisition produced. `pdf` is a PROJECTION of `manifest`."""
    job: str
    pdf: Path
    manifest: Path
    raw_dir: Path
    sides: int          # physical sides pulled through the feeder
    kept: int           # pages in the PDF
    blanks: int         # recorded blank sides — NOT deleted
    deskewed: int
    device: str = ""

    @property
    def summary(self) -> str:
        return (f"{self.sides} side(s) → {self.kept} page(s)"
                f"{f', {self.blanks} blank recorded' if self.blanks else ''}")


def _scandrill() -> SimpleNamespace:
    """The scandrill modules we use — VENDORED at `pdfdrill.scandrill`, so
    pdfdrill owns the acquisition code outright (no external checkout, nothing
    outside git). Lazy + isolated: the third-party imports (img2pdf/pikepdf/
    Pillow) only load when someone actually scans, and tests inject fakes here
    instead of needing a scanner."""
    from .scandrill import assemble as assemble_mod
    from .scandrill import config as config_mod
    from .scandrill import manifest as manifest_mod
    from .scandrill.producers import adf as adf_mod
    return SimpleNamespace(adf=adf_mod, assemble=assemble_mod,
                           manifest=manifest_mod, config=config_mod)


def available() -> bool:
    """True when the acquisition stack can load (its deps are the [scan] extra)."""
    try:
        _scandrill()
    except Exception:                                     # noqa: BLE001
        return False
    return True


def job_name(now: "dt.datetime | None" = None) -> str:
    """Name for one acquisition: ``scan-YYYYmmdd-HHMM``.

    A timestamp is CORRECT here and only here — a job names an acquisition
    EVENT (one stack through the feeder), which genuinely is identified by when
    it happened. It is NOT the document prefix: one stack is usually several
    documents, so the per-document ``sender-date-type`` bibkey can only be
    derived downstream, once segmentation knows who sent what."""
    return (now or dt.datetime.now()).strftime("scan-%Y%m%d-%H%M")


def scan(job: "str | None" = None, out_dir: "str | Path | None" = None, *,
         simplex: bool = False, from_dir: "str | Path | None" = None,
         device: "str | None" = None, deskew: bool = True,
         config: "str | None" = None, title: "str | None" = None,
         timeout: float = 60.0, scan_timeout: float = 1800.0,
         on_progress=None) -> ScanResult:
    """Acquire one stack and assemble its lossless PDF.

    `from_dir` re-ingests an existing ``raw_*.png`` batch instead of scanning
    (the scanner is never touched). `on_progress(str)` receives step messages.
    Raises :class:`ScanUnavailable` when SCANDRILL is absent, and lets
    SCANDRILL's own ``ScannerError`` surface for device problems.
    """
    try:
        s = _scandrill()
    except Exception as exc:                              # noqa: BLE001
        raise ScanUnavailable(f"{INSTALL_HINT}\n  ({exc})") from exc

    say = on_progress or (lambda _m: None)
    job = job or job_name()
    out_dir = Path(out_dir) if out_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    job_dir = out_dir / f"{job}.job"
    # `raw_dir` is THE anchor: sides land here, deskewed copies go to raw/proc/,
    # manifest paths are recorded relative to it — so assemble must resolve
    # against it too (invariant 2).
    raw_dir = Path(from_dir) if from_dir else job_dir / "raw"
    cfg = s.config.Config.load(config) if config else s.config.Config.load()

    if from_dir:
        dev = device or getattr(cfg, "device", None) or "from-dir"
    else:
        dev = s.adf.resolve_device(device or getattr(cfg, "device", None),
                                   timeout=timeout)
        say(f"device: {dev}")
        say(f"scanning {cfg.source} @ {cfg.resolution}dpi → {raw_dir}")
        s.adf.scan_adf(raw_dir, device=dev, cfg=cfg, timeout=scan_timeout)

    m = s.manifest.Manifest(job=job, created=dt.datetime.now().isoformat(),
                            lang=cfg.lang, source_root=str(Path(raw_dir).resolve()))
    pages = s.adf.ingest_raw_dir(m, raw_dir, device=dev, source=cfg.source,
                                 rel_to=raw_dir,
                                 blank_threshold=cfg.blank_threshold,
                                 duplex=not simplex)
    if not pages:
        raise ScanUnavailable(f"no raw_*.png found in {raw_dir} "
                              f"(was the feeder empty?)")

    n_deskew = 0
    if deskew:
        s.adf.measure_skew(pages, job_dir=raw_dir, cfg=cfg)
        if getattr(cfg, "apply_deskew", True):
            # Rotation is the ONLY pixel-touching step, it is recorded, and raw/
            # is kept — so the original is always recoverable.
            n_deskew = s.adf.apply_deskew(pages, job_dir=raw_dir, cfg=cfg)
            say(f"deskew: rotated {n_deskew} page(s) (raw kept)")

    manifest_path = out_dir / f"{job}.ingest.json"
    m.save(manifest_path)
    pdf = out_dir / f"{job}.pdf"
    # ocr is NOT passed: assemble's default is False and must stay that way
    # (invariant 1) — an OCR layer would misroute the scan to pdfminer.
    s.assemble.assemble(m, pdf, job_dir=raw_dir, title=title)

    kept = len(m.kept_pages())
    say(f"assembled {kept} page(s) → {pdf}")
    return ScanResult(job=job, pdf=pdf, manifest=manifest_path, raw_dir=raw_dir,
                      sides=len(pages), kept=kept, blanks=len(pages) - kept,
                      deskewed=n_deskew, device=dev)
