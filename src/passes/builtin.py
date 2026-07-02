"""The built-in enhancement passes, in dependency order.

Maps the named slots (ChatGPT's list + the ones it omits that we already wanted)
onto our existing capabilities. Three are FULLY WIRED today (math / citation /
concepts); the rest are honest, named, ordered slots that report what they find
or that their wiring is the open task — so the pipeline's coverage AND gaps are
visible at a glance, never silently missing.

Imports are lazy (inside run/applies) so importing the package is cheap and free
of cycles.
"""
from __future__ import annotations

from .base import EnhancementPass, PassContext, PassResult, register_pass


def _objs(doc) -> list:
    o = getattr(doc, "objects", None)
    if o is None:
        return []
    return list(o.values()) if isinstance(o, dict) else list(o)


def _has_type(doc, types: tuple[str, ...]) -> bool:
    return any(getattr(x, "type", None) in types for x in _objs(doc))


# --------------------------------------------------------------------------- #
# Fully wired
# --------------------------------------------------------------------------- #
class MathPass(EnhancementPass):
    name = "math"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        try:
            from mathlayer import parse as mlparse
        except Exception:
            return False
        return mlparse.available() and _has_type(ctx.doc, ("Formula", "Equation"))

    def run(self, ctx: PassContext) -> PassResult:
        from mathlayer import annotate_document
        c = annotate_document(ctx.doc)
        return PassResult(self.name, "ran", changed=c["seen"] > 0,
                          summary=f"{c['parsed']}/{c['seen']} FO/EQ → canonical math",
                          stats=c)


class CitationPass(EnhancementPass):
    """Link in-text Citations to References. When the model has Citations but NO
    References yet (the LaTeX-source case), discover the bib the source NAMES and
    build THIS paper's bibliography (the cited subset of a shared .bib) first —
    the bibsource discovery, reused here so `enhance` does it automatically."""
    name = "citation"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        return _has_type(ctx.doc, ("Citation",))

    @staticmethod
    def _source_dir(ctx: PassContext):
        from pathlib import Path
        src = (getattr(ctx.doc, "meta", {}) or {}).get("latex_source_dir")
        if src and Path(src).is_dir():
            return src
        if ctx.pdf is not None:                  # <pdf>.drill/texsrc fallback
            cand = Path(str(ctx.pdf) + ".drill") / "texsrc"
            if cand.is_dir():
                return str(cand)
        return None

    def run(self, ctx: PassContext) -> PassResult:
        from pdfdrill import bibliography
        doc = ctx.doc

        if not _has_type(doc, ("Reference",)):
            src = self._source_dir(ctx)
            if src:
                r = bibliography.build_bibliography_from_source(doc, src)
                return PassResult(self.name, "ran",
                                  changed=(r["created"] or r["linked"]) > 0,
                                  summary=f"{r['linked']} citations linked; "
                                          f"{r['created']} refs built from the "
                                          f"source bib (cited subset)",
                                  stats=r)
            return PassResult(self.name, "ran", changed=False,
                              summary="citations present but no references / "
                                      "source bib to build from")

        already = sum(1 for a in getattr(doc, "alignments", []) if a.kind == "cites")
        if already:
            return PassResult(self.name, "ran", changed=False,
                              summary=f"already linked ({already} cites edges)")
        n = bibliography.link_citations(doc)
        return PassResult(self.name, "ran", changed=n > 0,
                          summary=f"{n} in-text citations linked to references",
                          stats={"linked": n})


class ConceptsPass(EnhancementPass):
    """Glossary + acronym in one read (Schwartz-Hearst + glossary/notation
    sections). Records a doc-level summary; the graph ingest consumes the same
    records downstream."""
    name = "concepts"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        return bool(_objs(ctx.doc))

    def run(self, ctx: PassContext) -> PassResult:
        from semantic import concepts
        recs = concepts.concept_records(ctx.doc)
        acro = sum(1 for r in recs if r.get("subtype") == "acronym")
        meta = getattr(ctx.doc, "meta", None)
        if isinstance(meta, dict):
            meta["concepts"] = {"total": len(recs), "acronyms": acro}
        return PassResult(self.name, "ran", changed=bool(recs),
                          summary=f"{len(recs)} concepts ({acro} acronyms, "
                                  f"{len(recs) - acro} glossary/terms)",
                          stats={"concepts": len(recs), "acronyms": acro})


# --------------------------------------------------------------------------- #
# Named, ordered slots — report presence / flag the open wiring honestly
# --------------------------------------------------------------------------- #
class FrontmatterPass(EnhancementPass):
    """Provenance: detect the document's frontmatter (via the semantic/frontend
    FrontMatter object, with the Document IR as input format) and conclude it to
    a BibTeX-like record stored on doc.meta['bibtex'] (+ ['frontmatter']).
    Enriches from the sidecar's CACHED arXiv metadata first — offline, no network."""
    name = "frontmatter"
    requires = ()

    def run(self, ctx: PassContext) -> PassResult:
        from semantic.frontend import detect, to_bibtex

        meta = getattr(ctx.doc, "meta", None)
        if not isinstance(meta, dict):
            return PassResult(self.name, "n/a", summary="document has no meta")

        # enrich from the sidecar's cached arXiv metadata (offline; never fetches)
        sc = ctx.sidecar
        if sc is not None and hasattr(sc, "get_evidence"):
            try:
                if not meta.get("title") and sc.get_evidence("arxiv_title"):
                    meta["title"] = sc.get_evidence("arxiv_title")
                if not (meta.get("authors") or meta.get("author")) \
                        and sc.get_evidence("arxiv_authors"):
                    meta["authors"] = sc.get_evidence("arxiv_authors")
                if not meta.get("arxiv_id") and sc.get_evidence("source_arxiv_id"):
                    meta["arxiv_id"] = sc.get_evidence("source_arxiv_id")
            except Exception:
                pass

        dets = detect(ctx.doc, fmt="docmodel", kind="frontmatter")
        if not dets:
            return PassResult(self.name, "n/a",
                              summary="no frontmatter signal (no title/author/id)")
        fm = dets[0]
        rec = to_bibtex(fm)
        bk = meta.get("bibkey")
        if bk and not rec.get("citekey"):
            rec["citekey"] = bk
        if fm.fields.get("title") and not meta.get("title"):
            meta["title"] = fm.fields["title"]

        changed = meta.get("bibtex") != rec or meta.get("frontmatter") != fm.fields
        meta["frontmatter"] = fm.fields
        meta["bibtex"] = rec
        return PassResult(self.name, "ran", changed=changed,
                          summary=f"{rec['entrytype']} record "
                                  f"(author {'set' if rec.get('author') else 'empty'}, "
                                  f"title {'set' if rec.get('title') else 'empty'})",
                          stats={"entrytype": rec["entrytype"],
                                 "has_author": bool(rec.get("author"))})


class AbstractPass(EnhancementPass):
    name = "abstract"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        return _has_type(ctx.doc, ("Abstract",))

    def run(self, ctx: PassContext) -> PassResult:
        n = sum(1 for x in _objs(ctx.doc) if getattr(x, "type", None) == "Abstract")
        return PassResult(self.name, "ran", summary=f"{n} abstract object(s) present")


class TocPass(EnhancementPass):
    """TOC source = the Section tree. Injecting a links-bearing TOC when absent
    (reusing booktoc's printed→PDF page map) is the open task — this slot reports
    the source today."""
    name = "toc"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        return _has_type(ctx.doc, ("Section",))

    def run(self, ctx: PassContext) -> PassResult:
        n = sum(1 for x in _objs(ctx.doc) if getattr(x, "type", None) == "Section")
        return PassResult(self.name, "ran", summary=f"{n} sections (TOC source; "
                          f"links-bearing injection is the open wiring)")


class IndexPass(EnhancementPass):
    name = "index"
    requires = ("concepts",)               # an index is built from the term set

    def run(self, ctx: PassContext) -> PassResult:
        return PassResult(self.name, "n/a",
                          summary="planned: index from \\index{} source / concept terms")


class SummaryPass(EnhancementPass):
    name = "summary"
    requires = ("math", "citation", "concepts")   # draws on enriched content

    def run(self, ctx: PassContext) -> PassResult:
        return PassResult(self.name, "n/a",
                          summary="planned: abstractive chapter/section summaries")


for _p in (FrontmatterPass(), MathPass(), CitationPass(), ConceptsPass(),
           AbstractPass(), TocPass(), IndexPass(), SummaryPass()):
    register_pass(_p)

# quantity (S1.3) lives in its own module; importing it registers the pass in
# dependency order before summary (it has no deps; summary's deps are unchanged).
from . import quantity as _quantity   # noqa: E402,F401
