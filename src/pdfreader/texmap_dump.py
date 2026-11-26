r"""texmap's answers as DATA, for a reader that is not Python.

glyphdrill3 writes Unicode inside its maths (drillgroup errors-open G8: 1,909
lines in its 204 T-0158 readings) where contracts/reading.md §7 asks for the
LaTeX command. The rule already exists here, in `texmap` and
`docmodel_six._maths_char`; a second copy written in C would drift from it.
So the tables are written out once, as one JSON file with its checksum, and
the C side reads them (coordinator, 2026-11-26).

    src/pdfreader/data/texmap.json         the tables
    src/pdfreader/data/texmap.json.sha256  sha256 of that file, `sha256sum` format

Sections:

  maths_chars      Unicode character -> LaTeX, inside maths (§7). Every
                   character of the maths-bearing blocks whose answer is not
                   the character itself.
  glyph_names      family -> glyph name -> [latex, kind, package]: what
                   `texmap.project` answers for every name the tables know.
  cid_tables       code position -> glyph name, for fonts that state no names:
                   CM (`CM_ENCODING`), mathabx (`MATHABX`), the render-verified
                   `_TEX_SLOTS`, esint (`_ESINT_CID`, LaTeX directly), and the
                   MathTime Pro 2 font -> CM encoding map.
  family_rules     [regex, family, [literals]] in `texmap.FAMILY_RULES`
                   order. Stem = the font name after its last `+`, trailing
                   size digits removed, lowercased. The FIRST rule with a
                   literal occurring anywhere in the stem gives the family;
                   none means `text`. The literals are what each regex matched
                   in the stems seen (`font_stems`), so on those names this is
                   `family_of` exactly, with no regex engine. (A prefix table
                   cannot do it: most maths fonts in the library carry a
                   subset tag glued on without a `+`.)
  font_stems       stem -> family, the names the literals were taken from.

Regenerate after any change to texmap:

    PYTHONPATH=src python3 -m pdfreader.texmap_dump            # from font_stems in the file
    PYTHONPATH=src python3 -m pdfreader.texmap_dump --collect DIR
                                                     # re-collect stems from *.drill.json under DIR

`tests/test_texmap_dump_is_current.py` fails when the file is not what this
module writes now, so the data cannot drift from the code silently.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from pdfreader import texmap as T

DATA = Path(__file__).resolve().parent / "data" / "texmap.json"
SUM = DATA.with_name(DATA.name + ".sha256")

#: The Unicode blocks maths is written in.
_BLOCKS = [(0x00A0, 0x00FF), (0x0370, 0x03FF), (0x2000, 0x206F),
           (0x2100, 0x214F), (0x2190, 0x21FF), (0x2200, 0x22FF),
           (0x2300, 0x23FF), (0x25A0, 0x25FF), (0x27C0, 0x27EF),
           (0x27F0, 0x27FF), (0x2900, 0x297F), (0x2980, 0x29FF),
           (0x2A00, 0x2AFF), (0x2B00, 0x2BFF), (0x1D400, 0x1D7FF)]

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_SIZE = re.compile(r"\d+$")


def stem(fontname: str) -> str:
    """A font's stem: everything after the last `+` (the subset tag, whatever
    its letters), no trailing size digits, lowercased."""
    return _SIZE.sub("", (fontname or "").rsplit("+", 1)[-1]).strip().lower()


def maths_chars() -> dict[str, str]:
    from pdfreader.docmodel_six import _maths_char
    out = {}
    for lo, hi in _BLOCKS:
        for cp in range(lo, hi + 1):
            ch = chr(cp)
            tex = _maths_char(ch)
            if tex != ch:
                out[ch] = tex
    return out


def _names() -> set[str]:
    """Every glyph name the tables mention: their keys and the CID tables' values."""
    names: set[str] = set()
    for v in vars(T).values():
        if isinstance(v, dict):
            for k, x in v.items():
                if isinstance(k, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", k):
                    names.add(k)
                if isinstance(x, dict):
                    names.update(n for n in x.values()
                                 if isinstance(n, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", n))
    for table in (T.CM_ENCODING, T.MATHABX):
        for slots in table.values():
            names.update(slots.values())
    names.update(T._TEX_SLOTS.values())
    return names


def glyph_names() -> dict[str, dict[str, list]]:
    fams = sorted({label for _, label in T.FAMILY_RULES} | {"text"})
    out: dict[str, dict[str, list]] = {}
    names = sorted(_names())
    for fam in fams:
        rows = {}
        for n in names:
            tok = T.project(fam, n)
            if tok.latex is not None:
                rows[n] = [tok.latex, tok.kind, tok.package]
        out[fam] = rows
    return out


def cid_tables() -> dict:
    return {
        "cm": {k: {str(c): n for c, n in sorted(v.items())}
               for k, v in sorted(T.CM_ENCODING.items())},
        "mathabx": {k: {str(c): n for c, n in sorted(v.items())}
                    for k, v in sorted(T.MATHABX.items())},
        "verified_slots": [[fam, slot, name] for (fam, slot), name
                           in sorted(T._TEX_SLOTS.items())],
        "esint_latex": {str(c): tex for c, tex in sorted(T._ESINT_CID.items())},
        "mtpro2_encoding": [list(x) for x in T._MTPRO2_ENCODING],
    }


def family_rules(stems: dict[str, str]) -> list[list]:
    """`FAMILY_RULES` without regexes: each rule, in its order, with the literal
    strings it matched in the stems seen (trailing size digits off).

    A reader takes the FIRST rule one of whose literals occurs anywhere in the
    stem; none means `text`. That is `family_of`'s own unanchored search, and
    on every stem seen it gives the same family (the test holds it to that).
    Not a prefix table: 1,057 of the 1,594 non-text stems in the library carry
    a subset tag glued on WITHOUT a `+` (`bcggrbmvygbqfbhksxmtmi`), so no
    prefix of the stem says anything about its family.
    """
    rules: list[list] = []
    for rx, label in T.FAMILY_RULES:
        lits: set[str] = set()
        for s in stems:
            m = rx.search(s)
            if m:
                lit = _SIZE.sub("", m.group(0).lower())
                if lit:
                    lits.add(lit)
        rules.append([rx.pattern, label, sorted(lits)])
    return rules


def family_by_rules(rules: list[list], s: str) -> str:
    """The reader's side of `family_rules`, for the test and for reference."""
    for _pattern, label, lits in rules:
        if any(lit in s for lit in lits):
            return label
    return "text"


def collect(root: Path) -> dict[str, str]:
    """stem -> family over every font list in the *.drill.json under `root`."""
    seen: dict[str, str] = {}
    for f in root.rglob("*.drill.json"):
        try:
            fonts = json.loads(f.read_text(encoding="utf-8")).get("fonts_layer") or []
        except (OSError, ValueError):
            continue
        for x in fonts:
            name = (x or {}).get("name") or (x or {}).get("base_name") or ""
            s = stem(name)
            if s:
                seen.setdefault(s, T.family_of(name.rsplit("+", 1)[-1]))
    return seen


def build(stems: dict[str, str]) -> dict:
    stems = {s: T.family_of(s) for s in sorted(stems)}   # today's rules decide
    return {
        "format": "pdfdrill-texmap/1",
        "texmap_sha256": hashlib.sha256(
            Path(T.__file__).read_bytes()).hexdigest(),
        "maths_chars": maths_chars(),
        "glyph_names": glyph_names(),
        "cid_tables": cid_tables(),
        "family_rules": family_rules(stems),
        "font_stems": stems,
    }


def render(doc: dict) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=0, sort_keys=False)
            + "\n").encode("utf-8")


def write(doc: dict) -> str:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    raw = render(doc)
    DATA.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    SUM.write_text(f"{digest}  {DATA.name}\n", encoding="utf-8")
    return digest


def main(argv: list[str]) -> int:
    if argv[:1] == ["--collect"]:
        stems = collect(Path(argv[1]))
    else:
        stems = json.loads(DATA.read_text(encoding="utf-8"))["font_stems"]
    digest = write(build(stems))
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    print(f"{DATA} sha256 {digest}: {len(doc['maths_chars'])} maths characters, "
          f"{sum(len(v) for v in doc['glyph_names'].values())} glyph names in "
          f"{len(doc['glyph_names'])} families, {len(doc['font_stems'])} font stems, "
          f"{sum(len(r[2]) for r in doc['family_rules'])} literals in {len(doc['family_rules'])} family rules")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
