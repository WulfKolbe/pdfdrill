"""
PromoteCleanedText mutator.

Some documents arrive already containing 'cleaned' realizations from prior
processors (the converter's DehyphenationProcessor produces these in the
`dehyphenated_para_NNNN` streams). This mutator promotes that cleaned content
to be the canonical `Paragraph.props.text` value.

Use when you trust the existing cleaned streams more than the raw OCR text.
Use `Dehyphenate` (in the same package) when you want to re-run dehyphenation
with the improved heuristic.
"""
from __future__ import annotations

from docmodel.core import Document
from ..base import BaseMutator


class PromoteCleanedText(BaseMutator):

    def apply(self, doc: Document) -> None:
        for para in doc.objects_of_type("Paragraph"):
            cleaned = next(
                (r for r in para.realizations if r.role == "cleaned"
                 and r.stream in doc.streams and r.start is not None),
                None,
            )
            if cleaned is None:
                continue
            stream = doc.stream(cleaned.stream)
            anchors = stream.slice_anchors(cleaned.start, cleaned.end)
            text = "".join(
                stream.payload[a].get("codepoint", "") for a in anchors
            )
            if text == para.props.get("text"):
                continue
            if "text_raw" not in para.props:
                para.props["text_raw"] = para.props.get("text", "")
            para.props["text"] = text
            self.bump("paragraphs_updated")

        if self.debug:
            self.log(f"counters: {self.counters}")
