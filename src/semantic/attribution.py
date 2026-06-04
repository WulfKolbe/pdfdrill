"""
Region-based sender/recipient attribution.

Classify each line by its REGION (geometry + content cues) and split a page into
the sender side (header/footer/stamp — letterhead + registration) and the body
(which holds the recipient block). The recipient's address then comes from the
recipient region, so it attaches to the recipient Person — not the sender.

Pure + decoupled: uses only semantic.blocks (classify_block, detect_recipient).
The caller runs sender_of / address extraction on the returned region texts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .blocks import BlockRole, classify_block, detect_recipient

# region helpers (shape {top_left_x, top_left_y, width, height})


def _x0(r): return float(r.get("top_left_x", 0) or 0)
def _y0(r): return float(r.get("top_left_y", 0) or 0)
def _x1(r): return _x0(r) + float(r.get("width", 0) or 0)
def _y1(r): return _y0(r) + float(r.get("height", 0) or 0)


@dataclass
class Attribution:
    sender_text: str                       # header/footer/stamp region text
    body_text: str                         # body region text
    recipient: Optional[dict[str, str]]    # {name, address} from the body, or None


_SENDER_ROLES = {BlockRole.HEADER, BlockRole.FOOTER, BlockRole.STAMP}


def attribute(lines: list[dict[str, Any]]) -> Attribution:
    """Split a page's lines (each {text, region}) into sender vs body by region,
    and pull the recipient out of the body. `page_height` is taken as the lowest
    line bottom so classify_block's position fallback is calibrated to content."""
    regions = [l["region"] for l in lines if l.get("region")]
    page_height = max((_y1(r) for r in regions), default=1000.0) or 1000.0

    sender_parts: list[str] = []
    body_parts: list[str] = []
    for l in lines:
        r = l.get("region")
        t = l.get("text", "")
        if not r or not t.strip():
            continue
        role = classify_block(t, [_x0(r), _y0(r), _x1(r), _y1(r)], page_height)
        if role in _SENDER_ROLES:
            sender_parts.append(t)
        elif role == BlockRole.BODY:
            body_parts.append(t)
    body_text = "\n".join(body_parts)
    return Attribution(sender_text="\n".join(sender_parts), body_text=body_text,
                       recipient=detect_recipient(body_text))
