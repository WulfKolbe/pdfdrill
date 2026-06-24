"""FORMAT module: plain text (the OCR / pdftotext surface). Normalises raw text
into blank-line-separated blocks the frontmatter cell uses to find letterhead /
recipient / date. One module per format."""
from __future__ import annotations

import re

from ..contract import FormatModule, Surface, register_format


class TextFormat(FormatModule):
    format = "text"

    def surface(self, raw: str) -> Surface:
        lines = raw.splitlines()
        # group into blocks separated by blank lines (a letterhead, an address
        # block, a date line, the salutation+body are visually separated so)
        blocks: list[list[str]] = []
        cur: list[str] = []
        for ln in lines:
            if ln.strip():
                cur.append(ln.rstrip())
            elif cur:
                blocks.append(cur)
                cur = []
        if cur:
            blocks.append(cur)
        return Surface(format=self.format, raw=raw, lines=lines,
                       meta={"blocks": blocks})


register_format(TextFormat())
