"""The `measurement` enhancement pass (S2.1) — bound measurements onto the IR.

Runs `semantic.measurements.measurement_records` (SO.MEAS.BIND) and stores each
Paragraph's measurements under `props['meas']` (a list). Requires the quantity
pass (it reads `props['quant']` via the FO objects) and concepts (nearest-concept
binding). Idempotent by content, like the quantity pass."""
from __future__ import annotations

from .base import EnhancementPass, PassContext, PassResult, register_pass


class MeasurementPass(EnhancementPass):
    name = "measurement"
    requires = ("quantity", "concepts")

    def applies(self, ctx: PassContext) -> bool:
        objs = getattr(ctx.doc, "objects", None)
        return bool(objs)

    def run(self, ctx: PassContext) -> PassResult:
        from semantic.measurements import measurement_records
        recs = measurement_records(ctx.doc)
        by_para: dict[str, list[dict]] = {}
        for r in recs:
            by_para.setdefault(r["para_id"], []).append(r)

        objs = ctx.doc.objects
        objmap = objs if isinstance(objs, dict) else {o.id: o for o in objs}
        changed = 0
        for pid, rlist in by_para.items():
            p = objmap.get(pid)
            if p is None:
                continue
            stored = [{k: v for k, v in r.items() if k != "para_id"} for r in rlist]
            if p.props.get("meas") != stored:
                p.props["meas"] = stored
                changed += 1

        return PassResult(
            self.name, "ran", changed=changed > 0,
            summary=(f"{len(recs)} measurements on {len(by_para)} paragraphs"
                     if recs else "no measurements bound"),
            stats={"measurements": len(recs), "paragraphs": len(by_para),
                   "changed": changed})


register_pass(MeasurementPass())
