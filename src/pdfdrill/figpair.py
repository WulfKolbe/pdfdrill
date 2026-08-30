"""340 — a per-document figure-pairing table, edited by hand.

Which MathPix crop shows which of the author's figure files cannot be joined
reliably. 339 measured the automatic join on the one document where both sides
state a page: 4 unique pairs out of 62 annotated rows, 43 lost because the page
carries several crops and 14 CONTESTED, where two subfigures share one crop and
no rule can split them. 344 then found those 4 were the entire measurable
population in the corpus.

A person settles that in seconds by looking. The editing surface is report.tex
itself: the image table gains a column holding a placeholder that renders the
crop, and the filename inside it is overwritten with the author's own. The
report is recompiled, the pairs are harvested once, and everything downstream
reads the sidecar instead of re-deriving a join that does not work.

    crop        the MathPix crop's filename stem, as the placeholder shipped
    base        the author's figure file, as a human typed it
    identifier  the report row the pair belongs to
    contested   a crop several identifiers legitimately share

`<stem>.figpairs.json` next to the PDF. Absent is normal and is NOT an error:
most documents have no annotated figures, and an empty table must read as
"nothing to pair here", never as "the pairing was lost".

Deliberately the same shape as `notation.py`'s table, down to `present` being
distinct from `entries == []`, because both answer the same kind of question:
editorial knowledge about ONE document, recorded rather than inferred.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SUFFIX = ".figpairs.json"
SCHEMA_VERSION = 1


@dataclass
class Pair:
    crop: str                      # the MathPix crop stem the placeholder held
    base: str = ""                 # the author's file, typed over it
    identifier: str = ""           # the report row
    page: str = ""
    contested: bool = False        # several identifiers share this crop
    note: str = ""

    @property
    def resolved(self) -> bool:
        """Edited to something other than the placeholder it shipped with."""
        return bool(self.base) and self.base != self.crop

    def to_dict(self) -> dict:
        d = {"crop": self.crop, "base": self.base}
        for k in ("identifier", "page", "note"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.contested:
            d["contested"] = True
        return d


@dataclass
class PairTable:
    bibkey: str = ""
    version: int = SCHEMA_VERSION
    entries: list = field(default_factory=list)
    path: Path | None = None
    present: bool = False

    def to_dict(self) -> dict:
        return {"version": self.version, "bibkey": self.bibkey,
                "entries": [e.to_dict() for e in self.entries]}

    def by_identifier(self, ident: str):
        return next((e for e in self.entries if e.identifier == ident), None)

    def by_crop(self, crop: str):
        return [e for e in self.entries if e.crop == crop]

    @property
    def resolved(self) -> list:
        return [e for e in self.entries if e.resolved]


def path_for(pdf: Path) -> Path:
    pdf = Path(pdf)
    stem = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
    return pdf.parent / (stem + SUFFIX)


def load(pdf: Path) -> PairTable:
    """The table beside `pdf`. An absent file is an EMPTY table, not an error."""
    p = path_for(pdf)
    t = PairTable(path=p)
    if not p.is_file():
        return t
    t.present = True
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return t
    t.bibkey = d.get("bibkey", "")
    t.version = int(d.get("version") or SCHEMA_VERSION)
    for e in d.get("entries") or []:
        if not isinstance(e, dict) or not e.get("crop"):
            continue
        t.entries.append(Pair(crop=e["crop"], base=e.get("base", ""),
                              identifier=e.get("identifier", ""),
                              page=str(e.get("page", "")),
                              contested=bool(e.get("contested")),
                              note=e.get("note", "")))
    return t


def save(table: PairTable, pdf: Path) -> Path:
    p = path_for(pdf)
    p.write_text(json.dumps(table.to_dict(), indent=1, ensure_ascii=False),
                 encoding="utf-8")
    return p
