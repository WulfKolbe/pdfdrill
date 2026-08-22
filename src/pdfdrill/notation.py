"""103 — a per-document notation table.

A book invents its own symbols. Heim's `S` with two limits is a discrete
integral, not a sum; another author's identical glyph is a sum. Nothing in the
OCR can tell them apart, and nothing should try — the distinction is editorial
knowledge about ONE document, so it lives beside that document and is read, not
inferred.

    glyph_context  what the OCR produced, as a pattern to recognise
    macro_name     the name this document gives it
    definition     what it means, in LaTeX or prose

The file is `<stem>.notation.json` next to the PDF. Absent is normal and is NOT
an error: most documents need no table, and an empty table must read as "this
document declares no special notation", never as "no table was found and
something may be missing".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SUFFIX = ".notation.json"
SCHEMA_VERSION = 1


@dataclass
class Entry:
    glyph_context: str          # e.g. "\\mathbf{S}_{lower}^{upper}"
    macro_name: str             # e.g. "discrete_integral"
    definition: str             # e.g. "\\sum_{k=lower}^{upper} f(k)\\,\\Delta k"
    note: str = ""              # provenance: page, who decided, why
    examples: list = field(default_factory=list)   # identifiers exhibiting it

    def to_dict(self) -> dict:
        d = {"glyph_context": self.glyph_context, "macro_name": self.macro_name,
             "definition": self.definition}
        if self.note:
            d["note"] = self.note
        if self.examples:
            d["examples"] = list(self.examples)
        return d


@dataclass
class NotationTable:
    bibkey: str = ""
    version: int = SCHEMA_VERSION
    entries: list = field(default_factory=list)
    path: Path | None = None
    present: bool = False       # did a file exist? distinct from `entries == []`

    def to_dict(self) -> dict:
        return {"version": self.version, "bibkey": self.bibkey,
                "entries": [e.to_dict() for e in self.entries]}

    def by_macro(self, name: str):
        return next((e for e in self.entries if e.macro_name == name), None)

    def __len__(self):
        return len(self.entries)


def path_for(pdf: Path) -> Path:
    return Path(pdf).with_suffix("").with_name(Path(pdf).stem + SUFFIX)


def load(pdf: Path) -> NotationTable:
    """The table beside `pdf`. An absent file yields an EMPTY table, present=False.

    Never raises for absence. A malformed file DOES raise, because a table that
    exists and cannot be read is a different situation from one that was never
    written, and silently treating the first as the second would let a typo
    disable a document's notation without a word.
    """
    p = path_for(pdf)
    t = NotationTable(bibkey=Path(pdf).stem, path=p)
    if not p.is_file():
        return t
    data = json.loads(p.read_text(encoding="utf-8"))
    t.present = True
    t.version = int(data.get("version", SCHEMA_VERSION))
    t.bibkey = data.get("bibkey") or t.bibkey
    for raw in data.get("entries", []):
        missing = [k for k in ("glyph_context", "macro_name", "definition")
                   if not raw.get(k)]
        if missing:
            raise ValueError(f"{p.name}: entry missing {', '.join(missing)}")
        t.entries.append(Entry(raw["glyph_context"], raw["macro_name"],
                               raw["definition"], raw.get("note", ""),
                               list(raw.get("examples", []))))
    names = [e.macro_name for e in t.entries]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"{p.name}: duplicate macro_name {sorted(dup)}")
    return t


def save(pdf: Path, table: NotationTable) -> Path:
    p = path_for(pdf)
    p.write_text(json.dumps(table.to_dict(), indent=1, ensure_ascii=False),
                 encoding="utf-8")
    return p
