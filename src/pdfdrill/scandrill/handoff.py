"""Stage III — hand the PDF + provenance to pdfdrill.

The deliverable is a pair sitting next to each other: ``job.pdf`` and its
``ingest.json``. This module writes SCANDRILL's page-provenance into pdfdrill's
own sidecar so the two toolchains share one state file, and can drive pdfdrill's
scanned-bundle analysis.

**The merge contract.** pdfdrill's ``Sidecar._load()`` reads the whole JSON dict
and ``save()`` writes the whole dict back — so unknown top-level keys round-trip
untouched. That is what makes a namespaced ``scandrill`` key safe in BOTH
directions: pdfdrill preserves ours, and we never rebuild its keys from scratch.
We read-modify-write; we never author the file wholesale.

The sidecar's *location* comes from pdfdrill's own ``blob_dir_for`` (via
``tools.sidecar_path``) — it is NOT always ``<pdf>.drill.json``; the library
layout uses ``<stem>/<stem>.drill.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .manifest import Manifest, merge_into_sidecar
from .tools import DEFAULT as DEFAULT_TOOLS, Tools

# Read-only/analysis commands that inform "is this PDF good enough?".
# Deliberately NOT the build/extract commands (model/mathpix/tiddlers/...): those
# are pdfdrill's job downstream, are preflight-gated, and cost real money/time.
ANALYSIS_COMMANDS = ("size", "route", "autosegment", "pageside", "continuity",
                     "pdfinfo", "status", "doctor", "ls", "links", "fonts",
                     "images", "qr", "entities", "segment", "ordered")

# Hard-blocked here: pdfdrill's SKILL gates these behind `preflight --ack`, and
# tools.run_pdfdrill sets PDFDRILL_NO_PREFLIGHT=1 for automation — which would
# walk straight through that gate. They also cost money (mathpix/vision) and are
# pdfdrill's decision to make, not ours.
BUILD_COMMANDS = ("model", "mathpix", "latex", "tiddlers", "semantic", "make",
                  "vision", "visionocr", "snip", "render", "elements", "merge")


class HandoffError(RuntimeError):
    pass


@dataclass
class HandoffResult:
    pdf: Path
    sidecar: Path | None = None
    merged: bool = False
    analyses: dict | None = None
    warnings: list[str] = field(default_factory=list)


def route_warnings(manifest: Manifest, analyses: dict | None) -> list[str]:
    """Catch the OCR/route interaction: our own text layer misleads pdfdrill.

    Measured on one real scan, same pages, only `--ocr` differing:

        no_ocr.pdf   → "scanned → Gemma 4 [keyed]"                  (correct)
        with_ocr.pdf → "born-digital → pdfminer/text-layer"         (WRONG)

    `route` infers born-digital from the presence of a text layer, so grafting
    OCR makes a scan look born-digital and sends pdfdrill to pdfminer — which
    would merely re-extract our plain tesseract text instead of running the
    vision lane that reads equations (SKILL rule 4: never accept a 0-equation
    model of a math paper). The OCR layer helps a human search the PDF and
    actively hurts pdfdrill's routing, so it must be surfaced, not buried.
    """
    if not analyses:
        return []
    route = (analyses.get("route") or {}).get("out", "")
    if not route:
        return []
    ocr_applied = bool((manifest.ocr or {}).get("applied"))
    scanned_origin = any(
        (p.origin or {}).get("kind") in {"adf", "camera"} for p in manifest.pages
    )
    if ocr_applied and "born-digital" in route:
        return [
            "pdfdrill routed this as BORN-DIGITAL because of the OCR text layer "
            "WE added — but these pages are a scan. pdfminer will just re-read "
            "our tesseract text instead of running a vision lane. Hand pdfdrill "
            "the PDF built WITHOUT --ocr, or force the lane explicitly."
        ]
    if scanned_origin and "born-digital" in route and not ocr_applied:
        return [
            "pdfdrill routed scanned pages as born-digital — the PDF has a text "
            "layer from somewhere unexpected; check before trusting extraction."
        ]
    return []


def sidecar_for(pdf: str | Path, tools: Tools | None = None) -> Path:
    """Resolve the sidecar path via pdfdrill's own rule; raise if unavailable."""
    tools = tools or DEFAULT_TOOLS
    p = tools.sidecar_path(pdf)
    if p is None:
        raise HandoffError(
            f"cannot resolve pdfdrill's sidecar layout — is PDFDRILL_HOME correct? "
            f"(looked in {tools.pdfdrill_home})"
        )
    return p


def merge_provenance(
    manifest: Manifest,
    pdf: str | Path,
    *,
    tools: Tools | None = None,
) -> Path:
    """Merge ingest provenance into pdfdrill's sidecar, additively.

    Read-modify-write under the single ``scandrill`` key: every pdfdrill key
    (facts/evidence/pdfinfo/layers/transitions/...) is preserved, and a later
    pdfdrill run preserves ours in turn.

    Goes through **pdfdrill's own Sidecar class**, not a hand-rolled JSON write.
    pdfdrill only initialises its default skeleton when the file is absent, so a
    sidecar authored by us would leave it with no ``pdf``/``facts``/``evidence``
    keys at all — its class owns creation, layout and the version stamp.
    """
    tools = tools or DEFAULT_TOOLS
    path = sidecar_for(pdf, tools)
    if path.exists():
        # Fail loudly on a corrupt file rather than let pdfdrill's loader raise
        # somewhere less legible.
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise HandoffError(f"sidecar at {path} is unreadable: {exc}") from exc
        if not isinstance(existing, dict):
            raise HandoffError(f"sidecar at {path} is not a JSON object")

    sc = tools.pdfdrill_sidecar(pdf)
    if sc is None:
        raise HandoffError(f"pdfdrill sidecar module unavailable "
                           f"(PDFDRILL_HOME={tools.pdfdrill_home})")
    merged = merge_into_sidecar(manifest, sc._data)
    sc._data.clear()
    sc._data.update(merged)
    sc.save()
    return path


def analyze(
    pdf: str | Path,
    commands: tuple[str, ...] = ("size", "route"),
    *,
    tools: Tools | None = None,
    timeout: float = 600.0,
) -> dict:
    """Run pdfdrill's read-only analysis to judge the PDF we just built.

    Per the design rule, this is used to *check the artifact*, not to extract
    content — pdfdrill decides its own lane downstream. Unknown/failed commands
    are reported, never raised: analysis is advisory.
    """
    tools = tools or DEFAULT_TOOLS
    blocked = [c for c in commands if c in BUILD_COMMANDS]
    if blocked:
        raise HandoffError(
            f"refusing to run pdfdrill build/extract command(s) {blocked}: they are "
            f"preflight-gated, may cost money, and are pdfdrill's call downstream. "
            f"Analysis commands: {', '.join(ANALYSIS_COMMANDS)}"
        )
    out: dict[str, dict] = {}
    for cmd in commands:
        try:
            r = tools.run_pdfdrill(cmd, pdf, timeout=timeout)
            out[cmd] = {
                "rc": r.returncode,
                "out": (r.stdout or "").strip(),
                "err": (r.stderr or "").strip()[:400],
            }
        except FileNotFoundError as exc:
            raise HandoffError(str(exc)) from exc
        except Exception as exc:  # a slow/odd command must not sink the handoff
            out[cmd] = {"rc": -1, "out": "", "err": f"{type(exc).__name__}: {exc}"}
    return out


def handoff(
    manifest: Manifest,
    pdf: str | Path,
    *,
    commands: tuple[str, ...] = ("size", "route"),
    merge: bool = True,
    tools: Tools | None = None,
) -> HandoffResult:
    """Full stage III: merge provenance, then run advisory analysis."""
    pdf = Path(pdf)
    if not pdf.exists():
        raise HandoffError(f"no such PDF: {pdf}")
    res = HandoffResult(pdf=pdf)
    if merge:
        res.sidecar = merge_provenance(manifest, pdf, tools=tools)
        res.merged = True
    if commands:
        res.analyses = analyze(pdf, commands, tools=tools)
        res.warnings = route_warnings(manifest, res.analyses)
    return res
