"""
docops CLI entry point.

Usage:
    python -m docops.main \\
        --in     HeimMF.docmodel.json \\
        --config docops_config.json \\
        --out-dir ./out [--name HeimMF] \\
        [--save-mutated HeimMF.mutated.docmodel.json]

Workflow:
  1. Load the input docmodel JSON into a live Document.
  2. Read the config (a list of operator entries).
  3. Run every Mutator in order on the Document.
  4. (Optional) write the resulting mutated Document back to JSON.
  5. Run every Projector in order, writing each one's output to
     <out-dir>/<name><projector.ext>.

If no --config is given, the default pipeline at <package>/default_config.json
is used: Dehyphenate → PlainText → LLMCompact → TiddlyWiki.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from docmodel.core import Document

from .base import BaseMutator, BaseProjector
from .loader import load_config, load_operators


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


def load_document(path: str) -> Document:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Document.from_dict(data)


def save_document(doc: Document, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)


def run(
    in_path: str,
    config_path: str,
    out_dir: str,
    base_name: Optional[str],
    save_mutated_path: Optional[str],
    debug_names: list[str],
) -> None:
    print(f"[main] loading {in_path}", file=sys.stderr)
    doc = load_document(in_path)
    print(
        f"[main] loaded: streams={len(doc.streams)} objects={len(doc.objects)} "
        f"alignments={len(doc.alignments)}",
        file=sys.stderr,
    )

    raw = load_config(config_path)
    operators = load_operators(raw, debug_names=debug_names)
    print(f"[main] loaded {len(operators)} operators", file=sys.stderr)

    if base_name is None:
        # Derive from input filename (strip .docmodel.json or .json).
        base_name = os.path.basename(in_path)
        for suffix in (".docmodel.json", ".json"):
            if base_name.endswith(suffix):
                base_name = base_name[: -len(suffix)]
                break

    os.makedirs(out_dir, exist_ok=True)

    # ----- Pass 1: mutators -----
    for op in operators:
        if isinstance(op, BaseMutator):
            print(f"[main] mutator: {op.name()}", file=sys.stderr)
            op.apply(doc)
            if op.counters:
                print(f"[{op.name()}] {op.counters}", file=sys.stderr)

    if save_mutated_path:
        save_document(doc, save_mutated_path)
        print(f"[main] wrote mutated docmodel to {save_mutated_path}",
              file=sys.stderr)

    # ----- Pass 2: projectors -----
    for op in operators:
        if isinstance(op, BaseProjector):
            print(f"[main] projector: {op.name()}", file=sys.stderr)
            result = op.project(doc)
            out_path = os.path.join(out_dir, base_name + op.output_extension())
            op.write(result, out_path)
            print(f"[{op.name()}] wrote {out_path}", file=sys.stderr)
            if op.counters:
                print(f"[{op.name()}] {op.counters}", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="in_path", required=True,
                   help="Input docmodel JSON")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH,
                   help="Operator pipeline config (JSON list)")
    p.add_argument("--out-dir", default=".",
                   help="Directory for projector outputs")
    p.add_argument("--name", default=None,
                   help="Basename for projector output files "
                        "(default: derived from --in)")
    p.add_argument("--save-mutated", default=None,
                   help="Also write the mutated Document to this path")
    p.add_argument("--debug", default="",
                   help="Comma-separated operator names to enable debug logging for")
    args = p.parse_args()

    debug = [s.strip() for s in args.debug.split(",") if s.strip()]
    run(
        in_path=args.in_path,
        config_path=args.config,
        out_dir=args.out_dir,
        base_name=args.name,
        save_mutated_path=args.save_mutated,
        debug_names=debug,
    )


if __name__ == "__main__":
    main()
