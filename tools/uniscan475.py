#!/usr/bin/env python3
r"""475/478 — characters in a maths value that are not mathematics.

A maths string may legitimately hold ASCII, Greek, the mathematical operator
and arrow blocks, letterlike and blackboard forms, and the alphanumeric
symbols plane. Anything else is a glyph the OCR could not name and reached
for something that looked like it.

FOUR CLASSES ARE CALLED OUT BY NAME because they are never mathematics:
CJK, Cyrillic, Hangul, private use.

AND ONE IS TREATED SEPARATELY (478). U+2FF0-2FFB, IDEOGRAPHIC DESCRIPTION
CHARACTERS, are not a glyph at all — they are MathPix's own decomposition
operators, describing a character as an arrangement of parts (⿱ = "above to
below"). Every occurrence is an internal sequence that escaped unwrapped, so
there is nothing to guess at: the sequence DESCRIBES the character it failed
to name, and the description is the recovery.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

IDC = (0x2FF0, 0x2FFB)          # ideographic description characters (478)

#: blocks a maths value may legitimately hold, as (lo, hi, name)
MATH_OK = [
    (0x0000, 0x007F, "ASCII"),
    (0x00A0, 0x00FF, "Latin-1 Supplement"),          # × ÷ ° ± µ ¬
    (0x0100, 0x017F, "Latin Extended-A"),
    (0x0370, 0x03FF, "Greek and Coptic"),
    (0x1F00, 0x1FFF, "Greek Extended"),
    (0x2000, 0x206F, "General Punctuation"),
    (0x2070, 0x209F, "Super/Subscripts"),
    (0x20D0, 0x20FF, "Combining Marks for Symbols"),
    (0x2100, 0x214F, "Letterlike Symbols"),
    (0x2150, 0x218F, "Number Forms"),
    (0x2190, 0x21FF, "Arrows"),
    (0x2200, 0x22FF, "Mathematical Operators"),
    (0x2300, 0x23FF, "Miscellaneous Technical"),
    (0x25A0, 0x25FF, "Geometric Shapes"),
    (0x27C0, 0x27EF, "Misc Math Symbols-A"),
    (0x27F0, 0x27FF, "Supplemental Arrows-A"),
    (0x2900, 0x297F, "Supplemental Arrows-B"),
    (0x2980, 0x29FF, "Misc Math Symbols-B"),
    (0x2A00, 0x2AFF, "Supplemental Math Operators"),
    (0x1D400, 0x1D7FF, "Mathematical Alphanumeric Symbols"),
]

NEVER_MATHS = [
    (0x0400, 0x04FF, "Cyrillic"),
    (0x0500, 0x052F, "Cyrillic Supplement"),
    (0x1100, 0x11FF, "Hangul Jamo"),
    (0xAC00, 0xD7AF, "Hangul Syllables"),
    (0x3130, 0x318F, "Hangul Compatibility Jamo"),
    (0xE000, 0xF8FF, "Private Use Area"),
    (0xF0000, 0xFFFFD, "Supplementary Private Use A"),
    (0x2E80, 0x2EFF, "CJK Radicals Supplement"),
    (0x2F00, 0x2FDF, "Kangxi Radicals"),
    (0x3000, 0x303F, "CJK Symbols and Punctuation"),
    (0x3040, 0x309F, "Hiragana"),
    (0x30A0, 0x30FF, "Katakana"),
    (0x3400, 0x4DBF, "CJK Ext A"),
    (0x4E00, 0x9FFF, "CJK Unified Ideographs"),
    (0xF900, 0xFAFF, "CJK Compatibility Ideographs"),
    (0xFF00, 0xFFEF, "Halfwidth and Fullwidth Forms"),
    (0x20000, 0x2A6DF, "CJK Ext B"),
    (0x2A700, 0x2EBEF, "CJK Ext C-F"),
]

CJKISH = {"CJK Radicals Supplement", "Kangxi Radicals",
          "CJK Symbols and Punctuation", "Hiragana", "Katakana", "CJK Ext A",
          "CJK Unified Ideographs", "CJK Compatibility Ideographs",
          "Halfwidth and Fullwidth Forms", "CJK Ext B", "CJK Ext C-F"}


def block_of(o: int) -> str:
    if IDC[0] <= o <= IDC[1]:
        return "Ideographic Description (U+2FF0-2FFB)"
    for lo, hi, name in NEVER_MATHS:
        if lo <= o <= hi:
            return name
    for lo, hi, name in MATH_OK:
        if lo <= o <= hi:
            return ""                       # legitimate
    return "other (U+%04X block)" % (o & ~0xFF)


def offenders(latex: str) -> list:
    out = []
    for i, c in enumerate(latex or ""):
        b = block_of(ord(c))
        if b:
            out.append({"pos": i, "char": c, "cp": "U+%04X" % ord(c),
                        "name": unicodedata.name(c, "?"), "block": b})
    return out


def scan(tiddlers_path: Path) -> tuple:
    """(offending rows, does this document contain ANY CJK at all)."""
    try:
        t = json.loads(Path(tiddlers_path).read_text(encoding="utf-8",
                                                     errors="replace"))
    except (OSError, ValueError):
        return [], False
    t = t.get("tiddlers", t) if isinstance(t, dict) else t
    rows, any_cjk = [], False
    for x in t:
        title = x.get("title", "")
        lx = x.get("latex") or ""
        # "any CJK at all" is asked of the WHOLE document, prose included
        for v in (lx, x.get("text") or "", x.get("mathpix_text") or ""):
            if any(block_of(ord(c)) in CJKISH for c in v):
                any_cjk = True
                break
        if not re.search(r"_(EQ|FOX?|TAB)\d", title) or not lx:
            continue
        offs = offenders(lx)
        if offs:
            rows.append({"id": title, "page": x.get("page"),
                         "conf": x.get("confidence"),
                         "uri": x.get("canonical_uri") or "",
                         "latex": lx, "offenders": offs})
    return rows, any_cjk


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    docs, n = {}, 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        tp = list(d.glob("*.tiddlers.json"))
        if not tp:
            continue
        n += 1
        rows, any_cjk = scan(tp[0])
        if rows or any_cjk:
            docs[d.name] = {"rows": rows, "any_cjk": any_cjk}
        print("\r%d scanned, %d documents with something" % (n, len(docs)),
              end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"documents_scanned": n, "documents": docs}, sys.stdout,
              indent=1, ensure_ascii=False)
