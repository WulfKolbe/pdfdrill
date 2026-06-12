"""
The vertical slice (two-store plan, step 4): the stratum-4 claim extractor
(semantic/claims.py) emits kitems WITH EVIDENCE SPANS from the docmodel, and
the rulebook projector renders accepted/supported kitems as flat Markdown,
one statement per line, each carrying its [→k:hash] drill-down anchor.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic import claims, kitems, rulebook, fixpoint


def _doc():
    doc = Document(); doc.meta["bibkey"] = "Heim1979"
    doc.add(DocObject(type="Section", id="s1", props={"caption": "Theory",
                                                      "flow_index": 1}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "We propose a novel mass formula for elementary particles. "
                "It extends earlier work.",
        "page": 14, "parent_section": "s1", "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "The metric tensor is defined as the field g that measures "
                "distances. Nothing else here.",
        "page": 15, "parent_section": "s1", "flow_index": 3}))
    doc.add(DocObject(type="Paragraph", id="p3", props={
        "text": "Plain prose without any claim or definition.",
        "page": 16, "parent_section": "s1", "flow_index": 4}))
    return doc


def test_claims_pass_emits_kitems_with_spans():
    doc = _doc()
    g = SemanticGraph(); r = IdentityResolver(g)
    res = fixpoint.run_fixpoint(g, r, [(4, claims.make_claims_pass(doc, "Heim1979"))])
    ks = kitems.all_kitems(g)
    by_kind = {}
    for e in ks:
        by_kind.setdefault(e.subtype, []).append(e)
    assert len(by_kind.get("claim", [])) == 1
    assert len(by_kind.get("definition", [])) == 1
    claim = by_kind["claim"][0]
    p = claim.properties()
    assert "novel mass formula" in p["statement_md"]
    assert "extends earlier work" not in p["statement_md"]   # ONE sentence
    spans = [x.grounding for x in claim.evidence if x.prop == "span"]
    assert spans and spans[0]["node"] == "p1" and spans[0]["page"] == 14
    assert spans[0]["bibkey"] == "Heim1979"
    assert kitems.status_of(g, claim.id) == "supported"
    # idempotent under the fixpoint (re-run -> nothing new)
    res2 = fixpoint.run_fixpoint(g, r, [(4, claims.make_claims_pass(doc, "Heim1979"))])
    assert res2["new_kitems"] == 0 and len(kitems.all_kitems(g)) == len(ks)


def test_rulebook_projects_statements_with_anchors():
    doc = _doc()
    g = SemanticGraph(); r = IdentityResolver(g)
    fixpoint.run_fixpoint(g, r, [(4, claims.make_claims_pass(doc, "Heim1979"))])
    md = rulebook.project_rulebook(g, "Heim1979")
    assert "novel mass formula" in md
    assert "is defined as" in md
    assert "[→k:" in md                          # drill-down anchors
    assert "(supported)" in md                   # status visible (1 span only)
    # one statement per line, grouped by kind heading
    assert "## " in md
    # the anchor is the kitem hash prefix — resolvable
    import re
    h8 = re.search(r"\[→k:([0-9a-f]{8})\]", md).group(1)
    assert any(kitems.kitem_hash(e.properties()["statement_md"]).startswith(h8)
               for e in kitems.all_kitems(g))


def test_rulebook_excludes_proposed_and_disputed():
    g = SemanticGraph(); r = IdentityResolver(g)
    kitems.emit_kitem(g, r, "An ungrounded guess.", kind="claim", stratum=4,
                      spans=[], produced_by="p")
    md = rulebook.project_rulebook(g, "X")
    assert "ungrounded guess" not in md
    assert "1 kitem(s) below the bar" in md      # honest count, not silence


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
