"""P10 — crossref: one index over (bibkey, kind, id, signature, evidence).

The signature is opaque to the index; formulas supply the SLT .lg form,
which canonicalizes latex spelling variants (x_{5} == x_5).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.crossref import (add_entries, entries_from_tiddlers,
                               formula_signature, load_store, map_books, rank)


def test_signature_canonicalizes_latex_spelling():
    assert formula_signature(r"x_{5}+\alpha") == \
        formula_signature(r"x_5 + \alpha")
    assert formula_signature(r"x_{5}") != formula_signature(r"x_{6}")


def test_rank_exact_beats_partial_and_is_cross_bibkey():
    sig_a = formula_signature(r"a+b")
    sig_ab = formula_signature(r"a+b+c")
    entries = [
        {"bibkey": "B1", "kind": "formula", "id": "B1_FO1",
         "signature": sig_a, "evidence": {}},
        {"bibkey": "B2", "kind": "formula", "id": "B2_EQ1",
         "signature": sig_ab, "evidence": {}},
    ]
    top = rank(entries, sig_a, kind="formula")
    assert top[0][0] == 1.0 and top[0][1]["id"] == "B1_FO1"
    assert 0 < top[1][0] < 1.0                    # partial overlap ranks lower
    assert rank(entries, sig_a, exclude_bibkey="B1")[0][1]["bibkey"] == "B2"


def test_index_store_roundtrip_and_idempotent_reindex(tmp_path):
    tid = tmp_path / "k.tiddlers.json"
    tid.write_text(json.dumps([
        {"title": "k_EQ0001", "latex": "a=b", "page": "003",
         "equation_number": "(1)"},
        {"title": "k_FO0001", "latex": "x_{5}"},
        {"title": "k_PARA_1", "text": "no latex"},
    ]))
    entries, unparsed = entries_from_tiddlers(tid, "k")
    assert len(entries) == 2 and unparsed == 0
    assert entries[0]["evidence"]["equation_number"] == "(1)"
    store = tmp_path / "crossref.json"
    n1 = add_entries(store, entries, "k", kind="formula")
    n2 = add_entries(store, entries, "k", kind="formula")   # re-index
    assert n1 == n2 == 2                                    # never duplicates
    assert len(load_store(store)) == 2


def test_map_books_buckets_exact_near_unmatched():
    def e(bk, i, latex):
        return {"bibkey": bk, "kind": "formula", "id": f"{bk}_{i}",
                "signature": formula_signature(latex),
                "evidence": {"latex": latex}}
    entries = [e("A", 1, r"x_{5}+\alpha"), e("A", 2, r"a+b+c+d+e"),
               e("A", 3, r"\zeta_{99}"),
               e("REG", 1, r"x_5+\alpha"),      # exact (canonicalized)
               e("REG", 2, r"a+b+c+d")]         # near
    r = map_books(entries, "A", "REG", threshold=0.5)
    assert r["total"] == 3
    assert len(r["exact"]) == 1 and r["exact"][0][1]["id"] == "REG_1"
    assert len(r["near"]) == 1 and r["near"][0][1]["id"] == "REG_2"
    assert r["unmatched"] == 1


def test_slt_edit_distance_semantics():
    """P11: distance 1-2 reads as divergent OCR, large as a different formula;
    a layout flip (sub vs sup) costs on the relation side."""
    from pdfdrill.crossref import slt_edit_distance
    a = formula_signature(r"\tau > 0")
    assert slt_edit_distance(a, formula_signature(r"\tau > 1")) == 1
    assert slt_edit_distance(a, a) == 0
    assert slt_edit_distance(
        formula_signature(r"x_2"), formula_signature(r"x^2")) == 1
    assert slt_edit_distance(
        a, formula_signature(r"\int_0^1 f(x)\,dx")) > 5


def test_slt_tokens_survive_unresolved_none_ids():
    """A register signature carried an Unresolved 'none' node id — the token
    extractor must not crash on it (live failure, 2026-08-18)."""
    from pdfdrill.crossref import slt_tokens
    labels, rels = slt_tokens(
        "N, n0, x, 1.0\nN, none, ?, 1.0\nE, none, n0, Right, 1.0")
    assert "x" in labels and rels == ["Right"]


def test_nearest_by_distance_prunes_to_the_true_minimum():
    from pdfdrill.crossref import nearest_by_distance
    cands = [{"id": c, "signature": formula_signature(l)}
             for c, l in (("far", r"\int_a^b g(t)dt"),
                          ("close", r"\tau > 1"),
                          ("exact", r"\tau > 0"))]
    d, best = nearest_by_distance(cands, formula_signature(r"\tau > 0"))
    assert d == 0 and best["id"] == "exact"
