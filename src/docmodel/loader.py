"""
Module loader. Reads config.json, filters to application/python module entries,
sorts by procOrder, and dynamically imports module classes.

The TypeScript version used 'application/javascript' as the trigger type and
expected .ts files. Here we use 'application/python' and look up classes by
classname in our `docmodel.modules` package (or any package given in `path`).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .base_module import BaseModule, ModuleConfig


def load_config(config_path: str) -> list[dict[str, Any]]:
    """Load a JSON config file. Must be a list of entries (like the TS version)."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Config at {config_path} must be a JSON array")
    return data


# Map classname -> dotted-import-path so the loader can find each module.
# We register modules here rather than reading file paths, which is cleaner
# in Python and avoids the TS-style filesystem scan.
DEFAULT_REGISTRY: dict[str, str] = {
    "PageProcessor":               "docmodel.modules.page",
    "FootnoteProcessor":           "docmodel.modules.footnote",
    "CitationProcessor":           "docmodel.modules.citation",
    "TableProcessor":              "docmodel.modules.table",
    "SidenoteProcessor":           "docmodel.modules.sidenote",
    "TocProcessor":                "docmodel.modules.toc",
    "AbstractProcessor":           "docmodel.modules.abstract",
    "DiagramProcessor":            "docmodel.modules.diagram",
    "HeaderProcessor":             "docmodel.modules.header",
    "PictureProcessor":            "docmodel.modules.picture",
    "ListProcessor":               "docmodel.modules.list_items",
    "EquationProcessor":           "docmodel.modules.equation",
    "FormulaProcessor":            "docmodel.modules.formula",
    "ParagraphProcessor":          "docmodel.modules.paragraph",
    "DehyphenationProcessor":      "docmodel.modules.dehyphenation",
    "DocumentFlowProcessor":       "docmodel.modules.document_flow",
    "DocumentStructureProcessor":  "docmodel.modules.document_structure",
}


def load_modules(
    raw_entries: list[dict[str, Any]],
    bibkey: str,
    debug_modules: Optional[list[str]] = None,
    registry: Optional[dict[str, str]] = None,
) -> list[BaseModule]:
    """
    Instantiate modules from config entries.

    Only entries with type == 'application/python' are considered. They are
    sorted by procOrder ascending (matching TS behavior).
    """
    debug_modules = debug_modules or []
    registry = registry or DEFAULT_REGISTRY

    module_entries = [
        e for e in raw_entries if e.get("type") == "application/python"
    ]
    module_entries.sort(key=lambda e: int(e.get("procOrder", 0)))

    out: list[BaseModule] = []
    for entry in module_entries:
        cfg = ModuleConfig.from_dict(entry)
        if not cfg.classname:
            print(f"[loader] skipping entry without classname: {entry}", file=sys.stderr)
            continue
        if cfg.classname not in registry:
            print(f"[loader] unknown classname: {cfg.classname}", file=sys.stderr)
            continue
        modname = registry[cfg.classname]
        try:
            mod = importlib.import_module(modname)
        except ImportError as e:
            print(f"[loader] failed to import {modname}: {e}", file=sys.stderr)
            continue
        cls = getattr(mod, cfg.classname, None)
        if cls is None:
            print(f"[loader] class {cfg.classname} not found in {modname}", file=sys.stderr)
            continue
        flags = {"debug": cfg.classname in debug_modules}
        out.append(cls(cfg, bibkey, flags))
        print(f"[loader] loaded {cfg.classname} (procOrder={cfg.proc_order})", file=sys.stderr)
    return out
