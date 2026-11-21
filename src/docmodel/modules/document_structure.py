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
        # LAST, so the container it sets wins over the section parent above.
        self._link_reading_children(doc)

    # ---------- helpers ----------

    def _link_reading_children(self, doc: Document) -> None:
        r"""Carry the READING'S OWN parent/child relation into the model.

        A reading may state that some lines belong to another line: Gemma4
        7bd3786 writes a figure's printed subcaptions as lines whose parent is
        the diagram, in `children_ids`. `page.ingest` keeps every field of the
        line (`payload = dict(line)`), so the relation is in the stream — and
        nothing in `src/docmodel/` ever read it, so the objects came out as
        SIBLINGS under the same Section.

        MEASURED on 2312.11532 pp 6-7, Gemma4 b696b9f: the `diagram` line has
        six `children_ids`, the subcaptions "(a) 20NG-NPMI." … "(f) NYT-TQ.",
        and in the model

            Diagram   obj_6f30000d6c74  children=[]  parent=<Section>
            Paragraph obj_44b67bfedb32  parent=<the same Section>

        `pagecheck.check_overlap` skips a pair where one unit's key is in the
        other's `ancestors`, and `ancestors` walks a chain built from `parent`
        and then OVERRIDDEN by `children` (drillgroup pagecheck.py 244-248,
        281-287, 317). Siblings share no such chain, so every subcaption was
        counted as overlapping its own diagram.

        THE SHAPE IS THE ONE THE MODEL ALREADY USES. `Table` owns its
        `TableCell`s exactly this way — 5 Tables and 90 cells on this document,
        the cells' `parent` being the Table and not a Section — so a content
        object owning content children is established here, not invented. The
        subcaptions stay Paragraph objects rather than becoming the diagram's
        own lines: a printed subcaption is text a reader cites, and the owner's
        second requirement is that every drilled paragraph stay addressable.

        `parent_section` is untouched: that prop, not `parent`, is what carries
        a content object's section, so the section relation is not lost.
        """
        index = self.build_line_index(doc)
        if not index or self.LINES_STREAM not in doc.streams:
            return
        stream = doc.stream(self.LINES_STREAM)
        order = list(stream.anchors)
        pos = {a: i for i, a in enumerate(order)}
        # line id -> the object that realizes it, NARROWEST SPAN WINNING.
        #
        # A `Page` realization spans its whole page and `Document` the whole
        # document, so "the first object that claims this line" is a container
        # for every line — `owner[the diagram line]` came out as the Page, and
        # with it `child is parent` for all six subcaptions and nothing linked
        # at all. `unclaimed.py` records the same trap and skips a type list;
        # the span is the sharper test, because it also prefers a TableCell to
        # its Table without naming either.
        owner: dict[str, DocObject] = {}
        width: dict[str, int] = {}
        for obj in doc.objects.values():
            for rz in obj.realizations:
                if rz.stream != self.LINES_STREAM:
                    continue
                i, j = pos.get(rz.start), pos.get(rz.end)
                if i is None or j is None:
                    continue
                if j < i:
                    i, j = j, i
                span = j - i
                for a in order[i:j + 1]:
                    lid = stream.payload[a].get("id")
                    if not lid:
                        continue
                    if lid not in owner or span < width[lid]:
                        owner[lid], width[lid] = obj, span
        for lid, payload in index.items():
            kids = payload.get("children_ids")
            if not kids or not isinstance(kids, (list, tuple)):
                continue
            parent = owner.get(lid)
            if parent is None:
                continue
            for kid_id in kids:
                child = owner.get(kid_id)
                # A child line realized by the PARENT'S OWN object is not a
                # relation — a container whose realization spans its children
                # (a table's cells inside its own range) would otherwise be
                # made its own parent and `_ancestors` would loop.
                if child is None or child is parent:
                    continue
                # OWNERSHIP IS EXCLUSIVE, and this is the part that decides
                # whether the relation is visible at all.
                #
                # `pagecheck` builds its chain as `parents[id] = o["parent"]`
                # and then OVERWRITES it from every object's `children`, in
                # document order — so when a Section and a Diagram both list
                # the same Paragraph, the LAST one in the objects list wins.
                # The Section won, and `ancestors` for each subcaption came out
                # [Document, Section] with the Diagram nowhere in it: the
                # overlap was still counted although the Diagram held all six
                # children and each child's `parent` was the Diagram.
                #
                # Measured on 2312.11532 p6 (Gemma4 b696b9f, yolo): 5 overlaps
                # before and 5 after, until the Paragraph was taken out of the
                # Section's `children`. A content object has ONE owner; the
                # section is still reachable through the Diagram and through
                # `parent_section`, which this does not touch.
                old_parent = doc.objects.get(child.parent) if child.parent else None
                if old_parent is not None and old_parent is not parent:
                    old_parent.children = [c for c in old_parent.children
                                           if c != child.id]
                if child.id not in parent.children:
                    parent.children.append(child.id)
                child.parent = parent.id


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
            #: AND THE BACK-LINK. `a in b.children` must imply
            #: `a.parent == b.id`, or a walker that descends and one that
            #: ascends read two different documents. Measured before writing
            #: it: 272 of 1805.01788's 313 links and 242 of 0864's 353 had no
            #: parent, with ZERO conflicts and no id listed twice. A FILL, not
            #: an overwrite -- where another writer has already claimed the
            #: object, its claim stands.
            if obj.parent is None:
                obj.parent = owner.id

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
            if o.parent is None:          #: the back-link, as above
                o.parent = root.id

        # Sibling next/prev for top-level Sections, mirroring TS behavior.
        for i, s in enumerate(top_sections):
            if i > 0:
                s.props["prev_sibling"] = top_sections[i - 1].id
            if i < len(top_sections) - 1:
                s.props["next_sibling"] = top_sections[i + 1].id

        doc.add(root)
        doc.meta["root_id"] = root.id
