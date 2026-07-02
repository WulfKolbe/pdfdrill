"""The `quantity` enhancement pass (S1.3) — typed quantities onto the IR.

Runs `semantic.quantities.quantity_records` (SO.QUANT.EXTRACT) over the Document
and stores each object's records under `props['quant']` (a list — one object can
carry several quantities), mirroring how `nlp` and `math` store their layers.
Idempotent by content: an object whose existing `props['quant']` equals what the
extractor produces now is left untouched and counted as unchanged, so a re-run
reports changed=0 (the R5 discipline; `kitems.emit_kitem` is the reference)."""
from __future__ import annotations

from .base import EnhancementPass, PassContext, PassResult, register_pass


def _strip_obj_id(recs: list[dict]) -> list[dict]:
    # what gets STORED on the object omits the redundant obj_id (it IS the object)
    return [{k: v for k, v in r.items() if k != "obj_id"} for r in recs]


class QuantityPass(EnhancementPass):
    name = "quantity"
    requires = ()

    def applies(self, ctx: PassContext) -> bool:
        objs = getattr(ctx.doc, "objects", None)
        return bool(objs)

    def run(self, ctx: PassContext) -> PassResult:
        from semantic.quantities import quantity_records
        recs = quantity_records(ctx.doc)
        by_obj: dict[str, list[dict]] = {}
        for r in recs:
            by_obj.setdefault(r["obj_id"], []).append(r)

        objs = ctx.doc.objects
        objmap = objs if isinstance(objs, dict) else {o.id: o for o in objs}
        changed = 0
        kinds: dict[str, int] = {}
        for oid, rlist in by_obj.items():
            o = objmap.get(oid)
            if o is None:
                continue
            stored = _strip_obj_id(rlist)
            if o.props.get("quant") != stored:      # content-identical → no-op
                o.props["quant"] = stored
                changed += 1
            for r in rlist:
                kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1

        return PassResult(
            self.name, "ran", changed=changed > 0,
            summary=f"{len(recs)} quantities on {len(by_obj)} objects "
                    f"({', '.join(f'{k}:{v}' for k, v in sorted(kinds.items()))})"
                    if recs else "no quantities found",
            stats={"records": len(recs), "objects": len(by_obj),
                   "changed": changed, "kinds": kinds})


register_pass(QuantityPass())
