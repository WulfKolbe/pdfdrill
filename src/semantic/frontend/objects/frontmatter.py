"""OBJECT module: FRONTMATTER — the provenance header of ANY document, in any
format. Format-agnostic: it owns only the canonical schema and the conclusion it
licenses; the surface parsing lives in the per-format CELLS.

The unification (the user's rule): an `agent` carries a ROLE, and
  author (LaTeX)  ≡  sender (letter)  ≡  issuer (invoice)
all map to the BibTeX `author`. A letter's RECIPIENT is the only genre-specific
addition — it becomes a new BibTeX `recipient` field, NOT an address entity per
author. (An optional address-book node for the recipient is a higher-layer
choice handled by the semantic graph, not here.)
"""
from __future__ import annotations

from typing import Any

from ..contract import DetectedObject, ObjectModule, register_object

# which agent roles are the "author" of the document (the issuing party)
_AUTHOR_ROLES = ("author", "sender", "issuer")

# genre -> BibTeX entry type
_ENTRYTYPE = {
    "article": "article", "book": "book", "report": "report",
    "letter": "letter", "invoice": "misc", "": "misc",
}


class FrontMatter(ObjectModule):
    kind = "frontmatter"

    def schema(self) -> dict[str, Any]:
        return {
            "genre": "str  # article|book|report|letter|invoice|…",
            "title": "str",
            "agents": "[{role: author|sender|issuer, name, org?, address?}]",
            "date": "str?",
            "recipients": "[{name?, address?}]",
            "identifiers": "[{scheme: doi|arxiv|isbn|invoice_no|…, value}]",
            "subject": "str?",
        }

    # ----- the conclusion this object licenses: a BibTeX-like record -----
    def conclude(self, obj: DetectedObject) -> dict[str, Any]:
        f = obj.fields
        authors = [a["name"] for a in f.get("agents", [])
                   if a.get("role") in _AUTHOR_ROLES and a.get("name")]
        rec: dict[str, Any] = {
            "entrytype": _ENTRYTYPE.get(f.get("genre", ""), "misc"),
            "author": " and ".join(authors),
        }
        if f.get("title"):
            rec["title"] = f["title"]
        if f.get("date"):
            rec["date"] = f["date"]
        if f.get("subject"):
            rec["title"] = rec.get("title") or f["subject"]
        # the recipient is a NEW field (the audience a journal leaves implicit)
        recips = [r["name"] for r in f.get("recipients", []) if r.get("name")]
        if recips:
            rec["recipient"] = " and ".join(recips)
        for ident in f.get("identifiers", []):
            scheme, value = ident.get("scheme"), ident.get("value")
            if scheme and value:
                rec[scheme] = value
        return rec


register_object(FrontMatter())
