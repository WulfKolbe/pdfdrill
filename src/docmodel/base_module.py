"""
BaseModule — abstract base for all processors.

Mirrors the TypeScript BaseModule but produces DocObjects/Realizations
instead of TiddlyWiki tiddlers. Modules collaborate via a shared Document.

Lifecycle (driven by main pipeline, in order):

    1.  __init__(config, bibkey, flags)
    2.  init(doc)                — once after construction, before any processing
    3.  process_document(doc)    — synchronous, in procOrder
    4.  process_objects(doc)     — async-ish, after all process_document have run

`find_items` / `create_object` are the canonical content-extraction split,
preserved from the TypeScript design for ease of porting modules. They are
optional hooks with no-op defaults: most modules override them, while
post-pass modules (e.g. DocumentFlowProcessor) do all their work in
`process_objects` and leave the hooks alone. A module may also override
`process_document` directly when the split is awkward.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Optional

from .core import Document, DocObject


@dataclass
class ModuleConfig:
    title: str = ""
    type: str = ""
    classname: Optional[str] = None
    proc_order: int = 0
    path: Optional[str] = None
    tags: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ModuleConfig":
        known = {"title", "type", "classname", "procOrder", "path", "tags"}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(
            title=d.get("title", ""),
            type=d.get("type", ""),
            classname=d.get("classname"),
            proc_order=int(d.get("procOrder", 0)),
            path=d.get("path"),
            tags=d.get("tags", ""),
            extra=extra,
        )


class BaseModule(ABC):
    """
    Base for processors. Subclasses override the lifecycle hooks they need:
    the find_items/create_object split (the common case), or process_objects
    for cross-object post-passes. All hooks have no-op defaults.
    """

    # The primary text stream's name is fixed; modules that produce object
    # realizations in body text point into this stream.
    LINES_STREAM = "mathpix_lines"

    def __init__(
        self,
        config: ModuleConfig,
        bibkey: str,
        flags: Optional[dict[str, Any]] = None,
    ):
        self.config = config
        self.bibkey = bibkey
        self.flags = flags or {}
        self.debug = bool(self.flags.get("debug", False))
        self.counters: dict[str, int] = {}

    # ----- Lifecycle hooks (override as needed) -----

    def init(self, doc: Document) -> None:
        """Called once after construction. Default: no-op."""
        return None

    def process_document(self, doc: Document) -> None:
        """
        Stage 1 (synchronous). Default implementation runs the
        find_items/create_object split that most modules use.
        """
        items = self.find_items(doc)
        for item in items:
            obj = self.create_object(item, doc)
            if obj is not None:
                doc.add(obj)
        return None

    def process_objects(self, doc: Document) -> None:
        """Stage 2. Default: no-op. Override for cross-object processing."""
        return None

    # ----- Content-extraction hooks (override the ones that fit) -----
    #
    # The default process_document() drives find_items -> create_object. Modules
    # that use that split override these; post-pass modules that work in
    # process_objects can leave them as the no-op defaults below.

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        """Extract item dicts from the document. The shape is module-specific."""
        return []

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        """Convert a single item into a DocObject (or None to skip)."""
        return None

    # ----- Utilities -----

    def name(self) -> str:
        return self.config.classname or self.config.title or self.__class__.__name__

    def log(self, message: str) -> None:
        import sys
        print(f"[{self.name()}] {message}", file=sys.stderr)

    def bump(self, key: str, n: int = 1) -> int:
        self.counters[key] = self.counters.get(key, 0) + n
        return self.counters[key]

    def build_line_index(self, doc: Document) -> dict[str, dict]:
        """
        Build a map line_id -> mathpix line payload dict, for cross-reference
        resolution. The TS code calls this `byId`.
        """
        idx: dict[str, dict] = {}
        if self.LINES_STREAM not in doc.streams:
            return idx
        stream = doc.stream(self.LINES_STREAM)
        for anchor in stream.anchors:
            p = stream.payload[anchor]
            lid = p.get("id")
            if lid:
                idx[lid] = p
        return idx

    def build_anchor_index(self, doc: Document) -> dict[str, "object"]:
        """
        Build a map line_id -> anchor in mathpix_lines, once. The companion to
        build_line_index (which maps line_id -> payload). Build it once per run
        and reuse it; for a single line_id, `build_anchor_index(doc).get(id)`.
        """
        idx: dict[str, "object"] = {}
        if self.LINES_STREAM not in doc.streams:
            return idx
        stream = doc.stream(self.LINES_STREAM)
        for anchor in stream.anchors:
            lid = stream.payload[anchor].get("id")
            if lid:
                idx[lid] = anchor
        return idx
