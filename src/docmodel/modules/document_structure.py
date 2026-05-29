"""
DocumentStructureProcessor (procOrder 999, post-pass).

Builds the hierarchical document structure on top of the flow-ordered objects
produced by DocumentFlowProcessor:

  1. Section hierarchy from level: each Section gets a parent (a higher-level
     Section ancestor, or the synthetic Document root).
  2. Section numbering ('1', '1.2', '1.2.3') derived from the hierarchy.
  3. Each content object (Paragraph, Equation, Table, ...) is assigned a
     parent_section based on its flow position relative to Section anchors.
  4. A synthetic root `Document` object is created with bibkey as id, owning
     all top-level Sections (and any orphan content before the first section).

Like DocumentFlowProcessor, this writes results as props/children on the
existing objects — it does not create extra "FLOW" or "TOC" tiddlers.
"""
from __future__ import annotations

from typing import Optional

from ..base_module import BaseModule
from ..core import Document, DocObject


_CONTENT_TYPES = {
    "Paragraph", "Equation", "Table", "Picture", "Diagram",
    "Footnote", "Sidenote", "Formula", "ListItem",
    "Abstract", "Toc",
}


class DocumentStructureProcessor(BaseModule):
    # A post-pass module: all work happens in process_objects. find_items/
    # create_object keep their base no-op defaults.

    def process_objects(self, doc: Document) -> None:
        sections = self._sections_in_flow_order(doc)
        self._assign_section_parents(sections, doc)
        self._assign_section_numbers(sections, doc)
        self._assign_content_parent_sections(sections, doc)
        self._create_document_root(sections, doc)

    # ---------- helpers ----------

    @staticmethod
    def _flow_index(obj: DocObject) -> int:
        v = obj.props.get("flow_index")
        return v if isinstance(v, int) else 10**9  # objects without flow last

    def _sections_in_flow_order(self, doc: Document) -> list[DocObject]:
        sections = [o for o in doc.objects.values() if o.type == "Section"]
        sections.sort(key=self._flow_index)
        return sections

    def _assign_section_parents(self, sections: list[DocObject], doc: Document) -> None:
        stack: list[DocObject] = []
        for section in sections:
            level = section.props.get("level", 1)
            while stack and stack[-1].props.get("level", 1) >= level:
                stack.pop()
            if stack:
                parent = stack[-1]
                section.parent = parent.id
                if section.id not in parent.children:
                    parent.children.append(section.id)
            stack.append(section)

    def _assign_section_numbers(self, sections: list[DocObject], doc: Document) -> None:
        # Walk in flow order, maintaining a running counter per depth.
        # The depth of a section is the length of its ancestor chain among
        # other Section objects.
        counters: list[int] = []
        depth_of: dict[str, int] = {}
        for section in sections:
            depth = self._section_depth(section, doc)
            depth_of[section.id] = depth
            if depth >= len(counters):
                counters.extend([0] * (depth + 1 - len(counters)))
            counters[depth] += 1
            # Reset all deeper counters when going up or staying level.
            for i in range(depth + 1, len(counters)):
                counters[i] = 0
            number = ".".join(str(counters[i]) for i in range(depth + 1) if counters[i] > 0)
            section.props["section_number"] = number

    def _section_depth(self, section: DocObject, doc: Document) -> int:
        d = 0
        cur = section
        while cur.parent:
            parent = doc.objects.get(cur.parent)
            if parent is None or parent.type != "Section":
                break
            d += 1
            cur = parent
        return d

    def _assign_content_parent_sections(
        self, sections: list[DocObject], doc: Document,
    ) -> None:
        if not sections:
            return
        # Sort all content objects by flow_index; walk side-by-side with
        # sections to bucket them.
        content = [
            o for o in doc.objects.values()
            if o.type in _CONTENT_TYPES and isinstance(o.props.get("flow_index"), int)
        ]
        content.sort(key=self._flow_index)
        section_flow = [(self._flow_index(s), s) for s in sections]

        for obj in content:
            f = obj.props["flow_index"]
            # Find the latest section whose flow_index is <= obj's flow_index.
            owner: Optional[DocObject] = None
            for sf, s in section_flow:
                if sf <= f:
                    owner = s
                else:
                    break
            if owner is None:
                continue  # before any section; will be attached to root
            obj.props["parent_section"] = owner.id
            if obj.id not in owner.children:
                owner.children.append(obj.id)

    def _create_document_root(
        self, sections: list[DocObject], doc: Document,
    ) -> None:
        # Top-level sections = those whose parent is None (after _assign_section_parents).
        top_sections = [s for s in sections if s.parent is None]
        # Orphans: any content object whose parent_section was never set.
        orphans = [
            o for o in doc.objects.values()
            if o.type in _CONTENT_TYPES
            and "parent_section" not in o.props
            and isinstance(o.props.get("flow_index"), int)
        ]

        pages = [o for o in doc.objects.values() if o.type == "Page"]
        paragraphs = [o for o in doc.objects.values() if o.type == "Paragraph"]

        root = DocObject(
            type="Document",
            id=self.bibkey,  # human-readable id, matches the TS convention
            props={
                "bibkey": self.bibkey,
                "total_pages": len(pages),
                "total_sections": len(sections),
                "total_paragraphs": len(paragraphs),
                "first_section_id": top_sections[0].id if top_sections else None,
            },
        )
        for s in top_sections:
            s.parent = root.id
            root.children.append(s.id)
        for o in orphans:
            o.props["parent_section"] = root.id
            if o.id not in root.children:
                root.children.append(o.id)

        # Sibling next/prev for top-level Sections, mirroring TS behavior.
        for i, s in enumerate(top_sections):
            if i > 0:
                s.props["prev_sibling"] = top_sections[i - 1].id
            if i < len(top_sections) - 1:
                s.props["next_sibling"] = top_sections[i + 1].id

        doc.add(root)
        doc.meta["root_id"] = root.id
