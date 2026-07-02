"""
S4.2: quantities + measurements ingest into the semantic graph. A tiny
in-memory doc with one bound measurement, ingested TWICE — one QUANTITY entity
(content-hash dedup), one MEASURES edge, grounding carrying conditions, and a
registered produced_by (question.py) so the compiler stays quiet.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.entity import EntityType
from semantic.relation import RelationType
from semantic import build, question


def _o(id, t, **props):
    ns = types.SimpleNamespace(id=id, type=t, props=props)
    ns.parent = None
    return ns


def _doc():
    fo = _o("q1", "Formula", latex=r"5,550,689", flow_index=1, page=9,
            quant=[{"kind": "number", "value": 5550689, "unit": None,
                    "dimension": None, "raw": "5,550,689"}])
    para = _o("p1", "Paragraph", flow_index=2, page=9,
              text="we could add {{X_FO0001||FO}} new facts",
              meas=[{"concept": "KBC Potential", "concept_source": "section",
                     "measure": "could add",
                     "quantity_ref": {"obj_id": "q1", "idx": 0},
                     "conditions": {"accuracy": 0.82},
                     "sentence_span": [0, 44]}])
    d = types.SimpleNamespace()
    d.objects = {o.id: o for o in (fo, para)}
    d.meta = {"bibkey": "testdoc", "title": "T"}
    return d


def _records(doc):
    quant = []
    meas = []
    for o in doc.objects.values():
        for i, q in enumerate(o.props.get("quant") or []):
            quant.append({**q, "obj_id": o.id})
        for m in o.props.get("meas") or []:
            meas.append({**m, "para_id": o.id})
    return quant, meas


def test_ingest_dedups_and_relates():
    g = SemanticGraph()
    r = IdentityResolver(g)
    doc = _doc()
    quant, meas = _records(doc)

    c1 = build.ingest_docmodel(g, r, doc, "testdoc",
                               quant_records=quant, meas_records=meas)
    assert c1.get("quantities") == 1
    assert c1.get("measurements") == 1

    qents = [e for e in g.entities.values() if e.type == EntityType.QUANTITY]
    assert len(qents) == 1
    q = qents[0]
    assert q.subtype == "number"
    # grounded evidence: the source object + page + layer
    ev = [e for e in q.evidence if (e.grounding or {}).get("layer") == "quant"]
    assert ev and ev[0].grounding.get("node") == "q1"
    assert ev[0].grounding.get("page") == 9

    edges = [x for x in g.relations if x.predicate == RelationType.MEASURES]
    assert len(edges) == 1
    e = edges[0]
    assert e.object_id == q.id
    assert e.produced_by == "measurement"
    assert e.grounding.get("conditions") == {"accuracy": 0.82}
    subj = g.get(e.subject_id)
    assert subj.type == EntityType.CONCEPT

    # --- second ingest: found-not-minted, no duplicate edge -----------------
    c2 = build.ingest_docmodel(g, r, doc, "testdoc",
                               quant_records=quant, meas_records=meas)
    qents2 = [e for e in g.entities.values() if e.type == EntityType.QUANTITY]
    assert len(qents2) == 1
    edges2 = [x for x in g.relations if x.predicate == RelationType.MEASURES]
    assert len(edges2) == 1


def test_default_kwargs_do_not_break_existing_callers():
    g = SemanticGraph()
    r = IdentityResolver(g)
    counts = build.ingest_docmodel(g, r, _doc(), "testdoc")   # no new kwargs
    assert not [e for e in g.entities.values() if e.type == EntityType.QUANTITY]
    assert counts.get("quantities", 0) == 0


def test_questions_registered():
    assert question.get("quantity") is not None
    assert question.get("measurement") is not None
    assert EntityType.QUANTITY in question.get("quantity").emits_entities
    assert RelationType.MEASURES in question.get("measurement").emits_relations


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
