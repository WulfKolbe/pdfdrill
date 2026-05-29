"""
docops loader.

Reads a JSON list of operator entries, instantiates each via a registry,
and returns them in order. Same shape as docmodel/loader.py.
"""
from __future__ import annotations

import importlib
import json
import sys
from typing import Optional

from .base import BaseOperator, BaseMutator, BaseProjector, OperatorConfig


DEFAULT_REGISTRY: dict[str, str] = {
    # Mutators
    "Dehyphenate":          "docops.mutators.dehyphenate",
    "PromoteCleanedText":   "docops.mutators.promote_cleaned",

    # Projectors
    "PlainTextProjector":   "docops.projectors.plaintext",
    "LLMCompactProjector":  "docops.projectors.llm_compact",
    "TiddlyWikiProjector":  "docops.projectors.tiddlywiki",
    "CompressedTiddlersProjector": "docops.projectors.compressed_tiddlers",
    "ComparisonHtmlProjector": "docops.projectors.comparison_html",
    "FormulaReportProjector": "docops.projectors.formula_report",
}


def load_config(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Config at {path} must be a JSON array of operator entries")
    return data


def load_operators(
    entries: list[dict],
    debug_names: Optional[list[str]] = None,
    registry: Optional[dict[str, str]] = None,
) -> list[BaseOperator]:
    debug_names = debug_names or []
    registry = registry or DEFAULT_REGISTRY

    operators: list[BaseOperator] = []
    for raw in entries:
        # Allow shared config files: silently skip entries that aren't
        # operator entries (e.g. docmodel module entries identified by
        # 'type'='application/python').
        if "op" not in raw:
            continue
        cfg = OperatorConfig.from_dict(raw)
        if not cfg.enabled:
            print(f"[loader] skipping disabled {cfg.classname}", file=sys.stderr)
            continue
        if cfg.classname not in registry:
            print(f"[loader] unknown operator: {cfg.classname}", file=sys.stderr)
            continue
        modname = registry[cfg.classname]
        try:
            mod = importlib.import_module(modname)
        except ImportError as e:
            print(f"[loader] failed to import {modname}: {e}", file=sys.stderr)
            continue
        cls = getattr(mod, cfg.classname, None)
        if cls is None:
            print(f"[loader] class {cfg.classname} not in {modname}", file=sys.stderr)
            continue

        # Validate that the class matches the declared op type, so misconfig
        # gets caught early instead of producing weird runtime behavior.
        if cfg.op == "mutator" and not issubclass(cls, BaseMutator):
            print(f"[loader] {cfg.classname} declared as mutator but isn't a BaseMutator",
                  file=sys.stderr)
            continue
        if cfg.op == "projector" and not issubclass(cls, BaseProjector):
            print(f"[loader] {cfg.classname} declared as projector but isn't a BaseProjector",
                  file=sys.stderr)
            continue

        flags = {"debug": cfg.classname in debug_names or cfg.title in debug_names}
        operators.append(cls(cfg, flags))
        print(f"[loader] loaded {cfg.op}:{cfg.classname}", file=sys.stderr)
    return operators
