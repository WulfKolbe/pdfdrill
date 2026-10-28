# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Refinement pass: patch warm-up pages from the page's glyphs.

`refine_range` runs in a worker process. It opens the PDF once, and for
each page of its range loads the page file the warm-up wrote, reads the
glyphs, runs the modules and writes the page file back.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import assign, continuation, glyphlayout, glyphs, modules
from .modules import tables


class RefineError(RuntimeError):
    pass


def require_pdfminer() -> None:
    missing = glyphs.missing_features()
    if missing:
        raise RefineError(
            "the refinement pass needs the patched pdfminer ("
            + ", ".join(missing) + "); run scripts/install-pdfminer.sh")


def refine_page(page: dict, page_glyphs: glyphs.PageGlyphs) -> dict:
    """Patch `page` in place; return this page's statistics."""
    g = page_glyphs.glyphs
    own = assign.by_text(page["lines"], g,
                             assign.owners(page["lines"], g))
    stats = {
        "page": page["page"],
        "glyphs": g.n,
        "rules": page_glyphs.rules.n,
        "unassigned": sum(1 for i in range(g.n)
                          if own[i] < 0 and g.text[i].strip()),
        "agreement": round(assign.agreement(page["lines"], g, own), 4),
        "error": page_glyphs.error,
    }
    for _name, process in modules.MODULES:
        modules.apply(page, process(page, page_glyphs, own))
    continuation.mark(page)
    return stats


def refine_range(pdf: str, page_dir: str, first: int, last: int,
                 build: bool = False) -> list[dict]:
    """`build`: no warm-up page was written; make it from the glyphs."""
    out = []
    for pg in glyphs.read_pages(Path(pdf), first, last):
        if tables.GRID and tables.grids(pg.rules, pg.posts):
            # a table's cells are found by where the glyphs' ink is: a font
            # box can be far from it (cmex10 hangs below its baseline)
            pg = next(glyphs.read_pages(Path(pdf), pg.page, pg.page,
                                        ink=True))
        path = Path(page_dir) / f"page-{pg.page:04d}.json"
        page = (glyphlayout.page_from_glyphs(Path(pdf).stem, pg) if build
                else json.loads(path.read_text("utf-8")))
        out.append(refine_page(page, pg))
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(page, ensure_ascii=False), "utf-8")
        os.replace(tmp, path)
    return out


def build_range(pdf: str, page_dir: str, first: int, last: int) -> int:
    """The warm-up from the glyphs, without the refinement: write the pages,
    return their line count."""
    n = 0
    for pg in glyphs.read_pages(Path(pdf), first, last):
        page = glyphlayout.page_from_glyphs(Path(pdf).stem, pg)
        continuation.mark(page)
        path = Path(page_dir) / f"page-{pg.page:04d}.json"
        path.write_text(json.dumps(page, ensure_ascii=False), "utf-8")
        n += len(page["lines"])
    return n
