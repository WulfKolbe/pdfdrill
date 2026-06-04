"""
Phase C — block-role classifier.

Classify a layout block into a role so the graph builder can attribute evidence:
the SENDER lives in the letterhead (header), the RECIPIENT is a body address
block, and company registration data (HRB/USt-ID/Vorstand) is in the footer.

Content cues win over position (a franking stamp sits high but is not a header; a
registration line mid-page is still footer-class). Position is the fallback.
Pure functions over (text, bbox, page_height) — unit-testable without a PDF.
HANDWRITTEN is not inferable from text alone (it needs OCR-confidence signal),
so it is never returned here; the OCR layer can override later.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional


class BlockRole(str, Enum):
    HEADER = "header"
    FOOTER = "footer"
    BODY = "body"
    TABLE = "table"
    SIGNATURE = "signature"
    STAMP = "stamp"
    HANDWRITTEN = "handwritten"
    OTHER = "other"


_STAMP = re.compile(r"Deutsche\s+Post|Entgelt\s+bezahlt|\bDPAG\b|Frankier|"
                    r"\bP\s+DV\b|\bPorto\b|Postvertriebsstück", re.I)
_SIGNATURE = re.compile(r"Mit\s+freundlichen\s+Grüßen|Hochachtungsvoll|"
                        r"\bi\.\s?A\.|\bi\.\s?V\.|\bppa\.", re.I)
_FOOTER = re.compile(r"\bHRB\b|\bHRA\b|Amtsgericht|Handelsregister|USt\.?-?\s?ID|"
                     r"Umsatzsteuer-?ID|Vorstand|Aufsichtsrat|Geschäftsführer|"
                     r"\bSitz\b|Postanschrift|Hausanschrift|Vers\.-St|\bVNR\b", re.I)
_OTHER = re.compile(r"\bbitte\s+wenden\b|\bFortsetzung\b|^\s*Seite\s+\d", re.I)
_RECIPIENT = re.compile(r"^\s*(Herrn|Herr|Frau|Firma|An\s+die|An\s+den)\b", re.I)
# table: ≥2 lines that each hold ≥2 numeric columns separated by 2+ spaces
_NUMCOL = re.compile(r"\d[\d.,]*\s{2,}\d[\d.,]*")


def _looks_like_table(text: str) -> bool:
    rows = [ln for ln in text.splitlines() if _NUMCOL.search(ln)]
    return len(rows) >= 2


def classify_block(text: str, bbox, page_height: float = 1000.0) -> BlockRole:
    t = text or ""
    if _STAMP.search(t):
        return BlockRole.STAMP
    if _SIGNATURE.search(t):
        return BlockRole.SIGNATURE
    if _FOOTER.search(t):
        return BlockRole.FOOTER
    if _OTHER.search(t):
        return BlockRole.OTHER
    if _RECIPIENT.search(t):
        return BlockRole.BODY                 # recipient address block
    if _looks_like_table(t):
        return BlockRole.TABLE
    # position fallback (bbox = [x1, y1, x2, y2], top-left origin). Header is
    # judged by the block's TOP (a letterhead starts at the top, even if it runs
    # a little down); footer by its bottom.
    top = (bbox[1] / page_height) if page_height else 0.0
    bottom = (bbox[3] / page_height) if page_height else 0.0
    if top < 0.22:
        return BlockRole.HEADER
    if bottom > 0.82:
        return BlockRole.FOOTER
    return BlockRole.BODY


def classify_blocks(blocks: list[dict[str, Any]],
                    page_height: float = 1000.0) -> list[dict[str, Any]]:
    """Tag each block dict ({text, bbox, …}) with a `role` (the enum value)."""
    for b in blocks:
        b["role"] = classify_block(b.get("text", ""), b.get("bbox", [0, 0, 0, 0]),
                                   page_height).value
    return blocks


_PLZ_CITY = re.compile(r"\b\d{5}\s+[A-ZÄÖÜ]")


def detect_recipient(text: str) -> Optional[dict[str, str]]:
    """Text-level recipient extraction (Phase-C attribution without bbox): find a
    `Herrn/Frau/Firma …` block and split it into {name, address}. The name is the
    line after a bare marker (or the marker line minus the marker); the address is
    the following street + PLZ-city lines, name excluded. Returns None if no
    recipient marker is present."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for i, ln in enumerate(lines):
        if not _RECIPIENT.match(ln):
            continue
        block: list[str] = []
        for s in lines[i:]:
            if not s and block:
                break
            if s:
                block.append(s)
            if _PLZ_CITY.search(s) and len(block) > 1:
                break
            if len(block) >= 5:
                break
        if not block:
            continue
        marker = block[0]
        rest = block[1:]
        if re.fullmatch(r"(Herrn|Herr|Frau|Firma|An\s+den|An\s+die)", marker, re.I) and rest:
            name, addr_lines = rest[0], rest[1:]
        else:
            name = re.sub(r"^(Herrn|Herr|Frau|Firma)\s+", "", marker, flags=re.I)
            addr_lines = rest
        # Reject a non-name (e.g. the block was just a PLZ-city line) so we don't
        # fabricate a recipient Person named after a postal code.
        if re.match(r"^\s*\d{4,}", name) or not re.search(r"[A-Za-zÄÖÜäöüß]{2,}", name):
            return None
        return {"name": name, "address": ", ".join(addr_lines)}
    return None


def is_sender_region(role: str) -> bool:
    return role in (BlockRole.HEADER.value, BlockRole.FOOTER.value)


def is_recipient_region(role: str) -> bool:
    return role == BlockRole.BODY.value
