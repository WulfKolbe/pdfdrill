#!/usr/bin/env python3
"""docgraph.py - a lazy, indexed runtime view over a packed docmodel.

``docpack`` is a *storage* format; this is the *access* layer on top of it,
adopting the lazy / reference-based ideas from the design note:

  * the packed model is already reference-based (shared STR/BOX/REG/GEOM/PROF
    tables + integer indices), so nothing needs to be duplicated -- a node
    resolves its own props/text from the tables on demand;
  * ``cached_property`` materialises a node's text exactly once on first access;
  * indexes (by id, by type, and reverse object-links) are built once at load
    from the cheap ``objects`` list -- the 25 MB of per-character streams are
    *never* expanded unless a projector actually asks for them.

For the example model, fully unpacking expands 353k codepoint dicts; a projector
like ``tables`` or ``reading_order`` touches none of them, so the lazy view
loads and projects without paying for the streams at all.

The offset-``TextSlice`` idea from the note (one master string + start/end) does
*not* fit the line/paragraph text here -- those duplicated strings are not
substrings of a single document, so interning (what docpack does) is the right
tool. The one place the slice idea applies is character streams, where the
packed ``t`` blob already is the master string and each anchor's codepoint is a
length-1 slice at its position; ``chars()`` exposes that directly.

stdlib only (imports docpack for per-item resolution).
"""
from __future__ import annotations

from functools import cached_property
from typing import Any, Iterator, Optional

from . import docpack

# object-id link relations that live in props (the document's object graph)
LINK_RELATIONS = (
    "prev_in_flow", "next_in_flow", "parent_section",
    "cited_reference_id", "embedded_image_id",
    "next_sibling", "prev_sibling", "first_section_id",
)


class GraphNode:
    """Lazy wrapper around one packed object."""

    __slots__ = ("_raw", "_g", "__dict__")

    def __init__(self, raw: dict, graph: "DocGraph"):
        self._raw = raw
        self._g = graph

    @property
    def id(self) -> str:
        return self._g._U.STR[self._raw["id"]]

    @property
    def type(self) -> str:
        return self._g._U.OTYPE[self._raw["type"]]

    @cached_property
    def props(self) -> dict:
        # de-intern this node's props once, on first access
        return self._g._U._de_strs(self._raw.get("props", {}))

    @cached_property
    def text(self) -> Optional[str]:
        p = self.props
        return p.get("text") or p.get("caption")

    @property
    def parent(self) -> Optional["GraphNode"]:
        pid = self._raw.get("parent")
        return None if pid is None else self._g._node_by_packed_id(pid)

    @property
    def children(self) -> list["GraphNode"]:
        return [self._g._node_by_packed_id(c) for c in self._raw.get("children", [])]

    def linked(self, relation: str) -> list["GraphNode"]:
        """Outgoing object-id links stored in props (e.g. ``next_in_flow``)."""
        v = self.props.get(relation)
        if v is None:
            return []
        ids = v if isinstance(v, list) else [v]
        out = []
        for i in ids:
            n = self._g.get(i)
            if n is not None:
                out.append(n)
        return out

    def incoming(self, relation: str | None = None) -> list["GraphNode"]:
        """Reverse object-links: nodes that point at this node."""
        return self._g._incoming(self.id, relation)

    def realizations(self) -> list[dict]:
        return [self._g._U._unpack_realization(r) for r in self._raw.get("realizations", [])]

    def __repr__(self) -> str:
        return f"<GraphNode {self.id} {self.type}>"


class DocGraph:
    def __init__(self, packed: dict):
        assert packed.get("docpack"), "DocGraph needs a packed (docpack) model"
        self._packed = packed
        self._U = docpack.Unpacker(packed)          # reused for per-item resolution
        self.meta = packed["meta"]

        # cheap indexes over objects only -- streams stay untouched
        self._by_packed_id: dict[int, GraphNode] = {}
        self._by_id: dict[str, GraphNode] = {}
        self.type_index: dict[str, list[str]] = {}
        STR = self._U.STR
        for raw in packed["objects"]:
            node = GraphNode(raw, self)
            self._by_packed_id[raw["id"]] = node
            self._by_id[STR[raw["id"]]] = node
            self.type_index.setdefault(self._U.OTYPE[raw["type"]], []).append(STR[raw["id"]])

        self._incoming_idx: Optional[dict] = None    # built lazily

    # -- loading -----------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "DocGraph":
        obj = docpack._load(path)
        if not obj.get("docpack"):
            obj = docpack.pack(obj)                   # accept a plain model too
        return cls(obj)

    # -- node access -------------------------------------------------------
    def get(self, node_id: str) -> Optional[GraphNode]:
        return self._by_id.get(node_id)

    def _node_by_packed_id(self, pid: int) -> GraphNode:
        return self._by_packed_id[pid]

    def of_type(self, type_name: str) -> Iterator[GraphNode]:
        for nid in self.type_index.get(type_name, ()):
            yield self._by_id[nid]

    def __iter__(self) -> Iterator[GraphNode]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    # -- reverse object-link index (built on first use) --------------------
    def _build_incoming(self) -> None:
        idx: dict[tuple[str, str], list[str]] = {}
        for node in self._by_id.values():
            src = node.id
            for rel in LINK_RELATIONS:
                v = node.props.get(rel)
                if v is None:
                    continue
                for tgt in (v if isinstance(v, list) else [v]):
                    idx.setdefault((tgt, rel), []).append(src)
        self._incoming_idx = idx

    def _incoming(self, target_id: str, relation: str | None) -> list[GraphNode]:
        if self._incoming_idx is None:
            self._build_incoming()
        assert self._incoming_idx is not None
        if relation is not None:
            return [self._by_id[i] for i in self._incoming_idx.get((target_id, relation), [])]
        out = []
        for (tgt, _rel), srcs in self._incoming_idx.items():
            if tgt == target_id:
                out.extend(self._by_id[i] for i in srcs)
        return out

    # -- stream access (lazy; char streams never expand to per-char dicts) -
    def chars(self, stream_name: str) -> str:
        """The master codepoint string of a character stream (no dict build)."""
        s = self._packed["streams"][stream_name]
        if s["k"] != "c":
            raise ValueError(f"{stream_name} is not a character stream")
        return s["t"]

    def line(self, stream_name: str, i: int) -> dict:
        """Resolve a single line of a payload stream from the shared tables."""
        s = self._packed["streams"][stream_name]
        if s["k"] != "p":
            raise ValueError(f"{stream_name} is not a payload stream")
        return self._U._unpack_line(s["p"][i])

    def stream_anchor(self, stream_name: str, i: int) -> str:
        ah = self._packed["streams"][stream_name]["ah"]
        h = ah[i * docpack.ANCHOR_HEX:(i + 1) * docpack.ANCHOR_HEX]
        return docpack._restore_anchor(h)


if __name__ == "__main__":
    import sys
    g = DocGraph.load(sys.argv[1])
    print(f"{len(g)} nodes; types: " + ", ".join(
        f"{t}:{len(ids)}" for t, ids in sorted(g.type_index.items(), key=lambda kv: -len(kv[1]))[:6]))
    doc = next(g.of_type("Document"), None)
    if doc:
        print("Document:", doc.id, "->", [n.id for n in doc.children][:5], "...")
    p1 = next(g.of_type("Paragraph"), None)
    if p1:
        print("first paragraph text:", repr(p1.text)[:80])
        print("  incoming next_in_flow:", [n.id for n in p1.incoming("next_in_flow")])
