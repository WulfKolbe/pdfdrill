"""The `genre` enhancement pass — the inferred BibTeX-entrytype certificate.

Runs `semantic.genre.infer_genre` (SO.GENRE.INFER) and persists the verdict on
`doc.meta['genre']` = {entrytype, confidence, evidence}. Downstream passes GATE
on it (never a CLI switch): CitationPass reports n/a on a confident @manual —
bracketed `[VOL]`-style tokens there are a controlled vocabulary (concepts),
not citations (the Axe-Fx-manual failure). Idempotent by content."""
from __future__ import annotations

from .base import EnhancementPass, PassContext, PassResult, register_pass


class GenrePass(EnhancementPass):
    name = "genre"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        return bool(getattr(ctx.doc, "objects", None))

    def run(self, ctx: PassContext) -> PassResult:
        from semantic.genre import infer_genre
        g = infer_genre(ctx.doc)
        meta = getattr(ctx.doc, "meta", None)
        if not isinstance(meta, dict):
            return PassResult(self.name, "n/a", summary="document has no meta")
        changed = meta.get("genre") != g
        meta["genre"] = g
        ev = "; ".join(g["evidence"][:3]) or "no signals"
        return PassResult(
            self.name, "ran", changed=changed,
            summary=f"@{g['entrytype']} (confidence {g['confidence']:.2f}; {ev})",
            stats=g)


register_pass(GenrePass())
