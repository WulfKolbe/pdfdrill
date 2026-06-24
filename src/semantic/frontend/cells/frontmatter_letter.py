"""CELL (frontmatter × text): detect the frontmatter of a commercial LETTER from
a plain-text / OCR surface — the letterhead (sender), the recipient block, the
date. Sender → agent role=sender (≡ author); recipient → recipients[].

BOOTSTRAP PARSER for the (frontmatter, text) slot. A LEAN grammar will generate
this and its test corpus; this hand parser fixes the cell contract meanwhile.
The geometry-aware sender/recipient attribution in semantic/attribution.py is
the richer producer this will defer to once wired; here we read clean blocks.
"""
from __future__ import annotations

import re

from ..contract import CellModule, DetectedObject, Surface, register_cell

# salutation markers that end the address region and begin the body
_SALUTATION = re.compile(r"^(sehr geehrte|sehr geehrter|liebe|lieber|hallo|dear)\b", re.I)
# a recipient block often opens with an addressing word
_ADDRESSEE = re.compile(r"^(herrn|frau|herr|firma|an)\b", re.I)
_DATE = re.compile(r"\b(\d{1,2}\.\s*\w+\s*\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")
_PLZ_LINE = re.compile(r"^\d{4,5}\s+\w")


def _block_text(block: list[str]) -> str:
    return " / ".join(b.strip() for b in block if b.strip())


def _looks_address(block: list[str]) -> bool:
    return any(_PLZ_LINE.match(b.strip()) for b in block)


class FrontMatterLetter(CellModule):
    kind = "frontmatter"
    format = "text"

    def detect(self, surface: Surface) -> list[DetectedObject]:
        blocks: list[list[str]] = surface.meta.get("blocks", [])
        if not blocks:
            return []

        # SENDER = the letterhead = the first block (name line + maybe address).
        sender_block = blocks[0]
        sender_name = sender_block[0].strip() if sender_block else ""

        # RECIPIENT = an addressee block (opens with Herrn/Frau/Firma/An, or the
        # first address-shaped block after the letterhead, before the salutation).
        recipient_name = ""
        date = None
        for blk in blocks[1:]:
            if any(_SALUTATION.match(b.strip()) for b in blk):
                break
            if not recipient_name and (any(_ADDRESSEE.match(b.strip()) for b in blk)
                                       or _looks_address(blk)):
                # name = first non-addressing line in the block
                for b in blk:
                    s = b.strip()
                    if s and not _ADDRESSEE.match(s) and not _PLZ_LINE.match(s):
                        recipient_name = s
                        break
            if date is None:
                for b in blk:
                    m = _DATE.search(b)
                    if m:
                        date = m.group(1).strip()
                        break

        if not sender_name:
            return []
        fields = {
            "genre": "letter",
            "title": None,
            "agents": [{"role": "sender", "name": sender_name,
                        "address": _block_text(sender_block[1:]) or None}],
            "date": date,
            "recipients": ([{"name": recipient_name}] if recipient_name else []),
            "identifiers": [],
            "subject": None,
        }
        return [DetectedObject(kind=self.kind, format=self.format, fields=fields,
                               confidence=0.6)]


register_cell(FrontMatterLetter())
