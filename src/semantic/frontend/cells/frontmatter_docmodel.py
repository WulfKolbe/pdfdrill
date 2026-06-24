"""CELL (frontmatter × docmodel): detect a document's frontmatter from the built
Document IR — title/authors/date from meta, an arXiv id from meta or a bibkey
that IS an arXiv id, a DOI if present. Genre defaults to a paper (article).

BOOTSTRAP for the (frontmatter, docmodel) slot. The richer arXiv-metadata
enrichment (sidecar) is a context concern handled by the FrontmatterPass, which
mutates doc.meta before calling this — this cell stays Document-pure.
"""
from __future__ import annotations

import re

from ..contract import CellModule, DetectedObject, Surface, register_cell

_ARXIV = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


def _authors(meta: dict) -> list[str]:
    a = meta.get("authors") or meta.get("author")
    if not a:
        return []
    if isinstance(a, str):
        a = re.split(r"\s+and\s+|,\s*", a)
    return [str(x).strip() for x in a if x and str(x).strip()]


class FrontMatterDocmodel(CellModule):
    kind = "frontmatter"
    format = "docmodel"

    def detect(self, surface: Surface) -> list[DetectedObject]:
        m = surface.meta.get("doc_meta", {}) or {}
        title = m.get("title")
        agents = [{"role": "author", "name": n} for n in _authors(m)]
        date = m.get("date") or (str(m["year"]) if m.get("year") else None)

        idents: list[dict] = []
        aid = m.get("arxiv_id")
        bk = m.get("bibkey")
        if not aid and bk and _ARXIV.match(str(bk)):
            aid = str(bk)
        if aid:
            idents.append({"scheme": "arxiv", "value": aid})
        if m.get("doi"):
            idents.append({"scheme": "doi", "value": m["doi"]})

        if not (title or agents or idents):
            return []
        fields = {
            "genre": m.get("genre") or "article",
            "title": title,
            "agents": agents,
            "date": date,
            "recipients": [],
            "identifiers": idents,
            "subject": None,
        }
        return [DetectedObject(kind=self.kind, format=self.format,
                               fields=fields, confidence=0.7)]


register_cell(FrontMatterDocmodel())
