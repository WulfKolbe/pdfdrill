"""
Dehyphenate mutator.

Walks every Paragraph DocObject, looks at the line anchors of its surface
realization, detects line-break soft hyphens, and rewrites `Paragraph.props.text`
with the cleaned version. The original (pre-cleaning) text is preserved in
`Paragraph.props.text_raw` if not already set.

Improved heuristic over the demo DehyphenationProcessor in the converter:

    join lines A and B (B follows A in the paragraph) iff:
      - A's tail matches `(\\w+)-\\s*$`                 ... A ends with hyphen
      - B's first whitespace-delimited token does NOT contain another hyphen
        (e.g. "to-one" → compound, keep hyphen)
      - B's first character is lowercase (Latin or German Umlaut)
      - A's tail word (before '-') is NOT in PRESERVE_PREFIXES
        (well-, self-, non-, ...)

When the conditions hold the hyphen and the line break are dropped, joining
the two parts directly. Otherwise the original spacing is preserved.

This mutator also records its work as Alignment edges of kind 'dehyphenate'
between the source line and the cleaned text — but since the cleaned text
lives only in `Paragraph.props.text` (not as a separate stream), the
alignments use props {"src_line_id": ..., "soft_break_removed": bool}
rather than right-side anchors.
"""
from __future__ import annotations

from docmodel.core import Document, Alignment, Range
from docmodel.text_utils import HYPHEN_TAIL, NEXT_WORD, is_soft_break
from ..base import BaseMutator


class Dehyphenate(BaseMutator):
    """Rewrite Paragraph.text by removing soft-hyphen line breaks."""

    LINES_STREAM = "mathpix_lines"

    def apply(self, doc: Document) -> None:
        if self.LINES_STREAM not in doc.streams:
            self.log("no mathpix_lines stream; skipping")
            return
        stream = doc.stream(self.LINES_STREAM)

        for para in list(doc.objects_of_type("Paragraph")):
            self._process_paragraph(para, stream, doc)

        if self.debug:
            self.log(f"counters: {self.counters}")

    def _process_paragraph(self, para, stream, doc: Document) -> None:
        surface = next(
            (r for r in para.realizations
             if r.stream == self.LINES_STREAM and r.role == "surface"
             and r.start is not None),
            None,
        )
        if surface is None:
            return
        anchors = stream.slice_anchors(surface.start, surface.end)
        if not anchors:
            return

        # Gather per-anchor display text (the text we'll concatenate).
        line_texts: list[tuple[str, dict]] = []
        for a in anchors:
            payload = stream.payload[a]
            txt = payload.get("text_display") or payload.get("text") or ""
            line_texts.append((txt, payload))

        original = " ".join(t for t, _ in line_texts if t)
        cleaned, joins, alignment_records = self._dehyphenate(line_texts)

        self.bump("paragraphs_examined")
        if cleaned == original:
            return  # no rewrite needed

        # Persist original text once (if not already saved by a prior run).
        if "text_raw" not in para.props:
            para.props["text_raw"] = original
        para.props["text"] = cleaned
        para.props["dehyphenate_joins"] = joins
        self.bump("paragraphs_modified")
        if joins:
            self.bump("joins_applied", joins)
        kept = sum(1 for _, soft in alignment_records if not soft)
        if kept:
            self.bump("hyphens_preserved_as_compound", kept)

        # Emit Alignment edges back to source for provenance.
        for src_anchor_idx, soft_break in alignment_records:
            src_anchor = anchors[src_anchor_idx]
            doc.alignments.append(Alignment(
                kind="dehyphenate",
                left=Range(self.LINES_STREAM, src_anchor, src_anchor),
                right=Range(self.LINES_STREAM, src_anchor, src_anchor),  # self-loop: we mutated a prop, not a separate stream
                props={
                    "soft_break_removed": soft_break,
                    "by": "docops.Dehyphenate",
                    "para_id": para.id,
                },
            ))

    # ----- the heuristic -----

    def _dehyphenate(
        self, line_texts: list[tuple[str, dict]],
    ) -> tuple[str, int, list[tuple[int, bool]]]:
        """
        Return (joined_text, joins_applied, [(source_idx, was_soft_break), ...]).

        Only source lines that participated in a *soft break decision* (either
        "joined" or "kept hyphen but examined") are recorded in alignments;
        clean lines without a trailing hyphen are not.
        """
        parts: list[str] = []
        joins = 0
        records: list[tuple[int, bool]] = []

        for i, (txt, _payload) in enumerate(line_texts):
            if not txt:
                continue
            if i == 0:
                parts.append(txt)
                continue

            prev = parts[-1] if parts else ""
            m = HYPHEN_TAIL.search(prev)
            if m is None:
                parts.append(" " + txt)
                continue

            # prev ends with a hyphen; decide
            tail_word = m.group(1)
            n = NEXT_WORD.match(txt.lstrip())
            next_token = n.group(1) if n else ""

            soft = is_soft_break(tail_word, next_token)
            records.append((i, soft))
            if soft:
                # Drop trailing hyphen on prev, no whitespace.
                parts[-1] = prev[: m.start()] + tail_word
                parts.append(txt.lstrip())
                joins += 1
            else:
                # Keep the hyphen — and DON'T insert a space, because the
                # hyphen itself is the joiner ("one-" + "to-one" => "one-to-one").
                parts.append(txt.lstrip())

        return "".join(parts), joins, records
