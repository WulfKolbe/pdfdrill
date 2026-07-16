"""``scandrill`` command line — the prototype driver.

    scandrill ingest  <dir> --job NAME [--mask '*.png'] [--order name|mtime] [--lang de-DE]
    scandrill assemble <job.ingest.json> -o out.pdf [--job-dir DIR]
    scandrill build    <dir> -o out.pdf --job NAME       # ingest + assemble in one shot
    scandrill devices                                     # enumerate scanners
    scandrill adf --job NAME [--scan | --from-dir RAW]    # I-D) ADF producer
    scandrill tools                                       # show external-tool availability
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import ingest as ing
from .assemble import assemble
from . import handoff as ho
from .config import Config
from .manifest import Manifest
from .meta import DEFAULT_PRODUCER, DocMeta
from .ocr import tesseract_lang
from .producers import adf as adf_mod
from .tools import DEFAULT as TOOLS


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_manifest(job: str, lang: str, root: str | None) -> Manifest:
    return Manifest(job=job, created=_now_iso(), lang=lang, source_root=root)


def cmd_ingest(a) -> int:
    m = _new_manifest(a.job, a.lang, str(Path(a.dir).resolve()))
    pages = ing.add_folder(m, a.dir, mask=a.mask, order=a.order, rel_to=a.dir)
    out = Path(a.out or f"{a.job}.ingest.json")
    m.save(out)
    kept = len(m.kept_pages())
    blanks = len(pages) - kept
    print(f"ingested {len(pages)} images → {out}  ({kept} kept, {blanks} blank-dropped)")
    return 0


def _meta_from_args(a, manifest) -> DocMeta:
    return DocMeta.from_manifest(
        manifest,
        title=getattr(a, "title", None),
        author=getattr(a, "author", None),
        subject=getattr(a, "subject", None),
        keywords=getattr(a, "keywords", None),
        creator=getattr(a, "creator", None),
        producer=getattr(a, "producer", None),
        lang=getattr(a, "lang", None),
    )


def cmd_assemble(a) -> int:
    m = Manifest.load(a.manifest)
    job_dir = a.job_dir or str(Path(a.manifest).resolve().parent)
    meta = _meta_from_args(a, m)
    out = assemble(m, a.out, job_dir=job_dir, meta=meta,
                   ocr=a.ocr, ocr_lang=a.ocr_lang)
    # persist pdf name back into the manifest next to itself
    m.save(a.manifest)
    extra = f", OCR text layer ({a.ocr_lang or tesseract_lang(meta.lang)})" if a.ocr else ""
    print(f"assembled {len(m.kept_pages())} pages → {out}  "
          f"(/Lang={meta.lang}{extra})")
    return 0


def cmd_build(a) -> int:
    root = str(Path(a.dir).resolve())
    m = _new_manifest(a.job, a.lang or "de-DE", root)
    pages = ing.add_folder(m, a.dir, mask=a.mask, order=a.order, rel_to=a.dir)
    manifest_path = Path(a.out).with_suffix(".ingest.json")
    meta = _meta_from_args(a, m)
    out = assemble(m, a.out, job_dir=a.dir, meta=meta, ocr=a.ocr, ocr_lang=a.ocr_lang)
    m.save(manifest_path)
    kept = len(m.kept_pages())
    extra = " + OCR text layer" if a.ocr else ""
    print(f"built {out} from {len(pages)} images ({kept} kept){extra} "
          f"+ sidecar {manifest_path}")
    return 0


def cmd_devices(a) -> int:
    devices = adf_mod.list_devices(timeout=a.timeout)
    if not devices:
        print("no SANE devices found")
        return 1
    print("scanners:")
    for name, desc in devices:
        print(f"  {name}\n      {desc}")
    try:
        dev = adf_mod.resolve_device(timeout=a.timeout)
    except adf_mod.ScannerError as exc:
        print(f"\nresolve failed: {exc}")
        return 1
    print(f"\nwould use: {dev}")
    cfg = Config.load()
    if a.sources:
        # Diagnostic only — the rig is fixed (config), we do not negotiate options.
        try:
            srcs = adf_mod.probe_sources(dev, timeout=a.timeout)
        except adf_mod.ScannerError as exc:
            print(f"  source probe failed: {exc}")
            return 0
        print(f"  offers --source: {srcs or '(none reported)'}")
        if srcs and cfg.source not in srcs:
            print(f"  WARNING: configured source {cfg.source!r} is NOT offered by "
                  f"this device", file=sys.stderr)
    return 0


def cmd_adf(a) -> int:
    cfg = Config.load(a.config)
    job_dir = Path(a.job_dir or f"{a.job}.job")
    raw_dir = Path(a.from_dir) if a.from_dir else job_dir / "raw"

    if a.from_dir:
        device = a.device or cfg.device or "from-dir"
    else:
        # The rig is fixed (ADF Duplex @ 300 dpi) — no option probing. Only the
        # device is resolved, because its eN index is not stable.
        try:
            device = adf_mod.resolve_device(
                a.device or cfg.device,
                env_device=os.environ.get("SCANDRILL_DEVICE"),
                timeout=a.timeout,
            )
        except adf_mod.ScannerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"device: {device}")
        print(f"scanning {cfg.source} @ {cfg.resolution}dpi → {raw_dir} ...")
        files = adf_mod.scan_adf(raw_dir, device=device, cfg=cfg, timeout=a.scan_timeout)
        print(f"  {len(files)} raw sides")

    m = _new_manifest(a.job, cfg.lang, str(raw_dir.resolve()))
    pages = adf_mod.ingest_raw_dir(
        m, raw_dir, device=device, source=cfg.source, rel_to=raw_dir,
        blank_threshold=cfg.blank_threshold, duplex=not a.simplex,
    )
    if not pages:
        print(f"error: no raw_*.png found in {raw_dir}", file=sys.stderr)
        return 1

    if not a.no_skew:
        n = adf_mod.measure_skew(pages, job_dir=raw_dir, cfg=cfg)
        if n:
            print(f"skew: measured {n} sides, fused per sheet")
            for sheet_no, front, back in adf_mod.group_sheets(pages):
                bits = []
                for side, pg in (("front", front), ("back", back)):
                    if pg is None:
                        continue
                    ang = pg.skew_deg
                    bits.append(f"{side}={'—' if ang is None else f'{ang:+.2f}°'}"
                                f"[{pg.extra.get('skew_method', '?')}]")
                src = (front or back).extra.get("skew_source", "none")
                print(f"  sheet{sheet_no}: {' '.join(bits)}  fused={src}")
        else:
            print("skew: BlobTracker unavailable — angles not recorded")

        # ADF scans are always skewed → deskew always (raw/ retained).
        if cfg.apply_deskew and not a.no_deskew:
            n_rot = adf_mod.apply_deskew(pages, job_dir=raw_dir, cfg=cfg)
            skipped = [p for p in pages
                       if p.status != "removed_blank" and not p.skew_applied]
            print(f"deskew: rotated {n_rot} pages → {raw_dir / cfg.deskew_dir}/ "
                  f"(raw kept)")
            for p in skipped:
                print(f"  seq{p.seq}: {p.extra.get('deskew', 'not rotated')}")

    out = Path(a.out or f"{a.job}.ingest.json")
    m.save(out)
    kept = len(m.kept_pages())
    print(f"ingested {len(pages)} sides → {out}  "
          f"({kept} kept, {len(pages) - kept} recorded blank, 0 deleted)")
    return 0


def cmd_serve(a) -> int:
    from .server import JobStore, make_server

    job_dir = Path(a.job_dir or f"{a.job}.job").resolve()
    roots = [Path(r).resolve() for r in (a.allow_root or [])]
    store = JobStore(a.job, job_dir, _now_iso(), a.lang, roots)
    httpd = make_server(store, host=a.host, port=a.port, verbose=a.verbose)

    print(f"drop zone:  http://{a.host}:{a.port}/")
    print(f"job dir:    {job_dir}")
    print(f"manifest:   {store.manifest_path}")
    if roots:
        print("allowed roots (drag-a-path mode, no copying):")
        for r in roots:
            print(f"  {r}")
    else:
        print("no --allow-root given: dropping PATHS is disabled; "
              "dropping FILES (upload) still works.")
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"\n  WARNING: bound to {a.host}, not loopback. This endpoint writes "
              f"files and reads anything under the allowed roots.", file=sys.stderr)
    print("\nCtrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\nstopped. {len(store.manifest.pages)} pages in {store.manifest_path}")
    finally:
        httpd.server_close()
        store.save()
    return 0


def cmd_handoff(a) -> int:
    m = Manifest.load(a.manifest)
    pdf = Path(a.pdf) if a.pdf else Path(a.manifest).resolve().parent / (m.pdf or "")
    cmds = tuple(a.analyze.split(",")) if a.analyze else ()
    try:
        res = ho.handoff(m, pdf, commands=cmds, merge=not a.no_merge)
    except ho.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if res.merged:
        n = len(m.pages)
        removed = sum(1 for p in m.pages if p.status.startswith("removed"))
        print(f"merged provenance for {n} pages ({removed} removed, accounted for) "
              f"→ {res.sidecar}")
    for cmd, r in (res.analyses or {}).items():
        head = (r["out"].splitlines() or [r["err"]])[0][:160] if (r["out"] or r["err"]) else ""
        print(f"  pdfdrill {cmd}: {'ok' if r['rc'] == 0 else 'rc=' + str(r['rc'])}  {head}")
    for w in res.warnings:
        print(f"\n  WARNING: {w}", file=sys.stderr)
    return 0


def cmd_tools(a) -> int:
    avail = TOOLS.available()
    print("external tool availability:")
    for name, ok in avail.items():
        print(f"  [{'x' if ok else ' '}] {name}")
    print(f"\n  pdfdrill_home    = {TOOLS.pdfdrill_home}")
    print(f"  pylepto_home     = {TOOLS.pylepto_home}")
    print(f"  blobtracker_home = {TOOLS.blobtracker_home}")
    return 0


def _add_meta_args(p: argparse.ArgumentParser) -> None:
    """Document metadata + OCR options, shared by `assemble` and `build`."""
    g = p.add_argument_group("document metadata")
    g.add_argument("--title")
    g.add_argument("--author")
    g.add_argument("--subject")
    g.add_argument("--keywords")
    g.add_argument("--creator", help="producing application")
    g.add_argument("--producer", help=f"default: {DEFAULT_PRODUCER}")
    g.add_argument("--lang", help="BCP-47, e.g. de-DE (default: the job's)")
    o = p.add_argument_group("OCR text layer (opt-in; image stays byte-identical)")
    o.add_argument("--ocr", action="store_true",
                   help="graft an invisible tesseract text layer")
    o.add_argument("--ocr-lang", help="tesseract code, e.g. deu (default: from --lang)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scandrill", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="scan a folder of images into an ingest.json")
    pi.add_argument("dir")
    pi.add_argument("--job", required=True)
    pi.add_argument("--mask", default="*")
    pi.add_argument("--order", default="name", choices=["name", "mtime"])
    pi.add_argument("--lang", default="de-DE")
    pi.add_argument("-o", "--out")
    pi.set_defaults(func=cmd_ingest)

    pa = sub.add_parser("assemble", help="lossless PDF from an existing ingest.json")
    pa.add_argument("manifest")
    pa.add_argument("-o", "--out", required=True)
    pa.add_argument("--job-dir")
    _add_meta_args(pa)
    pa.set_defaults(func=cmd_assemble)

    pb = sub.add_parser("build", help="ingest a folder AND assemble in one step")
    pb.add_argument("dir")
    pb.add_argument("-o", "--out", required=True)
    pb.add_argument("--job", required=True)
    pb.add_argument("--mask", default="*")
    pb.add_argument("--order", default="name", choices=["name", "mtime"])
    _add_meta_args(pb)
    pb.set_defaults(func=cmd_build)

    pd = sub.add_parser("devices", help="enumerate scanners and show which would be used")
    pd.add_argument("--timeout", type=float, default=60.0,
                    help="mDNS discovery is slow; a short timeout returns only the "
                         "first device")
    pd.add_argument("--sources", action="store_true",
                    help="also probe the resolved device's --source options "
                         "(diagnostic; the rig itself is fixed in scandrill.toml)")
    pd.set_defaults(func=cmd_devices)

    pf = sub.add_parser(
        "adf", help="I-D) ADF producer (scanimage; non-destructive)",
        description="Fixed rig: ADF Duplex @ 300 dpi (scandrill.toml). Scanner "
                    "options are not probed; only the device is resolved.",
    )
    pf.add_argument("--job", required=True)
    pf.add_argument("--from-dir", help="ingest an existing raw_%%d.png batch instead of scanning")
    pf.add_argument("--device", help="explicit SANE device (never enumerates)")
    pf.add_argument("--config", help="path to scandrill.toml (default: search upward)")
    pf.add_argument("--simplex", action="store_true", help="one side per sheet")
    pf.add_argument("--no-skew", action="store_true", help="skip the skew measurement pass")
    pf.add_argument("--no-deskew", action="store_true",
                    help="measure but do not rotate (deskew is ON by default)")
    pf.add_argument("--job-dir")
    pf.add_argument("--timeout", type=float, default=60.0, help="device discovery timeout")
    pf.add_argument("--scan-timeout", type=float, default=1800.0)
    pf.add_argument("-o", "--out")
    pf.set_defaults(func=cmd_adf)

    ps = sub.add_parser(
        "serve", help="I-B) drop-zone server (drag & drop / upload)",
        description="Drop images in a browser; the page list is a render of "
                    "ingest.json. Dropping FILES uploads bytes into <job>/raw/. "
                    "Dropping PATHS (text/uri-list) references originals without "
                    "copying — only under an --allow-root.",
    )
    ps.add_argument("--job", required=True)
    ps.add_argument("--job-dir")
    ps.add_argument("--host", default="127.0.0.1", help="default: loopback only")
    ps.add_argument("--port", type=int, default=8799)
    ps.add_argument("--allow-root", action="append", metavar="DIR",
                    help="allow path-reference drops under DIR (repeatable)")
    ps.add_argument("--lang", default="de-DE")
    ps.add_argument("-v", "--verbose", action="store_true")
    ps.set_defaults(func=cmd_serve)

    ph = sub.add_parser(
        "handoff", help="III) merge provenance into pdfdrill's sidecar + analyse",
        description="Merges ingest.json page-provenance under a single `scandrill` "
                    "key in pdfdrill's own sidecar (additive; never clobbers), then "
                    "runs read-only pdfdrill analysis on the built PDF.",
    )
    ph.add_argument("manifest")
    ph.add_argument("--pdf", help="default: the manifest's `pdf` field, alongside it")
    ph.add_argument("--analyze", default="size,route",
                    help="comma-separated read-only pdfdrill commands ('' to skip)")
    ph.add_argument("--no-merge", action="store_true", help="analyse only")
    ph.set_defaults(func=cmd_handoff)

    pt = sub.add_parser("tools", help="report external tool availability")
    pt.set_defaults(func=cmd_tools)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
