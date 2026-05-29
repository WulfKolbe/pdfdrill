"""
DehyphenationProcessor (procOrder 14).

Demonstrates the cross-stream pattern for cleaning OCR artifacts without
destroying the original. For every Paragraph DocObject this builds a derived
`dehyphenated_para_NNNN` stream of character anchors and stores explicit
`Alignment` edges of kind 'dehyphenate' from the source line anchors (in
`mathpix_lines`) to the corresponding runs of derived characters.

Heuristic applied: when a line ends with a hyphen and the next contributing
line starts with a lowercase letter or digit, the hyphen is treated as a
soft break and dropped. This is intentionally a *naive demo*: it will
false-positive on real hyphenated compounds like "one-to-one" (it produces
"oneto-one"). The point isn't that the heuristic is good — it's that the
architecture makes a bad heuristic safe: the source mathpix_lines stream is
not touched, so the cleaned stream can later be replaced by a better pass
(dictionary lookup, language model, compound detection) without losing data.
That replacement is one swap of derived stream + alignment edges; no other
layer is affected.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization, Range, Alignment
from ..text_utils import HYPHEN_TAIL


# A line is hyphenation-broken if its visible text ends with `word-` (shared
# HYPHEN_TAIL) AND the next line's visible text begins with a lowercase letter
# or a digit. The continuation test below is intentionally naive (see the
# module docstring): a real compound like "one-to-one" is mis-joined on
# purpose, to demonstrate that the cross-stream design keeps that safe.
_NEXT_CONTINUATION = re.compile(r"^[a-zäöüß0-9]")


class DehyphenationProcessor(BaseModule):

    DERIVED_STREAM_PREFIX = "dehyphenated_para_"

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        paras = doc.objects_of_type("Paragraph")
        return [{"para": p} for p in paras]

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        # We don't create a new DocObject — we attach a cleaned realization
        # to the existing Paragraph and produce alignments.
        para: DocObject = item["para"]
        surface = next(
            (r for r in para.realizations if r.stream == self.LINES_STREAM
             and r.role == "surface"),
            None,
        )
        if surface is None or surface.start is None or surface.end is None:
            return None

        stream = doc.stream(self.LINES_STREAM)
        anchors = stream.slice_anchors(surface.start, surface.end)
        if not anchors:
            return None

        n = self.bump("paragraphs_dehyphenated")
        derived_name = f"{self.DERIVED_STREAM_PREFIX}{n:04d}"
        derived = doc.ensure_stream(derived_name)

        first_derived_anchor = None
        last_derived_anchor = None
        join_count = 0

        for i, source_anchor in enumerate(anchors):
            payload = stream.payload[source_anchor]
            text = payload.get("text_display") or payload.get("text") or ""
            if not text:
                continue

            # Detect soft hyphen: this line ends with '-' and the next prose
            # anchor in the paragraph continues lowercase.
            is_soft_break = False
            if HYPHEN_TAIL.search(text) and i + 1 < len(anchors):
                next_text = (
                    stream.payload[anchors[i + 1]].get("text_display")
                    or stream.payload[anchors[i + 1]].get("text")
                    or ""
                )
                if _NEXT_CONTINUATION.match(next_text):
                    is_soft_break = True
                    join_count += 1

            # If this is a soft break, drop the trailing hyphen.
            written = text.rstrip()
            if is_soft_break:
                written = written[:-1]      # drop the '-'
                joiner = ""                  # no whitespace inserted
            else:
                joiner = " " if i < len(anchors) - 1 else ""

            # Emit character anchors for the written text + joiner.
            line_start_anchor = None
            line_end_anchor = None
            for ch in written + joiner:
                a = derived.append(codepoint=ch)
                if first_derived_anchor is None:
                    first_derived_anchor = a
                if line_start_anchor is None:
                    line_start_anchor = a
                line_end_anchor = a
                last_derived_anchor = a

            # Alignment edge: this source line maps to this run of derived
            # chars. Kind 'dehyphenate' carries provenance info as props.
            if line_start_anchor is not None:
                doc.add_alignment(Alignment(
                    kind="dehyphenate",
                    left=Range(self.LINES_STREAM, source_anchor, source_anchor),
                    right=Range(derived_name, line_start_anchor, line_end_anchor),
                    props={
                        "soft_break_removed": is_soft_break,
                    },
                ))

        if first_derived_anchor is not None:
            para.add_realization(Realization(
                stream=derived_name,
                start=first_derived_anchor,
                end=last_derived_anchor,
                role="cleaned",
                props={"joins_applied": join_count},
            ))
        return None  # we mutated existing object; nothing to add
