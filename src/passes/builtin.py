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
    name = "citation"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        return _has_type(ctx.doc, ("Reference",)) and _has_type(ctx.doc, ("Citation",))

    def run(self, ctx: PassContext) -> PassResult:
        from pdfdrill import bibliography
        n = bibliography.link_citations(ctx.doc)
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
    name = "frontmatter"
    requires = ()

    def run(self, ctx: PassContext) -> PassResult:
        meta = getattr(ctx.doc, "meta", {}) or {}
        title = meta.get("title")
        return PassResult(self.name, "ran" if title else "n/a",
                          summary=f"title {'present' if title else 'absent'} "
                                  f"(BibTeX provenance wiring: semantic/frontend)")


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
