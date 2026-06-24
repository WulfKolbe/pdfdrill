"""CELL (frontmatter × latex): detect the frontmatter of a LaTeX document from
its preamble (\\title / \\author / \\date / documentclass).

BOOTSTRAP PARSER. This is exactly the (object,format) slot a LEAN grammar will
generate on the fly (recursion via fixed-point), with the grammar also producing
this cell's test corpus. The hand parser below implements the cell contract so
the generated one can replace it without changing any caller.
"""
from __future__ import annotations

import re

from ..contract import CellModule, DetectedObject, Surface, register_cell

_TITLE = re.compile(r"\\title\s*\{(.+?)\}", re.S)
_AUTHOR = re.compile(r"\\author\s*\{(.+?)\}", re.S)
_DATE = re.compile(r"\\date\s*\{(.+?)\}", re.S)

# documentclass -> frontmatter genre
_GENRE = {"article": "article", "book": "book", "report": "report",
          "memoir": "book", "amsart": "article", "scrartcl": "article"}


def _clean(s: str) -> str:
    s = re.sub(r"\\(thanks|footnote)\s*\{[^}]*\}", "", s)  # drop affil footnotes
    s = re.sub(r"\\[a-zA-Z]+\b", "", s)                    # drop remaining macros
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def _split_authors(block: str) -> list[str]:
    # authors are separated by \and (LaTeX) or, failing that, commas
    parts = re.split(r"\\and\b", block)
    if len(parts) == 1:
        parts = re.split(r"\s*,\s*", block)
    return [a for a in (_clean(p) for p in parts) if a]


class FrontMatterLatex(CellModule):
    kind = "frontmatter"
    format = "latex"

    def detect(self, surface: Surface) -> list[DetectedObject]:
        pre = surface.meta.get("preamble", surface.raw)
        title_m = _TITLE.search(pre)
        author_m = _AUTHOR.search(pre)
        date_m = _DATE.search(pre)
        if not (title_m or author_m):
            return []
        genre = _GENRE.get(surface.meta.get("documentclass", ""), "article")
        fields = {
            "genre": genre,
            "title": _clean(title_m.group(1)) if title_m else "",
            "agents": [{"role": "author", "name": n}
                       for n in (_split_authors(author_m.group(1)) if author_m else [])],
            "date": _clean(date_m.group(1)) if date_m else None,
            "recipients": [],
            "identifiers": [],
            "subject": None,
        }
        return [DetectedObject(kind=self.kind, format=self.format, fields=fields,
                               confidence=0.95)]


register_cell(FrontMatterLatex())
