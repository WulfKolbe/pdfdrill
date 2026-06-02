"""
Read-only module-dependency audit (Agent 1). Scans imports per source file and
emits a JSON list to stdout — never modifies any source.

    python -m features.audit_deps [root=src]

Each entry: {"module", "inputs" (internal modules it imports),
"outputs" (top-level classes/functions it defines)}.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import warnings

_INTERNAL = {"pdfdrill", "docmodel", "docops", "features"}


def _scan(path: str) -> tuple[list[str], list[str]]:
    try:
        with warnings.catch_warnings():       # don't surface scanned code's warnings
            warnings.simplefilter("ignore")
            tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, OSError):
        return [], []
    imports: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mod = ("." * (n.level or 0)) + (n.module or "")
            if n.level or (n.module and n.module.split(".")[0] in _INTERNAL):
                imports.add(mod)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in _INTERNAL:
                    imports.add(a.name)
    defines = [n.name for n in tree.body
               if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    return sorted(imports), defines


def audit(root: str = "src") -> list[dict]:
    out = []
    for dp, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            inputs, outputs = _scan(p)
            module = os.path.relpath(p, root)[:-3].replace(os.sep, ".")
            out.append({"module": module, "inputs": inputs, "outputs": outputs})
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = argv[0] if argv else "src"
    json.dump(audit(root), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
