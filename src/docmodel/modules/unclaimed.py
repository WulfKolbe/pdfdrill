r"""UnclaimedLineProcessor (procOrder 998) — everything in the reading reaches
the model.

OWNER, 2026-11-10: "the lines.json is the interface and the rest must be normal
pdfdrill function not any special cases … Any kind of correction is unwanted."

WHAT WAS WRONG
--------------
`lines.json` is the documented interface, and the model built from it kept only
the 16 line types `docmodel.line_types` names. Every other record was DROPPED —
not reported, not counted, simply absent from the model, and therefore from
`inspect`, `md`, `tiddlers` and every other projection.

MEASURED with a reading in GLYPHDRILL3's shape, 8 records in: the model came out
with 4 objects and the inspector drew 2 boxes. `column`, `gd3_block`,
`gd3_white` and `gd3_word` were gone. A reader cannot adjust a layout stage — a
blob search written in C, in that case — whose output is invisible.

It is the same class of defect as the figure glyphs (D1, 2109f4a7): content
present in the input, absent from the result, and nothing saying so. The claim
ledger (634) could already COUNT lines claimed by no module; nothing kept them.

THE RULE
--------
A module that recognises a record claims it exactly as before — this runs after
all of them and takes only what is left. A record nobody claimed becomes one
object carrying ITS OWN TYPE and ITS OWN REGION.

NO CORRECTION. The region is passed through byte-for-byte: not re-scaled, not
clipped to the page box, not rounded, not reordered, not renamed. The owner's
instruction was explicit, and the reason is sound — a rectangle in the wrong
place is the producing stage's defect to see and fix, so a viewer that silently
improved its input would be worse than useless for the job it is for.

`type` is kept in `lines_type` rather than becoming the object's own `type`,
because `DocObject.type` is a closed vocabulary that five readers enforce
(line_types, the TiddlyWiki and LaTeX projectors, the host-line pick, the
report). Putting `gd3_block` there would make every one of those refuse it.
`ReadingRecord` is the object type; the reading's own word for it rides along
untouched, which is what a person adjusting that stage needs to see.

WHY procOrder 998
-----------------
After every recognising module (max 14) and before DocumentFlowProcessor (999),
which assigns `flow_index` — so these objects take their place in the reading
order like any other instead of being appended outside it.
"""
from __future__ import annotations

from typing import Any

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization

#: Objects that SPAN lines without accounting for them. A Page realizes every
#: line on its page; a Document spans all of them. Treating either as a claim
#: marks the whole reading claimed.
_CONTAINERS = frozenset({"Page", "Document"})


class UnclaimedLineProcessor(BaseModule):
    """One object per reading record that no other module claimed."""

    def _claimed_anchors(self, doc: Document) -> set:
        """Every mathpix_lines anchor some object already realizes.

        Taken from the REALIZATIONS rather than from the claim ledger: the
        ledger is a measurement that can be switched off (`start_recording`
        fails soft and the CLI says so), and a module whose correctness depended
        on a measurement being enabled would silently duplicate every line on a
        run where it was not.
        """
        claimed: set = set()
        order = doc.stream(self.LINES_STREAM).anchors
        index = {a: i for i, a in enumerate(order)}
        for obj in doc.objects.values():
            # A CONTAINER IS NOT A CLAIMANT. `Page` realizes every line on its
            # page (0..7 of 8, on the measured reading) and `Document` spans the
            # whole document, so counting their spans marked EVERY record
            # claimed and this module kept nothing — which is how the first
            # version of it silently did nothing at all. They describe where
            # content sits; they do not account for it.
            if obj.type in _CONTAINERS:
                continue
            for rz in obj.realizations:
                if rz.stream != self.LINES_STREAM:
                    continue
                i, j = index.get(rz.start), index.get(rz.end)
                if i is None or j is None:
                    continue
                if j < i:
                    i, j = j, i
                claimed.update(order[i:j + 1])
        return claimed

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        claimed = self._claimed_anchors(doc)
        items: list[dict[str, Any]] = []
        for anchor in stream.anchors:
            if anchor in claimed:
                continue
            payload = stream.payload[anchor]
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                # VERBATIM. The reading's own type and its own rectangle.
                "lines_type": payload.get("type"),
                "region": payload.get("region"),
                "text": payload.get("text_display") or payload.get("text") or "",
                "image_id": payload.get("_image_id"),
                "cnt": payload.get("cnt"),
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document):
        props = {
            "page": item["page"],
            "lines_type": item["lines_type"],
            "region": item["region"],
            "text": item["text"],
        }
        if item.get("image_id") is not None:
            props["image_id"] = item["image_id"]
        if item.get("cnt") is not None:
            props["cnt"] = item["cnt"]
        obj = DocObject(type="ReadingRecord", props=props)
        obj.add_realization(Realization(
            stream=self.LINES_STREAM, start=item["anchor"], end=item["anchor"],
            role="surface"))
        self.bump(f"records_kept_{item['lines_type'] or 'untyped'}")
        return obj
