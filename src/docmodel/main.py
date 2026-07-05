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
import os
import sys
from typing import Any

from .core import Document
from .loader import load_config, load_modules
from .modules.page import ingest_lines_json


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


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
    doc.meta["source"] = lines_json.get("source") or "mathpix"
    ingest_lines_json(doc, lines_json)
    print(
        f"[main] ingested {len(doc.stream('mathpix_lines'))} lines "
        f"across {doc.meta.get('num_pages', 0)} pages",
        file=sys.stderr,
    )

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
    out = doc.to_dict()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
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
