#!/usr/bin/env python3
"""634 — the claim ledger, measured on one drilled document.

Runs the SHIPPED code, not a copy of it: `docmodel.ledger.materialize` (the
same function `pdfdrill model --ledger` prints) and
`docops.conserve.anchor_claims` (646, the output-side twin). Writes
ledger.json + result.json + report.txt beside itself and prints the summary.

    python3 script.py <doc-dir>            # the dir holding model.docmodel.json

THE CROSS-CHECK IS ANCHOR BY ANCHOR, not count by count: two instruments can
agree on "243" while disagreeing about which 243, and that agreement would be
worthless. `zero_agrees` / `multi_agrees` are SET equalities.
"""
import json
import sys
from collections import Counter
from pathlib import Path

def _repo() -> Path:
    """The checkout, whether this copy sits in the repo's out/634/ or beside a
    library document. Walked, not hardcoded: an evidence script that only runs
    from the place it was written is not evidence."""
    for base in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        for cand in (base, *base.parents):
            if (cand / "src" / "docmodel" / "ledger.py").is_file():
                return cand
    return Path("/home/wkolbe/MX/PDFDRILL")


REPO = _repo()
sys.path.insert(0, str(REPO / "src"))

from docmodel import ledger as L                       # noqa: E402
from docops.conserve import anchor_claims              # noqa: E402
from pdfdrill.model_io import load_model               # noqa: E402


def main(docdir: Path) -> dict:
    model = docdir / "model.docmodel.json"
    doc = load_model(model)
    led = L.materialize(doc)
    cons = anchor_claims(doc)

    zl = [e["anchor"] for e in led["zero"]]
    zc = [e["anchor"] for e in cons["unclaimed"]]
    ml = [e["anchor"] for e in led["multi"]]
    mc = [e["anchor"] for e in cons["doubly_claimed"]]

    c = led["counts"]
    res = {
        "document": docdir.name,
        "bibkey": doc.meta.get("bibkey"),
        "build": doc.meta.get("build"),
        "objects": len(doc.objects),
        "stream_length": led["total"],
        "claimed_0": c["claimed_0"],
        "claimed_1": c["claimed_1"],
        "claimed_multi": c["claimed_multi"],
        "sum": c["claimed_0"] + c["claimed_1"] + c["claimed_multi"],
        "sum_equals_stream_length":
            c["claimed_0"] + c["claimed_1"] + c["claimed_multi"] == led["total"],
        "block_claims": c["block_claims"],
        "inline_claims": c["inline_claims"],
        "container_claims": c["container_claims"],
        "by_module": led["by_module"],
        "by_module_inline": led["by_module_inline"],
        "by_module_container": led["by_module_container"],
        "module_pairs": led["module_pairs"],
        "type_pairs": {"+".join(k): v for k, v in cons["pairs"].most_common()},
        "zero_by_line_type": led["zero_by_line_type"],
        "zero_by_page": led["zero_by_page"],
        "attributed_realizations": led["attributed_realizations"],
        "unattributed_block_claims": led["by_module"].get("unattributed", 0),
        "conserve": {
            "unclaimed": len(cons["unclaimed"]),
            "doubly_claimed": len(cons["doubly_claimed"]),
            "claims": cons["claims"],
            "inline_skipped": cons["inline_skipped"],
        },
        "cross_check": {
            "zero_counts_agree": len(zl) == len(zc),
            "multi_counts_agree": len(ml) == len(mc),
            "zero_anchors_agree": zl == zc,          # same anchors, same order
            "multi_anchors_agree": ml == mc,
            "block_claims_equal_conserve_claims":
                c["block_claims"] == cons["claims"],
            "inline_claims_equal_conserve_inline":
                c["inline_claims"] == cons["inline_skipped"],
            "zero_only_in_ledger": sorted(set(zl) - set(zc)),
            "zero_only_in_conserve": sorted(set(zc) - set(zl)),
            "multi_only_in_ledger": sorted(set(ml) - set(mc)),
            "multi_only_in_conserve": sorted(set(mc) - set(ml)),
        },
        # the module pair <-> type pair map, so a reader can move between the
        # two instruments' vocabularies without re-deriving it
        "pair_map": dict(Counter(
            ("+".join(e["modules"]), "+".join(e["types"]))
            for e in led["multi"]).most_common()) and [
            {"modules": k[0], "types": k[1], "anchors": v}
            for k, v in Counter(
                ("+".join(e["modules"]), "+".join(e["types"]))
                for e in led["multi"]).most_common()],
    }

    here = Path(__file__).resolve().parent
    (here / "ledger.json").write_text(
        json.dumps(led, indent=1, ensure_ascii=False), encoding="utf-8")
    (here / "result.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    (here / "report.txt").write_text(
        L.format_ledger(led, limit=60, title=str(doc.meta.get("bibkey"))),
        encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items()
                      if k not in ("zero_by_page",)}, indent=1,
                     ensure_ascii=False))
    return res


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1
              else Path(__file__).resolve().parents[2]))
