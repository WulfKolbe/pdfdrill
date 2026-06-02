"""
Read-only nested-container audit (Agent 2). Scans for nested container *type
annotations* (e.g. `list[list[...]]`, `dict[str, list[dict[...]]]`) and nested
list/dict *literals*, emitting a JSON array of findings to stdout. Report only —
never modifies source.

    python -m features.audit_nested [root=src]

Each finding: {"file", "line", "purpose" (the source construct), "can_be_flattened"}.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import warnings

_CONTAINERS = {"list", "List", "dict", "Dict", "tuple", "Tuple", "set", "Set"}


def _container_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Subscript):
        v = node.value
        if isinstance(v, ast.Name) and v.id in _CONTAINERS:
            return v.id
        if isinstance(v, ast.Attribute) and v.attr in _CONTAINERS:
            return v.attr
    return None


def _has_nested_container(node: ast.AST) -> bool:
    """True if a container-subscript directly contains another container-subscript."""
    if _container_name(node) is None:
        return False
    for child in ast.walk(node):
        if child is node:
            continue
        if _container_name(child) is not None:
            return True
    return False


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _scan(path: str) -> list[dict]:
    try:
        with warnings.catch_warnings():       # don't surface scanned code's warnings
            warnings.simplefilter("ignore")
            tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, OSError):
        return []
    found: list[dict] = []
    seen: set[tuple] = set()
    for n in ast.walk(tree):
        purpose = None
        if isinstance(n, ast.Subscript) and _has_nested_container(n):
            purpose = _src(n)
        elif isinstance(n, ast.List) and any(isinstance(e, (ast.List, ast.Dict)) for e in n.elts):
            purpose = "nested list literal: " + _src(n)[:80]
        if purpose:
            key = (getattr(n, "lineno", 0), purpose)
            if key in seen:
                continue
            seen.add(key)
            found.append({"file": path, "line": getattr(n, "lineno", 0),
                          "purpose": purpose, "can_be_flattened": True})
    return found


def audit(root: str = "src") -> list[dict]:
    out: list[dict] = []
    for dp, _, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".py"):
                out.extend(_scan(os.path.join(dp, f)))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = argv[0] if argv else "src"
    json.dump(audit(root), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
