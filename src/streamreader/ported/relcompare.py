# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/relcompare.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""relcompare - two LaTeX readings compared by TeX's structure.

CONTRACT
    canon(text) -> canonical character or None: pdfminer's '(cid:N)' is a
      cmex10 code (no ToUnicode in CMEX); every size variant maps to its base
      symbol (big/Big/bigg/Bigg/\\left parentheses -> '(' ...), a tall
      delimiter counts once by its top piece, other extension pieces -> None;
      other texts lose Unicode variation selectors.
    structure(latex, workdir) -> dict(compiles, chars: Counter of canon()
      over ALL glyphs (delimiters carry no TeX id), rels: Counter of (rel,
      rel_label(base), rel_label(script)) from texroles truth). compiles False when
      texroles.build raises or produces no ids at all.
    compare(a, b, workdir) -> dict(a_compiles, b_compiles, equal,
      chars_only_a, chars_only_b, rels_only_a, rels_only_b) - the only_* are
      sorted lists (multiset differences); equal = both compile and all four
      differences are empty. Neither reading is truth.
"""
import os
from collections import Counter
from . import texroles

# cmex10 standard encoding, code -> canonical character (None: extension piece)
_CMEX = {}
for base, ch in ((0x00, "()[]⌊⌋⌈⌉{}⟨⟩|‖/\\"), (0x10, "()()[]⌊⌋⌈⌉{}⟨⟩/\\"), (0x20, "()[]⌊⌋⌈⌉{}⟨⟩/\\/\\")):
    for k, c in enumerate(ch):
        _CMEX[base + k] = c
_CMEX.update({0x30: "(", 0x31: ")", 0x32: "[", 0x33: "]", 0x38: "{", 0x39: "}",
              0x44: "⟨", 0x45: "⟩", 0x46: "⊔", 0x47: "⊔", 0x48: "∮", 0x49: "∮", 0x4A: "⊙", 0x4B: "⊙",
              0x4C: "⊕", 0x4D: "⊕", 0x4E: "⊗", 0x4F: "⊗", 0x50: "∑", 0x51: "∏", 0x52: "∫", 0x53: "∪",
              0x54: "∩", 0x55: "⊎", 0x56: "⋀", 0x57: "⋁", 0x58: "∑", 0x59: "∏", 0x5A: "∫", 0x5B: "∪",
              0x5C: "∩", 0x5D: "⊎", 0x5E: "⋀", 0x5F: "⋁", 0x60: "∐", 0x61: "∐", 0x62: "^", 0x63: "^",
              0x64: "^", 0x65: "~", 0x66: "~", 0x67: "~", 0x68: "[", 0x69: "]", 0x6A: "⌊", 0x6B: "⌋",
              0x6C: "⌈", 0x6D: "⌉", 0x6E: "{", 0x6F: "}", 0x70: "√", 0x71: "√", 0x72: "√", 0x73: "√",
              0x76: "√"})
for k in list(range(0x34, 0x38)) + list(range(0x3A, 0x44)) + [0x74, 0x75] + list(range(0x77, 0x80)):
    _CMEX.setdefault(k, None)


def rel_label(text):
    """canon(text), but never None: a glyph with a TeX id is a maths character
    and keeps its own text if canon() calls it an extension piece."""
    c = canon(text)
    return text if c is None else c


def canon(text):
    if text.startswith("(cid:") and text.endswith(")"):
        try:
            return _CMEX.get(int(text[5:-1]), text)
        except ValueError:
            return text
    return "".join(c for c in text if not 0xFE00 <= ord(c) <= 0xFE0F)


def structure(latex, workdir):
    try:
        r = texroles.build(latex, workdir)
    except Exception:
        return dict(compiles=False, chars=Counter(), rels=Counter())
    text = {g["id"]: rel_label(g["text"]) for g in r["glyphs"] if g["id"]}
    if not text:
        return dict(compiles=False, chars=Counter(), rels=Counter())
    rels = Counter((t["rel"], text.get(t["base"], "?"), text.get(t["script"], "?")) for t in r["truth"])
    chars = Counter(c for c in (canon(g["text"]) for g in r["glyphs"]) if c is not None)
    return dict(compiles=True, chars=chars, rels=rels)


def compare(a, b, workdir):
    A = structure(a, os.path.join(workdir, "a"))
    B = structure(b, os.path.join(workdir, "b"))
    d = dict(a_compiles=A["compiles"], b_compiles=B["compiles"],
             chars_only_a=sorted((A["chars"] - B["chars"]).elements()),
             chars_only_b=sorted((B["chars"] - A["chars"]).elements()),
             rels_only_a=sorted((A["rels"] - B["rels"]).elements()),
             rels_only_b=sorted((B["rels"] - A["rels"]).elements()))
    d["equal"] = A["compiles"] and B["compiles"] and not any(
        d[k] for k in ("chars_only_a", "chars_only_b", "rels_only_a", "rels_only_b"))
    return d
