"""
Main CLI entry point.

Usage:
    python -m docmodel.main --lines path/to/lines.json \\
                             [--config path/to/config.json] \\
                             [--bib BIBKEY] \\
                             [--out path/to/output.json] \\
                             [--debug ClassName,ClassName]

The output is a JSON document containing:
    - meta:        document-level metadata (bibkey, pages, ...)
    - streams:     all streams with anchors + per-anchor payload
    - objects:     all DocObjects with realizations + parent/children
    - alignments:  cross-stream typed correspondence edges
"""
from __future__ import annotations

import argparse
import json

from pdfdrill import jsonio as _jsonio
import os
import sys
from typing import Any

from . import ledger as _ledger
from .core import Document
from .loader import load_config, load_modules
from .modules.page import ingest_lines_json


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


def declared_source(lines_json: dict) -> str:
    """The reader a lines.json declares — at the top, or on its pages.

    897 — `lines_json.get("source")` reads the TOP LEVEL only, and a reading
    may declare itself per page instead. 168 of the 1,747 readings in this
    library do exactly that: `source: "pdfminer-docmodel"` on every page and
    `pages` as their only top-level key. Each one built a model that declared
    `meta.source = "mathpix"` — our own glyph reader's output, recorded as the
    paid reader's. It is the upstream half of the mislabelling already measured
    on 24 documents / 1,846 rows from the other end.

    A per-page declaration is not a mistake to tolerate, either: it is the only
    place a MERGED reading can say that its pages came from two readers (the
    emitter in `pdfreader/docmodel_six.py` states both and says so). So the
    pages are consulted, and only a UNANIMOUS answer is accepted — a reading
    whose pages disagree has no single producer, and naming one of them would
    be a guess recorded as provenance.
    """
    top = lines_json.get("source")
    if isinstance(top, str) and top:
        return top
    said = {pg.get("source") for pg in (lines_json.get("pages") or [])
            if isinstance(pg, dict)}
    said.discard(None)
    if len(said) == 1:
        only = said.pop()
        if isinstance(only, str) and only:
            return only
    return ""


def run(
    lines_path: str,
    config_path: str,
    bibkey: str,
    out_path: str,
    debug_modules: list[str],
) -> dict[str, Any]:
    # ----- Step 1: load lines.json -----
    with open(lines_path, "r", encoding="utf-8") as f:
        lines_json = json.load(f)
    print(f"[main] loaded {lines_path}", file=sys.stderr)

    # ----- Step 2: prepare Document and ingest the raw stream -----
    doc = Document()
    doc.meta["bibkey"] = bibkey
    doc.meta["source_path"] = lines_path
    # The producer of this lines.json (mathpix / tesseract / pdfminer / …). It
    # selects the IMAGE-CROP coordinate system downstream: MathPix regions are
    # page-image PIXELS served from cdn.mathpix.com; a pdfminer lines.json (our
    # DRILLPDFse route) carries regions in PDF POINTS served from OUR local
    # pyramid. No mixing — each source stays in its own coordinate system.
    doc.meta["source"] = declared_source(lines_json) or "mathpix"
    # 575 — the code that decided this object graph. Written once, here, and
    # never overwritten by a later save: an enrichment pass changes props, not
    # the structure whose counts a corpus measurement sums.
    from pdfdrill import buildstamp as _buildstamp
    doc.meta["build"] = _buildstamp.stamp()
    ingest_lines_json(doc, lines_json)
    print(
        f"[main] ingested {len(doc.stream('mathpix_lines'))} lines "
        f"across {doc.meta.get('num_pages', 0)} pages",
        file=sys.stderr,
    )

    # 634 — from here on every realization attached to an object records the
    # module that attached it (the claim ledger). Switched on for the rest of
    # the process, NOT just for the module loop: `cmd_model` runs
    # `heading_cleanup` after this function returns and saves the result, and a
    # recording thrown away at the end of the build would be a ledger thrown
    # away before anything could store it.
    _ledger.start_recording()

    # ----- Step 3: load modules from config -----
    raw = load_config(config_path)
    modules = load_modules(raw, bibkey, debug_modules=debug_modules)
    print(f"[main] loaded {len(modules)} modules", file=sys.stderr)

    # ----- Step 4: init -----
    for m in modules:
        m.init(doc)

    # ----- Step 5: process_document in procOrder -----
    for m in modules:
        m.process_document(doc)
        if m.counters:
            print(f"[{m.name()}] {m.counters}", file=sys.stderr)

    # ----- Step 6: process_objects post-pass -----
    for m in modules:
        m.process_objects(doc)

    # ----- Step 7: serialize -----
    # 634 — the claim ledger reaches the file this function writes itself (it
    # does not go through `model_io.save_model`, which carries the same hook).
    _led = _ledger.for_save(doc)
    if _led is not None:
        doc.meta["ledger"] = _led
    out = doc.to_dict()
    with open(out_path, "w", encoding="utf-8") as f:
        _jsonio.dump(out, f, indent=2)   # utf-8-safe (non-UTF-8 filenames)
    print(f"[main] wrote {out_path}", file=sys.stderr)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lines", required=True, help="Path to MathPix lines.json")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config.json")
    p.add_argument("--bib", default="DOC", help="Bibkey prefix for object ids")
    p.add_argument(
        "--out",
        default=None,
        help="Output JSON path. Defaults to <bibkey>.docmodel.json in cwd.",
    )
    p.add_argument(
        "--debug",
        default="",
        help="Comma-separated class names of modules to enable debug logging for",
    )
    args = p.parse_args()

    out_path = args.out or f"{args.bib}.docmodel.json"
    debug = [s.strip() for s in args.debug.split(",") if s.strip()]
    run(
        lines_path=args.lines,
        config_path=args.config,
        bibkey=args.bib,
        out_path=out_path,
        debug_modules=debug,
    )


if __name__ == "__main__":
    main()
