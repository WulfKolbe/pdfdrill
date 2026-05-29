"""
Core primitives for the DocObject model.

The model:
  - Anchor:      Opaque, stable identity for a position within a Stream.
  - Stream:      Ordered list of anchors plus per-anchor payload.
  - Range:       (stream_name, start_anchor, end_anchor) — half-inclusive interval.
  - Realization: One way a DocObject surfaces in one stream (Range + role + props).
  - DocObject:   Typed entity with stream-independent properties + realizations + children.
  - Alignment:   Typed correspondence between two ranges (often across streams).
  - Document:    The container that holds streams, objects, and alignments.

Identity is via opaque anchor IDs, not integer positions. Inserts/deletes in one
stream do not invalidate references from other streams or from objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from uuid import uuid4


# ---------- IDs ----------

def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}"


# ---------- Anchor ----------

@dataclass(frozen=True)
class Anchor:
    """Opaque stable identity for a position in some stream."""
    id: str = field(default_factory=lambda: _new_id("a_"))

    def __repr__(self) -> str:  # short, readable
        return f"Anchor({self.id})"


# ---------- Stream ----------

@dataclass
class Stream:
    """
    A named, ordered sequence of anchors with per-anchor payload (a dict).

    The payload dict is intentionally schema-free; different streams use
    different keys. For `mathpix_lines` the payload mirrors the original
    MathPix line object (text, region, font_size, type, page, ...).
    For character-level streams (e.g. `latex_<id>`) it's {'codepoint': 'x'}.
    """
    name: str
    anchors: list[Anchor] = field(default_factory=list)
    payload: dict[Anchor, dict[str, Any]] = field(default_factory=dict)
    # Reverse index from anchor -> position, kept in sync. For random access.
    _pos: dict[Anchor, int] = field(default_factory=dict, repr=False)

    def append(self, **props: Any) -> Anchor:
        a = Anchor()
        self.anchors.append(a)
        self.payload[a] = dict(props)
        self._pos[a] = len(self.anchors) - 1
        return a

    def index_of(self, a: Anchor) -> int:
        return self._pos[a]

    def slice_anchors(self, start: Anchor, end: Anchor) -> list[Anchor]:
        """Inclusive slice from start to end."""
        i = self._pos[start]
        j = self._pos[end]
        if i > j:
            i, j = j, i
        return self.anchors[i:j + 1]

    def __len__(self) -> int:
        return len(self.anchors)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "anchors": [a.id for a in self.anchors],
            "payload": {a.id: self.payload[a] for a in self.anchors},
        }


# ---------- Range ----------

@dataclass(frozen=True)
class Range:
    """
    A range of anchors within a named stream. Inclusive on both ends.

    Either end may be None when the Range serves only as a stream-level
    reference (e.g. a Realization into an opaque external stream like 'cdn'
    where the URL is the substance and there are no anchors to address).

    The stream is identified by name (not by reference) so a Range is a small,
    serializable, self-locating value object.
    """
    stream: str
    start: Optional[Anchor] = None
    end: Optional[Anchor] = None

    def to_dict(self) -> dict:
        return {
            "stream": self.stream,
            "start": self.start.id if self.start else None,
            "end": self.end.id if self.end else None,
        }


# ---------- Realization ----------

@dataclass
class Realization:
    """
    One way a DocObject surfaces in one stream.

    `role` distinguishes multiple realizations in the same stream — typically:
      'surface'  — where the object appears in running text/source
      'cleaned'  — a normalized version
      'caption'  — the caption sub-range of a figure
      'tikz'     — TikZ reconstruction of an image
      'cdn'      — opaque pointer (no anchor range) to a CDN-rendered image
    """
    stream: str
    start: Optional[Anchor] = None
    end: Optional[Anchor] = None
    role: str = "surface"
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "stream": self.stream,
            "start": self.start.id if self.start else None,
            "end": self.end.id if self.end else None,
            "role": self.role,
            "props": self.props,
        }


# ---------- DocObject ----------

@dataclass
class DocObject:
    """
    A typed entity with stream-independent properties and zero or more
    realizations across streams. Objects may have children (e.g. Section
    containing Paragraphs, MathExpression containing Fraction containing
    Numerator).
    """
    type: str = ""
    id: str = field(default_factory=lambda: _new_id("obj_"))
    props: dict[str, Any] = field(default_factory=dict)
    realizations: list[Realization] = field(default_factory=list)
    children: list[str] = field(default_factory=list)   # child object IDs
    parent: Optional[str] = None                         # parent object ID

    def add_realization(self, r: Realization) -> None:
        self.realizations.append(r)

    def realizations_in(self, stream: str) -> list[Realization]:
        return [r for r in self.realizations if r.stream == stream]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "props": self.props,
            "realizations": [r.to_dict() for r in self.realizations],
            "children": list(self.children),
            "parent": self.parent,
        }


# ---------- Alignment ----------

@dataclass
class Alignment:
    """
    A typed correspondence between two ranges, often across streams.

    `kind` examples: 'render' (latex_source -> unicode_render),
                     'dehyphenate', 'transliterate', 'normalize',
                     'bbox_overlap' (joining text and image streams), ...
    """
    kind: str
    left: Range
    right: Range
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "props": self.props,
        }


# ---------- Document ----------

@dataclass
class Document:
    """
    Container for streams, objects, and alignments. Provides simple indexes
    (by id, by type, by realization stream) so modules can ask the right
    questions efficiently without each maintaining its own bookkeeping.
    """
    streams: dict[str, Stream] = field(default_factory=dict)
    objects: dict[str, DocObject] = field(default_factory=dict)
    alignments: list[Alignment] = field(default_factory=list)
    # Bag of arbitrary document-level metadata (bibkey, source path, ...).
    meta: dict[str, Any] = field(default_factory=dict)

    # ----- streams -----
    def ensure_stream(self, name: str) -> Stream:
        if name not in self.streams:
            self.streams[name] = Stream(name=name)
        return self.streams[name]

    def stream(self, name: str) -> Stream:
        return self.streams[name]

    # ----- objects -----
    def add(self, obj: DocObject) -> DocObject:
        self.objects[obj.id] = obj
        return obj

    def add_child(self, parent: DocObject, child: DocObject) -> None:
        child.parent = parent.id
        parent.children.append(child.id)
        self.add(child)

    def objects_of_type(self, t: str) -> list[DocObject]:
        return [o for o in self.objects.values() if o.type == t]

    def objects_with_realization_in(self, stream: str) -> list[DocObject]:
        return [
            o for o in self.objects.values()
            if any(r.stream == stream for r in o.realizations)
        ]

    # ----- alignments -----
    def add_alignment(self, a: Alignment) -> None:
        self.alignments.append(a)

    # ----- serialization -----
    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "streams": {name: s.to_dict() for name, s in self.streams.items()},
            "objects": [o.to_dict() for o in self.objects.values()],
            "alignments": [a.to_dict() for a in self.alignments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        """
        Round-trip a Document from its JSON form.

        Anchors are reconstructed as `Anchor` objects with their original IDs;
        all references (in Realization.start/end and Alignment.left/right) are
        resolved through a single anchor lookup so identity is preserved
        across the document.
        """
        doc = cls()
        doc.meta = dict(d.get("meta", {}))

        # (stream_name, anchor_id) -> Anchor instance
        lookup: dict[tuple[str, str], Anchor] = {}

        for name, sd in d.get("streams", {}).items():
            stream = doc.ensure_stream(name)
            for aid in sd.get("anchors", []):
                a = Anchor(id=aid)
                stream.anchors.append(a)
                stream._pos[a] = len(stream.anchors) - 1
                stream.payload[a] = dict(sd.get("payload", {}).get(aid, {}))
                lookup[(name, aid)] = a

        def resolve(stream_name: str, aid: Any) -> Optional[Anchor]:
            if aid is None:
                return None
            return lookup.get((stream_name, aid))

        for od in d.get("objects", []):
            realizations: list[Realization] = []
            for rd in od.get("realizations", []):
                sname = rd["stream"]
                realizations.append(Realization(
                    stream=sname,
                    start=resolve(sname, rd.get("start")),
                    end=resolve(sname, rd.get("end")),
                    role=rd.get("role", "surface"),
                    props=dict(rd.get("props", {})),
                ))
            obj = DocObject(
                id=od["id"],
                type=od["type"],
                props=dict(od.get("props", {})),
                realizations=realizations,
                children=list(od.get("children", [])),
                parent=od.get("parent"),
            )
            doc.objects[obj.id] = obj

        for ad in d.get("alignments", []):
            ls, rs = ad["left"]["stream"], ad["right"]["stream"]
            doc.alignments.append(Alignment(
                kind=ad["kind"],
                left=Range(ls, resolve(ls, ad["left"]["start"]),
                            resolve(ls, ad["left"]["end"])),
                right=Range(rs, resolve(rs, ad["right"]["start"]),
                            resolve(rs, ad["right"]["end"])),
                props=dict(ad.get("props", {})),
            ))

        return doc
