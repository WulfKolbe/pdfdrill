"""
Convenience runner: extract all features from a text file (or stdin) → JSON.

    python -m features <file.txt> [--page PAGE_ID]
    cat doc.txt | python -m features

Additive only — reads text, prints Features. Does not touch the pipeline.
"""
from __future__ import annotations

import json
import sys

from . import extract_all, available_extractors


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    page_id = ""
    paths: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--page" and i + 1 < len(argv):
            page_id = argv[i + 1]; i += 2
        else:
            paths.append(argv[i]); i += 1
    text = open(paths[0], encoding="utf-8").read() if paths else sys.stdin.read()
    feats = extract_all(text, page_id)
    json.dump({"available": available_extractors(),
               "features": [f.to_dict() for f in feats]},
              sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
