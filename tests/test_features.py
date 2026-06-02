"""
Tests for the additive `features` extraction layer.

The no-dependency extractors (email/url/doi), the registry, the graph builder
(networkx) and the fuzzy matcher (rapidfuzz) are tested for real. The
library-backed extractors are tested only for graceful behaviour (return a list,
never crash) since their optional deps may be absent.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import features as F
from features import Feature, Relation, FeatureRegistry, build_graph
from features import extract_email, extract_url, extract_doi, match_entities
from features import audit_deps, audit_nested


# ---------------- core dataclasses + registry ----------------

def test_feature_create_is_deterministic_and_flat():
    a = Feature.create("p1", "EMAIL", "x@y.com", 0.95, 3, 10)
    b = Feature.create("p1", "EMAIL", "x@y.com", 0.95, 3, 10)
    assert a.id == b.id and a.id.startswith("email-")
    assert a.type == "EMAIL" and a.value == "x@y.com" and a.start == 3
    assert isinstance(a.to_dict(), dict)


def test_registry():
    r = FeatureRegistry()
    r.register_many([Feature.create("p", "EMAIL", "a@b.com", 0.9),
                     Feature.create("p", "URL", "http://x", 0.9)])
    assert len(r.find_features("EMAIL")) == 1
    assert r.types() == ["EMAIL", "URL"]


# ---------------- regex extractors (no deps) ----------------

def test_extract_email():
    feats = extract_email.extract("Contact sales@acme.co or bob@x.io.", "p7")
    vals = {f.value for f in feats}
    assert "sales@acme.co" in vals and "bob@x.io" in vals
    assert all(f.type == "EMAIL" and f.page_id == "p7" for f in feats)
    f0 = next(f for f in feats if f.value == "sales@acme.co")
    assert "Contact sales@acme.co"[f0.start:f0.end] == "sales@acme.co"


def test_extract_url_strips_trailing_punct():
    feats = extract_url.extract("See https://example.com/path. Also www.x.org).", "p")
    vals = {f.value for f in feats}
    assert "https://example.com/path" in vals
    assert "www.x.org" in vals       # trailing ')' and '.' stripped


def test_extract_doi():
    feats = extract_doi.extract("doi:10.1145/3290605.3300233 and 10.1007/xyz", "p")
    vals = {f.value for f in feats}
    assert "10.1145/3290605.3300233" in vals and "10.1007/xyz" in vals
    assert all(f.type == "DOI" for f in feats)


# ---------------- extract_all + availability ----------------

def test_extract_all_runs_available_and_is_graceful():
    text = "Invoice to bob@acme.com, ref https://acme.com/i/42, doi 10.5555/abc, on 2024-04-30, total $99.50."
    feats = F.extract_all(text, "p1")
    types = {f.type for f in feats}
    assert {"EMAIL", "URL", "DOI"} <= types     # always-on extractors fired
    avail = F.available_extractors()
    assert avail["email"] and avail["url"] and avail["doi"]
    # Library-backed extractors never crash even when their dep is missing.
    for mod in (F.extract_dates, F.extract_phone, F.extract_price,
                F.extract_names, F.extract_address):
        assert isinstance(mod.extract(text, "p1"), list)


# ---------------- graph builder (networkx) ----------------

def test_build_graph():
    rels = [Relation("a", "b", "SAME_AS", 0.9), Relation("b", "c", "SAME_AS", 0.8)]
    g = build_graph(rels)
    assert g.number_of_nodes() == 3 and g.number_of_edges() == 2
    assert g["a"]["b"]["type"] == "SAME_AS" and g["a"]["b"]["weight"] == 0.9
    import networkx as nx
    comps = list(nx.weakly_connected_components(g))
    assert len(comps) == 1 and comps[0] == {"a", "b", "c"}


# ---------------- fuzzy matcher (rapidfuzz) ----------------

def test_match_entities_links_ocr_typo_invoice_numbers():
    feats = [
        Feature.create("p", "INVOICE", "RE-2024-001", 0.9),
        Feature.create("p", "INVOICE", "RE-2024-OO1", 0.9),   # OCR O/0 typos
        Feature.create("p", "INVOICE", "ZZ-9999-XYZ", 0.9),
    ]
    rels = match_entities.match(feats, threshold=80)
    assert any(r.type == "SAME_AS" and 0.8 <= r.weight <= 1.0 for r in rels)
    linked = {(r.source, r.target) for r in rels}
    far = feats[2].id
    assert not any(far in pair for pair in linked)   # dissimilar not linked


# ---------------- read-only audits ----------------

def test_audit_deps_json():
    out = audit_deps.audit("src")
    assert isinstance(out, list) and out
    assert all({"module", "inputs", "outputs"} <= set(e) for e in out)
    json.dumps(out)                                  # JSON-serializable
    feat_mods = [e for e in out if e["module"].startswith("features.")]
    assert feat_mods                                 # found the new package


def test_audit_nested_json():
    out = audit_nested.audit("src")
    assert isinstance(out, list)
    assert all({"file", "line", "purpose", "can_be_flattened"} <= set(e) for e in out)
    json.dumps(out)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
